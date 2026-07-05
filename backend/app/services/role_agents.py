from __future__ import annotations

from dataclasses import dataclass

from app.core.ach_engine import EvidenceItem, default_sparse_lead_hypotheses
from app.core.agent_permissions import PermissionedRoleStore, tier_for_role
from app.core.quality import build_quality_assessment, render_structured_report


ROLE_AGENT_NAMES = {
    "enterprise_intel_agent",
    "social_intel_agent",
    "contact_discovery_agent",
    "supply_chain_agent",
    "purchase_intent_agent",
    "news_intel_agent",
    "search_planning_agent",
    "cross_verification_agent",
    "analysis_judgement_agent",
}

HIGH_CONFIDENCE_TYPES = {
    "company",
    "organization",
    "domain",
    "email",
    "phone",
    "username",
    "profile_url",
    "external_link",
}


@dataclass(frozen=True)
class RoleAgentResult:
    completed: bool
    message: str
    high_confidence_entities: list[dict]


def can_run_locally(job: dict) -> bool:
    role = str(job.get("agent_role") or "")
    return role in ROLE_AGENT_NAMES


def run_role_agent(store, investigation_id: str, job: dict) -> RoleAgentResult:
    detail = store.get_investigation(investigation_id)
    if detail is None:
        return RoleAgentResult(False, "investigation not found", [])

    tool_name = str(job.get("tool_name") or "")
    role = str(job.get("agent_role") or "")
    permissioned_store = PermissionedRoleStore(store, tier_for_role(role))
    if tool_name in {"cross_verification", "identity_match_review"}:
        _run_cross_verification(permissioned_store, detail)
    elif tool_name == "analysis_judgement":
        _run_analysis_judgement(permissioned_store, detail)
    elif tool_name == "constrained_query_planning":
        _run_query_planning(permissioned_store, detail)
    else:
        _run_collection_role(permissioned_store, detail, tool_name)

    updated = store.get_investigation(investigation_id) or detail
    return RoleAgentResult(
        completed=True,
        message=f"本地职责 Agent 完成：{tool_name}",
        high_confidence_entities=_high_confidence_entities(updated),
    )


def _run_collection_role(store, detail: dict, tool_name: str) -> None:
    investigation_id = detail["id"]
    seed = str(detail.get("seed_value") or "")
    if seed:
        snippet = f"{tool_name} 已将目标主体纳入本地职责采集闭环。"
        store.add_entity(investigation_id, "company", seed, tool_name, 0.62)
        store.add_evidence(investigation_id, seed, "role_agent_collection_note", tool_name, snippet)
        store.add_evidence_record(
            investigation_id,
            f"hcs://role-agent/{tool_name}/{investigation_id}",
            "role_agent_collection",
            tool_name,
            snippet,
            0.62,
        )
    _add_sparse_lead_candidate_entities(store, detail, tool_name)

    for entity in detail.get("entities", []):
        entity_type = str(entity.get("type") or "")
        value = str(entity.get("value") or "")
        confidence = float(entity.get("confidence") or 0)
        if confidence < 0.65 or not value:
            continue
        if entity_type == "domain":
            store.add_relationship(investigation_id, seed, value, "official_website", min(confidence, 0.82))
        elif entity_type == "email":
            store.add_relationship(investigation_id, seed, value, "uses_business_email", min(confidence, 0.82))
        elif entity_type == "phone":
            store.add_relationship(investigation_id, seed, value, "official_company_phone", min(confidence, 0.8))
        elif entity_type in {"business_scope", "product_scope", "purchase_category"}:
            store.add_relationship(investigation_id, seed, value, "company_has_business_scope", min(confidence, 0.78))


def _add_sparse_lead_candidate_entities(store, detail: dict, tool_name: str) -> None:
    if str(detail.get("seed_type") or "") != "sparse_lead":
        return
    investigation_id = detail["id"]
    seed = str(detail.get("seed_value") or "")
    metadata = detail.get("metadata") or {}
    display_name = str(metadata.get("lead_display_name") or "").strip()
    if display_name:
        store.add_entity(investigation_id, "identity", display_name, tool_name, 0.62)
        store.add_relationship(investigation_id, seed, display_name, "lead_has_decision_maker_candidate", 0.62)
        store.add_evidence(
            investigation_id,
            display_name,
            "platform_decision_candidate",
            tool_name,
            f"Platform lead display name provides decision-maker candidate: {display_name}",
        )
    for category in metadata.get("categories", []) or []:
        value = str(category or "").strip()
        if not value:
            continue
        store.add_entity(investigation_id, "business_scope", value, tool_name, 0.68)
        store.add_relationship(investigation_id, seed, value, "lead_category_suggests_business_scope", 0.68)
        store.add_evidence(
            investigation_id,
            value,
            "platform_business_scope_candidate",
            tool_name,
            f"Platform lead category suggests business scope: {value}",
        )


def _run_query_planning(store, detail: dict) -> None:
    investigation_id = detail["id"]
    seed = str(detail.get("seed_value") or "")
    anchors = [
        str(entity.get("value") or "")
        for entity in detail.get("entities", [])
        if str(entity.get("type") or "") in {"platform_account", "company_name_raw", "country_region", "purchase_category"}
    ]
    query = " ".join([seed, *anchors]).strip()
    if query:
        store.add_evidence(investigation_id, seed, "constrained_query_plan", "constrained_query_planning", f"优先使用约束检索：{query}")


def _run_cross_verification(store, detail: dict) -> None:
    investigation_id = detail["id"]
    seed = str(detail.get("seed_value") or "")
    ledger_by_value = _ledger_for_values(detail)

    for entity in detail.get("entities", []):
        value = str(entity.get("value") or "").strip()
        entity_type = str(entity.get("type") or "")
        confidence = float(entity.get("confidence") or 0)
        if not value or confidence < 0.55:
            continue
        evidence_ids = [record["id"] for record in ledger_by_value.get(value, [])]
        evidence_ids = evidence_ids or [record["id"] for record in detail.get("evidence_ledger", [])[:1]]
        if not evidence_ids:
            continue
        status = "CONFIRMED" if confidence >= 0.8 else "LIKELY"
        admiralty = _first_admiralty(detail, evidence_ids)
        predicate = _predicate_for_entity(entity_type)
        try:
            store.add_fact(
                investigation_id=investigation_id,
                statement=f"{seed or '目标'} {predicate} {value}.",
                subject=seed or value,
                predicate=predicate,
                object_value=value,
                status=status,
                confidence=min(0.95, max(confidence, 0.56)),
                admiralty_code=admiralty,
                evidence_ids=evidence_ids,
            )
        except ValueError:
            continue

    _ensure_default_hypotheses(store, detail)
    evidence_items = _ach_evidence_items(detail)
    if evidence_items:
        try:
            store.score_hypotheses(investigation_id, evidence_items)
        except ValueError:
            pass


def _run_analysis_judgement(store, detail: dict) -> None:
    investigation_id = detail["id"]
    updated = store.get_investigation(investigation_id) or detail
    assessment = build_quality_assessment(updated)
    report = render_structured_report(updated, assessment)
    confidence = min(0.95, max(0.1, float(assessment.get("score", 0)) / 100))
    store.complete_task(
        investigation_id=investigation_id,
        agent_id="local-analysis-agent",
        status="COMPLETED" if assessment.get("completion_ready") else "NEEDS_REVIEW",
        summary=f"本地分析完成：质量评分 {assessment.get('score', 0)} / 100",
        report_markdown=report,
        confidence=confidence,
    )


def _ensure_default_hypotheses(store, detail: dict) -> None:
    existing = {str(item.get("id") or "") for item in detail.get("hypotheses", [])}
    hypotheses = default_sparse_lead_hypotheses()
    if str(detail.get("seed_type") or "") != "sparse_lead":
        hypotheses = [
            *hypotheses[:1],
            type(hypotheses[0])("beta_partial_or_unverified_profile", "Public evidence supports only a partial or unverified company profile."),
            type(hypotheses[0])("gamma_same_name_or_noise", "Findings are mostly same-name noise or weak unrelated signals."),
        ]
    for hypothesis in hypotheses:
        if hypothesis.id in existing:
            continue
        store.add_hypothesis(detail["id"], hypothesis.id, hypothesis.statement, hypothesis.mutually_exclusive_group)


def _ach_evidence_items(detail: dict) -> list[dict]:
    items = []
    for record in detail.get("evidence_ledger", []):
        credibility = _credibility_from_admiralty(record.get("admiralty_code", ""))
        items.append(
            {
                "id": record.get("id", ""),
                "summary": record.get("snippet") or record.get("source_url") or "evidence",
                "kinds": [record.get("source_type") or "open_source"],
                "supports": ["alpha_real_procurement"] if detail.get("seed_type") == "sparse_lead" else ["alpha_real_procurement"],
                "contradicts": ["gamma_noise_or_unmatched_identity", "gamma_same_name_or_noise"],
                "source_reliability": str(record.get("source_reliability") or "C"),
                "credibility": credibility,
                "keywords": _keywords(record),
            }
        )
    return items


def _high_confidence_entities(detail: dict) -> list[dict]:
    results = []
    for entity in detail.get("entities", []):
        entity_type = str(entity.get("type") or "")
        confidence = float(entity.get("confidence") or 0)
        if entity_type in HIGH_CONFIDENCE_TYPES and confidence >= 0.7:
            results.append(entity)
    return results


def _ledger_for_values(detail: dict) -> dict[str, list[dict]]:
    values = {str(entity.get("value") or "") for entity in detail.get("entities", [])}
    result = {value: [] for value in values if value}
    for record in detail.get("evidence_ledger", []):
        text = f"{record.get('source_url', '')} {record.get('snippet', '')}"
        for value in values:
            if value and value.lower() in text.lower():
                result.setdefault(value, []).append(record)
    return result


def _first_admiralty(detail: dict, evidence_ids: list[str]) -> str:
    for record in detail.get("evidence_ledger", []):
        if record.get("id") in evidence_ids and record.get("admiralty_code"):
            return str(record["admiralty_code"])
    return "C-3"


def _predicate_for_entity(entity_type: str) -> str:
    return {
        "company": "has_company_identity",
        "organization": "has_company_identity",
        "domain": "has_official_domain",
        "email": "uses_contact_email",
        "phone": "uses_contact_phone",
        "address": "has_public_address",
        "business_scope": "has_business_scope",
        "product_scope": "has_product_scope",
        "purchase_category": "has_purchase_category",
        "identity": "has_decision_maker_candidate",
        "profile_url": "has_public_profile_candidate",
    }.get(entity_type, f"has_{entity_type}")


def _credibility_from_admiralty(code: str) -> float:
    if "-" not in code:
        return 0.5
    suffix = code.split("-", 1)[1]
    return {"1": 0.95, "2": 0.82, "3": 0.68, "4": 0.45, "5": 0.25, "6": 0.1}.get(suffix, 0.5)


def _keywords(record: dict) -> list[str]:
    text = f"{record.get('source_type', '')} {record.get('snippet', '')}".lower()
    return [keyword for keyword in ("contact", "official", "rfq", "purchase", "website", "import", "supplier") if keyword in text]
