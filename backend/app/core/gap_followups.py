from __future__ import annotations

from app.core.intelligence_memory import build_intelligence_memory
from app.core.planner import PlannedJob


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
