from __future__ import annotations

import os
import re
import time
from pathlib import Path
from shutil import which

from app.core.completion_policy import build_completion_policy
from app.core.gap_followups import (
    build_gap_analysis,
    build_gap_followup_summary,
    build_gap_tool_plan,
    plan_gap_followup_jobs,
)
from app.core.intelligence_memory import build_intelligence_memory
from app.core.inference import plan_progressive_jobs
from app.core.planner import StrategyProfile
from app.core.quality import build_quality_assessment, completion_status_for_detail, render_structured_report
from app.core.registry import default_tool_registry
from app.core.social_risk import build_social_risk_report
from app.core.tool_health import build_tool_health_report
from app.services.role_agents import can_run_locally, run_role_agent
from app.tools import get_adapter
from app.tools.base import ParsedToolOutput, run_tool_command


SOCIAL_ENTITY_TYPES = {
    "profile_url",
    "social_profile",
    "platform_account",
    "bio_snippet",
    "declared_location",
    "interest_tag",
    "risk_signal",
}

DEPENDENCY_ALIASES = {
    "enterprise_intel": {"company_osint", "candidate_business_discovery"},
    "social_intel": {"social_profile_search"},
    "contact_discovery": {"contact_discovery"},
    "supply_chain": {"supply_chain_mapping"},
    "purchase_intent": {"purchase_intent_assessment", "rfq_category_analysis"},
    "news_intel": {"company_news_monitoring"},
}

DEPENDENCY_READY_STATUSES = {"COMPLETED", "PARTIAL_FAILED", "FAILED", "BLOCKED"}
HEAVY_ENRICHMENT_TOOLS = {"amass", "spiderfoot", "reconng", "ghunt"}
FOLLOWUP_CONFIDENCE_THRESHOLD = 0.7
HTTP_PROBED_URL_FOLLOWUP_THRESHOLD = 0.6
OFFICIAL_SITE_SEARCH_URL_FOLLOWUP_THRESHOLD = 0.58
PRE_ANALYSIS_FOLLOWUP_LIMIT = 1
EVENT_OUTPUT_LIMIT = 4000


def run_investigation_jobs(
    store,
    investigation_id: str,
    max_jobs: int | None = None,
    artifact_root: Path | None = None,
    adapter_factory=get_adapter,
    max_wall_seconds: int | None = None,
) -> dict:
    detail = store.get_investigation(investigation_id)
    if detail is None:
        raise ValueError(f"investigation not found: {investigation_id}")

    artifact_root = artifact_root or Path("data/jobs")
    strategy = _strategy_from_detail(detail)
    registry = default_tool_registry()
    budget = max_jobs or detail.get("max_jobs", strategy.max_jobs)
    wall_limit = max_wall_seconds or int(os.getenv("WORKER_MAX_WALL_SECONDS", "3600"))
    deadline = time.monotonic() + wall_limit
    summary = {
        "investigation_id": investigation_id,
        "started": 0,
        "completed": 0,
        "failed": 0,
        "blocked": 0,
        "skipped": 0,
        "queued_followups": 0,
        "queued_gap_followups": 0,
        "role_completed": 0,
        "busy": False,
        "risk_report": {},
        "completion_policy": {},
        "completion_mode": "",
        "gap_followup_summary": _empty_gap_followup_summary(),
    }

    if any(job.get("status") == "RUNNING" for job in detail.get("jobs", [])):
        summary["busy"] = True
        summary["quality_assessment"] = build_quality_assessment(detail)
        summary["completion_policy"] = build_completion_policy({**detail, "quality_assessment": summary["quality_assessment"]})
        summary["completion_mode"] = summary["completion_policy"]["completion_mode"]
        return summary

    if (
        detail.get("status") == "BLOCKED"
        and not detail.get("jobs")
        and (detail.get("metadata") or {}).get("initial_skipped_routes")
    ):
        summary["blocked"] = 1
        summary["quality_assessment"] = build_quality_assessment(detail)
        summary["completion_policy"] = build_completion_policy({**detail, "quality_assessment": summary["quality_assessment"]})
        summary["completion_mode"] = summary["completion_policy"]["completion_mode"]
        return summary

    if _has_completed_analysis_judgement(detail):
        gap_result = _queue_gap_followups(store, detail, strategy)
        created = gap_result["created"]
        summary["queued_followups"] += created
        summary["queued_gap_followups"] += created
        summary["gap_followup_summary"] = gap_result["gap_followup_summary"]
        if created:
            detail = store.get_investigation(investigation_id) or detail

    store.set_investigation_status(investigation_id, "RUNNING")
    processed_job_ids: set[str] = set()
    while summary["started"] < budget and time.monotonic() < deadline:
        detail = store.get_investigation_raw(investigation_id)
        queued_jobs = [
            job
            for job in detail["jobs"]
            if job["status"] == "QUEUED" and job["id"] not in processed_job_ids and _dependencies_satisfied(job, detail)
        ]
        if not queued_jobs:
            break
        job = sorted(queued_jobs, key=lambda item: _job_priority(item, detail))[0]
        processed_job_ids.add(job["id"])
        _run_single_job(
            store,
            detail,
            job,
            investigation_id,
            artifact_root,
            adapter_factory,
            strategy,
            registry,
            summary,
        )
        refreshed = store.get_investigation_raw(investigation_id)
        if refreshed and job.get("tool_name") == "analysis_judgement":
            gap_result = _queue_gap_followups(store, refreshed, strategy)
            created = gap_result["created"]
            summary["queued_followups"] += created
            summary["queued_gap_followups"] += created
            summary["gap_followup_summary"] = gap_result["gap_followup_summary"]

    detail = store.get_investigation(investigation_id)
    risk_report = _risk_report_for_detail(detail)
    store.save_risk_report(investigation_id, risk_report)
    detail = store.get_investigation(investigation_id)
    quality_assessment = build_quality_assessment(detail)
    policy_detail = {**detail, "quality_assessment": quality_assessment}
    completion_policy = build_completion_policy(policy_detail)
    requested_status = _final_status(detail, risk_report)
    final_status = _final_status_from_completion_policy(requested_status, risk_report, completion_policy)
    summary_text = _summary_text(risk_report, summary, quality_assessment)
    report_markdown = str(detail.get("report_markdown") or "")
    should_refresh_report = (
        _made_progress(summary)
        or _report_score_stale(report_markdown, quality_assessment)
        or (final_status == "NEEDS_REVIEW" and not report_markdown.strip())
    )
    if should_refresh_report:
        report_markdown = render_structured_report({**detail, "summary": summary_text, "completion_policy": completion_policy}, quality_assessment)
    if should_refresh_report and hasattr(store, "complete_task"):
        store.complete_task(
            investigation_id=investigation_id,
            agent_id="local-worker",
            status=final_status,
            summary=summary_text,
            report_markdown=report_markdown,
            confidence=_confidence_from_risk(risk_report),
        )
    else:
        store.set_investigation_status(
            investigation_id,
            final_status,
            summary=summary_text,
            confidence=_confidence_from_risk(risk_report),
        )
    summary["risk_report"] = risk_report
    summary["completion_policy"] = completion_policy
    summary["completion_mode"] = completion_policy["completion_mode"]
    summary["quality_assessment"] = quality_assessment
    return summary


def _made_progress(summary: dict) -> bool:
    return any(
        int(summary.get(key) or 0) > 0
        for key in ("started", "completed", "failed", "blocked", "skipped", "queued_followups", "role_completed")
    )


def _report_score_stale(report_markdown: str, quality_assessment: dict) -> bool:
    if not report_markdown.strip():
        return True
    expected = float(quality_assessment.get("score") or 0)
    match = re.search(r"完整度评分：([0-9]+(?:\.[0-9]+)?) / 100", report_markdown)
    if not match:
        return True
    return abs(float(match.group(1)) - expected) > 0.01


def _queue_gap_followups(store, detail: dict, strategy: StrategyProfile) -> dict:
    if not detail:
        return {"created": 0, "gap_followup_summary": _empty_gap_followup_summary()}
    planner_detail = dict(detail)
    if not planner_detail.get("intelligence_memory"):
        planner_detail["intelligence_memory"] = build_intelligence_memory(planner_detail)
    if not planner_detail.get("quality_assessment"):
        planner_detail["quality_assessment"] = build_quality_assessment(planner_detail)
    health_report = build_tool_health_report()
    health_by_name = {str(item.get("name") or ""): item for item in health_report.get("tools", [])}
    gap_analysis = build_gap_analysis(planner_detail)
    gap_tool_plan = build_gap_tool_plan(planner_detail, tool_health_by_name=health_by_name)
    gap_summary = build_gap_followup_summary(gap_tool_plan, gap_analysis)
    planned = plan_gap_followup_jobs(planner_detail, tool_health_by_name=health_by_name)
    remaining_jobs = max(0, detail.get("max_jobs", strategy.max_jobs) - len(detail.get("jobs", [])))
    created = store.add_jobs(detail["id"], planned[:remaining_jobs])
    blocked_tools = _blocked_gap_tools(gap_tool_plan)
    if created or blocked_tools or gap_summary["total_gaps"]:
        store.add_event(
            detail["id"],
            "worker",
            "info",
            "情报缺口补采计划已更新",
            {
                "queued_gap_followups": len(created),
                "gap_followup_summary": gap_summary,
                "blocked_tools": blocked_tools,
                "jobs": [
                    {
                        "tool_name": job["tool_name"],
                        "agent_role": job.get("agent_role"),
                        "target_type": job["target_type"],
                        "target_value": job["target_value"],
                        "depends_on": job.get("depends_on", ""),
                    }
                    for job in created
                ],
            },
        )
    return {"created": len(created), "gap_followup_summary": gap_summary}


def _empty_gap_followup_summary() -> dict:
    return {
        "total_gaps": 0,
        "blocking_gaps": 0,
        "ready": 0,
        "queued": 0,
        "already_attempted": 0,
        "blocked_by_config": 0,
        "exhausted": 0,
        "manual_review_required": 0,
    }


def _blocked_gap_tools(gap_tool_plan: list[dict]) -> list[dict]:
    blocked_statuses = {"missing_config", "missing_executable", "credential_blocked", "disabled"}
    return [
        {
            "gap_key": item["gap_key"],
            "tool_name": item["tool_name"],
            "status": item["status"],
            "reason": item.get("health_reason", ""),
        }
        for item in gap_tool_plan
        if item["status"] in blocked_statuses
    ]


def _has_completed_analysis_judgement(detail: dict) -> bool:
    return any(
        job.get("tool_name") == "analysis_judgement" and job.get("status") == "COMPLETED"
        for job in detail.get("jobs", [])
    )


def _run_single_job(
    store,
    detail: dict,
    job: dict,
    investigation_id: str,
    artifact_root: Path,
    adapter_factory,
    strategy: StrategyProfile,
    registry,
    summary: dict,
) -> None:
    if job.get("agent_role", "tool_agent") != "tool_agent":
        if can_run_locally(job):
            summary["started"] += 1
            parsed = _execute_role_job(store, detail, job, strategy, registry)
            if parsed:
                summary["role_completed"] += 1
                refreshed = store.get_investigation_raw(investigation_id)
                summary["queued_followups"] += _queue_role_followups(store, refreshed, parsed.high_confidence_entities, strategy, registry)
            else:
                summary["failed"] += 1
            return
        summary["skipped"] += 1
        message = f"等待职责 Agent 执行：{job['tool_name']}"
        if hasattr(store, "mark_job_waiting_agent"):
            store.mark_job_waiting_agent(job["id"])
        store.add_event(
            detail["id"],
            "worker",
            "info",
            message,
            {"job_id": job["id"], "agent_role": job.get("agent_role"), "output_contract": job.get("output_contract")},
        )
        return

    summary["started"] += 1
    parsed = _execute_job(store, detail, job, artifact_root, adapter_factory)
    if parsed is None:
        _record_unsuccessful_job(summary, store, investigation_id, job["id"])
        return
    summary["completed"] += 1
    _write_parsed_output(store, investigation_id, parsed)
    refreshed = store.get_investigation_raw(investigation_id) or detail
    followups = _plan_followups(refreshed, parsed, strategy, registry)
    created = store.add_jobs(investigation_id, followups)
    summary["queued_followups"] += len(created)
    if created:
        store.add_event(
            investigation_id,
            "worker",
            "info",
            "递进推演已规划下一步工具任务",
            {
                "source_tool": parsed.tool,
                "source_target_type": parsed.target_type,
                "source_target_value": parsed.target_value,
                "queued_followups": len(created),
                "jobs": [
                    {
                        "tool_name": job["tool_name"],
                        "target_type": job["target_type"],
                        "target_value": job["target_value"],
                        "depends_on": job.get("depends_on", ""),
                    }
                    for job in created
                ],
            },
        )


def _record_unsuccessful_job(summary: dict, store, investigation_id: str, job_id: str) -> None:
    detail = store.get_investigation_raw(investigation_id)
    status = ""
    if detail:
        status = next((job.get("status") for job in detail.get("jobs", []) if job.get("id") == job_id), "")
    if status == "BLOCKED":
        summary["blocked"] += 1
    else:
        summary["failed"] += 1


def _execute_role_job(store, detail: dict, job: dict, strategy: StrategyProfile, registry) -> object | None:
    if not store.claim_job_for_worker(job["id"]):
        return None
    try:
        result = run_role_agent(store, detail["id"], job)
        if not result.completed:
            store.update_job_status(job["id"], "FAILED")
            store.add_event(detail["id"], "local-role-agent", "warning", result.message, {"job_id": job["id"]})
            return None
        store.update_job_status(job["id"], "COMPLETED")
        store.add_event(
            detail["id"],
            "local-role-agent",
            "info",
            result.message,
            {"job_id": job["id"], "agent_role": job.get("agent_role"), "tool_name": job.get("tool_name")},
        )
        return result
    except Exception as exc:
        store.update_job_status(job["id"], "FAILED")
        store.add_event(detail["id"], "local-role-agent", "error", f"本地职责 Agent 失败：{job['tool_name']}", {"job_id": job["id"], "error": str(exc)})
        return None


def _queue_role_followups(store, detail: dict, entities: list[dict], strategy: StrategyProfile, registry) -> int:
    if not detail or not entities:
        return 0
    existing = {(job["tool_name"], job["target_type"], job["target_value"]) for job in detail.get("jobs", [])}
    planned = plan_progressive_jobs(
        entities=entities,
        relationships=detail.get("relationships", []),
        depth=0,
        strategy=strategy,
        registry=registry,
        already_planned=existing,
        respect_tool_health=_respect_tool_health_for_followups(detail),
    )
    planned = [job for job in planned if getattr(job, "agent_role", "tool_agent") == "tool_agent"]
    remaining_jobs = max(0, detail.get("max_jobs", strategy.max_jobs) - len(detail.get("jobs", [])))
    created = store.add_jobs(detail["id"], planned[:remaining_jobs])
    if created:
        store.add_event(
            detail["id"],
            "local-role-agent",
            "info",
            "高置信线索已派生下一轮工具任务",
            {
                "queued_followups": len(created),
                "jobs": [
                    {
                        "tool_name": job["tool_name"],
                        "target_type": job["target_type"],
                        "target_value": job["target_value"],
                        "depends_on": job.get("depends_on", ""),
                    }
                    for job in created
                ],
            },
        )
    return len(created)


def _execute_job(store, detail: dict, job: dict, artifact_root: Path, adapter_factory) -> ParsedToolOutput | None:
    if not store.claim_job_for_worker(job["id"]):
        return None
    try:
        adapter = adapter_factory(job["tool_name"])
    except Exception as exc:
        store.update_job_status(job["id"], "BLOCKED")
        store.add_event(
            detail["id"],
            "worker",
            "warning",
            f"工具不可用：{job['tool_name']}",
            {"job_id": job["id"], "error": str(exc)},
        )
        return None

    workdir = artifact_root / detail["id"] / job["id"]
    timeout = _default_timeout(job["tool_name"])
    try:
        if hasattr(adapter, "run"):
            run_kwargs = {
                "target_type": job["target_type"],
                "target_value": job["target_value"],
                "workdir": workdir,
                "timeout_seconds": timeout,
            }
            if job["tool_name"] == "lead_anchor_extraction":
                run_kwargs["metadata"] = detail.get("metadata", {})
            run_result = adapter.run(**run_kwargs)
        else:
            command = adapter.build_command(
                target_type=job["target_type"],
                target_value=job["target_value"],
                workdir=workdir,
                timeout_seconds=timeout,
            )
            if command.args and which(command.args[0]) is None:
                store.update_job_status(job["id"], "BLOCKED")
                store.add_event(
                    detail["id"],
                    "worker",
                    "warning",
                    f"缺少工具命令：{command.args[0]}",
                    {"job_id": job["id"], "tool": job["tool_name"], "command": command.to_dict()},
                )
                return None
            run_result = run_tool_command(command)
        parsed = adapter.parse_artifact(run_result.command.expected_artifact, target_value=job["target_value"])
        store.update_job_status(job["id"], "COMPLETED" if run_result.returncode == 0 else "PARTIAL_FAILED")
        store.add_event(
            detail["id"],
            "worker",
            "info",
            f"完成工具任务：{job['tool_name']}",
            {
                "job_id": job["id"],
                "tool_name": job["tool_name"],
                "returncode": run_result.returncode,
                "stdout_excerpt": _event_output_excerpt(run_result.stdout_excerpt),
                "stderr_excerpt": _event_output_excerpt(run_result.stderr_excerpt),
            },
        )
        return parsed
    except FileNotFoundError as exc:
        store.update_job_status(job["id"], "BLOCKED")
        store.add_event(detail["id"], "worker", "warning", f"工具命令不存在：{job['tool_name']}", {"job_id": job["id"], "error": str(exc)})
        return None
    except Exception as exc:
        store.update_job_status(job["id"], "FAILED")
        store.add_event(detail["id"], "worker", "error", f"工具任务失败：{job['tool_name']}", {"job_id": job["id"], "error": str(exc)})
        return None


def _event_output_excerpt(value: str) -> str:
    if len(value) <= EVENT_OUTPUT_LIMIT:
        return value
    return f"{value[:EVENT_OUTPUT_LIMIT]}\n...[truncated event output from {len(value)} chars]"


def _write_parsed_output(store, investigation_id: str, parsed: ParsedToolOutput) -> None:
    for item in parsed.entities:
        store.add_entity(investigation_id, item.type, item.value, item.source_tool, item.confidence)
    evidence_records_by_value: dict[str, list[dict]] = {}
    for item in parsed.evidence:
        store.add_evidence(
            investigation_id,
            item.entity_value,
            item.evidence_kind,
            item.source_tool,
            item.snippet,
        )
        record = store.add_evidence_record(
            investigation_id,
            _evidence_source_url(item),
            item.evidence_kind,
            item.source_tool,
            item.snippet,
            _evidence_credibility(item),
        )
        evidence_records_by_value.setdefault(item.entity_value, []).append(record)
    for item in parsed.relationships:
        store.add_relationship(
            investigation_id,
            item.from_value,
            item.to_value,
            item.relationship_type,
            item.confidence,
        )
    _write_source_backed_facts(store, investigation_id, parsed, evidence_records_by_value)


def _write_source_backed_facts(
    store,
    investigation_id: str,
    parsed: ParsedToolOutput,
    evidence_records_by_value: dict[str, list[dict]],
) -> None:
    if parsed.tool != "official_site_extractor":
        return
    for entity in parsed.entities:
        fact_shape = _official_site_fact_shape(parsed.target_value, entity.type, entity.value)
        if fact_shape is None:
            continue
        evidence_records = evidence_records_by_value.get(entity.value) or []
        if not evidence_records:
            continue
        record = evidence_records[0]
        store.add_fact(
            investigation_id=investigation_id,
            statement=fact_shape["statement"],
            subject=fact_shape["subject"],
            predicate=fact_shape["predicate"],
            object_value=fact_shape["object"],
            status="CONFIRMED" if entity.confidence >= 0.74 else "LIKELY",
            confidence=entity.confidence,
            admiralty_code=str(record.get("admiralty_code") or "A-3"),
            evidence_ids=[str(item.get("id")) for item in evidence_records if item.get("id")],
        )


def _official_site_fact_shape(source_url: str, entity_type: str, value: str) -> dict | None:
    predicates = {
        "organization": "has_company_identity",
        "email": "uses_contact_email",
        "phone": "uses_contact_phone",
        "address": "has_operation_location",
        "business_scope": "has_business_scope",
    }
    predicate = predicates.get(entity_type)
    if predicate is None:
        return None
    return {
        "subject": source_url,
        "predicate": predicate,
        "object": value,
        "statement": f"Official site {source_url} supports {predicate}: {value}.",
    }


def _evidence_source_url(item) -> str:
    value = str(item.entity_value or "").strip()
    if value.startswith(("http://", "https://")):
        return value
    return f"hcs://tool-evidence/{item.source_tool}/{abs(hash((item.evidence_kind, value))) & 0xffffffff:x}"


def _evidence_credibility(item) -> float:
    kind = str(item.evidence_kind or "").lower()
    if "official" in kind or "contact" in kind:
        return 0.72
    if "news" in kind:
        return 0.62
    if "risk" in kind:
        return 0.58
    return 0.52


def _job_priority(job: dict, detail: dict) -> tuple[int, int, int, int, int, str]:
    tool_name = str(job.get("tool_name") or "")
    role = str(job.get("agent_role") or "tool_agent")
    target_type = str(job.get("target_type") or "")
    depth = int(job.get("depth") or 0)
    target_preference = _target_preference(target_type, tool_name)
    target_group_preference = _target_group_preference(job, detail)
    tool_preference = _tool_preference(tool_name, target_type)
    has_completed_collection = any(
        item.get("status") == "COMPLETED"
        and item.get("tool_name") not in {"cross_verification", "identity_match_review", "analysis_judgement"}
        for item in detail.get("jobs", [])
    )
    has_completed_cross = any(
        item.get("tool_name") in {"cross_verification", "identity_match_review"} and item.get("status") == "COMPLETED"
        for item in detail.get("jobs", [])
    )
    if role == "tool_agent":
        if tool_name == "lead_anchor_extraction":
            return (0, depth, target_preference, target_group_preference, tool_preference, tool_name)
        if tool_name in HEAVY_ENRICHMENT_TOOLS:
            if _is_inferred_job(job):
                return (85, depth, target_preference, target_group_preference, tool_preference, tool_name)
            return ((18 if has_completed_cross else 60), depth, target_preference, target_group_preference, tool_preference, tool_name)
        if has_completed_cross and depth <= 1 and _pre_analysis_followups_completed(detail) < PRE_ANALYSIS_FOLLOWUP_LIMIT:
            return (18, depth, target_preference, target_group_preference, tool_preference, tool_name)
        return ((40 if has_completed_collection else 10), depth, target_preference, target_group_preference, tool_preference, tool_name)
    if tool_name in {"cross_verification", "identity_match_review"}:
        return ((15 if has_completed_collection else 70), depth, 0, 0, 0, tool_name)
    if tool_name == "analysis_judgement":
        return ((20 if has_completed_cross else 90), depth, 0, 0, 0, tool_name)
    return (30, depth, target_preference, target_group_preference, tool_preference, tool_name)


def _dependencies_satisfied(job: dict, detail: dict) -> bool:
    dependencies = _dependency_tokens(str(job.get("depends_on") or ""))
    if not dependencies:
        return True
    jobs = detail.get("jobs", [])
    for dependency in dependencies:
        if dependency.startswith("completed:"):
            tool_name = dependency.removeprefix("completed:")
            if not any(job.get("tool_name") == tool_name and job.get("status") == "COMPLETED" for job in jobs):
                return False
            continue
        matched = _jobs_matching_dependency(dependency, jobs)
        if matched and not any(item.get("status") in DEPENDENCY_READY_STATUSES for item in matched):
            return False
    return True


def _dependency_tokens(depends_on: str) -> list[str]:
    return [
        token.strip()
        for token in depends_on.replace(";", ",").split(",")
        if token.strip()
        and not token.strip().startswith("inferred_from:")
        and not token.strip().startswith("gap:")
    ]


def _jobs_matching_dependency(dependency: str, jobs: list[dict]) -> list[dict]:
    tool_names = DEPENDENCY_ALIASES.get(dependency, {dependency})
    return [job for job in jobs if job.get("tool_name") in tool_names]


def _pre_analysis_followups_completed(detail: dict) -> int:
    return sum(
        1
        for job in detail.get("jobs", [])
        if _is_inferred_job(job)
        and int(job.get("depth") or 0) <= 1
        and job.get("tool_name") not in HEAVY_ENRICHMENT_TOOLS
        and job.get("status") in DEPENDENCY_READY_STATUSES
    )


def _is_inferred_job(job: dict) -> bool:
    return "inferred_from:" in str(job.get("depends_on") or "")


def _target_preference(target_type: str, tool_name: str) -> int:
    if target_type == "url" and tool_name in {"httpx", "katana", "official_site_extractor"}:
        return 0
    if target_type == "profile_url":
        return 1
    if target_type in {"domain", "subdomain"}:
        return 5
    return 3


def _target_group_preference(job: dict, detail: dict) -> int:
    target_type = str(job.get("target_type") or "")
    tool_name = str(job.get("tool_name") or "")
    target_value = str(job.get("target_value") or "")
    if target_type != "url" or tool_name not in {"httpx", "katana", "official_site_extractor"}:
        return 0
    for index, candidate in enumerate(detail.get("jobs", [])):
        if (
            candidate.get("target_type") == "url"
            and candidate.get("target_value") == target_value
            and candidate.get("tool_name") in {"httpx", "katana", "official_site_extractor"}
        ):
            return index
    return 0


def _tool_preference(tool_name: str, target_type: str = "") -> int:
    if target_type == "url":
        url_order = {
            "httpx": 6,
            "katana": 7,
            "official_site_extractor": 8,
        }
        if tool_name in url_order:
            return url_order[tool_name]
    order = {
        "lead_anchor_extraction": 0,
        "official_site_search": 3,
        "company_news": 5,
        "theharvester": 10,
        "socialscan": 15,
        "profile_parser": 20,
        "phoneinfoga": 25,
        "sherlock": 30,
        "maigret": 40,
        "amass": 50,
        "spiderfoot": 60,
        "reconng": 70,
        "ghunt": 80,
    }
    return order.get(tool_name, 100)


def _plan_followups(detail: dict, parsed: ParsedToolOutput, strategy: StrategyProfile, registry) -> list:
    already_planned = {(job["tool_name"], job["target_type"], job["target_value"]) for job in detail["jobs"]}
    entity_dicts = [
        {"type": entity.type, "value": entity.value, "source_tool": entity.source_tool, "confidence": entity.confidence}
        for entity in parsed.entities
        if _eligible_followup_entity(entity, parsed)
        if not (entity.type == parsed.target_type and entity.value == parsed.target_value)
    ]
    planned = plan_progressive_jobs(
        entities=entity_dicts,
        relationships=[
            {
                "from_value": relationship.from_value,
                "to_value": relationship.to_value,
                "relationship_type": relationship.relationship_type,
                "confidence": relationship.confidence,
            }
            for relationship in parsed.relationships
        ],
        depth=parsed_target_depth(detail, parsed),
        strategy=strategy,
        registry=registry,
        already_planned=already_planned,
        respect_tool_health=_respect_tool_health_for_followups(detail),
    )
    remaining_jobs = max(0, detail.get("max_jobs", strategy.max_jobs) - len(detail["jobs"]))
    return planned[:remaining_jobs]


def _respect_tool_health_for_followups(detail: dict) -> bool:
    metadata = detail.get("metadata") or {}
    return bool(metadata.get("respect_tool_health") or metadata.get("initial_skipped_routes"))


def _eligible_followup_entity(entity, parsed: ParsedToolOutput) -> bool:
    if entity.confidence >= FOLLOWUP_CONFIDENCE_THRESHOLD:
        return True
    return (
        entity.type == "url"
        and parsed.tool == "httpx"
        and entity.confidence >= HTTP_PROBED_URL_FOLLOWUP_THRESHOLD
    ) or (
        entity.type == "url"
        and parsed.tool == "official_site_search"
        and entity.confidence >= OFFICIAL_SITE_SEARCH_URL_FOLLOWUP_THRESHOLD
    )


def parsed_target_depth(detail: dict, parsed: ParsedToolOutput) -> int:
    for job in detail["jobs"]:
        if (
            job["target_type"] == parsed.target_type
            and job["target_value"] == parsed.target_value
            and job["tool_name"] == parsed.tool
        ):
            return job["depth"]
    return 0


def _risk_report_for_detail(detail: dict) -> dict:
    if not any(item.get("type") in SOCIAL_ENTITY_TYPES for item in detail.get("entities", [])):
        return {
            "overall_risk_score": 0,
            "overall_risk_level": "low",
            "category_scores": {},
            "review_required": False,
            "top_risk_signals": [],
            "public_profile_summary": {},
            "supporting_evidence": [],
        }
    return build_social_risk_report(
        entities=detail.get("entities", []),
        evidence=detail.get("evidence", []),
        relationships=detail.get("relationships", []),
    )


def _final_status(detail: dict, risk_report: dict) -> str:
    counts = detail.get("job_counts", {})
    useful = counts.get("COMPLETED", 0) + counts.get("PARTIAL_FAILED", 0)
    failed = counts.get("FAILED", 0)
    blocked = counts.get("BLOCKED", 0)
    if risk_report.get("review_required"):
        return "NEEDS_REVIEW"
    if useful and (failed or blocked):
        return "PARTIAL_FAILED"
    if useful:
        return "COMPLETED"
    if failed:
        return "FAILED"
    if blocked:
        return "BLOCKED"
    return "OPEN"


def _final_status_from_completion_policy(requested_status: str, risk_report: dict, completion_policy: dict) -> str:
    if risk_report.get("review_required"):
        return "NEEDS_REVIEW"
    if requested_status in {"FAILED", "PARTIAL_FAILED"}:
        return requested_status
    if requested_status == "BLOCKED" and completion_policy.get("completion_mode") != "blocked_by_environment":
        return "BLOCKED"
    recommended = str(completion_policy.get("recommended_status") or "")
    if recommended in {"COMPLETED", "NEEDS_REVIEW", "BLOCKED", "FAILED"}:
        return recommended
    return completion_status_for_detail({}, requested_status)


def _summary_text(risk_report: dict, summary: dict, quality_assessment: dict | None = None) -> str:
    if risk_report.get("review_required"):
        return f"已生成风险复核评分：{risk_report.get('overall_risk_score', 0)}"
    if summary["blocked"]:
        return "工具任务被环境依赖阻断"
    if quality_assessment and not quality_assessment.get("completion_ready"):
        return f"质量闸门未通过：完整度 {quality_assessment.get('score', 0)} / 100"
    if quality_assessment and quality_assessment.get("completion_ready"):
        return f"质量闸门已通过：完整度 {quality_assessment.get('score', 0)} / 100"
    if summary["completed"]:
        return f"已完成 {summary['completed']} 个工具任务"
    if summary["failed"]:
        return "工具任务未产生有效结果"
    return "没有可执行的队列任务"


def _confidence_from_risk(risk_report: dict) -> float | None:
    if not risk_report:
        return None
    score = risk_report.get("overall_risk_score")
    if score is None:
        return None
    return round(max(0, min(1, 1 - (score / 100))), 4)


def _strategy_from_detail(detail: dict) -> StrategyProfile:
    return StrategyProfile(
        name=detail["strategy"],
        max_depth=detail["max_depth"],
        max_jobs=detail["max_jobs"],
        max_entities=detail["max_entities"],
    )


def _default_timeout(tool_name: str) -> int:
    try:
        return default_tool_registry().get(tool_name).default_timeout_seconds
    except KeyError:
        return 60
