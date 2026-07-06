from __future__ import annotations

from app.core.intelligence_memory import build_intelligence_memory
from app.core.planner import PlannedJob


GAP_EXPLANATIONS = {
    "official_website": {
        "label": "Official website",
        "current_state": "No accepted official website or domain is linked to the target.",
        "missing_evidence": [
            "Official domain or URL tied to the target",
            "Page title or snippet showing target identity",
            "Source URL for review",
        ],
        "why_it_matters": "The task cannot be completed confidently without an official source boundary.",
        "manual_review_hint": "Inspect the company website, public registry, or trusted directory if automated search remains inconclusive.",
    },
    "decision_maker": {
        "label": "Decision maker candidate",
        "current_state": "No accepted person, title, or profile evidence is linked to the company.",
        "missing_evidence": [
            "Official team/about/contact page naming a responsible person",
            "Public profile or news item linking the person to the company",
            "Independent evidence for title or purchasing authority",
        ],
        "why_it_matters": "The task cannot be completed without a reviewable responsible person or role for commercial follow-up.",
        "manual_review_hint": "If automated tools do not find a public profile, inspect the company website, public directories, or CRM context.",
    },
    "contact_channel": {
        "label": "Contact channel",
        "current_state": "No accepted email or phone channel is linked to the target.",
        "missing_evidence": [
            "Email or phone visible on an official or high-quality source",
            "Source URL connecting the contact to the target",
        ],
        "why_it_matters": "Commercial follow-up requires a contact channel with provenance.",
        "manual_review_hint": "Review contact, footer, privacy, and support pages manually if extraction fails.",
    },
    "contact_email": {
        "label": "Contact email",
        "current_state": "No accepted email is linked to the target.",
        "missing_evidence": [
            "Email visible on an official or high-quality source",
            "Source URL connecting the email to the target",
        ],
        "why_it_matters": "Email evidence gives the operator a reviewable follow-up channel.",
        "manual_review_hint": "Review contact pages, footers, public directories, and source snippets manually.",
    },
    "contact_phone": {
        "label": "Contact phone",
        "current_state": "No accepted phone or WhatsApp channel is linked to the target.",
        "missing_evidence": [
            "Phone or WhatsApp visible on an official or high-quality source",
            "Source URL connecting the number to the target",
        ],
        "why_it_matters": "Phone evidence gives the operator a reviewable direct contact channel.",
        "manual_review_hint": "Review contact pages, footers, public directories, and source snippets manually.",
    },
    "business_scope": {
        "label": "Business scope",
        "current_state": "No accepted business or product scope is linked to the target.",
        "missing_evidence": [
            "Official product or service description",
            "Source-backed category or business scope",
        ],
        "why_it_matters": "The system needs scope evidence to judge relevance and buying fit.",
        "manual_review_hint": "Review product pages, company profiles, RFQs, and public catalogs.",
    },
    "operation_location": {
        "label": "Operation location",
        "current_state": "No accepted address or operating region is linked to the target.",
        "missing_evidence": [
            "Address, country, or operating region from a reviewable source",
            "Source URL or source type supporting the location",
        ],
        "why_it_matters": "Location evidence helps validate identity, logistics, and regional buying fit.",
        "manual_review_hint": "Review about, contact, legal, registry, and public profile pages.",
    },
    "purchase_intent": {
        "label": "Purchase intent",
        "current_state": "No accepted buying signal is linked to the target.",
        "missing_evidence": [
            "RFQ, news, procurement, category match, or business event",
            "Freshness marker or source date when available",
        ],
        "why_it_matters": "Buying intent evidence helps distinguish a real lead from a generic company profile.",
        "manual_review_hint": "Review RFQ context, recent news, trade records, and CRM notes.",
    },
    "cross_verification": {
        "label": "Cross verification",
        "current_state": "No confirmed, likely, or supported matrix row is available.",
        "missing_evidence": [
            "At least one matrix row linked to facts or evidence",
            "Source-family comparison or confidence rationale",
        ],
        "why_it_matters": "The quality gate needs verification, not only raw collection.",
        "manual_review_hint": "Review conflicts, duplicates, and source rankings before accepting claims.",
    },
    "evidence_ledger": {
        "label": "Evidence ledger",
        "current_state": "No source-backed evidence ledger records are available.",
        "missing_evidence": [
            "Evidence record with source URL or source type",
            "Snippet and source tool provenance",
        ],
        "why_it_matters": "Reports must remain grounded in reviewable evidence.",
        "manual_review_hint": "Collect source-backed records before treating findings as facts.",
    },
    "fact_pool": {
        "label": "Fact pool",
        "current_state": "No source-backed facts are available.",
        "missing_evidence": [
            "Fact statement linked to evidence IDs",
            "Status and confidence for each factual claim",
        ],
        "why_it_matters": "The final report needs structured facts rather than raw tool output.",
        "manual_review_hint": "Promote only source-backed claims into facts after review.",
    },
}


GAP_JOB_TEMPLATES = {
    "decision_maker": (
        ("social_profile_search", "social_intel_agent", "entities,evidence,relationships: public_profiles, role_candidates, identity_match_signals"),
        ("contact_discovery", "contact_discovery_agent", "entities,evidence,relationships: public_contacts, contact_pages, ownership_boundaries"),
    ),
    "news": (
        ("company_news", "tool_agent", "entities,evidence,relationships"),
        ("company_news_monitoring", "news_intel_agent", "entities,evidence,relationships,claims: business_events, buying_signals, risk_signals"),
    ),
    "business_scope": (
        ("company_osint", "enterprise_intel_agent", "entities,evidence,relationships: company_identity, website, business_scope, product_scope"),
    ),
    "operation_footprint": (
        ("company_osint", "enterprise_intel_agent", "entities,evidence,relationships: address, operating_regions, production_base"),
        ("supply_chain_mapping", "supply_chain_agent", "entities,evidence,relationships: upstream, downstream, partners, manufacturing_footprint"),
    ),
    "risk_signals": (
        ("company_news_monitoring", "news_intel_agent", "entities,evidence,relationships,claims: litigation, disputes, negative_news, contradiction_signals"),
        ("cross_verification", "cross_verification_agent", "claims,evidence,relationships: conflicts, source_rank, confidence_adjustments"),
    ),
}

SPARSE_LEAD_GAP_JOB_TEMPLATES = {
    **GAP_JOB_TEMPLATES,
    "business_scope": (
        ("candidate_business_discovery", "enterprise_intel_agent", "entities,evidence,relationships: candidate companies, public records, websites, business_scope"),
        ("rfq_category_analysis", "purchase_intent_agent", "entities,evidence,claims: purchase categories, RFQ intent signals, RFQ noise signals"),
    ),
    "operation_footprint": (
        ("candidate_business_discovery", "enterprise_intel_agent", "entities,evidence,relationships: candidate addresses, public records, operating_regions"),
        ("supply_chain_mapping", "supply_chain_agent", "entities,evidence,relationships: upstream, downstream, operating_footprint"),
    ),
}


def build_gap_analysis(detail: dict) -> list[dict]:
    assessment = detail.get("quality_assessment") or {}
    missing_keys = list(assessment.get("missing_keys") or [])
    blocking_keys = set(assessment.get("blocking_keys") or [])
    memory_gaps = (detail.get("intelligence_memory") or {}).get("collection_gaps") or []
    for gap in memory_gaps:
        key = str(gap.get("key") or "").strip()
        if key and key not in missing_keys:
            missing_keys.append(key)

    results = []
    for key in missing_keys:
        template = GAP_EXPLANATIONS.get(key)
        severity = "blocking" if key in blocking_keys else "important"
        if template is None:
            results.append(
                {
                    "gap_key": key,
                    "label": key.replace("_", " ").title(),
                    "severity": severity,
                    "current_state": "No deterministic gap explanation is registered for this key.",
                    "missing_evidence": ["Operator-defined evidence is required."],
                    "why_it_matters": "The quality gate cannot treat this gap as resolved without reviewable evidence.",
                    "manual_review_hint": "Manual review is required because no automatic tool mapping exists yet.",
                }
            )
            continue
        results.append({"gap_key": key, "severity": severity, **template})
    return results


def plan_gap_followup_jobs(detail: dict) -> list[PlannedJob]:
    memory = detail.get("intelligence_memory") or build_intelligence_memory(detail)
    gaps = memory.get("collection_gaps") or []
    if not gaps:
        return []

    seed_type = str(detail.get("seed_type") or "company")
    seed_value = str(detail.get("seed_value") or "")
    existing_gap_job_keys = {
        (str(job.get("tool_name") or ""), str(job.get("target_type") or ""), str(job.get("target_value") or ""), token)
        for job in detail.get("jobs", [])
        for token in str(job.get("depends_on") or "").split(";")
        if token.startswith("gap:")
    }
    existing_gap_tokens = {
        token
        for job in detail.get("jobs", [])
        for token in str(job.get("depends_on") or "").split(";")
        if token.startswith("gap:")
    }
    planned: list[PlannedJob] = []
    templates_by_gap = SPARSE_LEAD_GAP_JOB_TEMPLATES if seed_type == "sparse_lead" else GAP_JOB_TEMPLATES
    for gap in gaps:
        gap_key = str(gap.get("key") or "")
        gap_token = f"gap:{gap_key}"
        if gap_token in existing_gap_tokens:
            continue
        for tool_name, agent_role, output_contract in templates_by_gap.get(gap_key, ()):
            target_type = "company" if tool_name == "company_news" else seed_type
            target_value = seed_value
            key = (tool_name, target_type, target_value, gap_token)
            if key in existing_gap_job_keys:
                continue
            existing_gap_job_keys.add(key)
            planned.append(
                PlannedJob(
                    tool_name=tool_name,
                    target_type=target_type,
                    target_value=target_value,
                    depth=3,
                    agent_role=agent_role,
                    output_contract=output_contract,
                    depends_on=f"completed:analysis_judgement;{gap_token}",
                )
            )

    verifier_tool = "identity_match_review" if seed_type == "sparse_lead" else "cross_verification"
    if planned and not any(job.tool_name == verifier_tool for job in planned):
        planned.append(
            PlannedJob(
                tool_name=verifier_tool,
                target_type=seed_type,
                target_value=seed_value,
                depth=4,
                agent_role="cross_verification_agent",
                output_contract="claims,evidence,relationships: gap_followup_verification, confidence_adjustments",
                depends_on=";".join(["completed:analysis_judgement", "gap:verification"]),
            )
        )

    if planned:
        planned.append(
            PlannedJob(
                tool_name="analysis_judgement",
                target_type=seed_type,
                target_value=seed_value,
                depth=5,
                agent_role="analysis_judgement_agent",
                output_contract="claims,graph_slots,report: updated PIR, ACH, BLUF, risk_summary, directed_collection",
                depends_on=";".join(["cross_verification", "identity_match_review", "gap:reanalyze"]),
            )
        )
    return planned
