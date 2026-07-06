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


GAP_TOOL_MAPPINGS = {
    "official_website": (
        {
            "tool_name": "official_site_search",
            "agent_role": "tool_agent",
            "target_type": "seed",
            "reason": "Find official website candidates before crawling pages.",
            "expected_evidence": ["official_site_candidate", "website_title", "source_snippet"],
        },
        {
            "tool_name": "httpx",
            "agent_role": "tool_agent",
            "target_type": "domain",
            "reason": "Probe candidate domains or URLs for live official website evidence.",
            "expected_evidence": ["live_url", "title", "technology"],
        },
        {
            "tool_name": "katana",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Crawl candidate pages for contact, about, and business evidence.",
            "expected_evidence": ["business_page_url", "contact_page_url"],
        },
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract identity, contact, scope, and decision-maker evidence from official pages.",
            "expected_evidence": ["company_identity", "contact", "business_scope"],
        },
    ),
    "decision_maker": (
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract people, titles, and contact roles from official pages.",
            "expected_evidence": ["person_name", "job_title", "official_page_url"],
        },
        {
            "tool_name": "social_profile_search",
            "agent_role": "social_intel_agent",
            "target_type": "seed",
            "reason": "Find public profiles that may identify responsible people.",
            "expected_evidence": ["profile_url", "person_name", "company_link"],
        },
        {
            "tool_name": "company_news",
            "agent_role": "tool_agent",
            "target_type": "company",
            "reason": "Search public news for executives, managers, and buying signals.",
            "expected_evidence": ["news_url", "person_name", "role_or_quote"],
        },
    ),
    "contact_channel": (
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract email and phone evidence from official pages.",
            "expected_evidence": ["email", "phone", "source_url"],
        },
        {
            "tool_name": "contact_discovery",
            "agent_role": "contact_discovery_agent",
            "target_type": "seed",
            "reason": "Use role-agent contact discovery to collect public contact pages and ownership boundaries.",
            "expected_evidence": ["verified_email", "verified_phone", "contact_page"],
        },
        {
            "tool_name": "theharvester",
            "agent_role": "tool_agent",
            "target_type": "domain",
            "reason": "Collect public emails and domain-linked contacts when a domain is known.",
            "expected_evidence": ["email", "domain_source"],
        },
    ),
    "contact_email": (
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract email evidence from official pages.",
            "expected_evidence": ["email", "source_url"],
        },
        {
            "tool_name": "theharvester",
            "agent_role": "tool_agent",
            "target_type": "domain",
            "reason": "Collect public emails linked to a known domain.",
            "expected_evidence": ["email", "domain_source"],
        },
    ),
    "contact_phone": (
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract phone or WhatsApp evidence from official pages.",
            "expected_evidence": ["phone", "whatsapp", "source_url"],
        },
        {
            "tool_name": "contact_discovery",
            "agent_role": "contact_discovery_agent",
            "target_type": "seed",
            "reason": "Use role-agent contact discovery to collect public phone channels.",
            "expected_evidence": ["verified_phone", "contact_page"],
        },
    ),
    "business_scope": (
        {
            "tool_name": "company_osint",
            "agent_role": "enterprise_intel_agent",
            "target_type": "seed",
            "reason": "Collect company identity, public records, website, and business scope.",
            "expected_evidence": ["business_scope", "product_scope", "source_url"],
        },
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract product and service scope from official pages.",
            "expected_evidence": ["product_scope", "business_scope"],
        },
    ),
    "operation_location": (
        {
            "tool_name": "company_osint",
            "agent_role": "enterprise_intel_agent",
            "target_type": "seed",
            "reason": "Collect address and operating-region evidence.",
            "expected_evidence": ["address", "operating_region", "source_url"],
        },
        {
            "tool_name": "official_site_extractor",
            "agent_role": "tool_agent",
            "target_type": "url",
            "reason": "Extract address or regional footprint from official pages.",
            "expected_evidence": ["address", "country_region"],
        },
    ),
    "purchase_intent": (
        {
            "tool_name": "purchase_intent_assessment",
            "agent_role": "purchase_intent_agent",
            "target_type": "seed",
            "reason": "Assess public buying signals and category fit.",
            "expected_evidence": ["buying_signal", "category_fit", "source_url"],
        },
        {
            "tool_name": "company_news_monitoring",
            "agent_role": "news_intel_agent",
            "target_type": "seed",
            "reason": "Search recent public events for procurement or expansion signals.",
            "expected_evidence": ["news_url", "business_event", "buying_signal"],
        },
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


def build_gap_tool_plan(detail: dict, tool_health_by_name: dict[str, dict] | None = None) -> list[dict]:
    tool_health_by_name = tool_health_by_name or {}
    seed_type = str(detail.get("seed_type") or "company")
    seed_value = str(detail.get("seed_value") or "")
    existing = {
        (
            str(job.get("tool_name") or ""),
            str(job.get("target_type") or ""),
            str(job.get("target_value") or ""),
            str(job.get("depends_on") or ""),
        )
        for job in detail.get("jobs", [])
    }
    existing_simple = {(tool_name, target_type, target_value) for tool_name, target_type, target_value, _depends_on in existing}
    plan = []
    for gap in build_gap_analysis(detail):
        gap_key = gap["gap_key"]
        for mapping in GAP_TOOL_MAPPINGS.get(gap_key, ()):
            target_type = _gap_mapping_target_type(str(mapping["target_type"]), seed_type)
            for target_value in _gap_mapping_target_values(target_type, seed_type, seed_value, detail):
                depends_on = f"completed:analysis_judgement;gap:{gap_key}"
                health = tool_health_by_name.get(str(mapping["tool_name"]), {})
                status = str(health.get("status") or "ready")
                if (
                    (str(mapping["tool_name"]), target_type, target_value, depends_on) in existing
                    or (str(mapping["tool_name"]), target_type, target_value) in existing_simple
                ):
                    status = "already_attempted"
                plan.append(
                    {
                        "gap_key": gap_key,
                        "tool_name": mapping["tool_name"],
                        "agent_role": mapping["agent_role"],
                        "target_type": target_type,
                        "target_value": target_value,
                        "status": status,
                        "reason": mapping["reason"],
                        "expected_evidence": list(mapping["expected_evidence"]),
                        "depends_on": depends_on,
                        "health_reason": str(health.get("reason") or ""),
                    }
                )
    return plan


def _gap_mapping_target_type(value: str, seed_type: str) -> str:
    if value == "seed":
        return seed_type
    return value


def _gap_mapping_target_values(target_type: str, seed_type: str, seed_value: str, detail: dict) -> list[str]:
    if target_type in {seed_type, "company", "sparse_lead"}:
        return [seed_value] if seed_value else []
    accepted_types = {
        "domain": {"domain"},
        "url": {"url", "website", "official_website"},
        "profile_url": {"profile_url"},
    }.get(target_type, {target_type})
    values = []
    seen = set()
    for entity in detail.get("entities") or []:
        entity_type = str(entity.get("type") or "")
        value = str(entity.get("value") or "").strip()
        if not value or entity_type not in accepted_types or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def plan_gap_followup_jobs(detail: dict, tool_health_by_name: dict[str, dict] | None = None) -> list[PlannedJob]:
    if tool_health_by_name is not None:
        tool_plan = build_gap_tool_plan(detail, tool_health_by_name=tool_health_by_name)
        ready_items = [item for item in tool_plan if item["status"] == "ready"]
        if ready_items:
            planned = [
                PlannedJob(
                    tool_name=item["tool_name"],
                    target_type=item["target_type"],
                    target_value=item["target_value"],
                    depth=3,
                    agent_role=item["agent_role"],
                    output_contract="entities,evidence,relationships",
                    depends_on=item["depends_on"],
                )
                for item in ready_items
            ]
            seed_type = str(detail.get("seed_type") or "company")
            seed_value = str(detail.get("seed_value") or "")
            planned.append(
                PlannedJob(
                    tool_name="identity_match_review" if seed_type == "sparse_lead" else "cross_verification",
                    target_type=seed_type,
                    target_value=seed_value,
                    depth=4,
                    agent_role="cross_verification_agent",
                    output_contract="claims,evidence,relationships: gap_followup_verification, confidence_adjustments",
                    depends_on="completed:analysis_judgement;gap:verification",
                )
            )
            planned.append(
                PlannedJob(
                    tool_name="analysis_judgement",
                    target_type=seed_type,
                    target_value=seed_value,
                    depth=5,
                    agent_role="analysis_judgement_agent",
                    output_contract="claims,graph_slots,report: updated PIR, ACH, BLUF, risk_summary, directed_collection",
                    depends_on="cross_verification;identity_match_review;gap:reanalyze",
                )
            )
            return planned

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
