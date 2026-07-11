from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlsplit


FIELD_DEFINITIONS = [
    ("company_identity", "企业名称", {"company", "organization"}),
    ("official_website", "官网/域名", {"domain", "website", "official_website", "url"}),
    ("contact_email", "企业邮箱", {"email"}),
    ("contact_phone", "电话/WhatsApp", {"phone", "whatsapp"}),
    ("operation_location", "地址/经营区域", {"address", "declared_location", "likely_activity_region", "country_region"}),
    ("registration", "注册信息", {"registration", "registration_id", "tax_id", "nit", "rues"}),
    ("business_scope", "主营业务/产品匹配", {"business_scope", "product_scope", "purchase_category"}),
    ("decision_maker", "决策人候选", {"identity", "decision_maker", "person", "profile_url"}),
    ("purchase_intent", "采购意图", {"purchase_intent", "buying_signal", "rfq"}),
    ("risk_signal", "风险信号", {"risk_signal", "negative_signal", "litigation", "sanction"}),
]

SOURCE_HINTS = {
    "official": ("official", "website", "contact_page", "operator_seed"),
    "registry": ("registry", "rues", "nit", "state", "government", "gov"),
    "news": ("news", "gnews", "rss", "newspaper"),
    "directory": ("directory", "dnb", "bbb", "empresite", "einforma", "map"),
    "social": ("social", "linkedin", "facebook", "twitter", "instagram", "profile"),
    "tool": ("tool", "sherlock", "maigret", "theharvester", "amass", "spiderfoot", "ghunt", "phoneinfoga", "recon", "httpx"),
    "operator": ("operator", "manual", "crm", "alibaba", "screenshot"),
}

SOURCE_FAMILY_WEIGHT = {
    "official": 3,
    "registry": 3,
    "news": 2,
    "directory": 2,
    "social": 1,
    "tool": 1,
    "operator": 1,
    "unknown": 0.5,
}

# Minimum value length for ledger substring matching to avoid false positives
_MIN_LEDGER_MATCH_LENGTH = 4
MULTI_VALUE_FIELD_KEYS = {"contact_email", "contact_phone"}


def classify_source_family(source_type: str | None, source_tool: str | None) -> str:
    text = f"{source_type or ''} {source_tool or ''}".lower()
    for family, hints in SOURCE_HINTS.items():
        if any(hint in text for hint in hints):
            return family
    return "unknown"


def build_cross_verification_matrix(detail: dict[str, Any]) -> list[dict[str, Any]]:
    entities = detail.get("entities") or []
    evidence = detail.get("evidence") or []
    ledger = detail.get("evidence_ledger") or []
    facts = detail.get("facts") or []
    ledger_by_id = {item.get("id"): item for item in ledger}
    source_families_by_value = _source_families_by_value(entities, evidence, ledger, facts)
    linked_evidence_by_value = _linked_evidence_by_value(evidence, ledger, facts)
    fact_ids_by_value = _fact_ids_by_value(facts)

    rows = []
    for field_key, label, entity_types in FIELD_DEFINITIONS:
        candidates = [
            item for item in entities
            if str(item.get("type") or "") in entity_types and str(item.get("value") or "").strip()
        ]
        facts_for_field = [
            item for item in facts
            if _fact_matches_field(item, field_key, entity_types)
        ]
        values = [str(item.get("value")) for item in candidates]
        values.extend(
            str(item.get("object") or item.get("object_value"))
            for item in facts_for_field
            if item.get("object") or item.get("object_value")
        )
        candidate_value = _best_value(values, candidates, facts_for_field)
        support = sorted(_lookup_by_comparison_value(source_families_by_value, candidate_value, field_key))
        linked_evidence_ids = sorted(_lookup_by_comparison_value(linked_evidence_by_value, candidate_value, field_key))
        linked_fact_ids = sorted(_lookup_by_comparison_value(fact_ids_by_value, candidate_value, field_key))
        best_admiralty = _best_admiralty(linked_evidence_ids, ledger_by_id)
        contradiction_sources = _contradiction_sources(values, candidate_value, candidates, field_key)
        contradiction_details = _contradiction_details(candidate_value, candidates, field_key)
        status = _row_status(candidate_value, support, contradiction_sources, facts_for_field, best_admiralty)
        confidence = _row_confidence(status, support, best_admiralty)
        rows.append(
            {
                "field_key": field_key,
                "label": label,
                "candidate_value": candidate_value,
                "supporting_sources": support,
                "contradicting_sources": sorted(contradiction_sources),
                "source_count": len(support),
                "independent_source_count": len(set(support)),
                "best_admiralty_code": best_admiralty,
                "status": status,
                "confidence": confidence,
                "linked_evidence_ids": linked_evidence_ids,
                "linked_fact_ids": linked_fact_ids,
                "rationale": _rationale(label, candidate_value, support, contradiction_sources, status, contradiction_details),
            }
        )
    return rows


def _source_families_by_value(entities: list[dict], evidence: list[dict], ledger: list[dict], facts: list[dict]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    ledger_by_id = {str(item.get("id") or ""): item for item in ledger}
    for entity in entities:
        value = str(entity.get("value") or "")
        if value:
            result[value].add(classify_source_family("", entity.get("source_tool")))
    for item in evidence:
        value = str(item.get("entity_value") or "")
        if value:
            result[value].add(classify_source_family(item.get("evidence_kind"), item.get("source_tool")))
    for item in ledger:
        snippet = str(item.get("snippet") or "")
        if not snippet:
            continue
        family = classify_source_family(item.get("source_type"), item.get("source_tool"))
        for value in list(result.keys()):
            if not value or len(value) < _MIN_LEDGER_MATCH_LENGTH:
                continue
            if re.search(r'\b' + re.escape(value) + r'\b', snippet, re.IGNORECASE):
                result[value].add(family)
    for fact in facts:
        value = str(fact.get("object") or fact.get("object_value") or "")
        if not value:
            continue
        for evidence_id in fact.get("evidence_ids") or []:
            record = ledger_by_id.get(str(evidence_id))
            if record:
                result[value].add(classify_source_family(record.get("source_type"), record.get("source_tool")))
    return result


def _linked_evidence_by_value(evidence: list[dict], ledger: list[dict], facts: list[dict]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    known_values = set()
    for item in evidence:
        value = str(item.get("entity_value") or "")
        if value and item.get("id"):
            result[value].add(str(item["id"]))
            known_values.add(value)
    for fact in facts:
        value = str(fact.get("object") or fact.get("object_value") or "")
        if not value:
            continue
        for evidence_id in fact.get("evidence_ids") or []:
            result[value].add(str(evidence_id))
            known_values.add(value)
    for item in ledger:
        snippet = str(item.get("snippet") or "")
        if not snippet:
            continue
        for value in known_values:
            if not value or len(value) < _MIN_LEDGER_MATCH_LENGTH:
                continue
            if re.search(r'\b' + re.escape(value) + r'\b', snippet, re.IGNORECASE) and item.get("id"):
                result[value].add(str(item["id"]))
    return result


def _fact_ids_by_value(facts: list[dict]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        value = str(fact.get("object") or fact.get("object_value") or "")
        if value and fact.get("id"):
            result[value].add(str(fact["id"]))
    return result


def _lookup_by_comparison_value(mapping: dict[str, set[str]], value: str, field_key: str) -> set[str]:
    if not value:
        return set()
    norm_value = _normalize_for_comparison(value, field_key)
    result: set[str] = set()
    for candidate, items in mapping.items():
        if _normalize_for_comparison(candidate, field_key) == norm_value:
            result.update(items)
    return result


def _fact_matches_field(fact: dict, field_key: str, entity_types: set[str]) -> bool:
    predicate = str(fact.get("predicate") or "").lower()
    if field_key == "company_identity" and predicate in {"identity", "has_company_identity"}:
        return True
    if field_key == "decision_maker" and predicate in {"has_decision_maker_candidate", "has_public_profile_candidate"}:
        return True
    if predicate == field_key or predicate.endswith(f"_{field_key}"):
        return True
    return predicate in {f"has_{kind}" for kind in entity_types} | {f"uses_{kind}" for kind in entity_types}


def _best_value(values: list[str], candidates: list[dict], facts: list[dict]) -> str:
    clean = [value for value in values if value and value != "None"]
    if not clean:
        return ""
    counts = Counter(clean)
    confidence_by_value: dict[str, float] = defaultdict(float)
    weighted_count_by_value: dict[str, float] = defaultdict(float)
    for item in candidates:
        value = str(item.get("value") or "")
        if value:
            confidence_by_value[value] = max(confidence_by_value[value], float(item.get("confidence") or 0))
            family = classify_source_family("", item.get("source_tool"))
            weighted_count_by_value[value] += SOURCE_FAMILY_WEIGHT.get(family, 0.5)
    for fact in facts:
        value = str(fact.get("object") or fact.get("object_value") or "")
        if value:
            confidence_by_value[value] = max(confidence_by_value[value], float(fact.get("confidence") or 0))
            weighted_count_by_value[value] += SOURCE_FAMILY_WEIGHT.get("registry", 2)
    return sorted(
        counts.items(),
        key=lambda item: (-weighted_count_by_value.get(item[0], 0), -confidence_by_value[item[0]], item[0]),
    )[0][0]


def _best_admiralty(evidence_ids: list[str], ledger_by_id: dict[str, dict]) -> str:
    codes = [str(ledger_by_id[item].get("admiralty_code") or "") for item in evidence_ids if item in ledger_by_id]
    codes = [code for code in codes if code]
    if not codes:
        return ""
    return sorted(codes)[0]


def _normalize_for_comparison(value: str, field_key: str) -> str:
    """Normalize a value for contradiction comparison to avoid false conflicts."""
    if not value:
        return ""
    if field_key == "official_website":
        return _normalize_official_website(value)
    if field_key == "contact_phone":
        return re.sub(r'[\s\-\(\)\.]+', '', value).strip()
    if field_key == "contact_email":
        return value.strip().lower()
    return value.strip().lower()


def _normalize_official_website(value: str) -> str:
    v = value.lower().strip()
    if not v:
        return ""
    parsed = urlsplit(v if "://" in v else f"//{v}")
    host = parsed.hostname or v.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _contradiction_sources(values: list[str], candidate_value: str, candidates: list[dict], field_key: str = "") -> set[str]:
    norm_candidate = _normalize_for_comparison(candidate_value, field_key)
    distinct_candidates = [
        item
        for item in candidates
        if str(item.get("value") or "")
        and _normalize_for_comparison(str(item.get("value") or ""), field_key) != norm_candidate
    ]
    if not candidate_value or not distinct_candidates:
        return set()
    contradiction_families = {
        classify_source_family("", item.get("source_tool"))
        for item in distinct_candidates
    }
    if field_key not in MULTI_VALUE_FIELD_KEYS:
        return contradiction_families
    candidate_families = {
        classify_source_family("", item.get("source_tool"))
        for item in candidates
        if _normalize_for_comparison(str(item.get("value") or ""), field_key) == norm_candidate
    }
    return contradiction_families - candidate_families


def _contradiction_details(candidate_value: str, candidates: list[dict], field_key: str) -> list[str]:
    if not candidate_value:
        return []
    norm_candidate = _normalize_for_comparison(candidate_value, field_key)
    details = []
    seen = set()
    for item in candidates:
        value = str(item.get("value") or "")
        norm_value = _normalize_for_comparison(value, field_key)
        if not value or norm_value == norm_candidate:
            continue
        family = classify_source_family("", item.get("source_tool"))
        display_value = norm_value if field_key == "official_website" else value
        detail = f"{display_value} ({family})"
        if detail not in seen:
            details.append(detail)
            seen.add(detail)
    return sorted(details)


def _row_status(
    candidate_value: str,
    support: list[str],
    contradictions: set[str],
    facts: list[dict],
    admiralty: str,
) -> str:
    if contradictions:
        return "CONFLICTED"
    if any(item.get("status") == "CONFIRMED" or item.get("promotion_stage") == "ACCEPTED_FACT" for item in facts):
        return "CONFIRMED"
    if not candidate_value:
        return "MISSING"
    if len(set(support)) >= 2:
        return "LIKELY"
    if support and ("official" in support or "registry" in support or admiralty.startswith("A-")):
        return "SUPPORTED"
    if support:
        return "CANDIDATE"
    return "NEEDS_REVIEW"


def _row_confidence(status: str, support: list[str], admiralty: str) -> float:
    base = {
        "CONFIRMED": 0.9,
        "LIKELY": 0.78,
        "SUPPORTED": 0.65,
        "CANDIDATE": 0.45,
        "NEEDS_REVIEW": 0.3,
        "CONFLICTED": 0.2,
        "MISSING": 0.0,
    }[status]
    if admiralty.startswith("A-"):
        base += 0.05
    if len(set(support)) >= 3:
        base += 0.05
    return min(1.0, round(base, 2))


def _rationale(
    label: str,
    value: str,
    support: list[str],
    contradictions: set[str],
    status: str,
    contradiction_details: list[str] | None = None,
) -> str:
    if status == "MISSING":
        return f"{label} has not been collected."
    if contradictions:
        if contradiction_details:
            return f"{label} has conflicting candidate values: {', '.join(contradiction_details)}."
        return f"{label} has conflicting candidate values across {', '.join(sorted(contradictions))} sources."
    if support:
        return f"{label} is supported by {', '.join(support)} source family evidence."
    if value:
        return f"{label} has a candidate value but no strong independent support yet."
    return f"{label} requires further collection."
