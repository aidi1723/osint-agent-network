from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import os
import sqlite3
from threading import Lock
from uuid import uuid4

from app.core.ach_engine import EvidenceItem, Hypothesis, run_ach_analysis
from app.core.cross_verification import build_cross_verification_matrix
from app.core.evidence_ledger import build_evidence_record
from app.core.fact_pool import FactRecord, default_promotion_stage_for_status, validate_fact_record
from app.core.graph import build_investigation_graph
from app.core.intelligence_memory import build_intelligence_memory
from app.core.intelligence_requirements import apply_requirement_updates, build_intelligence_requirements
from app.core.planner import StrategyProfile, plan_initial_job_set, plan_initial_jobs
from app.core.quality import build_quality_assessment, completion_status_for_detail, render_structured_report
from app.core.registry import default_tool_registry


@dataclass
class Investigation:
    id: str
    name: str
    seed_type: str
    seed_value: str
    strategy: str
    status: str
    created_at: str
    max_depth: int
    max_jobs: int
    max_entities: int
    claimed_by_agent_id: str | None = None
    claimed_by_agent_name: str | None = None
    updated_at: str | None = None
    summary: str = ""
    report_markdown: str = ""
    confidence: float | None = None
    risk_report: dict | None = None
    metadata: dict | None = None


@dataclass
class Job:
    id: str
    investigation_id: str
    tool_name: str
    target_type: str
    target_value: str
    depth: int
    status: str = "QUEUED"
    agent_role: str = "tool_agent"
    output_contract: str = "entities,evidence,relationships"
    depends_on: str = ""
    claimed_by_agent_id: str | None = None
    claimed_by_agent_name: str | None = None
    claimed_at: str | None = None
    heartbeat_at: str | None = None
    attempt_count: int = 0
    last_error: str = ""


@dataclass
class Agent:
    id: str
    agent_name: str
    agent_type: str
    capabilities: list[str]
    status: str
    registered_at: str
    last_seen_at: str


@dataclass
class AgentEvent:
    id: str
    investigation_id: str
    agent_id: str
    level: str
    message: str
    metadata: dict
    created_at: str


@dataclass
class Entity:
    id: str
    investigation_id: str
    type: str
    value: str
    source_tool: str
    confidence: float
    created_at: str


@dataclass
class Evidence:
    id: str
    investigation_id: str
    entity_value: str
    evidence_kind: str
    source_tool: str
    snippet: str
    created_at: str


@dataclass
class Relationship:
    id: str
    investigation_id: str
    from_value: str
    to_value: str
    relationship_type: str
    confidence: float
    created_at: str


@dataclass
class MemoryStore:
    investigations: dict[str, Investigation] = field(default_factory=dict)
    jobs: dict[str, Job] = field(default_factory=dict)
    agents: dict[str, Agent] = field(default_factory=dict)
    events: dict[str, AgentEvent] = field(default_factory=dict)
    entities: dict[str, Entity] = field(default_factory=dict)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    evidence_ledger: dict[str, dict] = field(default_factory=dict)
    facts: dict[str, FactRecord] = field(default_factory=dict)
    hypotheses: dict[str, dict] = field(default_factory=dict)
    hypothesis_analysis: dict[str, dict] = field(default_factory=dict)
    relationships: dict[str, Relationship] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def create_investigation(
        self,
        name: str,
        seed_type: str,
        seed_value: str,
        strategy_name: str,
        metadata: dict | None = None,
        respect_tool_health: bool = False,
    ) -> Investigation:
        strategy = _strategy_from_name(strategy_name)
        registry = default_tool_registry()
        initial_plan = plan_initial_job_set(seed_type, seed_value, strategy, registry, respect_tool_health=respect_tool_health)
        planned_jobs = initial_plan.jobs
        skipped_routes = initial_plan.skipped_routes
        metadata = metadata or {}
        if respect_tool_health:
            metadata = {**metadata, "respect_tool_health": True}
        if skipped_routes:
            metadata = {**metadata, "initial_skipped_routes": [asdict(route) for route in skipped_routes]}
        planning_blocked = bool(skipped_routes and not planned_jobs)
        now = datetime.now(UTC).isoformat()
        investigation = Investigation(
            id=str(uuid4()),
            name=name,
            seed_type=seed_type,
            seed_value=seed_value,
            strategy=strategy.name,
            status="BLOCKED" if planning_blocked else "OPEN",
            created_at=now,
            updated_at=now,
            max_depth=strategy.max_depth,
            max_jobs=strategy.max_jobs,
            max_entities=strategy.max_entities,
            summary="工具任务被环境依赖阻断" if planning_blocked else "",
            metadata=metadata,
        )

        with self.lock:
            self.investigations[investigation.id] = investigation
            for planned in planned_jobs:
                job = Job(
                    id=str(uuid4()),
                    investigation_id=investigation.id,
                    tool_name=planned.tool_name,
                    target_type=planned.target_type,
                    target_value=planned.target_value,
                    depth=planned.depth,
                    agent_role=planned.agent_role,
                    output_contract=planned.output_contract,
                    depends_on=planned.depends_on,
                )
                self.jobs[job.id] = job
            if skipped_routes:
                event = AgentEvent(
                    id=str(uuid4()),
                    investigation_id=investigation.id,
                    agent_id="planner",
                    level="warning",
                    message="规划阶段跳过不可用工具",
                    metadata={"skipped_routes": [asdict(route) for route in skipped_routes]},
                    created_at=now,
                )
                self.events[event.id] = event

        return investigation

    def register_agent(
        self,
        agent_name: str,
        agent_type: str,
        capabilities: list[str],
    ) -> Agent:
        now = _now()
        agent = Agent(
            id=str(uuid4()),
            agent_name=agent_name,
            agent_type=agent_type,
            capabilities=capabilities,
            status="ONLINE",
            registered_at=now,
            last_seen_at=now,
        )
        with self.lock:
            self.agents[agent.id] = agent
        return agent

    def heartbeat_agent(self, agent_id: str) -> dict | None:
        with self.lock:
            agent = self.agents.get(agent_id)
            if agent is None:
                return None
            agent.last_seen_at = _now()
            agent.status = "ONLINE"
            return asdict(agent)

    def list_agents(self) -> list[dict]:
        with self.lock:
            return [asdict(agent) for agent in self.agents.values()]

    def claim_task(self, agent_id: str, capabilities: list[str]) -> dict | None:
        with self.lock:
            agent = self.agents.get(agent_id)
            if agent is None:
                return None
            capability_set = set(capabilities) | set(agent.capabilities)
            for investigation in self.investigations.values():
                if investigation.status != "OPEN":
                    continue
                if investigation.seed_type not in capability_set:
                    continue
                now = _now()
                investigation.status = "CLAIMED"
                investigation.claimed_by_agent_id = agent.id
                investigation.claimed_by_agent_name = agent.agent_name
                investigation.updated_at = now
                agent.last_seen_at = now
                return self._investigation_detail(investigation.id)
            return None

    def claim_job(self, agent_id: str, capabilities: list[str]) -> dict | None:
        with self.lock:
            agent = self.agents.get(agent_id)
            if agent is None:
                return None
            capability_set = set(capabilities) | set(agent.capabilities)
            for job in self.jobs.values():
                if job.status not in {"WAITING_AGENT", "QUEUED"}:
                    continue
                if job.agent_role == "tool_agent":
                    continue
                if job.agent_role not in capability_set and job.tool_name not in capability_set:
                    continue
                now = _now()
                job.status = "CLAIMED"
                job.claimed_by_agent_id = agent.id
                job.claimed_by_agent_name = agent.agent_name
                job.claimed_at = now
                job.heartbeat_at = now
                agent.last_seen_at = now
                self._touch_investigation(job.investigation_id, status="RUNNING")
                return asdict(job)
            return None

    def add_event(
        self,
        investigation_id: str,
        agent_id: str,
        level: str,
        message: str,
        metadata: dict | None = None,
    ) -> dict:
        event = AgentEvent(
            id=str(uuid4()),
            investigation_id=investigation_id,
            agent_id=agent_id,
            level=level,
            message=message,
            metadata=metadata or {},
            created_at=_now(),
        )
        with self.lock:
            self.events[event.id] = event
            self._touch_investigation(investigation_id, status="RUNNING")
        return asdict(event)

    def add_entity(
        self,
        investigation_id: str,
        entity_type: str,
        value: str,
        source_tool: str,
        confidence: float,
    ) -> dict:
        entity = Entity(
            id=str(uuid4()),
            investigation_id=investigation_id,
            type=entity_type,
            value=value,
            source_tool=source_tool,
            confidence=confidence,
            created_at=_now(),
        )
        with self.lock:
            self.entities[entity.id] = entity
            self._touch_investigation(investigation_id, status="RUNNING")
        return asdict(entity)

    def add_evidence(
        self,
        investigation_id: str,
        entity_value: str,
        evidence_kind: str,
        source_tool: str,
        snippet: str,
    ) -> dict:
        evidence = Evidence(
            id=str(uuid4()),
            investigation_id=investigation_id,
            entity_value=entity_value,
            evidence_kind=evidence_kind,
            source_tool=source_tool,
            snippet=snippet,
            created_at=_now(),
        )
        with self.lock:
            self.evidence[evidence.id] = evidence
            self._touch_investigation(investigation_id, status="RUNNING")
        return asdict(evidence)

    def add_evidence_record(
        self,
        investigation_id: str,
        source_url: str,
        source_type: str,
        source_tool: str,
        snippet: str,
        credibility: float,
    ) -> dict:
        record = build_evidence_record(
            id=str(uuid4()),
            investigation_id=investigation_id,
            source_url=source_url,
            source_type=source_type,
            source_tool=source_tool,
            snippet=snippet,
            observed_at=_now(),
            credibility=credibility,
        )
        data = asdict(record)
        with self.lock:
            self.evidence_ledger[record.id] = data
            self._touch_investigation(investigation_id, status="RUNNING")
        return data

    def add_fact(
        self,
        investigation_id: str,
        statement: str,
        subject: str,
        predicate: str,
        object_value: str,
        status: str,
        confidence: float,
        admiralty_code: str,
        evidence_ids: list[str],
    ) -> dict:
        now = _now()
        fact = FactRecord(
            id=str(uuid4()),
            investigation_id=investigation_id,
            statement=statement,
            subject=subject,
            predicate=predicate,
            object=object_value,
            status=status,
            promotion_stage=default_promotion_stage_for_status(status),
            confidence=confidence,
            admiralty_code=admiralty_code,
            evidence_ids=evidence_ids,
            observed_at=now,
            valid_from=now,
        )
        validate_fact_record(fact)
        with self.lock:
            existing = next(
                (
                    item
                    for item in self.facts.values()
                    if item.investigation_id == investigation_id
                    and item.subject == subject
                    and item.predicate == predicate
                    and item.object == object_value
                ),
                None,
            )
            if existing is not None:
                merged = _merge_fact_record(existing, fact)
                self.facts[existing.id] = merged
                self._touch_investigation(investigation_id, status="RUNNING")
                return _fact_as_dict(merged)
            self.facts[fact.id] = fact
            self._touch_investigation(investigation_id, status="RUNNING")
        return _fact_as_dict(fact)

    def add_hypothesis(
        self,
        investigation_id: str,
        hypothesis_id: str,
        statement: str,
        group: str = "default",
    ) -> dict:
        now = _now()
        row = {
            "id": hypothesis_id,
            "investigation_id": investigation_id,
            "statement": statement,
            "mutually_exclusive_group": group,
            "status": "UNVERIFIED",
            "support_score": 0.0,
            "inconsistency_score": 0.0,
            "supporting_evidence": [],
            "contradictory_evidence": [],
            "created_at": now,
            "updated_at": now,
        }
        with self.lock:
            self.hypotheses[f"{investigation_id}:{hypothesis_id}"] = row
            self._touch_investigation(investigation_id, status="RUNNING")
        return dict(row)

    def score_hypotheses(self, investigation_id: str, evidence_items: list[dict]) -> dict:
        with self.lock:
            rows = [
                item
                for item in self.hypotheses.values()
                if item["investigation_id"] == investigation_id
            ]
            hypotheses = [
                Hypothesis(
                    id=row["id"],
                    statement=row["statement"],
                    mutually_exclusive_group=row["mutually_exclusive_group"],
                )
                for row in rows
            ]
            ach_evidence = [
                EvidenceItem(
                    id=str(item["id"]),
                    summary=str(item["summary"]),
                    kinds=tuple(item.get("kinds", [])),
                    supports=tuple(item.get("supports", [])),
                    contradicts=tuple(item.get("contradicts", [])),
                    source_reliability=str(item.get("source_reliability", "unknown")),
                    credibility=float(item.get("credibility", 0.0)),
                    keywords=tuple(item.get("keywords", [])),
                )
                for item in evidence_items
            ]
            result = run_ach_analysis(hypotheses, ach_evidence)
            now = _now()
            for item in result.hypotheses:
                row = self.hypotheses.get(f"{investigation_id}:{item['id']}")
                if row is None:
                    continue
                row.update(
                    {
                        "status": item["status"],
                        "support_score": item["support_score"],
                        "inconsistency_score": item["inconsistency_score"],
                        "supporting_evidence": item["supporting_evidence"],
                        "contradictory_evidence": item["contradictory_evidence"],
                        "updated_at": now,
                    }
                )
            analysis = {
                "most_likely_hypothesis": result.most_likely_hypothesis,
                "triggered_indicators": result.triggered_indicators,
                "indicator_activation_rate": result.indicator_activation_rate,
                "confidence_language": result.confidence_language,
                "updated_at": now,
            }
            self.hypothesis_analysis[investigation_id] = analysis
            self._touch_investigation(investigation_id, status="RUNNING")
        return _ach_result_as_dict(result)

    def add_relationship(
        self,
        investigation_id: str,
        from_value: str,
        to_value: str,
        relationship_type: str,
        confidence: float,
    ) -> dict:
        relationship = Relationship(
            id=str(uuid4()),
            investigation_id=investigation_id,
            from_value=from_value,
            to_value=to_value,
            relationship_type=relationship_type,
            confidence=confidence,
            created_at=_now(),
        )
        with self.lock:
            self.relationships[relationship.id] = relationship
            self._touch_investigation(investigation_id, status="RUNNING")
        return asdict(relationship)

    def complete_task(
        self,
        investigation_id: str,
        agent_id: str,
        status: str,
        summary: str,
        report_markdown: str,
        confidence: float | None,
    ) -> dict | None:
        with self.lock:
            investigation = self.investigations.get(investigation_id)
            if investigation is None:
                return None
            preview = self._investigation_detail(investigation_id)
            preview["summary"] = summary
            preview["report_markdown"] = report_markdown
            assessment = build_quality_assessment(preview)
            investigation.status = completion_status_for_detail(preview, status)
            investigation.summary = summary
            investigation.report_markdown = render_structured_report(preview, assessment)
            investigation.confidence = confidence
            investigation.updated_at = _now()
            if agent_id in self.agents:
                self.agents[agent_id].last_seen_at = investigation.updated_at
            return self._investigation_detail(investigation_id)

    def list_jobs(self, investigation_id: str) -> list[dict]:
        with self.lock:
            return [
                asdict(job)
                for job in self.jobs.values()
                if job.investigation_id == investigation_id
            ]

    def update_job_status(self, job_id: str, status: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            job.status = status
            if status == "RUNNING":
                job.attempt_count += 1
                job.heartbeat_at = _now()
            self._touch_investigation(job.investigation_id)
            return asdict(job)

    def claim_job_for_worker(self, job_id: str) -> bool:
        """Atomically claim a QUEUED job for the local worker. Returns True on success."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None or job.status != "QUEUED":
                return False
            job.status = "RUNNING"
            job.attempt_count += 1
            job.heartbeat_at = _now()
            self._touch_investigation(job.investigation_id)
            return True

    def mark_job_waiting_agent(self, job_id: str, message: str = "") -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            if job.status == "QUEUED":
                job.status = "WAITING_AGENT"
            if message:
                job.last_error = message
            self._touch_investigation(job.investigation_id)
            return asdict(job)

    def add_jobs(self, investigation_id: str, planned_jobs) -> list[dict]:
        created = []
        with self.lock:
            for planned in planned_jobs:
                job = Job(
                    id=str(uuid4()),
                    investigation_id=investigation_id,
                    tool_name=planned.tool_name,
                    target_type=planned.target_type,
                    target_value=planned.target_value,
                    depth=planned.depth,
                    agent_role=getattr(planned, "agent_role", "tool_agent"),
                    output_contract=getattr(planned, "output_contract", "entities,evidence,relationships"),
                    depends_on=getattr(planned, "depends_on", ""),
                )
                self.jobs[job.id] = job
                created.append(asdict(job))
            self._touch_investigation(investigation_id)
        return created

    def replace_jobs(self, investigation_id: str, jobs: list[dict]) -> None:
        with self.lock:
            self.jobs = {
                key: item
                for key, item in self.jobs.items()
                if item.investigation_id != investigation_id
            }
            for item in jobs:
                job = Job(
                    id=item["id"],
                    investigation_id=investigation_id,
                    tool_name=item["tool_name"],
                    target_type=item["target_type"],
                    target_value=item["target_value"],
                    depth=item["depth"],
                    status=item.get("status", "QUEUED"),
                    agent_role=item.get("agent_role", "tool_agent"),
                    output_contract=item.get("output_contract", "entities,evidence,relationships"),
                    depends_on=item.get("depends_on", ""),
                )
                self.jobs[job.id] = job
            self._touch_investigation(investigation_id)

    def save_risk_report(self, investigation_id: str, risk_report: dict) -> dict | None:
        with self.lock:
            investigation = self.investigations.get(investigation_id)
            if investigation is None:
                return None
            investigation.risk_report = risk_report
            investigation.updated_at = _now()
            return self._investigation_detail(investigation_id)

    def set_investigation_status(
        self,
        investigation_id: str,
        status: str,
        summary: str | None = None,
        confidence: float | None = None,
    ) -> dict | None:
        with self.lock:
            investigation = self.investigations.get(investigation_id)
            if investigation is None:
                return None
            investigation.status = status
            if summary is not None:
                investigation.summary = summary
            if confidence is not None:
                investigation.confidence = confidence
            investigation.updated_at = _now()
            return self._investigation_detail(investigation_id)

    def cancel_task(self, investigation_id: str) -> dict | None:
        return self._set_lifecycle_status(investigation_id, "CANCELLED", clear_claim=False)

    def reopen_task(self, investigation_id: str) -> dict | None:
        return self._set_lifecycle_status(investigation_id, "OPEN", clear_claim=True)

    def retry_task(self, investigation_id: str) -> dict | None:
        with self.lock:
            investigation = self.investigations.get(investigation_id)
            if investigation is None:
                return None
            investigation.status = "OPEN"
            investigation.claimed_by_agent_id = None
            investigation.claimed_by_agent_name = None
            investigation.summary = ""
            investigation.report_markdown = ""
            investigation.confidence = None
            investigation.updated_at = _now()
            for job in self.jobs.values():
                if job.investigation_id == investigation_id:
                    job.status = "QUEUED"
            return self._investigation_detail(investigation_id)

    def archive_task(self, investigation_id: str) -> dict | None:
        return self._set_lifecycle_status(investigation_id, "ARCHIVED", clear_claim=True)

    def delete_task(self, investigation_id: str) -> bool:
        with self.lock:
            if investigation_id not in self.investigations:
                return False
            del self.investigations[investigation_id]
            self.jobs = {
                key: item for key, item in self.jobs.items() if item.investigation_id != investigation_id
            }
            self.events = {
                key: item for key, item in self.events.items() if item.investigation_id != investigation_id
            }
            self.entities = {
                key: item for key, item in self.entities.items() if item.investigation_id != investigation_id
            }
            self.evidence = {
                key: item for key, item in self.evidence.items() if item.investigation_id != investigation_id
            }
            self.evidence_ledger = {
                key: item
                for key, item in self.evidence_ledger.items()
                if item["investigation_id"] != investigation_id
            }
            self.facts = {
                key: item for key, item in self.facts.items() if item.investigation_id != investigation_id
            }
            self.hypotheses = {
                key: item
                for key, item in self.hypotheses.items()
                if item["investigation_id"] != investigation_id
            }
            self.hypothesis_analysis.pop(investigation_id, None)
            self.relationships = {
                key: item
                for key, item in self.relationships.items()
                if item.investigation_id != investigation_id
            }
            return True

    def release_stale_claims(self, now_iso: str | None = None, stale_after_seconds: int = 1800) -> int:
        now = _parse_iso(now_iso or _now())
        released = 0
        with self.lock:
            for investigation in self.investigations.values():
                if investigation.status not in {"CLAIMED", "RUNNING"}:
                    continue
                updated_at = _parse_iso(investigation.updated_at or investigation.created_at)
                if (now - updated_at).total_seconds() < stale_after_seconds:
                    continue
                investigation.status = "OPEN"
                investigation.claimed_by_agent_id = None
                investigation.claimed_by_agent_name = None
                investigation.updated_at = now.isoformat()
                released += 1
        return released

    def set_investigation_updated_at(self, investigation_id: str, updated_at: str) -> None:
        with self.lock:
            investigation = self.investigations.get(investigation_id)
            if investigation is not None:
                investigation.updated_at = updated_at

    def list_investigations(self, include_archived: bool = False) -> list[dict]:
        with self.lock:
            return [
                asdict(item)
                for item in self.investigations.values()
                if include_archived or item.status != "ARCHIVED"
            ]

    def get_investigation(self, investigation_id: str) -> dict | None:
        raw = self.get_investigation_raw(investigation_id)
        if raw is None:
            return None
        _apply_core_v3(raw)
        raw["intelligence_memory"] = build_intelligence_memory(raw)
        raw["quality_assessment"] = build_quality_assessment(raw)
        raw["graph"] = build_investigation_graph(raw)
        return raw

    def get_investigation_raw(self, investigation_id: str) -> dict | None:
        """Return investigation data without expensive derived computations."""
        with self.lock:
            return self._investigation_detail_raw(investigation_id)

    def _touch_investigation(self, investigation_id: str, status: str | None = None) -> None:
        investigation = self.investigations.get(investigation_id)
        if investigation is None:
            return
        if status and investigation.status in {"OPEN", "CLAIMED", "RUNNING"}:
            investigation.status = status
        investigation.updated_at = _now()

    def _set_lifecycle_status(
        self,
        investigation_id: str,
        status: str,
        clear_claim: bool,
    ) -> dict | None:
        with self.lock:
            investigation = self.investigations.get(investigation_id)
            if investigation is None:
                return None
            investigation.status = status
            if clear_claim:
                investigation.claimed_by_agent_id = None
                investigation.claimed_by_agent_name = None
            investigation.updated_at = _now()
            return self._investigation_detail(investigation_id)

    def _investigation_detail(self, investigation_id: str) -> dict | None:
        data = self._investigation_detail_raw(investigation_id)
        if data is None:
            return None
        _apply_core_v3(data)
        data["intelligence_memory"] = build_intelligence_memory(data)
        data["quality_assessment"] = build_quality_assessment(data)
        data["graph"] = build_investigation_graph(data)
        return data

    def _investigation_detail_raw(self, investigation_id: str) -> dict | None:
        investigation = self.investigations.get(investigation_id)
        if investigation is None:
            return None
        data = asdict(investigation)
        data["jobs"] = [
            asdict(job)
            for job in self.jobs.values()
            if job.investigation_id == investigation_id
        ]
        data["events"] = [
            asdict(event)
            for event in self.events.values()
            if event.investigation_id == investigation_id
        ]
        data["entities"] = [
            asdict(entity)
            for entity in self.entities.values()
            if entity.investigation_id == investigation_id
        ]
        data["evidence"] = [
            asdict(item)
            for item in self.evidence.values()
            if item.investigation_id == investigation_id
        ]
        data["evidence_ledger"] = [
            dict(item)
            for item in self.evidence_ledger.values()
            if item["investigation_id"] == investigation_id
        ]
        data["facts"] = [
            _fact_as_dict(item)
            for item in self.facts.values()
            if item.investigation_id == investigation_id
        ]
        data["hypotheses"] = [
            dict(item)
            for item in self.hypotheses.values()
            if item["investigation_id"] == investigation_id
        ]
        data["hypothesis_analysis"] = self.hypothesis_analysis.get(
            investigation_id,
            {
                "most_likely_hypothesis": "",
                "triggered_indicators": [],
                "indicator_activation_rate": 0.0,
                "confidence_language": "",
            },
        )
        data["relationships"] = [
            asdict(item)
            for item in self.relationships.values()
            if item.investigation_id == investigation_id
        ]
        data["jobs"] = _with_orchestration_jobs(data)
        data["job_counts"] = _job_counts(data["jobs"])
        data["risk_report"] = investigation.risk_report or {}
        return data


class SQLiteStore:
    def __init__(self, db_path: str = "data/osint.sqlite"):
        self.db_path = db_path
        self.lock = Lock()
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_schema()

    def schema_versions(self) -> list[dict]:
        with self.lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT version, applied_at FROM schema_migrations ORDER BY applied_at ASC, version ASC"
            ).fetchall()
        return [{"version": row["version"], "applied_at": row["applied_at"]} for row in rows]

    def system_counts(self) -> dict:
        with self.lock, closing(self._connect()) as conn:
            investigations = {
                row["status"]: row["count"]
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS count FROM investigations GROUP BY status"
                ).fetchall()
            }
            jobs = {
                row["status"]: row["count"]
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
                ).fetchall()
            }
            totals = {
                "investigations": conn.execute("SELECT COUNT(*) AS count FROM investigations").fetchone()["count"],
                "jobs": conn.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()["count"],
                "entities": conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()["count"],
                "evidence": conn.execute("SELECT COUNT(*) AS count FROM evidence").fetchone()["count"],
                "evidence_ledger": conn.execute("SELECT COUNT(*) AS count FROM evidence_ledger").fetchone()["count"],
                "facts": conn.execute("SELECT COUNT(*) AS count FROM facts").fetchone()["count"],
            }
        return {"totals": totals, "investigations_by_status": investigations, "jobs_by_status": jobs}

    def create_investigation(
        self,
        name: str,
        seed_type: str,
        seed_value: str,
        strategy_name: str,
        metadata: dict | None = None,
        respect_tool_health: bool = False,
    ) -> Investigation:
        strategy = _strategy_from_name(strategy_name)
        registry = default_tool_registry()
        initial_plan = plan_initial_job_set(seed_type, seed_value, strategy, registry, respect_tool_health=respect_tool_health)
        planned_jobs = initial_plan.jobs
        skipped_routes = initial_plan.skipped_routes
        now = _now()
        metadata = metadata or {}
        if respect_tool_health:
            metadata = {**metadata, "respect_tool_health": True}
        if skipped_routes:
            metadata = {**metadata, "initial_skipped_routes": [asdict(route) for route in skipped_routes]}
        planning_blocked = bool(skipped_routes and not planned_jobs)
        requirements = build_intelligence_requirements(seed_type, seed_value, strategy.name, metadata)
        metadata = {**metadata, "intelligence_requirements": requirements}
        investigation = Investigation(
            id=str(uuid4()),
            name=name,
            seed_type=seed_type,
            seed_value=seed_value,
            strategy=strategy.name,
            status="BLOCKED" if planning_blocked else "OPEN",
            created_at=now,
            updated_at=now,
            max_depth=strategy.max_depth,
            max_jobs=strategy.max_jobs,
            max_entities=strategy.max_entities,
            summary="工具任务被环境依赖阻断" if planning_blocked else "",
            metadata=metadata,
        )

        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO investigations (
                    id, name, seed_type, seed_value, strategy, status, created_at,
                    max_depth, max_jobs, max_entities, claimed_by_agent_id,
                    claimed_by_agent_name, updated_at, summary, report_markdown, confidence,
                    risk_report_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _investigation_row(investigation),
            )
            conn.executemany(
                """
                INSERT INTO jobs (
                    id, investigation_id, tool_name, target_type, target_value, depth, status,
                    agent_role, output_contract, depends_on, claimed_by_agent_id,
                    claimed_by_agent_name, claimed_at, heartbeat_at, attempt_count, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(uuid4()),
                        investigation.id,
                        planned.tool_name,
                        planned.target_type,
                        planned.target_value,
                        planned.depth,
                        "QUEUED",
                        planned.agent_role,
                        planned.output_contract,
                        planned.depends_on,
                        None,
                        None,
                        None,
                        None,
                        0,
                        "",
                    )
                    for planned in planned_jobs
                ],
            )
            if skipped_routes:
                conn.execute(
                    """
                    INSERT INTO events (
                        id, investigation_id, agent_id, level, message, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        investigation.id,
                        "planner",
                        "warning",
                        "规划阶段跳过不可用工具",
                        json.dumps({"skipped_routes": [asdict(route) for route in skipped_routes]}, ensure_ascii=False),
                        now,
                    ),
                )
        return investigation

    def register_agent(
        self,
        agent_name: str,
        agent_type: str,
        capabilities: list[str],
    ) -> Agent:
        now = _now()
        agent = Agent(
            id=str(uuid4()),
            agent_name=agent_name,
            agent_type=agent_type,
            capabilities=capabilities,
            status="ONLINE",
            registered_at=now,
            last_seen_at=now,
        )
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO agents (
                    id, agent_name, agent_type, capabilities_json, status, registered_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent.id,
                    agent.agent_name,
                    agent.agent_type,
                    json.dumps(agent.capabilities, ensure_ascii=False),
                    agent.status,
                    agent.registered_at,
                    agent.last_seen_at,
                ),
            )
        return agent

    def heartbeat_agent(self, agent_id: str) -> dict | None:
        now = _now()
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE agents SET last_seen_at = ?, status = ? WHERE id = ?",
                (now, "ONLINE", agent_id),
            )
            updated = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return _agent_from_row(updated)

    def list_agents(self) -> list[dict]:
        with self.lock, closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM agents ORDER BY registered_at ASC").fetchall()
        return [_agent_from_row(row) for row in rows]

    def claim_task(self, agent_id: str, capabilities: list[str]) -> dict | None:
        with self.lock, closing(self._connect()) as conn, conn:
            agent_row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if agent_row is None:
                return None
            agent = _agent_from_row(agent_row)
            capability_set = set(capabilities) | set(agent["capabilities"])
            rows = conn.execute(
                "SELECT * FROM investigations WHERE status = ? ORDER BY created_at ASC",
                ("OPEN",),
            ).fetchall()
            target = None
            for row in rows:
                if row["seed_type"] in capability_set:
                    target = row
                    break
            if target is None:
                return None
            now = _now()
            conn.execute(
                """
                UPDATE investigations
                SET status = ?, claimed_by_agent_id = ?, claimed_by_agent_name = ?, updated_at = ?
                WHERE id = ?
                """,
                ("CLAIMED", agent_id, agent["agent_name"], now, target["id"]),
            )
            conn.execute(
                "UPDATE agents SET last_seen_at = ? WHERE id = ?",
                (now, agent_id),
            )
        return self.get_investigation(target["id"])

    def claim_job(self, agent_id: str, capabilities: list[str]) -> dict | None:
        with self.lock, closing(self._connect()) as conn, conn:
            agent_row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if agent_row is None:
                return None
            agent = _agent_from_row(agent_row)
            capability_set = set(capabilities) | set(agent["capabilities"])
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status IN (?, ?) AND agent_role != ?
                ORDER BY rowid ASC
                """,
                ("WAITING_AGENT", "QUEUED", "tool_agent"),
            ).fetchall()
            target = None
            for row in rows:
                if row["agent_role"] in capability_set or row["tool_name"] in capability_set:
                    target = row
                    break
            if target is None:
                return None
            now = _now()
            conn.execute(
                """
                UPDATE jobs
                SET status = ?, claimed_by_agent_id = ?, claimed_by_agent_name = ?,
                    claimed_at = ?, heartbeat_at = ?
                WHERE id = ?
                """,
                ("CLAIMED", agent_id, agent["agent_name"], now, now, target["id"]),
            )
            conn.execute("UPDATE agents SET last_seen_at = ? WHERE id = ?", (now, agent_id))
            self._touch_investigation(conn, target["investigation_id"], status="RUNNING")
            updated = conn.execute("SELECT * FROM jobs WHERE id = ?", (target["id"],)).fetchone()
        return _job_from_row(updated)

    def add_event(
        self,
        investigation_id: str,
        agent_id: str,
        level: str,
        message: str,
        metadata: dict | None = None,
    ) -> dict:
        event = AgentEvent(
            id=str(uuid4()),
            investigation_id=investigation_id,
            agent_id=agent_id,
            level=level,
            message=message,
            metadata=metadata or {},
            created_at=_now(),
        )
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO events (
                    id, investigation_id, agent_id, level, message, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.investigation_id,
                    event.agent_id,
                    event.level,
                    event.message,
                    json.dumps(event.metadata, ensure_ascii=False),
                    event.created_at,
                ),
            )
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return asdict(event)

    def add_entity(
        self,
        investigation_id: str,
        entity_type: str,
        value: str,
        source_tool: str,
        confidence: float,
    ) -> dict:
        entity = Entity(
            id=str(uuid4()),
            investigation_id=investigation_id,
            type=entity_type,
            value=value,
            source_tool=source_tool,
            confidence=confidence,
            created_at=_now(),
        )
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO entities (
                    id, investigation_id, type, value, source_tool, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id, type, value, source_tool) DO UPDATE SET
                    confidence = MAX(confidence, excluded.confidence),
                    created_at = excluded.created_at
                """,
                (
                    entity.id,
                    entity.investigation_id,
                    entity.type,
                    entity.value,
                    entity.source_tool,
                    entity.confidence,
                    entity.created_at,
                ),
            )
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return asdict(entity)

    def add_evidence(
        self,
        investigation_id: str,
        entity_value: str,
        evidence_kind: str,
        source_tool: str,
        snippet: str,
    ) -> dict:
        evidence = Evidence(
            id=str(uuid4()),
            investigation_id=investigation_id,
            entity_value=entity_value,
            evidence_kind=evidence_kind,
            source_tool=source_tool,
            snippet=snippet,
            created_at=_now(),
        )
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO evidence (
                    id, investigation_id, entity_value, evidence_kind, source_tool, snippet, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id, entity_value, evidence_kind, source_tool) DO UPDATE SET
                    snippet = excluded.snippet,
                    created_at = excluded.created_at
                """,
                (
                    evidence.id,
                    evidence.investigation_id,
                    evidence.entity_value,
                    evidence.evidence_kind,
                    evidence.source_tool,
                    evidence.snippet,
                    evidence.created_at,
                ),
            )
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return asdict(evidence)

    def add_evidence_record(
        self,
        investigation_id: str,
        source_url: str,
        source_type: str,
        source_tool: str,
        snippet: str,
        credibility: float,
    ) -> dict:
        record = build_evidence_record(
            id=str(uuid4()),
            investigation_id=investigation_id,
            source_url=source_url,
            source_type=source_type,
            source_tool=source_tool,
            snippet=snippet,
            observed_at=_now(),
            credibility=credibility,
        )
        data = asdict(record)
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO evidence_ledger (
                    id, investigation_id, source_url, source_type, source_tool, snippet,
                    observed_at, admiralty_code, source_reliability,
                    information_credibility, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id, content_hash) DO UPDATE SET
                    source_url = excluded.source_url,
                    source_type = excluded.source_type,
                    source_tool = excluded.source_tool,
                    snippet = excluded.snippet,
                    observed_at = excluded.observed_at,
                    admiralty_code = excluded.admiralty_code,
                    source_reliability = excluded.source_reliability,
                    information_credibility = excluded.information_credibility
                """,
                (
                    record.id,
                    record.investigation_id,
                    record.source_url,
                    record.source_type,
                    record.source_tool,
                    record.snippet,
                    record.observed_at,
                    record.admiralty_code,
                    record.source_reliability,
                    record.information_credibility,
                    record.content_hash,
                ),
            )
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return data

    def add_fact(
        self,
        investigation_id: str,
        statement: str,
        subject: str,
        predicate: str,
        object_value: str,
        status: str,
        confidence: float,
        admiralty_code: str,
        evidence_ids: list[str],
    ) -> dict:
        now = _now()
        fact = FactRecord(
            id=str(uuid4()),
            investigation_id=investigation_id,
            statement=statement,
            subject=subject,
            predicate=predicate,
            object=object_value,
            status=status,
            promotion_stage=default_promotion_stage_for_status(status),
            confidence=confidence,
            admiralty_code=admiralty_code,
            evidence_ids=evidence_ids,
            observed_at=now,
            valid_from=now,
        )
        validate_fact_record(fact)
        with self.lock, closing(self._connect()) as conn, conn:
            existing = conn.execute(
                """
                SELECT * FROM facts
                WHERE investigation_id = ? AND subject = ? AND predicate = ? AND object_value = ?
                """,
                (investigation_id, subject, predicate, object_value),
            ).fetchone()
            if existing is not None:
                merged = _merge_fact_dict(_fact_from_row(existing), _fact_as_dict(fact))
                conn.execute(
                    """
                    UPDATE facts
                    SET statement = ?, status = ?, promotion_stage = ?, confidence = ?,
                        admiralty_code = ?, evidence_ids_json = ?, observed_at = ?
                    WHERE id = ?
                    """,
                    (
                        merged["statement"],
                        merged["status"],
                        merged["promotion_stage"],
                        merged["confidence"],
                        merged["admiralty_code"],
                        json.dumps(merged["evidence_ids"], ensure_ascii=False),
                        merged["observed_at"],
                        merged["id"],
                    ),
                )
                self._touch_investigation(conn, investigation_id, status="RUNNING")
                return merged
            conn.execute(
                """
                INSERT INTO facts (
                    id, investigation_id, statement, subject, predicate, object_value,
                    status, promotion_stage, confidence, admiralty_code, evidence_ids_json,
                    observed_at, valid_from, valid_to, supersedes_fact_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact.id,
                    fact.investigation_id,
                    fact.statement,
                    fact.subject,
                    fact.predicate,
                    fact.object,
                    fact.status,
                    fact.promotion_stage,
                    fact.confidence,
                    fact.admiralty_code,
                    json.dumps(fact.evidence_ids, ensure_ascii=False),
                    fact.observed_at,
                    fact.valid_from,
                    fact.valid_to,
                    fact.supersedes_fact_id,
                ),
            )
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return _fact_as_dict(fact)

    def add_hypothesis(
        self,
        investigation_id: str,
        hypothesis_id: str,
        statement: str,
        group: str = "default",
    ) -> dict:
        now = _now()
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO hypotheses (
                    id, investigation_id, statement, mutually_exclusive_group, status,
                    support_score, inconsistency_score, supporting_evidence_json,
                    contradictory_evidence_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis_id,
                    investigation_id,
                    statement,
                    group,
                    "UNVERIFIED",
                    0.0,
                    0.0,
                    "[]",
                    "[]",
                    now,
                    now,
                ),
            )
            self._touch_investigation(conn, investigation_id, status="RUNNING")
            row = conn.execute(
                "SELECT * FROM hypotheses WHERE investigation_id = ? AND id = ?",
                (investigation_id, hypothesis_id),
            ).fetchone()
        return _hypothesis_from_row(row)

    def score_hypotheses(self, investigation_id: str, evidence_items: list[dict]) -> dict:
        with self.lock, closing(self._connect()) as conn, conn:
            rows = conn.execute(
                "SELECT * FROM hypotheses WHERE investigation_id = ? ORDER BY rowid ASC",
                (investigation_id,),
            ).fetchall()
            hypotheses = [
                Hypothesis(
                    id=row["id"],
                    statement=row["statement"],
                    mutually_exclusive_group=row["mutually_exclusive_group"],
                )
                for row in rows
            ]
            ach_evidence = [
                EvidenceItem(
                    id=str(item["id"]),
                    summary=str(item["summary"]),
                    kinds=tuple(item.get("kinds", [])),
                    supports=tuple(item.get("supports", [])),
                    contradicts=tuple(item.get("contradicts", [])),
                    source_reliability=str(item.get("source_reliability", "unknown")),
                    credibility=float(item.get("credibility", 0.0)),
                    keywords=tuple(item.get("keywords", [])),
                )
                for item in evidence_items
            ]
            result = run_ach_analysis(hypotheses, ach_evidence)
            now = _now()
            for item in result.hypotheses:
                conn.execute(
                    """
                    UPDATE hypotheses
                    SET status = ?, support_score = ?, inconsistency_score = ?,
                        supporting_evidence_json = ?, contradictory_evidence_json = ?,
                        updated_at = ?
                    WHERE investigation_id = ? AND id = ?
                    """,
                    (
                        item["status"],
                        item["support_score"],
                        item["inconsistency_score"],
                        json.dumps(item["supporting_evidence"], ensure_ascii=False),
                        json.dumps(item["contradictory_evidence"], ensure_ascii=False),
                        now,
                        investigation_id,
                        item["id"],
                    ),
                )
            conn.execute(
                """
                INSERT OR REPLACE INTO hypothesis_analysis (
                    investigation_id, most_likely_hypothesis, triggered_indicators_json,
                    indicator_activation_rate, confidence_language, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    investigation_id,
                    result.most_likely_hypothesis,
                    json.dumps(result.triggered_indicators, ensure_ascii=False),
                    result.indicator_activation_rate,
                    result.confidence_language,
                    now,
                ),
            )
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return _ach_result_as_dict(result)

    def add_relationship(
        self,
        investigation_id: str,
        from_value: str,
        to_value: str,
        relationship_type: str,
        confidence: float,
    ) -> dict:
        relationship = Relationship(
            id=str(uuid4()),
            investigation_id=investigation_id,
            from_value=from_value,
            to_value=to_value,
            relationship_type=relationship_type,
            confidence=confidence,
            created_at=_now(),
        )
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO relationships (
                    id, investigation_id, from_value, to_value, relationship_type, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id, from_value, to_value, relationship_type) DO UPDATE SET
                    confidence = MAX(confidence, excluded.confidence),
                    created_at = excluded.created_at
                """,
                (
                    relationship.id,
                    relationship.investigation_id,
                    relationship.from_value,
                    relationship.to_value,
                    relationship.relationship_type,
                    relationship.confidence,
                    relationship.created_at,
                ),
            )
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return asdict(relationship)

    def complete_task(
        self,
        investigation_id: str,
        agent_id: str,
        status: str,
        summary: str,
        report_markdown: str,
        confidence: float | None,
    ) -> dict | None:
        now = _now()
        detail = self.get_investigation(investigation_id)
        if detail is None:
            return None
        detail["summary"] = summary
        detail["report_markdown"] = report_markdown
        assessment = build_quality_assessment(detail)
        final_status = completion_status_for_detail(detail, status)
        final_report = render_structured_report(detail, assessment)
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT id FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE investigations
                SET status = ?, summary = ?, report_markdown = ?, confidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (final_status, summary, final_report, confidence, now, investigation_id),
            )
            conn.execute(
                "UPDATE agents SET last_seen_at = ? WHERE id = ?",
                (now, agent_id),
            )
        return self.get_investigation(investigation_id)

    def list_jobs(self, investigation_id: str) -> list[dict]:
        with self.lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE investigation_id = ? ORDER BY rowid ASC",
                (investigation_id,),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def update_job_status(self, job_id: str, status: str) -> dict | None:
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            if status == "RUNNING":
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = ?, heartbeat_at = ?, attempt_count = attempt_count + 1
                    WHERE id = ?
                    """,
                    (status, _now(), job_id),
                )
            else:
                conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
            self._touch_investigation(conn, row["investigation_id"])
            updated = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_from_row(updated)

    def claim_job_for_worker(self, job_id: str) -> bool:
        """Atomically claim a QUEUED job for the local worker. Returns True on success."""
        with self.lock, closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET status = 'RUNNING', heartbeat_at = ?, attempt_count = attempt_count + 1
                WHERE id = ? AND status = 'QUEUED'
                """,
                (_now(), job_id),
            )
            if cursor.rowcount == 0:
                return False
            row = conn.execute("SELECT investigation_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row:
                self._touch_investigation(conn, row["investigation_id"])
        return True

    def mark_job_waiting_agent(self, job_id: str, message: str = "") -> dict | None:
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            next_status = "WAITING_AGENT" if row["status"] == "QUEUED" else row["status"]
            conn.execute(
                "UPDATE jobs SET status = ?, last_error = ? WHERE id = ?",
                (next_status, message or row["last_error"], job_id),
            )
            self._touch_investigation(conn, row["investigation_id"])
            updated = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_from_row(updated)

    def add_jobs(self, investigation_id: str, planned_jobs) -> list[dict]:
        created = []
        with self.lock, closing(self._connect()) as conn, conn:
            for planned in planned_jobs:
                job = Job(
                    id=str(uuid4()),
                    investigation_id=investigation_id,
                    tool_name=planned.tool_name,
                    target_type=planned.target_type,
                    target_value=planned.target_value,
                    depth=planned.depth,
                    agent_role=getattr(planned, "agent_role", "tool_agent"),
                    output_contract=getattr(planned, "output_contract", "entities,evidence,relationships"),
                    depends_on=getattr(planned, "depends_on", ""),
                )
                conn.execute(
                    """
                    INSERT INTO jobs (
                        id, investigation_id, tool_name, target_type, target_value, depth, status,
                        agent_role, output_contract, depends_on, claimed_by_agent_id,
                        claimed_by_agent_name, claimed_at, heartbeat_at, attempt_count, last_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.id,
                        job.investigation_id,
                        job.tool_name,
                        job.target_type,
                        job.target_value,
                        job.depth,
                        job.status,
                        job.agent_role,
                        job.output_contract,
                        job.depends_on,
                        job.claimed_by_agent_id,
                        job.claimed_by_agent_name,
                        job.claimed_at,
                        job.heartbeat_at,
                        job.attempt_count,
                        job.last_error,
                    ),
                )
                created.append(asdict(job))
            self._touch_investigation(conn, investigation_id)
        return created

    def replace_jobs(self, investigation_id: str, jobs: list[dict]) -> None:
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM jobs WHERE investigation_id = ?", (investigation_id,))
            for item in jobs:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        id, investigation_id, tool_name, target_type, target_value, depth, status,
                        agent_role, output_contract, depends_on, claimed_by_agent_id,
                        claimed_by_agent_name, claimed_at, heartbeat_at, attempt_count, last_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["id"],
                        investigation_id,
                        item["tool_name"],
                        item["target_type"],
                        item["target_value"],
                        item["depth"],
                        item.get("status", "QUEUED"),
                        item.get("agent_role", "tool_agent"),
                        item.get("output_contract", "entities,evidence,relationships"),
                        item.get("depends_on", ""),
                        item.get("claimed_by_agent_id"),
                        item.get("claimed_by_agent_name"),
                        item.get("claimed_at"),
                        item.get("heartbeat_at"),
                        item.get("attempt_count", 0),
                        item.get("last_error", ""),
                    ),
                )
            self._touch_investigation(conn, investigation_id)

    def save_risk_report(self, investigation_id: str, risk_report: dict) -> dict | None:
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT id FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE investigations SET risk_report_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(risk_report, ensure_ascii=False), _now(), investigation_id),
            )
        return self.get_investigation(investigation_id)

    def set_investigation_status(
        self,
        investigation_id: str,
        status: str,
        summary: str | None = None,
        confidence: float | None = None,
    ) -> dict | None:
        now = _now()
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT id, summary, confidence FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE investigations
                SET status = ?, summary = ?, confidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    row["summary"] if summary is None else summary,
                    row["confidence"] if confidence is None else confidence,
                    now,
                    investigation_id,
                ),
            )
        return self.get_investigation(investigation_id)

    def cancel_task(self, investigation_id: str) -> dict | None:
        return self._set_lifecycle_status(investigation_id, "CANCELLED", clear_claim=False)

    def reopen_task(self, investigation_id: str) -> dict | None:
        return self._set_lifecycle_status(investigation_id, "OPEN", clear_claim=True)

    def retry_task(self, investigation_id: str) -> dict | None:
        now = _now()
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT id FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE investigations
                SET status = ?, claimed_by_agent_id = NULL, claimed_by_agent_name = NULL,
                    summary = '', report_markdown = '', confidence = NULL, updated_at = ?
                WHERE id = ?
                """,
                ("OPEN", now, investigation_id),
            )
            conn.execute(
                "UPDATE jobs SET status = ? WHERE investigation_id = ?",
                ("QUEUED", investigation_id),
            )
        return self.get_investigation(investigation_id)

    def archive_task(self, investigation_id: str) -> dict | None:
        return self._set_lifecycle_status(investigation_id, "ARCHIVED", clear_claim=True)

    def delete_task(self, investigation_id: str) -> bool:
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT id FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM investigations WHERE id = ?", (investigation_id,))
        return True

    def release_stale_claims(self, now_iso: str | None = None, stale_after_seconds: int = 1800) -> int:
        now = _parse_iso(now_iso or _now())
        now_value = now.isoformat()
        released_ids = []
        with self.lock, closing(self._connect()) as conn, conn:
            rows = conn.execute(
                """
                SELECT id, created_at, updated_at
                FROM investigations
                WHERE status IN (?, ?)
                """,
                ("CLAIMED", "RUNNING"),
            ).fetchall()
            for row in rows:
                updated_at = _parse_iso(row["updated_at"] or row["created_at"])
                if (now - updated_at).total_seconds() >= stale_after_seconds:
                    released_ids.append(row["id"])
            for investigation_id in released_ids:
                conn.execute(
                    """
                    UPDATE investigations
                    SET status = ?, claimed_by_agent_id = NULL, claimed_by_agent_name = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    ("OPEN", now_value, investigation_id),
                )
        return len(released_ids)

    def set_investigation_updated_at(self, investigation_id: str, updated_at: str) -> None:
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE investigations SET updated_at = ? WHERE id = ?",
                (updated_at, investigation_id),
            )

    def list_investigations(self, include_archived: bool = False) -> list[dict]:
        with self.lock, closing(self._connect()) as conn:
            if include_archived:
                rows = conn.execute(
                    "SELECT * FROM investigations ORDER BY created_at ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM investigations WHERE status != ? ORDER BY created_at ASC",
                    ("ARCHIVED",),
                ).fetchall()
        return [_investigation_from_row(row) for row in rows]

    def get_investigation(self, investigation_id: str) -> dict | None:
        data = self.get_investigation_raw(investigation_id)
        if data is None:
            return None
        _apply_core_v3(data)
        data["intelligence_memory"] = build_intelligence_memory(data)
        data["quality_assessment"] = build_quality_assessment(data)
        data["graph"] = build_investigation_graph(data)
        return data

    def get_investigation_raw(self, investigation_id: str) -> dict | None:
        """Return investigation data without expensive derived computations."""
        with self.lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
            if row is None:
                return None
            data = _investigation_from_row(row)
            data["jobs"] = [
                _job_from_row(item)
                for item in conn.execute(
                    "SELECT * FROM jobs WHERE investigation_id = ? ORDER BY rowid ASC",
                    (investigation_id,),
                ).fetchall()
            ]
            data["events"] = [
                _event_from_row(item)
                for item in conn.execute(
                    "SELECT * FROM events WHERE investigation_id = ? ORDER BY created_at ASC",
                    (investigation_id,),
                ).fetchall()
            ]
            data["entities"] = [
                _entity_from_row(item)
                for item in conn.execute(
                    "SELECT * FROM entities WHERE investigation_id = ? ORDER BY created_at ASC",
                    (investigation_id,),
                ).fetchall()
            ]
            data["evidence"] = [
                _evidence_from_row(item)
                for item in conn.execute(
                    "SELECT * FROM evidence WHERE investigation_id = ? ORDER BY created_at ASC",
                    (investigation_id,),
                ).fetchall()
            ]
            data["evidence_ledger"] = [
                _evidence_ledger_from_row(item)
                for item in conn.execute(
                    "SELECT * FROM evidence_ledger WHERE investigation_id = ? ORDER BY observed_at ASC",
                    (investigation_id,),
                ).fetchall()
            ]
            data["facts"] = [
                _fact_from_row(item)
                for item in conn.execute(
                    "SELECT * FROM facts WHERE investigation_id = ? ORDER BY observed_at ASC",
                    (investigation_id,),
                ).fetchall()
            ]
            data["hypotheses"] = [
                _hypothesis_from_row(item)
                for item in conn.execute(
                    "SELECT * FROM hypotheses WHERE investigation_id = ? ORDER BY rowid ASC",
                    (investigation_id,),
                ).fetchall()
            ]
            analysis_row = conn.execute(
                "SELECT * FROM hypothesis_analysis WHERE investigation_id = ?",
                (investigation_id,),
            ).fetchone()
            data["hypothesis_analysis"] = (
                _hypothesis_analysis_from_row(analysis_row)
                if analysis_row is not None
                else {
                    "most_likely_hypothesis": "",
                    "triggered_indicators": [],
                    "indicator_activation_rate": 0.0,
                    "confidence_language": "",
                }
            )
            data["relationships"] = [
                _relationship_from_row(item)
                for item in conn.execute(
                    "SELECT * FROM relationships WHERE investigation_id = ? ORDER BY created_at ASC",
                    (investigation_id,),
                ).fetchall()
            ]
            data["jobs"] = _with_orchestration_jobs(data)
            data["job_counts"] = _job_counts(data["jobs"])
        return data

    def import_detail(self, detail: dict) -> None:
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO investigations (
                    id, name, seed_type, seed_value, strategy, status, created_at,
                    max_depth, max_jobs, max_entities, claimed_by_agent_id,
                    claimed_by_agent_name, updated_at, summary, report_markdown, confidence,
                    risk_report_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    detail["id"],
                    detail["name"],
                    detail["seed_type"],
                    detail["seed_value"],
                    detail["strategy"],
                    detail["status"],
                    detail["created_at"],
                    detail["max_depth"],
                    detail["max_jobs"],
                    detail["max_entities"],
                    detail.get("claimed_by_agent_id"),
                    detail.get("claimed_by_agent_name"),
                    detail.get("updated_at"),
                    detail.get("summary", ""),
                    detail.get("report_markdown", ""),
                    detail.get("confidence"),
                    json.dumps(detail.get("risk_report", {}), ensure_ascii=False),
                    json.dumps(detail.get("metadata", {}), ensure_ascii=False),
                ),
            )
            for job in detail.get("jobs", []):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO jobs (
                        id, investigation_id, tool_name, target_type, target_value, depth, status,
                        agent_role, output_contract, depends_on
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job["id"],
                        job["investigation_id"],
                        job["tool_name"],
                        job["target_type"],
                        job["target_value"],
                        job["depth"],
                        job.get("status", "QUEUED"),
                        job.get("agent_role", "tool_agent"),
                        job.get("output_contract", "entities,evidence,relationships"),
                        job.get("depends_on", ""),
                    ),
                )
            for event in detail.get("events", []):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO events (
                        id, investigation_id, agent_id, level, message, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["id"],
                        event["investigation_id"],
                        event["agent_id"],
                        event["level"],
                        event["message"],
                        json.dumps(event.get("metadata", {}), ensure_ascii=False),
                        event["created_at"],
                    ),
                )
            for entity in detail.get("entities", []):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO entities (
                        id, investigation_id, type, value, source_tool, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity["id"],
                        entity["investigation_id"],
                        entity["type"],
                        entity["value"],
                        entity["source_tool"],
                        entity["confidence"],
                        entity["created_at"],
                    ),
                )
            for evidence in detail.get("evidence", []):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO evidence (
                        id, investigation_id, entity_value, evidence_kind, source_tool, snippet, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence["id"],
                        evidence["investigation_id"],
                        evidence["entity_value"],
                        evidence["evidence_kind"],
                        evidence["source_tool"],
                        evidence["snippet"],
                        evidence["created_at"],
                    ),
                )
            for record in detail.get("evidence_ledger", []):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO evidence_ledger (
                        id, investigation_id, source_url, source_type, source_tool, snippet,
                        observed_at, admiralty_code, source_reliability,
                        information_credibility, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["id"],
                        record["investigation_id"],
                        record["source_url"],
                        record["source_type"],
                        record["source_tool"],
                        record.get("snippet", ""),
                        record["observed_at"],
                        record["admiralty_code"],
                        record["source_reliability"],
                        record["information_credibility"],
                        record["content_hash"],
                    ),
                )
            for fact in detail.get("facts", []):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO facts (
                        id, investigation_id, statement, subject, predicate, object_value,
                        status, promotion_stage, confidence, admiralty_code, evidence_ids_json,
                        observed_at, valid_from, valid_to, supersedes_fact_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fact["id"],
                        fact["investigation_id"],
                        fact["statement"],
                        fact["subject"],
                        fact["predicate"],
                        fact["object"],
                        fact["status"],
                        fact.get("promotion_stage") or default_promotion_stage_for_status(fact.get("status", "NEEDS_REVIEW")),
                        fact["confidence"],
                        fact.get("admiralty_code", ""),
                        json.dumps(fact.get("evidence_ids", []), ensure_ascii=False),
                        fact["observed_at"],
                        fact["valid_from"],
                        fact.get("valid_to"),
                        fact.get("supersedes_fact_id"),
                    ),
                )
            for hypothesis in detail.get("hypotheses", []):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO hypotheses (
                        id, investigation_id, statement, mutually_exclusive_group, status,
                        support_score, inconsistency_score, supporting_evidence_json,
                        contradictory_evidence_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hypothesis["id"],
                        hypothesis["investigation_id"],
                        hypothesis["statement"],
                        hypothesis.get("mutually_exclusive_group", "default"),
                        hypothesis.get("status", "UNVERIFIED"),
                        hypothesis.get("support_score", 0.0),
                        hypothesis.get("inconsistency_score", 0.0),
                        json.dumps(hypothesis.get("supporting_evidence", []), ensure_ascii=False),
                        json.dumps(hypothesis.get("contradictory_evidence", []), ensure_ascii=False),
                        hypothesis.get("created_at", _now()),
                        hypothesis.get("updated_at", _now()),
                    ),
                )
            analysis = detail.get("hypothesis_analysis") or {}
            if analysis.get("most_likely_hypothesis") or analysis.get("triggered_indicators"):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO hypothesis_analysis (
                        investigation_id, most_likely_hypothesis, triggered_indicators_json,
                        indicator_activation_rate, confidence_language, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        detail["id"],
                        analysis.get("most_likely_hypothesis", ""),
                        json.dumps(analysis.get("triggered_indicators", []), ensure_ascii=False),
                        analysis.get("indicator_activation_rate", 0.0),
                        analysis.get("confidence_language", ""),
                        analysis.get("updated_at", _now()),
                    ),
                )
            for relationship in detail.get("relationships", []):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO relationships (
                        id, investigation_id, from_value, to_value, relationship_type, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        relationship["id"],
                        relationship["investigation_id"],
                        relationship["from_value"],
                        relationship["to_value"],
                        relationship["relationship_type"],
                        relationship["confidence"],
                        relationship["created_at"],
                    ),
                )

    def import_agent(self, agent: dict) -> None:
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agents (
                    id, agent_name, agent_type, capabilities_json, status, registered_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent["id"],
                    agent["agent_name"],
                    agent["agent_type"],
                    json.dumps(agent.get("capabilities", []), ensure_ascii=False),
                    agent.get("status", "ONLINE"),
                    agent.get("registered_at", _now()),
                    agent.get("last_seen_at", _now()),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS investigations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    seed_type TEXT NOT NULL,
                    seed_value TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    max_depth INTEGER NOT NULL,
                    max_jobs INTEGER NOT NULL,
                    max_entities INTEGER NOT NULL,
                    claimed_by_agent_id TEXT,
                    claimed_by_agent_name TEXT,
                    updated_at TEXT,
                    summary TEXT NOT NULL DEFAULT '',
                    report_markdown TEXT NOT NULL DEFAULT '',
                    confidence REAL,
                    risk_report_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_value TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    agent_role TEXT NOT NULL DEFAULT 'tool_agent',
                    output_contract TEXT NOT NULL DEFAULT 'entities,evidence,relationships',
                    depends_on TEXT NOT NULL DEFAULT '',
                    claimed_by_agent_id TEXT,
                    claimed_by_agent_name TEXT,
                    claimed_at TEXT,
                    heartbeat_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    agent_type TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source_tool TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    entity_value TEXT NOT NULL,
                    evidence_kind TEXT NOT NULL,
                    source_tool TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS relationships (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    from_value TEXT NOT NULL,
                    to_value TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS evidence_ledger (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_tool TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    admiralty_code TEXT NOT NULL,
                    source_reliability TEXT NOT NULL,
                    information_credibility TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS facts (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_value TEXT NOT NULL,
                    status TEXT NOT NULL,
                    promotion_stage TEXT NOT NULL DEFAULT 'CANDIDATE_FACT',
                    confidence REAL NOT NULL,
                    admiralty_code TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    supersedes_fact_id TEXT,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS hypotheses (
                    id TEXT NOT NULL,
                    investigation_id TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    mutually_exclusive_group TEXT NOT NULL,
                    status TEXT NOT NULL,
                    support_score REAL NOT NULL DEFAULT 0,
                    inconsistency_score REAL NOT NULL DEFAULT 0,
                    supporting_evidence_json TEXT NOT NULL DEFAULT '[]',
                    contradictory_evidence_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (id, investigation_id),
                    FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS hypothesis_analysis (
                    investigation_id TEXT PRIMARY KEY,
                    most_likely_hypothesis TEXT NOT NULL,
                    triggered_indicators_json TEXT NOT NULL,
                    indicator_activation_rate REAL NOT NULL,
                    confidence_language TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_investigation_status
                    ON jobs(investigation_id, status);
                CREATE INDEX IF NOT EXISTS idx_investigations_status_created
                    ON investigations(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_events_investigation_created
                    ON events(investigation_id, created_at);
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(investigations)").fetchall()
            }
            if "risk_report_json" not in columns:
                conn.execute(
                    "ALTER TABLE investigations ADD COLUMN risk_report_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "metadata_json" not in columns:
                conn.execute(
                    "ALTER TABLE investigations ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
                )
            job_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "agent_role" not in job_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN agent_role TEXT NOT NULL DEFAULT 'tool_agent'")
            if "output_contract" not in job_columns:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN output_contract TEXT NOT NULL DEFAULT 'entities,evidence,relationships'"
                )
            if "depends_on" not in job_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN depends_on TEXT NOT NULL DEFAULT ''")
            if "claimed_by_agent_id" not in job_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN claimed_by_agent_id TEXT")
            if "claimed_by_agent_name" not in job_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN claimed_by_agent_name TEXT")
            if "claimed_at" not in job_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN claimed_at TEXT")
            if "heartbeat_at" not in job_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN heartbeat_at TEXT")
            if "attempt_count" not in job_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0")
            if "last_error" not in job_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN last_error TEXT NOT NULL DEFAULT ''")
            fact_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(facts)").fetchall()
            }
            if "promotion_stage" not in fact_columns:
                conn.execute(
                    "ALTER TABLE facts ADD COLUMN promotion_stage TEXT NOT NULL DEFAULT 'CANDIDATE_FACT'"
                )
                conn.execute(
                    """
                    UPDATE facts
                    SET promotion_stage = CASE
                        WHEN status = 'CONFIRMED' THEN 'ACCEPTED_FACT'
                        WHEN status = 'LIKELY' THEN 'ASSESSED_FACT'
                        WHEN status IN ('CONTRADICTED', 'RETIRED') THEN 'REJECTED_FACT'
                        ELSE 'CANDIDATE_FACT'
                    END
                    """
                )
            _record_schema_migration(conn, "20260522_core_v3")
            _record_schema_migration(conn, "20260522_stability_pack")
            _dedupe_existing_rows(conn)
            conn.executescript(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_unique_signal
                    ON entities(investigation_id, type, value, source_tool);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_unique_signal
                    ON evidence(investigation_id, entity_value, evidence_kind, source_tool);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_relationships_unique_signal
                    ON relationships(investigation_id, from_value, to_value, relationship_type);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_ledger_unique_hash
                    ON evidence_ledger(investigation_id, content_hash);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_unique_claim
                    ON facts(investigation_id, subject, predicate, object_value);
                """
            )

    def _touch_investigation(
        self,
        conn: sqlite3.Connection,
        investigation_id: str,
        status: str | None = None,
    ) -> None:
        row = conn.execute(
            "SELECT status FROM investigations WHERE id = ?",
            (investigation_id,),
        ).fetchone()
        if row is None:
            return
        next_status = row["status"]
        if status and next_status in {"OPEN", "CLAIMED", "RUNNING"}:
            next_status = status
        conn.execute(
            "UPDATE investigations SET status = ?, updated_at = ? WHERE id = ?",
            (next_status, _now(), investigation_id),
        )

    def _set_lifecycle_status(
        self,
        investigation_id: str,
        status: str,
        clear_claim: bool,
    ) -> dict | None:
        now = _now()
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT id FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
            if row is None:
                return None
            if clear_claim:
                conn.execute(
                    """
                    UPDATE investigations
                    SET status = ?, claimed_by_agent_id = NULL, claimed_by_agent_name = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, now, investigation_id),
                )
            else:
                conn.execute(
                    "UPDATE investigations SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, investigation_id),
                )
        return self.get_investigation(investigation_id)


def _strategy_from_name(name: str) -> StrategyProfile:
    strategies = {
        "quick": StrategyProfile.quick,
        "standard": StrategyProfile.standard,
        "deep": StrategyProfile.deep,
        "maximum": StrategyProfile.maximum,
    }
    try:
        return strategies[name]()
    except KeyError as exc:
        raise ValueError(f"unsupported strategy: {name}") from exc


def _dedupe_existing_rows(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM entities
        WHERE rowid NOT IN (
            SELECT rowid FROM (
                SELECT rowid,
                    ROW_NUMBER() OVER (
                        PARTITION BY investigation_id, type, value, source_tool
                        ORDER BY confidence DESC, created_at DESC, rowid DESC
                    ) AS rn
                FROM entities
            )
            WHERE rn = 1
        );

        DELETE FROM evidence
        WHERE rowid NOT IN (
            SELECT rowid FROM (
                SELECT rowid,
                    ROW_NUMBER() OVER (
                        PARTITION BY investigation_id, entity_value, evidence_kind, source_tool
                        ORDER BY created_at DESC, rowid DESC
                    ) AS rn
                FROM evidence
            )
            WHERE rn = 1
        );

        DELETE FROM relationships
        WHERE rowid NOT IN (
            SELECT rowid FROM (
                SELECT rowid,
                    ROW_NUMBER() OVER (
                        PARTITION BY investigation_id, from_value, to_value, relationship_type
                        ORDER BY confidence DESC, created_at DESC, rowid DESC
                    ) AS rn
                FROM relationships
            )
            WHERE rn = 1
        );

        DELETE FROM evidence_ledger
        WHERE rowid NOT IN (
            SELECT rowid FROM (
                SELECT rowid,
                    ROW_NUMBER() OVER (
                        PARTITION BY investigation_id, content_hash
                        ORDER BY observed_at DESC, rowid DESC
                    ) AS rn
                FROM evidence_ledger
            )
            WHERE rn = 1
        );

        DELETE FROM facts
        WHERE rowid NOT IN (
            SELECT rowid FROM (
                SELECT rowid,
                    ROW_NUMBER() OVER (
                        PARTITION BY investigation_id, subject, predicate, object_value
                        ORDER BY
                            CASE status
                                WHEN 'CONFIRMED' THEN 4
                                WHEN 'LIKELY' THEN 3
                                WHEN 'NEEDS_REVIEW' THEN 2
                                WHEN 'CONTRADICTED' THEN 1
                                ELSE 0
                            END DESC,
                            confidence DESC,
                            observed_at DESC,
                            rowid DESC
                    ) AS rn
                FROM facts
            )
            WHERE rn = 1
        );
        """
    )


def _record_schema_migration(conn: sqlite3.Connection, version: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (version, _now()),
    )


def _apply_core_v3(data: dict) -> None:
    matrix = build_cross_verification_matrix(data)
    requirements = build_intelligence_requirements(
        data["seed_type"],
        data["seed_value"],
        data["strategy"],
        data.get("metadata") or {},
    )
    data["cross_verification_matrix"] = matrix
    data["intelligence_requirements"] = apply_requirement_updates(
        requirements,
        matrix,
        data.get("facts") or [],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _investigation_row(investigation: Investigation) -> tuple:
    return (
        investigation.id,
        investigation.name,
        investigation.seed_type,
        investigation.seed_value,
        investigation.strategy,
        investigation.status,
        investigation.created_at,
        investigation.max_depth,
        investigation.max_jobs,
        investigation.max_entities,
        investigation.claimed_by_agent_id,
        investigation.claimed_by_agent_name,
        investigation.updated_at,
        investigation.summary,
        investigation.report_markdown,
        investigation.confidence,
        json.dumps(investigation.risk_report or {}, ensure_ascii=False),
        json.dumps(investigation.metadata or {}, ensure_ascii=False),
    )


def _investigation_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "seed_type": row["seed_type"],
        "seed_value": row["seed_value"],
        "strategy": row["strategy"],
        "status": row["status"],
        "created_at": row["created_at"],
        "max_depth": row["max_depth"],
        "max_jobs": row["max_jobs"],
        "max_entities": row["max_entities"],
        "claimed_by_agent_id": row["claimed_by_agent_id"],
        "claimed_by_agent_name": row["claimed_by_agent_name"],
        "updated_at": row["updated_at"],
        "summary": row["summary"],
        "report_markdown": row["report_markdown"],
        "confidence": row["confidence"],
        "risk_report": json.loads(row["risk_report_json"] or "{}"),
        "metadata": json.loads(row["metadata_json"] or "{}"),
    }


def _job_counts(jobs: list[dict]) -> dict:
    counts = {
        "QUEUED": 0,
        "RUNNING": 0,
        "COMPLETED": 0,
        "PARTIAL_FAILED": 0,
        "FAILED": 0,
        "BLOCKED": 0,
        "SKIPPED": 0,
    }
    for job in jobs:
        status = job.get("status", "QUEUED")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _with_orchestration_jobs(detail: dict) -> list[dict]:
    jobs = list(detail.get("jobs", []))
    if not _needs_company_orchestration(detail, jobs):
        return jobs
    existing_tools = {job["tool_name"] for job in jobs}
    strategy = _strategy_from_name(detail.get("strategy", "standard"))
    orchestration_jobs = [
        _planned_job_as_detail(detail["id"], planned)
        for planned in plan_initial_jobs("company", detail["seed_value"], strategy, default_tool_registry())
        if planned.tool_name not in existing_tools
    ]
    return [*jobs, *orchestration_jobs]


def _needs_company_orchestration(detail: dict, jobs: list[dict]) -> bool:
    if any(job.get("agent_role") == "analysis_judgement_agent" for job in jobs):
        return False
    if detail.get("seed_type") == "company":
        return True
    text = f"{detail.get('name', '')} {detail.get('seed_value', '')}".lower()
    return any(token in text for token in ("企业背调", "公司背调", " llc", " inc", " ltd", " company", " hospitality"))


def _planned_job_as_detail(investigation_id: str, planned) -> dict:
    return {
        "id": f"orchestration:{planned.tool_name}:{planned.target_type}:{planned.target_value}",
        "investigation_id": investigation_id,
        "tool_name": planned.tool_name,
        "target_type": planned.target_type,
        "target_value": planned.target_value,
        "depth": planned.depth,
        "status": "QUEUED",
        "agent_role": planned.agent_role,
        "output_contract": planned.output_contract,
        "depends_on": planned.depends_on,
    }


def _job_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "tool_name": row["tool_name"],
        "target_type": row["target_type"],
        "target_value": row["target_value"],
        "depth": row["depth"],
        "status": row["status"],
        "agent_role": row["agent_role"],
        "output_contract": row["output_contract"],
        "depends_on": row["depends_on"],
        "claimed_by_agent_id": row["claimed_by_agent_id"],
        "claimed_by_agent_name": row["claimed_by_agent_name"],
        "claimed_at": row["claimed_at"],
        "heartbeat_at": row["heartbeat_at"],
        "attempt_count": row["attempt_count"],
        "last_error": row["last_error"],
    }


def _agent_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "agent_name": row["agent_name"],
        "agent_type": row["agent_type"],
        "capabilities": json.loads(row["capabilities_json"]),
        "status": row["status"],
        "registered_at": row["registered_at"],
        "last_seen_at": row["last_seen_at"],
    }


def _event_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "agent_id": row["agent_id"],
        "level": row["level"],
        "message": row["message"],
        "metadata": json.loads(row["metadata_json"]),
        "created_at": row["created_at"],
    }


def _entity_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "type": row["type"],
        "value": row["value"],
        "source_tool": row["source_tool"],
        "confidence": row["confidence"],
        "created_at": row["created_at"],
    }


def _evidence_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "entity_value": row["entity_value"],
        "evidence_kind": row["evidence_kind"],
        "source_tool": row["source_tool"],
        "snippet": row["snippet"],
        "created_at": row["created_at"],
    }


def _evidence_ledger_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "source_url": row["source_url"],
        "source_type": row["source_type"],
        "source_tool": row["source_tool"],
        "snippet": row["snippet"],
        "observed_at": row["observed_at"],
        "admiralty_code": row["admiralty_code"],
        "source_reliability": row["source_reliability"],
        "information_credibility": row["information_credibility"],
        "content_hash": row["content_hash"],
    }


def _fact_from_row(row: sqlite3.Row) -> dict:
    promotion_stage = (
        row["promotion_stage"]
        if "promotion_stage" in row.keys()
        else default_promotion_stage_for_status(row["status"])
    )
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "statement": row["statement"],
        "subject": row["subject"],
        "predicate": row["predicate"],
        "object": row["object_value"],
        "status": row["status"],
        "promotion_stage": promotion_stage,
        "confidence": row["confidence"],
        "admiralty_code": row["admiralty_code"],
        "evidence_ids": json.loads(row["evidence_ids_json"] or "[]"),
        "observed_at": row["observed_at"],
        "valid_from": row["valid_from"],
        "valid_to": row["valid_to"],
        "supersedes_fact_id": row["supersedes_fact_id"],
    }


def _merge_fact_record(existing: FactRecord, incoming: FactRecord) -> FactRecord:
    merged = _merge_fact_dict(_fact_as_dict(existing), _fact_as_dict(incoming))
    return FactRecord(
        id=merged["id"],
        investigation_id=merged["investigation_id"],
        statement=merged["statement"],
        subject=merged["subject"],
        predicate=merged["predicate"],
        object=merged["object"],
        status=merged["status"],
        promotion_stage=merged["promotion_stage"],
        confidence=merged["confidence"],
        admiralty_code=merged["admiralty_code"],
        evidence_ids=merged["evidence_ids"],
        observed_at=merged["observed_at"],
        valid_from=merged["valid_from"],
        valid_to=merged.get("valid_to"),
        supersedes_fact_id=merged.get("supersedes_fact_id"),
    )


def _merge_fact_dict(existing: dict, incoming: dict) -> dict:
    status_rank = {"CONFIRMED": 4, "LIKELY": 3, "NEEDS_REVIEW": 2, "CONTRADICTED": 1, "RETIRED": 0}
    stronger = incoming if status_rank.get(incoming["status"], 0) > status_rank.get(existing["status"], 0) else existing
    if status_rank.get(incoming["status"], 0) == status_rank.get(existing["status"], 0):
        stronger = incoming if float(incoming.get("confidence") or 0) > float(existing.get("confidence") or 0) else existing
    evidence_ids = sorted({*existing.get("evidence_ids", []), *incoming.get("evidence_ids", [])})
    merged = dict(existing)
    merged.update(
        {
            "statement": stronger["statement"],
            "status": stronger["status"],
            "promotion_stage": default_promotion_stage_for_status(stronger["status"]),
            "confidence": max(float(existing.get("confidence") or 0), float(incoming.get("confidence") or 0)),
            "admiralty_code": _stronger_admiralty(existing.get("admiralty_code", ""), incoming.get("admiralty_code", "")),
            "evidence_ids": evidence_ids,
            "observed_at": incoming.get("observed_at") or existing.get("observed_at"),
        }
    )
    return merged


def _stronger_admiralty(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    return sorted([left, right])[0]


def _fact_as_dict(fact: FactRecord) -> dict:
    return {
        "id": fact.id,
        "investigation_id": fact.investigation_id,
        "statement": fact.statement,
        "subject": fact.subject,
        "predicate": fact.predicate,
        "object": fact.object,
        "status": fact.status,
        "promotion_stage": fact.promotion_stage,
        "confidence": fact.confidence,
        "admiralty_code": fact.admiralty_code,
        "evidence_ids": fact.evidence_ids,
        "observed_at": fact.observed_at,
        "valid_from": fact.valid_from,
        "valid_to": fact.valid_to,
        "supersedes_fact_id": fact.supersedes_fact_id,
    }


def _hypothesis_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "statement": row["statement"],
        "mutually_exclusive_group": row["mutually_exclusive_group"],
        "status": row["status"],
        "support_score": row["support_score"],
        "inconsistency_score": row["inconsistency_score"],
        "supporting_evidence": json.loads(row["supporting_evidence_json"] or "[]"),
        "contradictory_evidence": json.loads(row["contradictory_evidence_json"] or "[]"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _hypothesis_analysis_from_row(row: sqlite3.Row) -> dict:
    return {
        "most_likely_hypothesis": row["most_likely_hypothesis"],
        "triggered_indicators": json.loads(row["triggered_indicators_json"] or "[]"),
        "indicator_activation_rate": row["indicator_activation_rate"],
        "confidence_language": row["confidence_language"],
        "updated_at": row["updated_at"],
    }


def _ach_result_as_dict(result) -> dict:
    return {
        "most_likely_hypothesis": result.most_likely_hypothesis,
        "hypotheses": result.hypotheses,
        "triggered_indicators": result.triggered_indicators,
        "indicator_activation_rate": result.indicator_activation_rate,
        "confidence_language": result.confidence_language,
    }


def _relationship_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "from_value": row["from_value"],
        "to_value": row["to_value"],
        "relationship_type": row["relationship_type"],
        "confidence": row["confidence"],
        "created_at": row["created_at"],
    }


def create_default_store() -> MemoryStore | SQLiteStore:
    backend = os.getenv("OSINT_STORE_BACKEND", "sqlite").lower()
    if backend == "memory":
        return MemoryStore()
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    db_path = os.getenv("OSINT_DB_PATH", os.path.join(project_root, "data", "osint.sqlite"))
    return SQLiteStore(db_path)


store = create_default_store()
