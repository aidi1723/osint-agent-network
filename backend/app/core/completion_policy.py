from __future__ import annotations

from app.core.gap_followups import build_gap_analysis, build_gap_followup_summary, build_gap_tool_plan


SUPPORTED_VERIFICATION_STATUSES = {"CONFIRMED", "LIKELY", "SUPPORTED"}
BLOCKED_TOOL_STATUSES = {"missing_config", "missing_executable", "credential_blocked", "disabled"}
NON_ACCEPTABLE_BLOCKERS = {
    "company_identity",
    "official_website",
    "evidence_ledger",
    "fact_pool",
    "cross_verification",
    "bluf_report",
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
    gap_tool_plan = (
        list(detail["gap_tool_plan"])
        if "gap_tool_plan" in detail and detail["gap_tool_plan"] is not None
        else build_gap_tool_plan({**planner_detail, "gap_analysis": gap_analysis})
    )
    gap_summary = (
        dict(detail["gap_followup_summary"])
        if "gap_followup_summary" in detail and detail["gap_followup_summary"] is not None
        else build_gap_followup_summary(gap_tool_plan, gap_analysis)
    )
    evidence_floor = _evidence_floor(detail)
    remaining_blockers = _remaining_blockers(assessment, gap_analysis)
    strict_ready = bool(assessment.get("completion_ready"))
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


def _remaining_blockers(assessment: dict, gap_analysis: list[dict]) -> list[str]:
    blockers = {str(item) for item in assessment.get("blocking_keys") or [] if str(item).strip()}
    for gap in gap_analysis:
        if gap.get("severity") == "blocking":
            gap_key = str(gap.get("gap_key") or "").strip()
            if gap_key:
                blockers.add(gap_key)
    return sorted(blockers)


def _evidence_floor(detail: dict) -> dict:
    seed_type = str(detail.get("seed_type") or "company")
    if seed_type in {"domain", "url"}:
        return {
            "identity": _has_entity_type(detail, {"company", "organization", "domain", "url", "website", "official_website"}),
            "official_website": _has_entity_type(detail, {"domain", "url", "website", "official_website"}) or _has_source_url(detail),
            "business_scope": _has_entity_type(detail, {"business_scope", "product_scope"}) or _has_fact_predicate(detail, "business_scope"),
            "evidence_ledger": _has_evidence_ledger(detail),
            "fact_pool": _has_linked_fact(detail),
            "cross_verification": _has_supported_verification(detail),
        }
    if seed_type in {"email", "username"}:
        return {
            "identity": _has_entity_type(detail, {"email", "username", "identity", "profile_url", "platform_account"}),
            "source_record": bool(detail.get("evidence") or detail.get("evidence_ledger") or detail.get("relationships")),
            "evidence_ledger": _has_evidence_ledger(detail),
            "risk_summary": bool(detail.get("risk_report") or detail.get("summary") or detail.get("report_markdown")),
        }
    return {
        "identity": _has_entity_type(detail, {"company", "organization"}) or _has_fact_predicate(detail, "company_identity"),
        "official_website": _has_entity_type(detail, {"domain", "url", "website", "official_website"}) or _has_source_url(detail),
        "business_scope": _has_entity_type(detail, {"business_scope", "product_scope"}) or _has_fact_predicate(detail, "business_scope"),
        "contact_channel": _has_entity_type(detail, {"email", "phone", "whatsapp"}) or _has_contact_page(detail),
        "evidence_ledger": _has_evidence_ledger(detail),
        "fact_pool": _has_linked_fact(detail),
        "cross_verification": _has_supported_verification(detail),
    }


def _acceptable_limitations(detail: dict, remaining_blockers: list[str], evidence_floor: dict) -> list[str]:
    if not all(evidence_floor.values()):
        return []
    accepted = set(BASE_ACCEPTABLE_LIMITATIONS)
    if _has_entity_type(detail, {"email"}) or _has_contact_page(detail):
        accepted.add("contact_phone")
    if _has_entity_type(detail, {"phone", "whatsapp"}) or _has_contact_page(detail):
        accepted.add("contact_email")
    return sorted(key for key in remaining_blockers if key in accepted)


def _has_non_acceptable_blocker(remaining_blockers: list[str], detail: dict) -> bool:
    if set(remaining_blockers) & NON_ACCEPTABLE_BLOCKERS:
        return True
    matrix = detail.get("cross_verification_matrix") or []
    return any(str(row.get("status") or "").upper() in {"CONFLICT", "CONTRADICTED", "HIGH_RISK_CONFLICT"} for row in matrix)


def _environment_blocked(gap_tool_plan: list[dict], gap_summary: dict) -> bool:
    if int(gap_summary.get("ready") or 0) + int(gap_summary.get("queued") or 0) > 0:
        return False
    if int(gap_summary.get("blocked_by_config") or 0) > 0:
        return True
    return any(str(item.get("status") or "") in BLOCKED_TOOL_STATUSES for item in gap_tool_plan)


def _has_useful_evidence(detail: dict) -> bool:
    return bool(
        _has_evidence_ledger(detail)
        or _has_linked_fact(detail)
        or _has_supported_verification(detail)
    )


def _execution_failed_without_evidence(detail: dict) -> bool:
    jobs = detail.get("jobs") or []
    if _has_useful_evidence(detail) or not jobs:
        return False
    return all(str(job.get("status") or "") in {"FAILED", "PARTIAL_FAILED"} for job in jobs)


def _has_entity_type(detail: dict, accepted_types: set[str]) -> bool:
    return any(str(item.get("type") or "") in accepted_types and str(item.get("value") or "").strip() for item in detail.get("entities") or [])


def _has_source_url(detail: dict) -> bool:
    return any(str(item.get("source_url") or "").startswith(("http://", "https://")) for item in detail.get("evidence_ledger") or [])


def _has_contact_page(detail: dict) -> bool:
    for item in detail.get("evidence_ledger") or []:
        source_type = str(item.get("source_type") or "").lower()
        source_url = str(item.get("source_url") or "").lower()
        if "contact" in source_type or "/contact" in source_url:
            return True
    return any("contact" in str(item.get("evidence_kind") or "").lower() for item in detail.get("evidence") or [])


def _has_evidence_ledger(detail: dict) -> bool:
    return any(item.get("source_url") or item.get("source_type") for item in detail.get("evidence_ledger") or [])


def _has_linked_fact(detail: dict) -> bool:
    ledger_ids = {
        str(item.get("id") or "").strip()
        for item in detail.get("evidence_ledger") or []
        if str(item.get("id") or "").strip() and (item.get("source_url") or item.get("source_type"))
    }
    if not ledger_ids:
        return False
    return any(
        ledger_ids
        & {
            str(evidence_id).strip()
            for evidence_id in item.get("evidence_ids") or []
            if str(evidence_id).strip()
        }
        for item in detail.get("facts") or []
    )


def _has_fact_predicate(detail: dict, key: str) -> bool:
    return any(key in str(item.get("predicate") or "").lower() for item in detail.get("facts") or [])


def _has_supported_verification(detail: dict) -> bool:
    return any(
        str(item.get("status") or "").upper() in SUPPORTED_VERIFICATION_STATUSES
        and (
            str(item.get("candidate_value") or "").strip()
            or _has_any_id(item, ("evidence_ids", "linked_evidence_ids", "fact_ids", "linked_fact_ids"))
        )
        for item in detail.get("cross_verification_matrix") or []
    )


def _has_any_id(item: dict, keys: tuple[str, ...]) -> bool:
    for key in keys:
        value = item.get(key)
        if isinstance(value, (list, tuple, set)):
            if any(str(entry).strip() for entry in value):
                return True
            continue
        if str(value or "").strip():
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
    }
    if not remaining_blockers:
        return []
    return [action_by_key.get(key, f"Manually resolve evidence gap: {key}.") for key in sorted(set(remaining_blockers))]


def _environment_actions(gap_tool_plan: list[dict]) -> list[str]:
    actions = []
    for item in gap_tool_plan:
        status = str(item.get("status") or "")
        if status not in BLOCKED_TOOL_STATUSES:
            continue
        tool_name = str(item.get("tool_name") or "unknown_tool")
        reason = str(item.get("health_reason") or "Tool route is unavailable.")
        actions.append(f"Restore {tool_name}: {reason}")
    return actions or ["Restore blocked tool routes, credentials, or configuration, then rerun collection."]
