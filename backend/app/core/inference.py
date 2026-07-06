from __future__ import annotations

from urllib.parse import urlsplit

from app.core.normalization import NormalizationError, normalize_target
from app.core.planner import PlannedJob, StrategyProfile, plan_followup_jobs
from app.core.registry import ToolRegistry


HIGH_VALUE_URL_HINTS = (
    "about",
    "contact",
    "news",
    "press",
    "project",
    "blog",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
)


def plan_progressive_jobs(
    entities: list[dict],
    relationships: list[dict],
    depth: int,
    strategy: StrategyProfile,
    registry: ToolRegistry,
    already_planned: set[tuple[str, str, str]],
    runtime_env: dict[str, str] | None = None,
    respect_tool_health: bool = False,
) -> list[PlannedJob]:
    if depth >= strategy.max_depth:
        return []

    planned: list[PlannedJob] = []
    seen = set(already_planned)
    for entity in entities:
        for target_type, target_value in _candidate_targets(entity):
            try:
                followups = plan_followup_jobs(
                    target_type,
                    target_value,
                    depth=depth,
                    strategy=strategy,
                    registry=registry,
                    already_planned=seen,
                    runtime_env=runtime_env,
                    respect_tool_health=respect_tool_health,
                )
            except (NormalizationError, ValueError):
                continue
            for job in followups:
                if job.key in seen:
                    continue
                seen.add(job.key)
                planned.append(_with_inference_source(job, entity))
    return planned


def _candidate_targets(entity: dict) -> list[tuple[str, str]]:
    entity_type = str(entity.get("type") or entity.get("entity_type") or "")
    value = str(entity.get("value") or "")
    if not value:
        return []

    if entity_type == "external_link":
        targets = []
        if _looks_like_high_value_url(value):
            targets.append(("profile_url", value))
        domain = _domain_from_url(value)
        if domain:
            targets.append(("domain", domain))
        return targets

    if entity_type == "url":
        targets = [("url", value)]
        if _looks_like_high_value_url(value):
            targets.append(("profile_url", value))
        domain = _domain_from_url(value)
        if domain:
            targets.append(("domain", domain))
        return targets

    if entity_type == "news_article":
        return [("profile_url", value)] if value.startswith("http") else []

    if entity_type in {"organization", "company"}:
        return [("company", value)]

    if entity_type in {"email", "phone", "username", "profile_url", "domain", "subdomain"}:
        return [(entity_type, value)]

    return []


def _looks_like_high_value_url(value: str) -> bool:
    lowered = value.lower()
    return value.startswith(("http://", "https://")) and any(hint in lowered for hint in HIGH_VALUE_URL_HINTS)


def _domain_from_url(value: str) -> str:
    if not value.startswith(("http://", "https://")):
        return ""
    hostname = urlsplit(value).hostname or ""
    if not hostname:
        return ""
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def _with_inference_source(job: PlannedJob, entity: dict) -> PlannedJob:
    entity_type = str(entity.get("type") or entity.get("entity_type") or "unknown")
    entity_value = str(entity.get("value") or "")
    inferred_from = f"inferred_from:{entity_type}:{entity_value}"
    depends_on = inferred_from if not job.depends_on else f"{job.depends_on};{inferred_from}"
    return PlannedJob(
        tool_name=job.tool_name,
        target_type=job.target_type,
        target_value=job.target_value,
        depth=job.depth,
        agent_role=job.agent_role,
        output_contract=job.output_contract,
        depends_on=depends_on,
    )
