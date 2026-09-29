from __future__ import annotations

from typing import Any

from app.core.fact_pool import FACT_STATUSES


SOURCE_TYPES = {
    "official_website",
    "government_registry",
    "regulatory_filing",
    "original_social_profile",
    "mainstream_media",
    "industry_association",
    "business_directory",
    "job_board",
    "map_listing",
    "search_result",
    "aggregator",
    "tool_output",
    "single_weak_signal",
    "anonymous_forum",
    "unknown",
}


def validate_agent_payload(kind: str, payload: dict[str, Any]) -> list[str]:
    validators = {
        "entities": _validate_entities,
        "evidence": _validate_evidence,
        "evidence_records": _validate_evidence_record,
        "facts": _validate_fact,
        "relationships": _validate_relationship,
    }
    validator = validators.get(kind)
    if validator is None:
        return [f"unknown payload kind: {kind}"]
    return validator(payload)


def _validate_entities(payload: dict[str, Any]) -> list[str]:
    errors = []
    errors.extend(_require_strings(payload, ["task_id"]))
    entities = payload.get("entities")
    if not isinstance(entities, list) or not entities:
        errors.append("entities must be a non-empty list")
        return errors
    for index, item in enumerate(entities):
        prefix = f"entities[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        errors.extend(_require_strings(item, ["type", "value", "source_tool"], prefix=prefix))
        errors.extend(_number_between(item, "confidence", prefix=prefix))
    return errors


def _validate_evidence(payload: dict[str, Any]) -> list[str]:
    return _require_strings(payload, ["task_id", "entity_value", "evidence_kind", "source_tool", "snippet"])


def _validate_evidence_record(payload: dict[str, Any]) -> list[str]:
    errors = _require_strings(payload, ["task_id", "source_url", "source_type", "source_tool", "snippet"])
    source_type = payload.get("source_type")
    if isinstance(source_type, str) and source_type.strip() and source_type not in SOURCE_TYPES:
        errors.append("source_type is invalid")
    errors.extend(_number_between(payload, "credibility"))
    return errors


def _validate_fact(payload: dict[str, Any]) -> list[str]:
    errors = _require_strings(payload, ["task_id", "statement", "subject", "predicate", "object", "status"])
    status = payload.get("status")
    if isinstance(status, str) and status.strip() and status not in FACT_STATUSES:
        errors.append("status is invalid")
    errors.extend(_number_between(payload, "confidence"))
    if status in {"CONFIRMED", "LIKELY"}:
        if not str(payload.get("admiralty_code") or "").strip():
            errors.append("admiralty_code is required for confirmed or likely facts")
        evidence_ids = payload.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            errors.append("evidence_ids is required for confirmed or likely facts")
    return errors


def _validate_relationship(payload: dict[str, Any]) -> list[str]:
    errors = _require_strings(payload, ["task_id", "from", "to", "relationship_type"])
    errors.extend(_number_between(payload, "confidence"))
    return errors


def _require_strings(payload: dict[str, Any], fields: list[str], prefix: str = "") -> list[str]:
    errors = []
    for field in fields:
        value = payload.get(field)
        label = f"{prefix}.{field}" if prefix else field
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label} is required")
    return errors


def _number_between(payload: dict[str, Any], field: str, prefix: str = "") -> list[str]:
    label = f"{prefix}.{field}" if prefix else field
    try:
        value = float(payload[field])
    except (KeyError, TypeError, ValueError):
        return [f"{label} must be a number"]
    if not 0 <= value <= 1:
        return [f"{label} must be between 0 and 1"]
    return []
