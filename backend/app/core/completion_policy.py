from __future__ import annotations

import re

from app.core.gap_followups import build_gap_analysis, build_gap_followup_summary, build_gap_tool_plan


SUPPORTED_VERIFICATION_STATUSES = {"CONFIRMED", "LIKELY", "SUPPORTED"}
NEGATIVE_FACT_STATUSES = {"REJECTED", "DISPROVEN", "CONTRADICTED", "CONFLICTED", "FALSE", "INVALID"}
BLOCKED_TOOL_STATUSES = {"missing_config", "missing_executable", "credential_blocked", "disabled"}
PROFILE_IDENTITY_TYPES = {"email", "username", "identity", "profile_url", "platform_account"}
CONTACT_CHANNEL_TYPES = {"email", "phone", "whatsapp"}
CONTACT_EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.IGNORECASE)
CONTACT_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{5,}\d)")
CONFLICT_VERIFICATION_STATUSES = {"CONFLICT", "CONFLICTED", "CONTRADICTED", "HIGH_RISK_CONFLICT"}
BUSINESS_SCOPE_FIELD_KEYS = {"business_scope", "product_scope", "purchase_category"}
GENERIC_BUSINESS_SCOPE_TERMS = {
    "business",
    "businesses",
    "category",
    "categories",
    "company",
    "companies",
    "product",
    "products",
    "scope",
    "service",
    "services",
}
NON_ACCEPTABLE_BLOCKERS = {
    "company_identity",
    "official_website",
    "evidence_ledger",
    "fact_pool",
    "cross_verification",
    "bluf_report",
    "risk_review",
    "contact_channel",
    "unresolved_contradiction",
}
BASE_ACCEPTABLE_LIMITATIONS = {"decision_maker", "purchase_intent", "contact_phone", "contact_email"}


def build_completion_policy(detail: dict) -> dict:
    assessment = _quality_assessment(detail)
    planner_detail = {**detail, "quality_assessment": assessment}
    gap_analysis = (
        list(detail["gap_analysis"])
        if "gap_analysis" in detail and detail["gap_analysis"] is not None
        else build_gap_analysis(planner_detail)
    )
    if "gap_tool_plan" in detail and detail["gap_tool_plan"] is not None:
        gap_tool_plan = list(detail["gap_tool_plan"])
    elif "gap_analysis" in detail:
        gap_tool_plan = (
            build_gap_tool_plan(_planner_detail_for_explicit_gaps(planner_detail, gap_analysis))
            if gap_analysis
            else []
        )
    else:
        gap_tool_plan = build_gap_tool_plan({**planner_detail, "gap_analysis": gap_analysis})
    gap_summary = (
        dict(detail["gap_followup_summary"])
        if "gap_followup_summary" in detail and detail["gap_followup_summary"] is not None
        else build_gap_followup_summary(gap_tool_plan, gap_analysis)
    )
    evidence_floor = _evidence_floor(detail)
    remaining_blockers = _remaining_blockers(assessment, gap_analysis, detail)
    strict_ready = (
        bool(assessment.get("completion_ready"))
        and all(evidence_floor.values())
        and not remaining_blockers
        and not _has_non_acceptable_blocker(remaining_blockers, detail)
    )
    ready_tools = int(gap_summary.get("ready") or 0) + int(gap_summary.get("queued") or 0)
    auto_exhausted = ready_tools == 0 and bool(gap_analysis or remaining_blockers)
    environment_blocked = _environment_blocked(gap_tool_plan, gap_summary)
    useful_evidence = _has_useful_evidence(detail)
    acceptable_limitations = _acceptable_limitations(detail, remaining_blockers, evidence_floor)
    limited_ready = (
        not strict_ready
        and not ready_tools
        and bool(remaining_blockers)
        and all(evidence_floor.values())
        and not _has_non_acceptable_blocker(remaining_blockers, detail)
        and set(remaining_blockers).issubset(set(acceptable_limitations))
    )

    if strict_ready:
        return _policy(
            recommended_status="COMPLETED",
            completion_mode="strict",
            strict_ready=True,
            limited_ready=False,
            auto_exhausted=False,
            manual_decision_required=False,
            environment_blocked=False,
            reason="Strict quality gate is satisfied.",
            remaining_blockers=[],
            acceptable_limitations=[],
            operator_next_actions=[],
            evidence_floor=evidence_floor,
        )

    if ready_tools:
        return _policy(
            recommended_status="NEEDS_REVIEW",
            completion_mode="continue_collection",
            strict_ready=False,
            limited_ready=False,
            auto_exhausted=False,
            manual_decision_required=False,
            environment_blocked=False,
            reason="Ready automatic follow-up tools remain available for unresolved evidence gaps.",
            remaining_blockers=remaining_blockers,
            acceptable_limitations=acceptable_limitations,
            operator_next_actions=["Run the ready gap follow-up jobs before deciding whether the task is complete."],
            evidence_floor=evidence_floor,
        )

    if limited_ready:
        return _policy(
            recommended_status="COMPLETED",
            completion_mode="limited",
            strict_ready=False,
            limited_ready=True,
            auto_exhausted=True,
            manual_decision_required=False,
            environment_blocked=False,
            reason=_limited_reason(remaining_blockers),
            remaining_blockers=remaining_blockers,
            acceptable_limitations=acceptable_limitations,
            operator_next_actions=_operator_actions(remaining_blockers),
            evidence_floor=evidence_floor,
        )

    if environment_blocked:
        return _policy(
            recommended_status="NEEDS_REVIEW" if useful_evidence else "BLOCKED",
            completion_mode="blocked_by_environment",
            strict_ready=False,
            limited_ready=False,
            auto_exhausted=True,
            manual_decision_required=True,
            environment_blocked=True,
            reason="Automatic collection is blocked by unavailable tools, configuration, credentials, or disabled routes.",
            remaining_blockers=remaining_blockers,
            acceptable_limitations=acceptable_limitations,
            operator_next_actions=_environment_actions(gap_tool_plan),
            evidence_floor=evidence_floor,
        )

    if _execution_failed_without_evidence(detail):
        return _policy(
            recommended_status="FAILED",
            completion_mode="failed",
            strict_ready=False,
            limited_ready=False,
            auto_exhausted=True,
            manual_decision_required=True,
            environment_blocked=False,
            reason="Execution failed without collecting useful evidence.",
            remaining_blockers=remaining_blockers,
            acceptable_limitations=acceptable_limitations,
            operator_next_actions=["Inspect failed job errors and rerun after the execution issue is fixed."],
            evidence_floor=evidence_floor,
        )

    return _policy(
        recommended_status="NEEDS_REVIEW",
        completion_mode="ready_for_human_decision",
        strict_ready=False,
        limited_ready=False,
        auto_exhausted=auto_exhausted,
        manual_decision_required=True,
        environment_blocked=False,
        reason="Automatic collection is exhausted, but required evidence is still insufficient for strict or limited completion.",
        remaining_blockers=remaining_blockers,
        acceptable_limitations=acceptable_limitations,
        operator_next_actions=_operator_actions(remaining_blockers),
        evidence_floor=evidence_floor,
    )


def _quality_assessment(detail: dict) -> dict:
    assessment = detail.get("quality_assessment")
    if assessment:
        return dict(assessment)
    from app.core.quality import build_quality_assessment

    return build_quality_assessment(detail)


def _policy(
    *,
    recommended_status: str,
    completion_mode: str,
    strict_ready: bool,
    limited_ready: bool,
    auto_exhausted: bool,
    manual_decision_required: bool,
    environment_blocked: bool,
    reason: str,
    remaining_blockers: list[str],
    acceptable_limitations: list[str],
    operator_next_actions: list[str],
    evidence_floor: dict,
) -> dict:
    return {
        "recommended_status": recommended_status,
        "completion_mode": completion_mode,
        "strict_completion_ready": strict_ready,
        "limited_completion_ready": limited_ready,
        "auto_exhausted": auto_exhausted,
        "manual_decision_required": manual_decision_required,
        "environment_blocked": environment_blocked,
        "reason": reason,
        "remaining_blockers": sorted(set(remaining_blockers)),
        "acceptable_limitations": sorted(set(acceptable_limitations)),
        "operator_next_actions": operator_next_actions,
        "evidence_floor": evidence_floor,
    }


def _planner_detail_for_explicit_gaps(detail: dict, gap_analysis: list[dict]) -> dict:
    missing_keys = [
        gap_key
        for gap in gap_analysis
        for gap_key in [str(gap.get("gap_key") or "").strip()]
        if gap_key
    ]
    blocking_keys = [
        gap_key
        for gap in gap_analysis
        for gap_key in [str(gap.get("gap_key") or "").strip()]
        if gap_key and str(gap.get("severity") or "").strip().lower() == "blocking"
    ]
    return {
        **detail,
        "quality_assessment": {
            **dict(detail.get("quality_assessment") or {}),
            "missing_keys": missing_keys,
            "blocking_keys": blocking_keys,
        },
    }


def _remaining_blockers(assessment: dict, gap_analysis: list[dict], detail: dict) -> list[str]:
    blockers = {
        normalized
        for item in assessment.get("blocking_keys") or []
        for normalized in [_normalize_blocker_key(item)]
        if normalized
    }
    for gap in gap_analysis:
        if str(gap.get("severity") or "").strip().lower() == "blocking":
            gap_key = _normalize_blocker_key(gap.get("gap_key"))
            if gap_key:
                blockers.add(gap_key)
    if _has_high_risk_review(detail):
        blockers.add("risk_review")
    return sorted(blockers)


def _normalize_blocker_key(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _normalized_status(value: object) -> str:
    return str(value or "").strip().upper()


def _evidence_floor(detail: dict) -> dict:
    seed_type = str(detail.get("seed_type") or "company")
    if seed_type in {"domain", "url"}:
        return {
            "identity": _has_source_backed_identity(detail),
            "official_website": _has_source_backed_official_website(detail),
            "business_scope": _has_source_backed_business_scope(detail),
            "evidence_ledger": _has_evidence_ledger(detail),
            "fact_pool": _has_linked_fact(detail),
            "cross_verification": _has_source_backed_verification(detail),
            "bluf_report": _has_bluf_report(detail),
        }
    if seed_type in {"email", "username"}:
        source_backed_identity = _has_source_backed_profile_identity(detail)
        return {
            "identity": source_backed_identity,
            "source_record": source_backed_identity,
            "evidence_ledger": _has_evidence_ledger(detail),
            "risk_summary": bool(detail.get("risk_report") or detail.get("summary") or detail.get("report_markdown")),
            "cross_verification": _has_source_backed_verification(detail),
        }
    return {
        "identity": _has_source_backed_identity(detail),
        "official_website": _has_source_backed_official_website(detail),
        "business_scope": _has_source_backed_business_scope(detail),
        "contact_channel": _has_source_backed_contact_channel(detail),
        "evidence_ledger": _has_evidence_ledger(detail),
        "fact_pool": _has_linked_fact(detail),
        "cross_verification": _has_source_backed_verification(detail),
        "bluf_report": _has_bluf_report(detail),
    }


def _acceptable_limitations(detail: dict, remaining_blockers: list[str], evidence_floor: dict) -> list[str]:
    if not all(evidence_floor.values()):
        return []
    accepted = set(BASE_ACCEPTABLE_LIMITATIONS)
    if _has_source_backed_contact_type(detail, {"email"}) or _has_contact_page(detail):
        accepted.add("contact_phone")
    if _has_source_backed_contact_type(detail, {"phone", "whatsapp"}) or _has_contact_page(detail):
        accepted.add("contact_email")
    return sorted(key for key in remaining_blockers if key in accepted)


def _has_non_acceptable_blocker(remaining_blockers: list[str], detail: dict) -> bool:
    if set(remaining_blockers) & NON_ACCEPTABLE_BLOCKERS:
        return True
    if _has_high_risk_review(detail):
        return True
    if any(_has_conflict_status(fact) for fact in detail.get("facts") or []):
        return True
    matrix = detail.get("cross_verification_matrix") or []
    return any(_has_conflict_status(row) for row in matrix)


def _has_conflict_status(item: dict) -> bool:
    return _normalized_status(item.get("status")) in CONFLICT_VERIFICATION_STATUSES


def _has_high_risk_review(detail: dict) -> bool:
    risk_report = detail.get("risk_report") or {}
    if not isinstance(risk_report, dict):
        return False
    if bool(risk_report.get("review_required")):
        return True
    if str(risk_report.get("overall_risk_level") or "").strip().lower() in {"high", "critical"}:
        return True
    signals = risk_report.get("top_risk_signals") or risk_report.get("signals") or []
    return any(
        str(signal.get("severity") or "").strip().lower() in {"high", "critical"}
        for signal in signals
        if isinstance(signal, dict)
    )


def _environment_blocked(gap_tool_plan: list[dict], gap_summary: dict) -> bool:
    if int(gap_summary.get("ready") or 0) + int(gap_summary.get("queued") or 0) > 0:
        return False
    if int(gap_summary.get("blocked_by_config") or 0) > 0:
        return True
    return any(str(item.get("status") or "").strip().lower() in BLOCKED_TOOL_STATUSES for item in gap_tool_plan)


def _has_useful_evidence(detail: dict) -> bool:
    return bool(
        _has_evidence_ledger(detail)
        or _has_linked_fact(detail)
        or _has_source_backed_verification(detail)
    )


def _execution_failed_without_evidence(detail: dict) -> bool:
    jobs = detail.get("jobs") or []
    if _has_useful_evidence(detail) or not jobs:
        return False
    return all(_normalized_status(job.get("status")) in {"FAILED", "PARTIAL_FAILED"} for job in jobs)


def _entity_values(detail: dict, accepted_types: set[str]) -> set[str]:
    return {
        str(item.get("value") or "").strip().lower()
        for item in detail.get("entities") or []
        if str(item.get("type") or "") in accepted_types and str(item.get("value") or "").strip()
    }


def _has_source_backed_profile_identity(detail: dict) -> bool:
    values = _entity_values(detail, PROFILE_IDENTITY_TYPES)
    seed_type = str(detail.get("seed_type") or "")
    seed_value = str(detail.get("seed_value") or "").strip().lower()
    if seed_type in {"email", "username"} and seed_value:
        values.add(seed_value)
    return _has_source_backed_value(detail, values)


def _has_source_backed_identity(detail: dict) -> bool:
    values = _entity_values(
        detail,
        {"company", "organization", "domain", "url", "website", "official_website"},
    )
    seed_type = str(detail.get("seed_type") or "")
    seed_value = str(detail.get("seed_value") or "").strip().lower()
    if seed_type in {"company", "domain", "url"} and seed_value:
        values.add(seed_value)
    return _has_source_backed_value(detail, values) or _has_source_backed_field(
        detail,
        {"company_identity", "company identity", "organization identity"},
    )


def _has_source_backed_official_website(detail: dict) -> bool:
    values = _entity_values(detail, {"domain", "url", "website", "official_website"})
    seed_type = str(detail.get("seed_type") or "")
    seed_value = str(detail.get("seed_value") or "").strip().lower()
    if seed_type in {"domain", "url"} and seed_value:
        values.add(seed_value)
    return _has_source_backed_value(detail, values) or _has_source_backed_field(
        detail,
        {"official_website", "official website", "website", "source boundary"},
    )


def _has_source_backed_business_scope(detail: dict) -> bool:
    values = _concrete_business_scope_values(detail)
    return (
        _has_source_backed_value(detail, values)
        or _has_source_backed_business_scope_fact(detail, values)
        or _has_source_backed_business_scope_verification(detail, values)
    )


def _has_source_backed_contact_channel(detail: dict) -> bool:
    return (
        _has_source_backed_contact_type(detail, CONTACT_CHANNEL_TYPES)
        or _has_source_backed_contact_fact(detail)
        or _has_source_backed_contact_verification(detail)
    )


def _has_source_backed_contact_type(detail: dict, accepted_types: set[str]) -> bool:
    return _has_source_backed_value(detail, _entity_values(detail, accepted_types))


def _has_source_backed_value(detail: dict, values: set[str]) -> bool:
    values = {value for value in values if value}
    if not values:
        return False
    source_backed_ledger = _source_backed_ledger(detail)
    for item in source_backed_ledger:
        haystack = " ".join(
            str(item.get(key) or "").lower()
            for key in ("entity_value", "subject", "object", "source_url", "source_type", "snippet")
        )
        if any(value in haystack for value in values):
            return True

    source_backed_evidence_ids = _source_backed_evidence_ids(detail)
    if not source_backed_evidence_ids:
        return False
    for fact in detail.get("facts") or []:
        if not _fact_is_accepted(fact):
            continue
        linked_evidence_ids = {
            str(evidence_id).strip()
            for evidence_id in fact.get("evidence_ids") or []
            if str(evidence_id).strip()
        }
        if not linked_evidence_ids & source_backed_evidence_ids:
            continue
        haystack = " ".join(
            str(fact.get(key) or "").lower()
            for key in ("statement", "predicate", "subject", "object", "value")
        )
        if any(value in haystack for value in values):
            return True
    return False


def _has_source_backed_field(detail: dict, values_or_terms: set[str]) -> bool:
    terms = {str(term).strip().lower() for term in values_or_terms if str(term).strip()}
    if not terms:
        return False
    for item in _source_backed_ledger(detail):
        haystack = " ".join(
            str(item.get(key) or "").lower()
            for key in ("entity_value", "subject", "object", "source_url", "source_type", "snippet")
        )
        if any(term in haystack for term in terms):
            return True

    source_backed_evidence_ids = _source_backed_evidence_ids(detail)
    if not source_backed_evidence_ids:
        return False
    for fact in detail.get("facts") or []:
        if not _fact_is_accepted(fact):
            continue
        linked_evidence_ids = {
            str(evidence_id).strip()
            for evidence_id in fact.get("evidence_ids") or []
            if str(evidence_id).strip()
        }
        if not linked_evidence_ids & source_backed_evidence_ids:
            continue
        haystack = " ".join(
            str(fact.get(key) or "").lower()
            for key in ("statement", "predicate", "subject", "object", "value")
        )
        if any(term in haystack for term in terms):
            return True
    return False


def _concrete_business_scope_values(detail: dict) -> set[str]:
    return {
        value
        for value in _entity_values(detail, {"business_scope", "product_scope", "purchase_category"})
        if _has_concrete_business_scope_content(value)
    }


def _has_source_backed_business_scope_fact(detail: dict, values: set[str]) -> bool:
    source_backed_evidence_ids = _source_backed_evidence_ids(detail)
    if not source_backed_evidence_ids:
        return False
    for fact in detail.get("facts") or []:
        if not _fact_is_accepted(fact) or not _fact_has_source_backed_evidence(fact, source_backed_evidence_ids):
            continue
        predicate = str(fact.get("predicate") or "").strip().lower()
        has_business_scope_predicate = any(field_key in predicate for field_key in BUSINESS_SCOPE_FIELD_KEYS)
        content = _business_scope_fact_content(fact) if has_business_scope_predicate else ""
        if has_business_scope_predicate and _has_concrete_business_scope_content(content):
            return True
        if not values:
            continue
        haystack = " ".join(
            str(fact.get(key) or "").lower()
            for key in ("statement", "object", "value")
        )
        if any(value in haystack for value in values):
            return True
    return False


def _has_source_backed_business_scope_verification(detail: dict, values: set[str]) -> bool:
    source_backed_evidence_ids = _source_backed_evidence_ids(detail)
    source_backed_fact_ids = {
        str(item.get("id") or "").strip()
        for item in detail.get("facts") or []
        if str(item.get("id") or "").strip()
        and _fact_is_accepted(item)
        and _fact_has_source_backed_evidence(item, source_backed_evidence_ids)
    }
    for item in detail.get("cross_verification_matrix") or []:
        if _normalized_status(item.get("status")) not in SUPPORTED_VERIFICATION_STATUSES:
            continue
        field_key = str(item.get("field_key") or "").strip().lower()
        if field_key not in BUSINESS_SCOPE_FIELD_KEYS:
            continue
        linked_evidence_ids = {
            str(evidence_id).strip()
            for evidence_id in item.get("linked_evidence_ids") or item.get("evidence_ids") or []
            if str(evidence_id).strip()
        }
        linked_fact_ids = {
            str(fact_id).strip()
            for fact_id in item.get("linked_fact_ids") or item.get("fact_ids") or []
            if str(fact_id).strip()
        }
        if linked_fact_ids:
            if not linked_fact_ids & source_backed_fact_ids:
                continue
        elif not linked_evidence_ids & source_backed_evidence_ids:
            continue
        candidate_value = str(item.get("candidate_value") or "").strip().lower()
        if not _has_concrete_business_scope_content(candidate_value):
            continue
        if not values or any(value in candidate_value for value in values):
            return True
    return False


def _business_scope_fact_content(fact: dict) -> str:
    subject = str(fact.get("subject") or "").strip().lower()
    parts = []
    for key in ("statement", "object", "value"):
        value = str(fact.get(key) or "").strip().lower()
        if subject:
            value = value.replace(subject, " ")
        parts.append(value)
    return " ".join(parts)


def _has_concrete_business_scope_content(value: object) -> bool:
    tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return any(token not in GENERIC_BUSINESS_SCOPE_TERMS for token in tokens)


def _source_backed_ledger(detail: dict) -> list[dict]:
    return [
        item
        for item in detail.get("evidence_ledger") or []
        if item.get("source_url") or item.get("source_type")
    ]


def _source_backed_evidence_ids(detail: dict) -> set[str]:
    return {
        str(item.get("id") or "").strip()
        for item in _source_backed_ledger(detail)
        if str(item.get("id") or "").strip()
    }


def _fact_has_source_backed_evidence(fact: dict, source_backed_evidence_ids: set[str]) -> bool:
    return bool(
        source_backed_evidence_ids
        & {
            str(evidence_id).strip()
            for evidence_id in fact.get("evidence_ids") or []
            if str(evidence_id).strip()
        }
    )


def _fact_is_accepted(fact: dict) -> bool:
    status = _normalized_status(fact.get("status"))
    if status in NEGATIVE_FACT_STATUSES:
        return False
    promotion_stage = _normalized_status(fact.get("promotion_stage"))
    return status in SUPPORTED_VERIFICATION_STATUSES or promotion_stage == "ACCEPTED_FACT"


def _has_source_backed_contact_fact(detail: dict) -> bool:
    source_backed_evidence_ids = _source_backed_evidence_ids(detail)
    if not source_backed_evidence_ids:
        return False
    for fact in detail.get("facts") or []:
        if not _fact_is_accepted(fact) or not _fact_has_source_backed_evidence(fact, source_backed_evidence_ids):
            continue
        haystack = " ".join(
            str(fact.get(key) or "").lower()
            for key in ("statement", "predicate", "subject", "object", "value")
        )
        if _contains_contact_value(haystack):
            return True
    return False


def _has_source_backed_contact_verification(detail: dict) -> bool:
    source_backed_evidence_ids = _source_backed_evidence_ids(detail)
    source_backed_facts = [
        item
        for item in detail.get("facts") or []
        if str(item.get("id") or "").strip()
        and _fact_is_accepted(item)
        and _fact_has_source_backed_evidence(item, source_backed_evidence_ids)
    ]
    source_backed_fact_ids = {str(item.get("id") or "").strip() for item in source_backed_facts}
    evidence_by_id = {
        str(item.get("id") or "").strip(): item
        for item in _source_backed_ledger(detail)
        if str(item.get("id") or "").strip()
    }
    fact_by_id = {str(item.get("id") or "").strip(): item for item in source_backed_facts}
    contact_fields = {"contact_channel", "contact_phone", "contact_email", "phone", "email", "whatsapp"}
    for item in detail.get("cross_verification_matrix") or []:
        if _normalized_status(item.get("status")) not in SUPPORTED_VERIFICATION_STATUSES:
            continue
        field_key = str(item.get("field_key") or "").strip().lower()
        if field_key not in contact_fields:
            continue
        linked_evidence_ids = {
            str(evidence_id).strip()
            for evidence_id in item.get("linked_evidence_ids") or item.get("evidence_ids") or []
            if str(evidence_id).strip()
        }
        linked_fact_ids = {
            str(fact_id).strip()
            for fact_id in item.get("linked_fact_ids") or item.get("fact_ids") or []
            if str(fact_id).strip()
        }
        candidate_tokens = _contact_candidate_tokens(str(item.get("candidate_value") or ""))
        if candidate_tokens:
            for evidence_id in linked_evidence_ids & source_backed_evidence_ids:
                evidence = evidence_by_id.get(evidence_id) or {}
                haystack = " ".join(
                    str(evidence.get(key) or "")
                    for key in ("entity_value", "subject", "object", "source_url", "source_type", "snippet")
                )
                if _content_supports_contact_candidate(haystack, candidate_tokens):
                    return True
            for fact_id in linked_fact_ids & source_backed_fact_ids:
                fact = fact_by_id.get(fact_id) or {}
                haystack = " ".join(
                    str(fact.get(key) or "")
                    for key in ("statement", "predicate", "subject", "object", "value")
                )
                if _content_supports_contact_candidate(haystack, candidate_tokens):
                    return True
            continue
        for evidence_id in linked_evidence_ids & source_backed_evidence_ids:
            evidence = evidence_by_id.get(evidence_id) or {}
            haystack = " ".join(
                str(evidence.get(key) or "")
                for key in ("entity_value", "subject", "object", "source_url", "source_type", "snippet")
            )
            if _contains_contact_value(haystack):
                return True
        for fact_id in linked_fact_ids & source_backed_fact_ids:
            fact = fact_by_id.get(fact_id) or {}
            haystack = " ".join(
                str(fact.get(key) or "")
                for key in ("statement", "predicate", "subject", "object", "value")
            )
            if _contains_contact_value(haystack):
                return True
    return False


def _contact_candidate_tokens(value: str) -> set[str]:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return set()
    tokens = {match.group(0).lower() for match in CONTACT_EMAIL_RE.finditer(normalized)}
    for match in CONTACT_PHONE_RE.finditer(normalized):
        digits = re.sub(r"\D", "", match.group(0))
        if digits:
            tokens.add(digits)
    if not tokens and any(term in normalized for term in ("mailto:", "tel:", "whatsapp", "wa.me/")):
        tokens.add(normalized)
    return tokens


def _content_supports_contact_candidate(content: str, candidate_tokens: set[str]) -> bool:
    normalized = str(content or "").strip().lower()
    if not normalized:
        return False
    content_tokens = _contact_candidate_tokens(normalized)
    if candidate_tokens & content_tokens:
        return True
    content_digits = re.sub(r"\D", "", normalized)
    return any(token.isdigit() and token in content_digits for token in candidate_tokens)


def _contains_contact_value(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return False
    if CONTACT_EMAIL_RE.search(normalized):
        return True
    if CONTACT_PHONE_RE.search(normalized):
        return True
    if any(term in normalized for term in ("mailto:", "tel:", "whatsapp", "wa.me/")):
        return True
    return False


def _has_contact_page(detail: dict) -> bool:
    for item in detail.get("evidence_ledger") or []:
        source_type = str(item.get("source_type") or "").lower()
        source_url = str(item.get("source_url") or "").lower()
        if "contact" in source_type or "/contact" in source_url:
            return True
    return _has_source_backed_field(detail, {"contact"})


def _has_evidence_ledger(detail: dict) -> bool:
    return any(item.get("source_url") or item.get("source_type") for item in detail.get("evidence_ledger") or [])


def _has_bluf_report(detail: dict) -> bool:
    return bool(str(detail.get("report_markdown") or "").strip())


def _has_linked_fact(detail: dict) -> bool:
    ledger_ids = {
        str(item.get("id") or "").strip()
        for item in detail.get("evidence_ledger") or []
        if str(item.get("id") or "").strip() and (item.get("source_url") or item.get("source_type"))
    }
    if not ledger_ids:
        return False
    return any(
        _fact_is_accepted(item)
        and ledger_ids
        & {
            str(evidence_id).strip()
            for evidence_id in item.get("evidence_ids") or []
            if str(evidence_id).strip()
        }
        for item in detail.get("facts") or []
    )


def _has_source_backed_verification(detail: dict) -> bool:
    source_backed_evidence_ids = {
        str(item.get("id") or "").strip()
        for item in detail.get("evidence_ledger") or []
        if str(item.get("id") or "").strip() and (item.get("source_url") or item.get("source_type"))
    }
    source_backed_fact_ids = {
        str(item.get("id") or "").strip()
        for item in detail.get("facts") or []
        if str(item.get("id") or "").strip()
        and _fact_is_accepted(item)
        and source_backed_evidence_ids
        & {
            str(evidence_id).strip()
            for evidence_id in item.get("evidence_ids") or []
            if str(evidence_id).strip()
        }
    }
    for item in detail.get("cross_verification_matrix") or []:
        if _normalized_status(item.get("status")) not in SUPPORTED_VERIFICATION_STATUSES:
            continue
        linked_evidence_ids = {
            str(evidence_id).strip()
            for evidence_id in item.get("linked_evidence_ids") or item.get("evidence_ids") or []
            if str(evidence_id).strip()
        }
        linked_fact_ids = {
            str(fact_id).strip()
            for fact_id in item.get("linked_fact_ids") or item.get("fact_ids") or []
            if str(fact_id).strip()
        }
        if (
            linked_evidence_ids & source_backed_evidence_ids
            or linked_fact_ids & source_backed_fact_ids
        ):
            return True
    return False


def _limited_reason(remaining_blockers: list[str]) -> str:
    readable = ", ".join(remaining_blockers)
    return f"Core evidence floor is satisfied; only acceptable limitations remain: {readable}."


def _operator_actions(remaining_blockers: list[str]) -> list[str]:
    action_by_key = {
        "decision_maker": "Manually verify decision-maker from an official team page, public profile, or trusted directory.",
        "purchase_intent": "Manually review buying-intent context if this task is used for sales qualification.",
        "contact_phone": "Manually verify phone or WhatsApp if direct calling is required.",
        "contact_email": "Manually verify email if outbound email is required.",
        "official_website": "Confirm official website or trusted source boundary before closure.",
        "evidence_ledger": "Collect source-backed evidence records before accepting conclusions.",
        "fact_pool": "Promote source-backed claims into facts before accepting conclusions.",
        "cross_verification": "Run or perform cross-verification before accepting conclusions.",
        "risk_review": "Resolve high-risk or review-required signals before accepting conclusions.",
    }
    if not remaining_blockers:
        return []
    return [action_by_key.get(key, f"Manually resolve evidence gap: {key}.") for key in sorted(set(remaining_blockers))]


def _environment_actions(gap_tool_plan: list[dict]) -> list[str]:
    actions = []
    for item in gap_tool_plan:
        status = str(item.get("status") or "").strip().lower()
        if status not in BLOCKED_TOOL_STATUSES:
            continue
        tool_name = str(item.get("tool_name") or "unknown_tool")
        reason = str(item.get("health_reason") or "Tool route is unavailable.")
        actions.append(f"Restore {tool_name}: {reason}")
    return actions or ["Restore blocked tool routes, credentials, or configuration, then rerun collection."]
