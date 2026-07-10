from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
import json
import os
import sqlite3
from threading import Lock
from uuid import uuid4

from app.core.agent_auth import (
    AGENT_ROLE_TIERS,
    AgentRegistration,
    agent_output_contract_allows,
    agent_output_contract_sections,
    generate_agent_token,
    hash_agent_token,
    validate_agent_registration,
    validate_agent_role_tier,
)
from app.core.agent_payload_validation import validate_tool_output_payload
from app.core.agent_permissions import tier_for_role
from app.core.ach_engine import EvidenceItem, Hypothesis, run_ach_analysis
from app.core.completion_policy import build_completion_policy
from app.core.cross_verification import build_cross_verification_matrix
from app.core.evidence_ledger import build_evidence_record
from app.core.fact_pool import FactRecord, default_promotion_stage_for_status, validate_fact_record
from app.core.gap_followups import build_gap_analysis, build_gap_followup_summary, build_gap_tool_plan
from app.core.graph import build_investigation_graph
from app.core.intelligence_memory import build_intelligence_memory
from app.core.intelligence_requirements import apply_requirement_updates, build_intelligence_requirements
from app.core.planner import StrategyProfile, plan_initial_job_set, plan_initial_jobs
from app.core.quality import build_quality_assessment, completion_status_for_detail, render_structured_report
from app.core.registry import default_tool_registry


_AGENT_TOKEN_GENERATION_ATTEMPTS = 5
_AGENT_ACCESS_INVESTIGATION_STATUSES = frozenset({"CLAIMED", "RUNNING"})
_AGENT_ACCESS_JOB_STATUSES = frozenset({"CLAIMED", "RUNNING"})


class ToolOutputValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("invalid tool output")
        self.errors = errors


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
    role_tier: str | None = None
    token_hash: str | None = field(default=None, repr=False)
    token_created_at: str | None = None
    disabled_at: str | None = None


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
        recorded_skipped_routes = skipped_routes if respect_tool_health else []
        metadata = metadata or {}
        if respect_tool_health:
            metadata = {**metadata, "respect_tool_health": True}
        if recorded_skipped_routes:
            metadata = {**metadata, "initial_skipped_routes": [asdict(route) for route in recorded_skipped_routes]}
        planning_blocked = bool(recorded_skipped_routes and not planned_jobs)
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
            if recorded_skipped_routes:
                event = AgentEvent(
                    id=str(uuid4()),
                    investigation_id=investigation.id,
                    agent_id="planner",
                    level="warning",
                    message="规划阶段跳过不可用工具",
                    metadata={"skipped_routes": [asdict(route) for route in recorded_skipped_routes]},
                    created_at=now,
                )
                self.events[event.id] = event

        return investigation

    def register_agent(
        self,
        agent_name: str,
        agent_type: str,
        capabilities: list[str],
        role_tier: str,
    ) -> dict:
        validated_tier = validate_agent_role_tier(role_tier)
        agent_name, agent_type, capabilities = validate_agent_registration(
            agent_name, agent_type, capabilities
        )
        with self.lock:
            token, token_hash = _allocate_agent_token(
                {agent.token_hash for agent in self.agents.values() if agent.token_hash}
            )
            now = _now()
            agent = next(
                (item for item in self.agents.values() if item.agent_name == agent_name),
                None,
            )
            if agent is None:
                agent = Agent(
                    id=str(uuid4()),
                    agent_name=agent_name,
                    agent_type=agent_type,
                    capabilities=list(capabilities),
                    status="ONLINE",
                    registered_at=now,
                    last_seen_at=now,
                )
                self.agents[agent.id] = agent
            else:
                agent.agent_type = agent_type
                agent.capabilities = list(capabilities)
                agent.status = "ONLINE"
                agent.last_seen_at = now
            agent.role_tier = validated_tier
            agent.token_hash = token_hash
            agent.token_created_at = now
            agent.disabled_at = None
            return AgentRegistration({**_public_agent(agent), "agent_token": token})

    def heartbeat_agent(self, agent_id: str) -> dict | None:
        with self.lock:
            agent = self.agents.get(agent_id)
            if (
                agent is None
                or agent.disabled_at is not None
                or agent.role_tier not in AGENT_ROLE_TIERS
            ):
                return None
            agent.last_seen_at = _now()
            agent.status = "ONLINE"
            return _public_agent(agent)

    def list_agents(self) -> list[dict]:
        with self.lock:
            return [_public_agent(agent) for agent in self.agents.values()]

    def resolve_agent_token(self, token: object) -> dict | None:
        if not isinstance(token, str) or not token:
            return None
        token_hash = hash_agent_token(token)
        with self.lock:
            matches = [
                agent
                for agent in self.agents.values()
                if agent.token_hash == token_hash
                and agent.disabled_at is None
                and agent.role_tier in AGENT_ROLE_TIERS
            ]
            if len(matches) != 1:
                return None
            return _public_agent(matches[0])

    def rotate_agent_token(self, agent_id: str) -> dict | None:
        with self.lock:
            agent = self.agents.get(agent_id)
            if (
                agent is None
                or agent.disabled_at is not None
                or agent.role_tier not in AGENT_ROLE_TIERS
            ):
                return None
            token, token_hash = _allocate_agent_token(
                {item.token_hash for item in self.agents.values() if item.token_hash}
            )
            now = _now()
            agent.token_hash = token_hash
            agent.token_created_at = now
            return AgentRegistration(
                {"agent_id": agent.id, "agent_token": token, "token_created_at": now}
            )

    def agent_has_investigation_access(
        self,
        agent_id: str,
        investigation_id: str,
        required_tier: str,
        job_id: str | None = None,
        action: str | None = None,
    ) -> bool:
        if required_tier not in AGENT_ROLE_TIERS:
            return False
        with self.lock:
            return self._agent_has_investigation_access_locked(
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action=action,
            )

    def _agent_has_investigation_access_locked(
        self,
        agent_id: str,
        investigation_id: str,
        required_tier: str,
        job_id: str | None = None,
        action: str | None = None,
    ) -> bool:
        if required_tier not in AGENT_ROLE_TIERS:
            return False
        agent = self.agents.get(agent_id)
        if (
            agent is None
            or agent.disabled_at is not None
            or agent.role_tier != required_tier
        ):
            return False
        investigation = self.investigations.get(investigation_id)
        if (
            investigation is None
            or investigation.status not in _AGENT_ACCESS_INVESTIGATION_STATUSES
        ):
            return False
        if investigation.claimed_by_agent_id == agent_id:
            return True
        if not job_id or not action:
            return False
        job = self.jobs.get(job_id)
        return bool(
            job is not None
            and job.investigation_id == investigation_id
            and job.claimed_by_agent_id == agent_id
            and job.status in _AGENT_ACCESS_JOB_STATUSES
            and tier_for_role(job.agent_role) == required_tier
            and agent_output_contract_allows(job.output_contract, action)
        )

    def agent_add_event(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        level: str,
        message: str,
        metadata: dict | None = None,
    ) -> dict | None:
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
            if not self._agent_has_investigation_access_locked(
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="event",
            ):
                return None
            self.events[event.id] = event
            self._touch_investigation(investigation_id, status="RUNNING")
            return asdict(event)

    def agent_add_entities(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        entities: list[dict],
    ) -> list[dict] | None:
        if required_tier != "reader":
            return None
        records = [
            Entity(
                id=str(uuid4()),
                investigation_id=investigation_id,
                type=item["type"],
                value=item["value"],
                source_tool=item.get("source_tool", "agent"),
                confidence=float(item.get("confidence", 0.0)),
                created_at=_now(),
            )
            for item in entities
        ]
        with self.lock:
            if not self._agent_has_investigation_access_locked(
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="entities",
            ):
                return None
            for entity in records:
                self.entities[entity.id] = entity
            self._touch_investigation(investigation_id, status="RUNNING")
            return [asdict(entity) for entity in records]

    def agent_add_evidence(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        entity_value: str,
        evidence_kind: str,
        source_tool: str,
        snippet: str,
    ) -> dict | None:
        if required_tier != "reader":
            return None
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
            if not self._agent_has_investigation_access_locked(
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="evidence",
            ):
                return None
            self.evidence[evidence.id] = evidence
            self._touch_investigation(investigation_id, status="RUNNING")
            return asdict(evidence)

    def agent_add_evidence_record(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        source_url: str,
        source_type: str,
        source_tool: str,
        snippet: str,
        credibility: float,
    ) -> dict | None:
        if required_tier != "reader":
            return None
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
            if not self._agent_has_investigation_access_locked(
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="evidence_records",
            ):
                return None
            self.evidence_ledger[record.id] = data
            self._touch_investigation(investigation_id, status="RUNNING")
            return data

    def agent_add_fact(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        statement: str,
        subject: str,
        predicate: str,
        object_value: str,
        status: str,
        confidence: float,
        admiralty_code: str,
        evidence_ids: list[str],
    ) -> dict | None:
        if required_tier != "verifier":
            return None
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
            if not self._agent_has_investigation_access_locked(
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="facts",
            ):
                return None
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
            result = _merge_fact_record(existing, fact) if existing else fact
            self.facts[result.id] = result
            self._touch_investigation(investigation_id, status="RUNNING")
            return _fact_as_dict(result)

    def agent_add_hypothesis(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        hypothesis_id: str,
        statement: str,
        group: str = "default",
    ) -> dict | None:
        if required_tier != "verifier":
            return None
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
            if not self._agent_has_investigation_access_locked(
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="hypotheses",
            ):
                return None
            self.hypotheses[f"{investigation_id}:{hypothesis_id}"] = row
            self._touch_investigation(investigation_id, status="RUNNING")
            return dict(row)

    def agent_score_hypotheses(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        evidence_items: list[dict],
    ) -> dict | None:
        if required_tier != "verifier":
            return None
        with self.lock:
            if not self._agent_has_investigation_access_locked(
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="score_hypotheses",
            ):
                return None
            return self._score_hypotheses_locked(investigation_id, evidence_items)

    def agent_add_relationship(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        from_value: str,
        to_value: str,
        relationship_type: str,
        confidence: float,
    ) -> dict | None:
        if required_tier != "reader":
            return None
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
            if not self._agent_has_investigation_access_locked(
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="relationships",
            ):
                return None
            self.relationships[relationship.id] = relationship
            self._touch_investigation(investigation_id, status="RUNNING")
            return asdict(relationship)

    def agent_complete_task(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        status: str,
        summary: str,
        report_markdown: str,
        confidence: float | None,
    ) -> dict | None:
        if required_tier != "reporter":
            return None
        with self.lock:
            if not self._agent_has_investigation_access_locked(
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="complete_task",
            ):
                return None
            return self._complete_task_locked(
                investigation_id,
                agent_id,
                status,
                summary,
                report_markdown,
                confidence,
            )

    def claim_task(self, agent_id: str, capabilities: object) -> dict | None:
        with self.lock:
            agent = self.agents.get(agent_id)
            if (
                agent is None
                or agent.disabled_at is not None
                or agent.role_tier not in {"reader", "verifier", "reporter"}
            ):
                return None
            capability_set = _narrow_agent_capabilities(
                agent.capabilities, capabilities
            )
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

    def claim_job(self, agent_id: str, capabilities: object) -> dict | None:
        with self.lock:
            agent = self.agents.get(agent_id)
            if (
                agent is None
                or agent.disabled_at is not None
                or agent.role_tier not in AGENT_ROLE_TIERS
            ):
                return None
            capability_set = _narrow_agent_capabilities(
                agent.capabilities, capabilities
            )
            for job in self.jobs.values():
                if job.status not in {"WAITING_AGENT", "QUEUED"}:
                    continue
                investigation = self.investigations.get(job.investigation_id)
                if (
                    investigation is None
                    or investigation.status
                    not in _AGENT_ACCESS_INVESTIGATION_STATUSES
                ):
                    continue
                if agent.role_tier == "tool_agent":
                    if job.agent_role != "tool_agent" or job.tool_name not in capability_set:
                        continue
                else:
                    if job.agent_role == "tool_agent":
                        continue
                    if tier_for_role(job.agent_role) != agent.role_tier:
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

    def get_claimed_agent_job(
        self,
        agent_id: str,
        investigation_id: str,
        job_id: str,
        required_tier: str,
        *,
        require_tool_role: bool = False,
    ) -> dict | None:
        with self.lock:
            agent = self.agents.get(agent_id)
            investigation = self.investigations.get(investigation_id)
            job = self.jobs.get(job_id)
            if (
                agent is None
                or agent.disabled_at is not None
                or agent.role_tier != required_tier
                or investigation is None
                or investigation.status not in _AGENT_ACCESS_INVESTIGATION_STATUSES
                or job is None
                or job.investigation_id != investigation_id
                or job.claimed_by_agent_id != agent_id
                or job.status not in _AGENT_ACCESS_JOB_STATUSES
                or (require_tool_role and job.agent_role != "tool_agent")
            ):
                return None
            return asdict(job)

    def submit_tool_job_output(
        self,
        agent_id: str,
        investigation_id: str,
        job_id: str,
        payload: dict,
    ) -> dict | None:
        with self.lock:
            agent = self.agents.get(agent_id)
            investigation = self.investigations.get(investigation_id)
            job = self.jobs.get(job_id)
            if (
                agent is None
                or agent.disabled_at is not None
                or agent.role_tier != "tool_agent"
                or investigation is None
                or investigation.status not in _AGENT_ACCESS_INVESTIGATION_STATUSES
                or job is None
                or job.investigation_id != investigation_id
                or job.claimed_by_agent_id != agent_id
                or job.status not in _AGENT_ACCESS_JOB_STATUSES
                or job.agent_role != "tool_agent"
            ):
                return None
            errors = validate_tool_output_payload(
                payload,
                agent_output_contract_sections(job.output_contract),
                job.tool_name,
            )
            if errors:
                raise ToolOutputValidationError(errors)

            event, entities, evidence, relationships = _build_tool_output_records(
                investigation_id, agent_id, payload
            )
            original_status = job.status
            original_investigation_status = investigation.status
            original_updated_at = investigation.updated_at
            inserted: list[tuple[dict, str]] = []
            updated: list[tuple[object, dict]] = []
            created = {"entities": 0, "evidence": 0, "relationships": 0}
            try:
                if event is not None:
                    self.events[event.id] = event
                    inserted.append((self.events, event.id))
                for entity in entities:
                    existing = next(
                        (
                            item
                            for item in self.entities.values()
                            if _entity_signal_key(item) == _entity_signal_key(entity)
                        ),
                        None,
                    )
                    if existing is None:
                        self.entities[entity.id] = entity
                        inserted.append((self.entities, entity.id))
                        created["entities"] += 1
                    else:
                        updated.append((existing, asdict(existing)))
                        existing.confidence = max(
                            existing.confidence, entity.confidence
                        )
                for item in evidence:
                    existing = next(
                        (
                            stored
                            for stored in self.evidence.values()
                            if _evidence_signal_key(stored)
                            == _evidence_signal_key(item)
                        ),
                        None,
                    )
                    if existing is None:
                        self.evidence[item.id] = item
                        inserted.append((self.evidence, item.id))
                        created["evidence"] += 1
                    else:
                        updated.append((existing, asdict(existing)))
                        existing.snippet = item.snippet
                        existing.created_at = item.created_at
                for relationship in relationships:
                    existing = next(
                        (
                            item
                            for item in self.relationships.values()
                            if _relationship_signal_key(item)
                            == _relationship_signal_key(relationship)
                        ),
                        None,
                    )
                    if existing is None:
                        self.relationships[relationship.id] = relationship
                        inserted.append((self.relationships, relationship.id))
                        created["relationships"] += 1
                    else:
                        updated.append((existing, asdict(existing)))
                        existing.confidence = max(
                            existing.confidence, relationship.confidence
                        )
                job.status = "COMPLETED"
                self._touch_investigation(investigation_id, status="RUNNING")
            except Exception:
                for collection, item_id in reversed(inserted):
                    collection.pop(item_id, None)
                for item, original in reversed(updated):
                    for field_name, value in original.items():
                        setattr(item, field_name, value)
                job.status = original_status
                investigation.status = original_investigation_status
                investigation.updated_at = original_updated_at
                raise
            return _tool_output_result(job_id, created)

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
            return self._score_hypotheses_locked(investigation_id, evidence_items)

    def _score_hypotheses_locked(
        self, investigation_id: str, evidence_items: list[dict]
    ) -> dict:
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
            return self._complete_task_locked(
                investigation_id,
                agent_id,
                status,
                summary,
                report_markdown,
                confidence,
            )

    def _complete_task_locked(
        self,
        investigation_id: str,
        agent_id: str,
        status: str,
        summary: str,
        report_markdown: str,
        confidence: float | None,
    ) -> dict | None:
        investigation = self.investigations.get(investigation_id)
        if investigation is None:
            return None
        preview = self._investigation_detail(investigation_id)
        preview["summary"] = summary
        preview["report_markdown"] = report_markdown
        assessment = build_quality_assessment(preview)
        preview["quality_assessment"] = assessment
        _apply_gap_plans(preview)
        preview["completion_policy"] = build_completion_policy(preview)
        investigation.status = _policy_status_for_detail(preview, status)
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
        _apply_gap_plans(raw)
        raw["completion_policy"] = build_completion_policy(raw)
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
        _apply_gap_plans(data)
        data["completion_policy"] = build_completion_policy(data)
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

    def enqueue_worker_run(self, investigation_id: str, max_jobs: int | None = None) -> dict:
        now = _now()
        with self.lock, closing(self._connect()) as conn, conn:
            investigation = conn.execute(
                "SELECT id FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
            if investigation is None:
                raise ValueError(f"investigation not found: {investigation_id}")
            active = conn.execute(
                """
                SELECT * FROM worker_queue_runs
                WHERE investigation_id = ? AND status IN ('QUEUED', 'RUNNING')
                ORDER BY requested_at ASC
                LIMIT 1
                """,
                (investigation_id,),
            ).fetchone()
            if active is not None:
                status = "ALREADY_RUNNING" if active["status"] == "RUNNING" else "ALREADY_QUEUED"
                return self._worker_queue_response(conn, False, status, investigation_id, max_jobs)
            conn.execute(
                """
                INSERT INTO worker_queue_runs (
                    id, investigation_id, max_jobs, status, requested_at,
                    started_at, finished_at, worker_id, heartbeat_at, summary_json, error
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, '', NULL, '{}', '')
                """,
                (str(uuid4()), investigation_id, max_jobs, "QUEUED", now),
            )
            return self._worker_queue_response(conn, True, "QUEUED", investigation_id, max_jobs)

    def claim_next_worker_run(self, worker_id: str, stale_after_seconds: int = 1800) -> dict | None:
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        stale_cutoff = (now_dt - timedelta(seconds=max(0, stale_after_seconds))).isoformat()
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                UPDATE worker_queue_runs
                SET status = 'QUEUED', worker_id = '', started_at = NULL, heartbeat_at = NULL
                WHERE status = 'RUNNING'
                  AND COALESCE(heartbeat_at, started_at, requested_at) <= ?
                """,
                (stale_cutoff,),
            )
            target = conn.execute(
                """
                SELECT * FROM worker_queue_runs
                WHERE status = 'QUEUED'
                ORDER BY requested_at ASC
                LIMIT 1
                """
            ).fetchone()
            if target is None:
                return None
            conn.execute(
                """
                UPDATE worker_queue_runs
                SET status = 'RUNNING', worker_id = ?, started_at = ?, heartbeat_at = ?, error = ''
                WHERE id = ? AND status = 'QUEUED'
                """,
                (worker_id, now, now, target["id"]),
            )
            updated = conn.execute("SELECT * FROM worker_queue_runs WHERE id = ?", (target["id"],)).fetchone()
        return _worker_queue_claim_from_row(updated)

    def complete_worker_run(self, queue_id: str, summary: dict) -> dict | None:
        now = _now()
        summary_json = json.dumps(_worker_queue_summary(summary), ensure_ascii=False)
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM worker_queue_runs WHERE id = ?", (queue_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE worker_queue_runs
                SET status = 'COMPLETED', finished_at = ?, heartbeat_at = ?, summary_json = ?, error = ''
                WHERE id = ?
                """,
                (now, now, summary_json, queue_id),
            )
            updated = conn.execute("SELECT * FROM worker_queue_runs WHERE id = ?", (queue_id,)).fetchone()
        return _worker_queue_claim_from_row(updated)

    def fail_worker_run(self, queue_id: str, error: str) -> dict | None:
        now = _now()
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM worker_queue_runs WHERE id = ?", (queue_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE worker_queue_runs
                SET status = 'FAILED', finished_at = ?, heartbeat_at = ?, error = ?
                WHERE id = ?
                """,
                (now, now, _worker_queue_error_excerpt(error), queue_id),
            )
            updated = conn.execute("SELECT * FROM worker_queue_runs WHERE id = ?", (queue_id,)).fetchone()
        return _worker_queue_claim_from_row(updated)

    def worker_queue_snapshot(self, limit: int = 20) -> dict:
        with self.lock, closing(self._connect()) as conn:
            queued_count = conn.execute(
                "SELECT COUNT(*) AS count FROM worker_queue_runs WHERE status = 'QUEUED'"
            ).fetchone()["count"]
            running = conn.execute(
                """
                SELECT * FROM worker_queue_runs
                WHERE status = 'RUNNING'
                ORDER BY started_at ASC, requested_at ASC
                LIMIT 1
                """
            ).fetchone()
            pending_rows = conn.execute(
                """
                SELECT * FROM worker_queue_runs
                WHERE status = 'QUEUED'
                ORDER BY requested_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            completed_rows = conn.execute(
                """
                SELECT * FROM worker_queue_runs
                WHERE status = 'COMPLETED'
                ORDER BY finished_at DESC, requested_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            failed_rows = conn.execute(
                """
                SELECT * FROM worker_queue_runs
                WHERE status = 'FAILED'
                ORDER BY finished_at DESC, requested_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {
            "mode": "sqlite",
            "queue_depth": queued_count,
            "running": running["investigation_id"] if running is not None else None,
            "pending": [_worker_queue_pending_from_row(row) for row in pending_rows],
            "recent_runs": [_worker_queue_run_from_row(row) for row in completed_rows],
            "recent_errors": [_worker_queue_error_from_row(row) for row in failed_rows],
        }

    def _worker_queue_response(
        self,
        conn: sqlite3.Connection,
        accepted: bool,
        status: str,
        investigation_id: str,
        max_jobs: int | None,
    ) -> dict:
        queued_count = conn.execute(
            "SELECT COUNT(*) AS count FROM worker_queue_runs WHERE status = 'QUEUED'"
        ).fetchone()["count"]
        running = conn.execute(
            """
            SELECT investigation_id FROM worker_queue_runs
            WHERE status = 'RUNNING'
            ORDER BY started_at ASC, requested_at ASC
            LIMIT 1
            """
        ).fetchone()
        return {
            "accepted": accepted,
            "mode": "background",
            "status": status,
            "investigation_id": investigation_id,
            "max_jobs": max_jobs,
            "queue_depth": queued_count,
            "running": running["investigation_id"] if running is not None else None,
        }

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
        recorded_skipped_routes = skipped_routes if respect_tool_health else []
        now = _now()
        metadata = metadata or {}
        if respect_tool_health:
            metadata = {**metadata, "respect_tool_health": True}
        if recorded_skipped_routes:
            metadata = {**metadata, "initial_skipped_routes": [asdict(route) for route in recorded_skipped_routes]}
        planning_blocked = bool(recorded_skipped_routes and not planned_jobs)
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
            if recorded_skipped_routes:
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
                        json.dumps({"skipped_routes": [asdict(route) for route in recorded_skipped_routes]}, ensure_ascii=False),
                        now,
                    ),
                )
        return investigation

    def register_agent(
        self,
        agent_name: str,
        agent_type: str,
        capabilities: list[str],
        role_tier: str,
    ) -> dict:
        validated_tier = validate_agent_role_tier(role_tier)
        agent_name, agent_type, capabilities = validate_agent_registration(
            agent_name, agent_type, capabilities
        )
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT * FROM agents
                WHERE agent_name = ?
                ORDER BY registered_at ASC, id ASC
                LIMIT 1
                """,
                (agent_name,),
            ).fetchone()
            token, token_hash = _allocate_agent_token(
                {
                    row["token_hash"]
                    for row in conn.execute(
                        "SELECT token_hash FROM agents WHERE token_hash IS NOT NULL"
                    ).fetchall()
                }
            )
            now = _now()
            agent_id = existing["id"] if existing is not None else str(uuid4())
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO agents (
                        id, agent_name, agent_type, capabilities_json, status,
                        registered_at, last_seen_at, role_tier, token_hash,
                        token_created_at, disabled_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        agent_id,
                        agent_name,
                        agent_type,
                        json.dumps(capabilities, ensure_ascii=False),
                        "ONLINE",
                        now,
                        now,
                        validated_tier,
                        token_hash,
                        now,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE agents
                    SET agent_type = ?, capabilities_json = ?, status = 'ONLINE',
                        last_seen_at = ?, role_tier = ?, token_hash = ?,
                        token_created_at = ?, disabled_at = NULL
                    WHERE id = ?
                    """,
                    (
                        agent_type,
                        json.dumps(capabilities, ensure_ascii=False),
                        now,
                        validated_tier,
                        token_hash,
                        now,
                        agent_id,
                    ),
                )
                conn.execute(
                    """
                    UPDATE agents
                    SET token_hash = NULL, disabled_at = COALESCE(disabled_at, ?)
                    WHERE agent_name = ? AND id != ?
                    """,
                    (now, agent_name, agent_id),
                )
            row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return AgentRegistration({**_agent_from_row(row), "agent_token": token})

    def heartbeat_agent(self, agent_id: str) -> dict | None:
        now = _now()
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if (
                row is None
                or row["disabled_at"] is not None
                or row["role_tier"] not in AGENT_ROLE_TIERS
            ):
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

    def resolve_agent_token(self, token: object) -> dict | None:
        if not isinstance(token, str) or not token:
            return None
        token_hash = hash_agent_token(token)
        with self.lock, closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT * FROM agents
                WHERE token_hash = ? AND disabled_at IS NULL AND role_tier IS NOT NULL
                LIMIT 2
                """,
                (token_hash,),
            ).fetchall()
        if len(rows) != 1 or rows[0]["role_tier"] not in AGENT_ROLE_TIERS:
            return None
        return _agent_from_row(rows[0])

    def rotate_agent_token(self, agent_id: str) -> dict | None:
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id, role_tier, disabled_at FROM agents WHERE id = ?",
                (agent_id,),
            ).fetchone()
            if (
                row is None
                or row["disabled_at"] is not None
                or row["role_tier"] not in AGENT_ROLE_TIERS
            ):
                return None
            token, token_hash = _allocate_agent_token(
                {
                    item["token_hash"]
                    for item in conn.execute(
                        "SELECT token_hash FROM agents WHERE token_hash IS NOT NULL"
                    ).fetchall()
                }
            )
            now = _now()
            conn.execute(
                "UPDATE agents SET token_hash = ?, token_created_at = ? WHERE id = ?",
                (token_hash, now, agent_id),
            )
        return AgentRegistration(
            {"agent_id": agent_id, "agent_token": token, "token_created_at": now}
        )

    def agent_has_investigation_access(
        self,
        agent_id: str,
        investigation_id: str,
        required_tier: str,
        job_id: str | None = None,
        action: str | None = None,
    ) -> bool:
        if required_tier not in AGENT_ROLE_TIERS:
            return False
        with self.lock, closing(self._connect()) as conn:
            return self._agent_has_investigation_access_conn(
                conn,
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action=action,
            )

    def _agent_has_investigation_access_conn(
        self,
        conn: sqlite3.Connection,
        agent_id: str,
        investigation_id: str,
        required_tier: str,
        job_id: str | None = None,
        action: str | None = None,
    ) -> bool:
        if required_tier not in AGENT_ROLE_TIERS:
            return False
        agent = conn.execute(
            "SELECT role_tier, disabled_at FROM agents WHERE id = ?",
            (agent_id,),
        ).fetchone()
        if (
            agent is None
            or agent["disabled_at"] is not None
            or agent["role_tier"] != required_tier
        ):
            return False
        investigation_claim = conn.execute(
            """
            SELECT 1 FROM investigations
            WHERE id = ? AND claimed_by_agent_id = ? AND status IN (?, ?)
            """,
            (
                investigation_id,
                agent_id,
                *_AGENT_ACCESS_INVESTIGATION_STATUSES,
            ),
        ).fetchone()
        if investigation_claim is not None:
            return True
        if not job_id or not action:
            return False
        job_claim = conn.execute(
            """
            SELECT jobs.* FROM jobs AS jobs
            JOIN investigations AS investigations
              ON investigations.id = jobs.investigation_id
            WHERE jobs.id = ?
              AND jobs.investigation_id = ?
              AND jobs.claimed_by_agent_id = ?
              AND jobs.status IN (?, ?)
              AND investigations.status IN (?, ?)
            LIMIT 1
            """,
            (
                job_id,
                investigation_id,
                agent_id,
                *_AGENT_ACCESS_JOB_STATUSES,
                *_AGENT_ACCESS_INVESTIGATION_STATUSES,
            ),
        ).fetchone()
        return bool(
            job_claim is not None
            and tier_for_role(job_claim["agent_role"]) == required_tier
            and agent_output_contract_allows(job_claim["output_contract"], action)
        )

    def agent_add_event(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        level: str,
        message: str,
        metadata: dict | None = None,
    ) -> dict | None:
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
            conn.execute("BEGIN IMMEDIATE")
            if not self._agent_has_investigation_access_conn(
                conn,
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="event",
            ):
                return None
            _sqlite_insert_event(conn, event)
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return asdict(event)

    def agent_add_entities(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        entities: list[dict],
    ) -> list[dict] | None:
        if required_tier != "reader":
            return None
        records = [
            Entity(
                id=str(uuid4()),
                investigation_id=investigation_id,
                type=item["type"],
                value=item["value"],
                source_tool=item.get("source_tool", "agent"),
                confidence=float(item.get("confidence", 0.0)),
                created_at=_now(),
            )
            for item in entities
        ]
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if not self._agent_has_investigation_access_conn(
                conn,
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="entities",
            ):
                return None
            for entity in records:
                _sqlite_upsert_entity(conn, entity)
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return [asdict(entity) for entity in records]

    def agent_add_evidence(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        entity_value: str,
        evidence_kind: str,
        source_tool: str,
        snippet: str,
    ) -> dict | None:
        if required_tier != "reader":
            return None
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
            conn.execute("BEGIN IMMEDIATE")
            if not self._agent_has_investigation_access_conn(
                conn,
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="evidence",
            ):
                return None
            _sqlite_upsert_evidence(conn, evidence)
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return asdict(evidence)

    def agent_add_evidence_record(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        source_url: str,
        source_type: str,
        source_tool: str,
        snippet: str,
        credibility: float,
    ) -> dict | None:
        if required_tier != "reader":
            return None
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
            conn.execute("BEGIN IMMEDIATE")
            if not self._agent_has_investigation_access_conn(
                conn,
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="evidence_records",
            ):
                return None
            _sqlite_upsert_evidence_record(conn, record)
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return data

    def agent_add_fact(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        statement: str,
        subject: str,
        predicate: str,
        object_value: str,
        status: str,
        confidence: float,
        admiralty_code: str,
        evidence_ids: list[str],
    ) -> dict | None:
        if required_tier != "verifier":
            return None
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
            conn.execute("BEGIN IMMEDIATE")
            if not self._agent_has_investigation_access_conn(
                conn,
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="facts",
            ):
                return None
            existing = conn.execute(
                """
                SELECT * FROM facts
                WHERE investigation_id = ? AND subject = ? AND predicate = ? AND object_value = ?
                """,
                (investigation_id, subject, predicate, object_value),
            ).fetchone()
            if existing is not None:
                result = _merge_fact_dict(
                    _fact_from_row(existing), _fact_as_dict(fact)
                )
                conn.execute(
                    """
                    UPDATE facts
                    SET statement = ?, status = ?, promotion_stage = ?, confidence = ?,
                        admiralty_code = ?, evidence_ids_json = ?, observed_at = ?
                    WHERE id = ?
                    """,
                    (
                        result["statement"],
                        result["status"],
                        result["promotion_stage"],
                        result["confidence"],
                        result["admiralty_code"],
                        json.dumps(result["evidence_ids"], ensure_ascii=False),
                        result["observed_at"],
                        result["id"],
                    ),
                )
            else:
                result = _fact_as_dict(fact)
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
        return result

    def agent_add_hypothesis(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        hypothesis_id: str,
        statement: str,
        group: str = "default",
    ) -> dict | None:
        if required_tier != "verifier":
            return None
        now = _now()
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if not self._agent_has_investigation_access_conn(
                conn,
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="hypotheses",
            ):
                return None
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

    def agent_score_hypotheses(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        evidence_items: list[dict],
    ) -> dict | None:
        if required_tier != "verifier":
            return None
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if not self._agent_has_investigation_access_conn(
                conn,
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="score_hypotheses",
            ):
                return None
            return self._score_hypotheses_conn(conn, investigation_id, evidence_items)

    def agent_add_relationship(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        from_value: str,
        to_value: str,
        relationship_type: str,
        confidence: float,
    ) -> dict | None:
        if required_tier != "reader":
            return None
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
            conn.execute("BEGIN IMMEDIATE")
            if not self._agent_has_investigation_access_conn(
                conn,
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="relationships",
            ):
                return None
            _sqlite_upsert_relationship(conn, relationship)
            self._touch_investigation(conn, investigation_id, status="RUNNING")
        return asdict(relationship)

    def agent_complete_task(
        self,
        *,
        agent_id: str,
        required_tier: str,
        investigation_id: str,
        job_id: str | None,
        status: str,
        summary: str,
        report_markdown: str,
        confidence: float | None,
    ) -> dict | None:
        if required_tier != "reporter":
            return None
        preview = self.get_investigation(investigation_id)
        if preview is None:
            return None
        preview["summary"] = summary
        preview["report_markdown"] = report_markdown
        assessment = build_quality_assessment(preview)
        preview["quality_assessment"] = assessment
        _apply_gap_plans(preview)
        preview["completion_policy"] = build_completion_policy(preview)
        final_status = _policy_status_for_detail(preview, status)
        final_report = render_structured_report(preview, assessment)
        now = _now()
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            if not self._agent_has_investigation_access_conn(
                conn,
                agent_id,
                investigation_id,
                required_tier,
                job_id=job_id,
                action="complete_task",
            ):
                return None
            conn.execute(
                """
                UPDATE investigations
                SET status = ?, summary = ?, report_markdown = ?, confidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    final_status,
                    summary,
                    final_report,
                    confidence,
                    now,
                    investigation_id,
                ),
            )
            conn.execute(
                "UPDATE agents SET last_seen_at = ? WHERE id = ?", (now, agent_id)
            )
        return self.get_investigation(investigation_id)

    def claim_task(self, agent_id: str, capabilities: object) -> dict | None:
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            agent_row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if (
                agent_row is None
                or agent_row["disabled_at"] is not None
                or agent_row["role_tier"] not in {"reader", "verifier", "reporter"}
            ):
                return None
            agent = _agent_from_row(agent_row)
            capability_set = _narrow_agent_capabilities(
                agent["capabilities"], capabilities
            )
            rows = conn.execute(
                """
                SELECT * FROM investigations
                WHERE status = ? AND claimed_by_agent_id IS NULL
                ORDER BY created_at ASC
                """,
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
            updated = conn.execute(
                """
                UPDATE investigations
                SET status = ?, claimed_by_agent_id = ?, claimed_by_agent_name = ?, updated_at = ?
                WHERE id = ? AND status = ? AND claimed_by_agent_id IS NULL
                """,
                (
                    "CLAIMED",
                    agent_id,
                    agent["agent_name"],
                    now,
                    target["id"],
                    "OPEN",
                ),
            )
            if updated.rowcount != 1:
                return None
            conn.execute(
                "UPDATE agents SET last_seen_at = ? WHERE id = ?",
                (now, agent_id),
            )
        return self.get_investigation(target["id"])

    def claim_job(self, agent_id: str, capabilities: object) -> dict | None:
        with self.lock, closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            agent_row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
            if (
                agent_row is None
                or agent_row["disabled_at"] is not None
                or agent_row["role_tier"] not in AGENT_ROLE_TIERS
            ):
                return None
            agent = _agent_from_row(agent_row)
            capability_set = _narrow_agent_capabilities(
                agent["capabilities"], capabilities
            )
            rows = conn.execute(
                """
                SELECT jobs.* FROM jobs
                JOIN investigations ON investigations.id = jobs.investigation_id
                WHERE jobs.status IN (?, ?)
                  AND jobs.claimed_by_agent_id IS NULL
                  AND investigations.status IN (?, ?)
                ORDER BY jobs.rowid ASC
                """,
                (
                    "WAITING_AGENT",
                    "QUEUED",
                    *_AGENT_ACCESS_INVESTIGATION_STATUSES,
                ),
            ).fetchall()
            target = None
            for row in rows:
                if agent["role_tier"] == "tool_agent":
                    if row["agent_role"] != "tool_agent" or row["tool_name"] not in capability_set:
                        continue
                else:
                    if row["agent_role"] == "tool_agent":
                        continue
                    if tier_for_role(row["agent_role"]) != agent["role_tier"]:
                        continue
                    if row["agent_role"] not in capability_set and row["tool_name"] not in capability_set:
                        continue
                target = row
                break
            if target is None:
                return None
            now = _now()
            updated = conn.execute(
                """
                UPDATE jobs
                SET status = ?, claimed_by_agent_id = ?, claimed_by_agent_name = ?,
                    claimed_at = ?, heartbeat_at = ?
                WHERE id = ?
                  AND status IN (?, ?)
                  AND claimed_by_agent_id IS NULL
                  AND EXISTS (
                      SELECT 1 FROM investigations
                      WHERE investigations.id = jobs.investigation_id
                        AND investigations.status IN (?, ?)
                  )
                """,
                (
                    "CLAIMED",
                    agent_id,
                    agent["agent_name"],
                    now,
                    now,
                    target["id"],
                    "WAITING_AGENT",
                    "QUEUED",
                    *_AGENT_ACCESS_INVESTIGATION_STATUSES,
                ),
            )
            if updated.rowcount != 1:
                return None
            conn.execute("UPDATE agents SET last_seen_at = ? WHERE id = ?", (now, agent_id))
            self._touch_investigation(conn, target["investigation_id"], status="RUNNING")
            updated = conn.execute("SELECT * FROM jobs WHERE id = ?", (target["id"],)).fetchone()
        return _job_from_row(updated)

    def get_claimed_agent_job(
        self,
        agent_id: str,
        investigation_id: str,
        job_id: str,
        required_tier: str,
        *,
        require_tool_role: bool = False,
    ) -> dict | None:
        with self.lock, closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT jobs.*, agents.role_tier, agents.disabled_at,
                       investigations.status AS investigation_status
                FROM jobs
                JOIN agents ON agents.id = jobs.claimed_by_agent_id
                JOIN investigations ON investigations.id = jobs.investigation_id
                WHERE jobs.id = ?
                  AND jobs.investigation_id = ?
                  AND jobs.claimed_by_agent_id = ?
                """,
                (job_id, investigation_id, agent_id),
            ).fetchone()
        if (
            row is None
            or row["disabled_at"] is not None
            or row["role_tier"] != required_tier
            or row["status"] not in _AGENT_ACCESS_JOB_STATUSES
            or row["investigation_status"] not in _AGENT_ACCESS_INVESTIGATION_STATUSES
            or (require_tool_role and row["agent_role"] != "tool_agent")
        ):
            return None
        return _job_from_row(row)

    def submit_tool_job_output(
        self,
        agent_id: str,
        investigation_id: str,
        job_id: str,
        payload: dict,
    ) -> dict | None:
        with self.lock, closing(self._connect()) as conn, conn:
            row = conn.execute(
                """
                SELECT jobs.*, agents.role_tier, agents.disabled_at,
                       investigations.status AS investigation_status
                FROM jobs
                JOIN agents ON agents.id = jobs.claimed_by_agent_id
                JOIN investigations ON investigations.id = jobs.investigation_id
                WHERE jobs.id = ?
                  AND jobs.investigation_id = ?
                  AND jobs.claimed_by_agent_id = ?
                """,
                (job_id, investigation_id, agent_id),
            ).fetchone()
            if (
                row is None
                or row["disabled_at"] is not None
                or row["role_tier"] != "tool_agent"
                or row["investigation_status"]
                not in _AGENT_ACCESS_INVESTIGATION_STATUSES
                or row["status"] not in _AGENT_ACCESS_JOB_STATUSES
                or row["agent_role"] != "tool_agent"
            ):
                return None
            errors = validate_tool_output_payload(
                payload,
                agent_output_contract_sections(row["output_contract"]),
                row["tool_name"],
            )
            if errors:
                raise ToolOutputValidationError(errors)

            event, entities, evidence, relationships = _build_tool_output_records(
                investigation_id, agent_id, payload
            )
            completed = conn.execute(
                """
                UPDATE jobs
                SET status = 'COMPLETED'
                WHERE id = ?
                  AND investigation_id = ?
                  AND claimed_by_agent_id = ?
                  AND status IN (?, ?)
                  AND agent_role = 'tool_agent'
                  AND tool_name = ?
                  AND output_contract = ?
                  AND EXISTS (
                      SELECT 1 FROM investigations
                      WHERE investigations.id = jobs.investigation_id
                        AND investigations.status IN (?, ?)
                  )
                  AND EXISTS (
                      SELECT 1 FROM agents
                      WHERE agents.id = jobs.claimed_by_agent_id
                        AND agents.role_tier = 'tool_agent'
                        AND agents.disabled_at IS NULL
                  )
                """,
                (
                    job_id,
                    investigation_id,
                    agent_id,
                    *_AGENT_ACCESS_JOB_STATUSES,
                    row["tool_name"],
                    row["output_contract"],
                    *_AGENT_ACCESS_INVESTIGATION_STATUSES,
                ),
            )
            if completed.rowcount != 1:
                return None
            created = _insert_tool_output_records(
                conn, event, entities, evidence, relationships
            )
            self._touch_investigation(conn, investigation_id, status="RUNNING")
            return _tool_output_result(job_id, created)

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
            _sqlite_insert_event(conn, event)
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
            _sqlite_upsert_entity(conn, entity)
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
            _sqlite_upsert_evidence(conn, evidence)
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
            _sqlite_upsert_evidence_record(conn, record)
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
            return self._score_hypotheses_conn(conn, investigation_id, evidence_items)

    def _score_hypotheses_conn(
        self,
        conn: sqlite3.Connection,
        investigation_id: str,
        evidence_items: list[dict],
    ) -> dict:
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
            _sqlite_upsert_relationship(conn, relationship)
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
        detail["quality_assessment"] = assessment
        _apply_gap_plans(detail)
        detail["completion_policy"] = build_completion_policy(detail)
        final_status = _policy_status_for_detail(detail, status)
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
        _apply_gap_plans(data)
        data["completion_policy"] = build_completion_policy(data)
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
                INSERT INTO agents (
                    id, agent_name, agent_type, capabilities_json, status,
                    registered_at, last_seen_at, role_tier, token_created_at, disabled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    agent_name = excluded.agent_name,
                    agent_type = excluded.agent_type,
                    capabilities_json = excluded.capabilities_json,
                    status = excluded.status,
                    registered_at = excluded.registered_at,
                    last_seen_at = excluded.last_seen_at,
                    role_tier = COALESCE(excluded.role_tier, agents.role_tier),
                    token_created_at = COALESCE(excluded.token_created_at, agents.token_created_at),
                    disabled_at = COALESCE(excluded.disabled_at, agents.disabled_at)
                """,
                (
                    agent["id"],
                    agent["agent_name"],
                    agent["agent_type"],
                    json.dumps(agent.get("capabilities", []), ensure_ascii=False),
                    agent.get("status", "ONLINE"),
                    agent.get("registered_at", _now()),
                    agent.get("last_seen_at", _now()),
                    agent.get("role_tier"),
                    agent.get("token_created_at"),
                    agent.get("disabled_at"),
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
                    last_seen_at TEXT NOT NULL,
                    role_tier TEXT,
                    token_hash TEXT,
                    token_created_at TEXT,
                    disabled_at TEXT
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

                CREATE TABLE IF NOT EXISTS worker_queue_runs (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    max_jobs INTEGER,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    worker_id TEXT NOT NULL DEFAULT '',
                    heartbeat_at TEXT,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
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
                CREATE INDEX IF NOT EXISTS idx_worker_queue_status_requested
                    ON worker_queue_runs(status, requested_at);
                CREATE INDEX IF NOT EXISTS idx_worker_queue_investigation_status
                    ON worker_queue_runs(investigation_id, status);
                """
            )
            conn.execute("BEGIN IMMEDIATE")
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
            agent_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(agents)").fetchall()
            }
            if "role_tier" not in agent_columns:
                conn.execute("ALTER TABLE agents ADD COLUMN role_tier TEXT")
            if "token_hash" not in agent_columns:
                conn.execute("ALTER TABLE agents ADD COLUMN token_hash TEXT")
            if "token_created_at" not in agent_columns:
                conn.execute("ALTER TABLE agents ADD COLUMN token_created_at TEXT")
            if "disabled_at" not in agent_columns:
                conn.execute("ALTER TABLE agents ADD COLUMN disabled_at TEXT")
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
            _record_schema_migration(conn, "20260706_persistent_background_queue")
            _dedupe_agent_token_hashes(conn)
            _dedupe_existing_rows(conn)
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_unique_signal
                    ON entities(investigation_id, type, value, source_tool)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_unique_signal
                    ON evidence(investigation_id, entity_value, evidence_kind, source_tool)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_relationships_unique_signal
                    ON relationships(investigation_id, from_value, to_value, relationship_type)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_ledger_unique_hash
                    ON evidence_ledger(investigation_id, content_hash)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_unique_claim
                    ON facts(investigation_id, subject, predicate, object_value)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_unique_token_hash
                    ON agents(token_hash) WHERE token_hash IS NOT NULL
                """
            )
            _record_schema_migration(conn, "20260710_agent_credentials")

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


def _apply_gap_plans(data: dict) -> None:
    gap_analysis = build_gap_analysis(data)
    gap_tool_plan = build_gap_tool_plan(data)
    data["gap_analysis"] = gap_analysis
    data["gap_tool_plan"] = gap_tool_plan
    data["gap_followup_summary"] = build_gap_followup_summary(gap_tool_plan, gap_analysis)


def _policy_status_for_detail(detail: dict, requested_status: str) -> str:
    if requested_status in {"FAILED", "PARTIAL_FAILED", "CANCELLED", "ARCHIVED"}:
        return requested_status
    policy = detail.get("completion_policy") or build_completion_policy(detail)
    if requested_status == "COMPLETED":
        return str(policy.get("recommended_status") or completion_status_for_detail(detail, requested_status))
    if requested_status == "BLOCKED" and policy.get("completion_mode") == "blocked_by_environment":
        return str(policy.get("recommended_status") or "BLOCKED")
    return completion_status_for_detail(detail, requested_status)


def _dedupe_existing_rows(conn: sqlite3.Connection) -> None:
    statements = (
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
        )
        """,
        """
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
        )
        """,
        """
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
        )
        """,
        """
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
        )
        """,
        """
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
        )
        """,
    )
    for statement in statements:
        conn.execute(statement)


def _record_schema_migration(conn: sqlite3.Connection, version: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (version, _now()),
    )


def _dedupe_agent_token_hashes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE agents
        SET token_hash = NULL, token_created_at = NULL
        WHERE token_hash IN (
            SELECT token_hash FROM agents
            WHERE token_hash IS NOT NULL
            GROUP BY token_hash HAVING COUNT(*) > 1
        )
        """
    )


def _worker_queue_pending_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "max_jobs": row["max_jobs"],
        "status": row["status"],
        "requested_at": row["requested_at"],
    }


def _worker_queue_claim_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "max_jobs": row["max_jobs"],
        "status": row["status"],
        "requested_at": row["requested_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "worker_id": row["worker_id"],
        "heartbeat_at": row["heartbeat_at"],
        "summary": json.loads(row["summary_json"] or "{}"),
        "error": row["error"],
    }


def _worker_queue_run_from_row(row: sqlite3.Row) -> dict:
    summary = json.loads(row["summary_json"] or "{}")
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "max_jobs": row["max_jobs"],
        "requested_at": row["requested_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "started": int(summary.get("started") or 0),
        "completed": int(summary.get("completed") or 0),
        "failed": int(summary.get("failed") or 0),
        "blocked": int(summary.get("blocked") or 0),
        "queued_followups": int(summary.get("queued_followups") or 0),
    }


def _worker_queue_error_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "investigation_id": row["investigation_id"],
        "max_jobs": row["max_jobs"],
        "requested_at": row["requested_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error": row["error"],
    }


def _worker_queue_summary(summary: dict) -> dict:
    return {
        "started": int(summary.get("started") or 0),
        "completed": int(summary.get("completed") or 0),
        "failed": int(summary.get("failed") or 0),
        "blocked": int(summary.get("blocked") or 0),
        "queued_followups": int(summary.get("queued_followups") or 0),
    }


def _worker_queue_error_excerpt(value: str, limit: int = 500) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[truncated]"


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


def _sqlite_insert_event(conn: sqlite3.Connection, event: AgentEvent) -> None:
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


def _sqlite_upsert_entity(conn: sqlite3.Connection, entity: Entity) -> None:
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


def _sqlite_upsert_evidence(conn: sqlite3.Connection, evidence: Evidence) -> None:
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


def _sqlite_upsert_evidence_record(conn: sqlite3.Connection, record) -> None:
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


def _sqlite_upsert_relationship(
    conn: sqlite3.Connection, relationship: Relationship
) -> None:
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


def _build_tool_output_records(
    investigation_id: str,
    agent_id: str,
    payload: dict,
) -> tuple[
    AgentEvent | None,
    list[Entity],
    list[Evidence],
    list[Relationship],
]:
    now = _now()
    event_payload = payload.get("event")
    event = (
        AgentEvent(
            id=str(uuid4()),
            investigation_id=investigation_id,
            agent_id=agent_id,
            level=event_payload.get("level", "info"),
            message=event_payload["message"],
            metadata=event_payload.get("metadata", {}),
            created_at=now,
        )
        if event_payload is not None
        else None
    )
    entities = [
        Entity(
            id=str(uuid4()),
            investigation_id=investigation_id,
            type=item["type"],
            value=item["value"],
            source_tool=item["source_tool"],
            confidence=float(item["confidence"]),
            created_at=now,
        )
        for item in payload.get("entities", [])
    ]
    evidence = [
        Evidence(
            id=str(uuid4()),
            investigation_id=investigation_id,
            entity_value=item["entity_value"],
            evidence_kind=item["evidence_kind"],
            source_tool=item["source_tool"],
            snippet=item["snippet"],
            created_at=now,
        )
        for item in payload.get("evidence", [])
    ]
    relationships = [
        Relationship(
            id=str(uuid4()),
            investigation_id=investigation_id,
            from_value=item["from"],
            to_value=item["to"],
            relationship_type=item["relationship_type"],
            confidence=float(item["confidence"]),
            created_at=now,
        )
        for item in payload.get("relationships", [])
    ]
    entities, evidence, relationships = _coalesce_tool_output_records(
        entities, evidence, relationships
    )
    return event, entities, evidence, relationships


def _entity_signal_key(entity: Entity) -> tuple[str, str, str, str]:
    return (
        entity.investigation_id,
        entity.type,
        entity.value,
        entity.source_tool,
    )


def _evidence_signal_key(evidence: Evidence) -> tuple[str, str, str, str]:
    return (
        evidence.investigation_id,
        evidence.entity_value,
        evidence.evidence_kind,
        evidence.source_tool,
    )


def _relationship_signal_key(
    relationship: Relationship,
) -> tuple[str, str, str, str]:
    return (
        relationship.investigation_id,
        relationship.from_value,
        relationship.to_value,
        relationship.relationship_type,
    )


def _coalesce_tool_output_records(
    entities: list[Entity],
    evidence: list[Evidence],
    relationships: list[Relationship],
) -> tuple[list[Entity], list[Evidence], list[Relationship]]:
    entity_by_key: dict[tuple[str, str, str, str], Entity] = {}
    for entity in entities:
        existing = entity_by_key.get(_entity_signal_key(entity))
        if existing is None:
            entity_by_key[_entity_signal_key(entity)] = entity
        else:
            existing.confidence = max(existing.confidence, entity.confidence)

    evidence_by_key: dict[tuple[str, str, str, str], Evidence] = {}
    for item in evidence:
        existing = evidence_by_key.get(_evidence_signal_key(item))
        if existing is None:
            evidence_by_key[_evidence_signal_key(item)] = item
        else:
            existing.snippet = item.snippet
            existing.created_at = item.created_at

    relationship_by_key: dict[tuple[str, str, str, str], Relationship] = {}
    for relationship in relationships:
        existing = relationship_by_key.get(_relationship_signal_key(relationship))
        if existing is None:
            relationship_by_key[_relationship_signal_key(relationship)] = relationship
        else:
            existing.confidence = max(
                existing.confidence, relationship.confidence
            )

    return (
        list(entity_by_key.values()),
        list(evidence_by_key.values()),
        list(relationship_by_key.values()),
    )


def _insert_tool_output_records(
    conn: sqlite3.Connection,
    event: AgentEvent | None,
    entities: list[Entity],
    evidence: list[Evidence],
    relationships: list[Relationship],
) -> dict[str, int]:
    created = {"entities": 0, "evidence": 0, "relationships": 0}
    if event is not None:
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
    for entity in entities:
        existing = conn.execute(
            """
            SELECT 1 FROM entities
            WHERE investigation_id = ? AND type = ? AND value = ? AND source_tool = ?
            """,
            _entity_signal_key(entity),
        ).fetchone()
        if existing is None:
            created["entities"] += 1
        conn.execute(
            """
            INSERT INTO entities (
                id, investigation_id, type, value, source_tool, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(investigation_id, type, value, source_tool) DO UPDATE SET
                confidence = MAX(confidence, excluded.confidence)
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
    for item in evidence:
        existing = conn.execute(
            """
            SELECT 1 FROM evidence
            WHERE investigation_id = ? AND entity_value = ?
              AND evidence_kind = ? AND source_tool = ?
            """,
            _evidence_signal_key(item),
        ).fetchone()
        if existing is None:
            created["evidence"] += 1
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
                item.id,
                item.investigation_id,
                item.entity_value,
                item.evidence_kind,
                item.source_tool,
                item.snippet,
                item.created_at,
            ),
        )
    for relationship in relationships:
        existing = conn.execute(
            """
            SELECT 1 FROM relationships
            WHERE investigation_id = ? AND from_value = ?
              AND to_value = ? AND relationship_type = ?
            """,
            _relationship_signal_key(relationship),
        ).fetchone()
        if existing is None:
            created["relationships"] += 1
        conn.execute(
            """
            INSERT INTO relationships (
                id, investigation_id, from_value, to_value, relationship_type, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(investigation_id, from_value, to_value, relationship_type) DO UPDATE SET
                confidence = MAX(confidence, excluded.confidence)
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
    return created


def _tool_output_result(
    job_id: str,
    created: dict[str, int],
) -> dict:
    return {
        "job_id": job_id,
        "status": "COMPLETED",
        "created": created,
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _narrow_agent_capabilities(
    registered_capabilities: list[str], requested_capabilities: object
) -> set[str]:
    registered = set(registered_capabilities)
    if not isinstance(requested_capabilities, list) or not requested_capabilities:
        return registered
    return registered.intersection(
        item for item in requested_capabilities if isinstance(item, str)
    )


def _allocate_agent_token(existing_hashes: set[str]) -> tuple[str, str]:
    for _ in range(_AGENT_TOKEN_GENERATION_ATTEMPTS):
        token = generate_agent_token()
        token_hash = hash_agent_token(token)
        if token_hash not in existing_hashes:
            return token, token_hash
    raise RuntimeError("unable to generate unique agent credential")


def _public_agent(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "agent_name": agent.agent_name,
        "agent_type": agent.agent_type,
        "capabilities": list(agent.capabilities),
        "status": agent.status,
        "registered_at": agent.registered_at,
        "last_seen_at": agent.last_seen_at,
        "role_tier": agent.role_tier,
        "token_created_at": agent.token_created_at,
        "disabled_at": agent.disabled_at,
    }


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
        "role_tier": row["role_tier"],
        "token_created_at": row["token_created_at"],
        "disabled_at": row["disabled_at"],
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
