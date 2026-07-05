from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_PIR_STATUS = "OPEN"
DEFAULT_EEI_STATUS = "MISSING"
PIR_STATUSES = {"OPEN", "PARTIAL", "ANSWERED", "BLOCKED", "NEEDS_REVIEW"}
EEI_STATUSES = {"MISSING", "CANDIDATE", "SUPPORTED", "CONFIRMED", "CONFLICTED"}


BASE_PIRS = [
    ("pir_identity", "Is the target organization or account identity real and operational?", "high"),
    ("pir_purchase_capacity", "Does the target show credible purchase capacity or purchase intent?", "high"),
    ("pir_contact_confidence", "Are the contact channels tied to the target by public evidence?", "high"),
    ("pir_decision_maker", "Is the decision-maker candidate supported by public evidence?", "medium"),
    ("pir_risk", "Are there risk, contradiction, fraud, litigation, reputation, or sanctions signals?", "high"),
]

SPARSE_LEAD_EXTRA_PIRS = [
    ("pir_identity_match", "Do public records belong to the same buyer represented by the platform lead?", "high"),
]

BASE_EEIS = [
    ("eei_company_identity", "Legal or operating company name", "company_identity", True),
    ("eei_official_website", "Official website or domain", "official_website", True),
    ("eei_contact_email", "Public contact email", "contact_email", False),
    ("eei_contact_phone", "Public phone or WhatsApp", "contact_phone", False),
    ("eei_operation_location", "Address or operating region", "operation_location", True),
    ("eei_registration", "Registration identifier or registry profile", "registration", False),
    ("eei_business_scope", "Business scope and product fit", "business_scope", True),
    ("eei_decision_maker", "Decision-maker candidate", "decision_maker", False),
    ("eei_purchase_signal", "Import, project, RFQ, or purchase-intent signal", "purchase_intent", False),
    ("eei_risk_signal", "Risk or contradiction signal", "risk_signal", False),
]

SPARSE_LEAD_EXTRA_EEIS = [
    ("eei_platform_anchor", "Platform anchor fields", "platform_anchor", True),
    ("eei_identity_match", "Public-record to buyer identity match", "identity_match", True),
]

DOMAIN_EEIS = [
    ("eei_official_website", "Official website or domain", "official_website", True),
    ("eei_contact_email", "Public contact email", "contact_email", False),
    ("eei_business_scope", "Business scope and product fit", "business_scope", False),
    ("eei_risk_signal", "Risk or contradiction signal", "risk_signal", False),
]

EMAIL_EEIS = [
    ("eei_contact_email", "Email ownership and context", "contact_email", True),
    ("eei_company_identity", "Linked organization identity", "company_identity", False),
    ("eei_official_website", "Linked official domain", "official_website", False),
    ("eei_risk_signal", "Risk or contradiction signal", "risk_signal", False),
]


def build_intelligence_requirements(
    seed_type: str,
    seed_value: str,
    strategy: str,
    metadata: dict[str, Any] | None,
) -> dict:
    metadata = metadata or {}
    supplied = metadata.get("intelligence_requirements")
    if isinstance(supplied, dict):
        normalized = normalize_intelligence_requirements(supplied)
        if normalized["pirs"] and normalized["eeis"]:
            return normalized

    pirs = [_pir(*item) for item in BASE_PIRS]
    if seed_type == "sparse_lead":
        pirs.extend(_pir(*item) for item in SPARSE_LEAD_EXTRA_PIRS)

    if seed_type == "domain":
        eei_source = DOMAIN_EEIS
    elif seed_type == "email":
        eei_source = EMAIL_EEIS
    else:
        eei_source = BASE_EEIS
    eeis = [_eei(*item) for item in eei_source]
    if seed_type == "sparse_lead":
        eeis.extend(_eei(*item) for item in SPARSE_LEAD_EXTRA_EEIS)

    requirements = {
        "decision_context": _default_decision_context(seed_type, seed_value),
        "confidence_requirement": _confidence_requirement(strategy),
        "pirs": pirs,
        "eeis": eeis,
    }
    if isinstance(supplied, dict):
        requirements["decision_context"] = str(
            supplied.get("decision_context") or requirements["decision_context"]
        )
        requirements["confidence_requirement"] = str(
            supplied.get("confidence_requirement") or requirements["confidence_requirement"]
        )
    return requirements


def normalize_intelligence_requirements(raw: dict[str, Any]) -> dict:
    pirs = []
    for index, item in enumerate(raw.get("pirs") or [], start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        status = str(item.get("status") or DEFAULT_PIR_STATUS)
        pirs.append(
            {
                "id": str(item.get("id") or f"pir_custom_{index}"),
                "question": question,
                "priority": str(item.get("priority") or "medium"),
                "status": status if status in PIR_STATUSES else DEFAULT_PIR_STATUS,
                "answer": str(item.get("answer") or ""),
                "confidence": _bounded_float(item.get("confidence"), 0.0),
                "linked_fact_ids": _string_list(item.get("linked_fact_ids")),
                "remaining_gaps": _string_list(item.get("remaining_gaps")),
            }
        )
    eeis = []
    for index, item in enumerate(raw.get("eeis") or [], start=1):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        field_key = str(item.get("field_key") or "").strip()
        if not label or not field_key:
            continue
        status = str(item.get("status") or DEFAULT_EEI_STATUS)
        eeis.append(
            {
                "id": str(item.get("id") or f"eei_custom_{index}"),
                "label": label,
                "field_key": field_key,
                "required": bool(item.get("required", True)),
                "status": status if status in EEI_STATUSES else DEFAULT_EEI_STATUS,
                "linked_entity_values": _string_list(item.get("linked_entity_values")),
                "linked_fact_ids": _string_list(item.get("linked_fact_ids")),
            }
        )
    return {
        "decision_context": str(raw.get("decision_context") or ""),
        "confidence_requirement": str(raw.get("confidence_requirement") or "standard"),
        "pirs": pirs,
        "eeis": eeis,
    }


def apply_requirement_updates(requirements: dict, matrix: list[dict], facts: list[dict]) -> dict:
    updated = deepcopy(requirements)
    by_field = {row.get("field_key"): row for row in matrix}
    accepted_fact_ids = {
        str(fact.get("id"))
        for fact in facts
        if fact.get("promotion_stage") == "ACCEPTED_FACT" or fact.get("status") in {"CONFIRMED", "LIKELY"}
    }
    for eei in updated.get("eeis", []):
        row = by_field.get(eei.get("field_key"))
        if not row:
            continue
        status = str(row.get("status") or "")
        if status in {"CONFIRMED", "LIKELY"}:
            eei["status"] = "CONFIRMED"
        elif status == "SUPPORTED":
            eei["status"] = "SUPPORTED"
        elif status == "CONFLICTED":
            eei["status"] = "CONFLICTED"
        elif row.get("candidate_value"):
            eei["status"] = "CANDIDATE"
        eei["linked_entity_values"] = [str(row.get("candidate_value"))] if row.get("candidate_value") else []
        eei["linked_fact_ids"] = list(row.get("linked_fact_ids") or [])

    for pir in updated.get("pirs", []):
        if accepted_fact_ids:
            pir["status"] = "PARTIAL"
            pir["linked_fact_ids"] = sorted(accepted_fact_ids)[:6]
        if pir.get("id") == "pir_identity" and _field_confirmed(updated, "company_identity"):
            pir["status"] = "ANSWERED"
            pir["answer"] = "Identity is supported by cross-verified public-source evidence."
            pir["confidence"] = max(float(pir.get("confidence") or 0), 0.75)
        if pir.get("id") == "pir_contact_confidence" and (
            _field_confirmed(updated, "contact_email") or _field_confirmed(updated, "contact_phone")
        ):
            pir["status"] = "ANSWERED"
            pir["answer"] = "At least one contact channel is supported by public-source evidence."
            pir["confidence"] = max(float(pir.get("confidence") or 0), 0.7)
    return updated


def requirement_coverage(requirements: dict) -> dict:
    pirs = requirements.get("pirs") or []
    eeis = requirements.get("eeis") or []
    required = [item for item in eeis if item.get("required")]
    return {
        "pir_total": len(pirs),
        "pir_answered": sum(1 for item in pirs if item.get("status") == "ANSWERED"),
        "pir_partial": sum(1 for item in pirs if item.get("status") == "PARTIAL"),
        "required_eei_total": len(required),
        "eei_confirmed": sum(1 for item in eeis if item.get("status") == "CONFIRMED"),
        "required_eei_confirmed": sum(1 for item in required if item.get("status") == "CONFIRMED"),
    }


def _pir(id: str, question: str, priority: str) -> dict:
    return {
        "id": id,
        "question": question,
        "priority": priority,
        "status": DEFAULT_PIR_STATUS,
        "answer": "",
        "confidence": 0.0,
        "linked_fact_ids": [],
        "remaining_gaps": [],
    }


def _eei(id: str, label: str, field_key: str, required: bool) -> dict:
    return {
        "id": id,
        "label": label,
        "field_key": field_key,
        "required": required,
        "status": DEFAULT_EEI_STATUS,
        "linked_entity_values": [],
        "linked_fact_ids": [],
    }


def _default_decision_context(seed_type: str, seed_value: str) -> str:
    if seed_type == "sparse_lead":
        return "Qualify sparse platform buyer lead."
    if seed_type == "company":
        return "Assess public-source company identity, contactability, risk, and purchase fit."
    return f"Assess public-source intelligence for {seed_type}: {seed_value}."


def _confidence_requirement(strategy: str) -> str:
    if strategy in {"deep", "maximum"}:
        return "strict"
    if strategy == "quick":
        return "quick"
    return "standard"


def _bounded_float(value: Any, default: float) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _field_confirmed(requirements: dict, field_key: str) -> bool:
    return any(
        item.get("field_key") == field_key and item.get("status") == "CONFIRMED"
        for item in requirements.get("eeis", [])
    )
