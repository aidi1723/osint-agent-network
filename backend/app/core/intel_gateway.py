from __future__ import annotations

from dataclasses import dataclass
import os

from app.core.normalization import normalize_target
from app.core.registry import ToolRegistry, default_tool_registry
from app.core.tool_health import CREDENTIAL_BLOCKED, MISSING_CONFIG, MISSING_EXECUTABLE, build_tool_health_report


@dataclass(frozen=True)
class IntelRoute:
    tool_name: str
    target_type: str
    target_value: str
    priority: int
    agent_role: str = "tool_agent"
    output_contract: str = "entities,evidence,relationships"
    depends_on: str = ""
    source_tier: str = "open_source_tool"
    skip_reason: str = ""


@dataclass(frozen=True)
class IntelPlan:
    target_type: str
    target_value: str
    strategy_name: str
    routes: list[IntelRoute]
    skipped_routes: list[IntelRoute]


@dataclass(frozen=True)
class _RouteTemplate:
    tool_name: str
    source_tier: str = "open_source_tool"
    agent_role: str = "tool_agent"
    output_contract: str = "entities,evidence,relationships"
    depends_on: str = ""
    required_config: tuple[str, ...] = ()


ROUTE_MATRIX: dict[str, tuple[_RouteTemplate, ...]] = {
    "username": (
        _RouteTemplate("sherlock", "account_existence"),
        _RouteTemplate("maigret", "profile_dossier"),
        _RouteTemplate("socialscan", "account_existence"),
    ),
    "email": (
        _RouteTemplate("socialscan", "account_existence"),
        _RouteTemplate("spiderfoot", "passive_enrichment", required_config=("SPIDERFOOT_BASE_URL",)),
        _RouteTemplate("reconng", "passive_enrichment", required_config=("RECONNG_COMMAND",)),
        _RouteTemplate("ghunt", "credentialed_google_enrichment", required_config=("GHUNT_COOKIE_PATH",)),
    ),
    "phone": (
        _RouteTemplate("phoneinfoga", "phone_metadata", required_config=("PHONEINFOGA_BASE_URL",)),
    ),
    "domain": (
        _RouteTemplate("theharvester", "domain_discovery"),
        _RouteTemplate("subfinder", "passive_subdomain_discovery"),
        _RouteTemplate("amass", "dns_discovery"),
        _RouteTemplate("httpx", "http_probe"),
        _RouteTemplate("spiderfoot", "passive_enrichment", required_config=("SPIDERFOOT_BASE_URL",)),
        _RouteTemplate("reconng", "passive_enrichment", required_config=("RECONNG_COMMAND",)),
    ),
    "subdomain": (
        _RouteTemplate("httpx", "http_probe"),
        _RouteTemplate("amass", "dns_discovery"),
        _RouteTemplate("spiderfoot", "passive_enrichment", required_config=("SPIDERFOOT_BASE_URL",)),
    ),
    "url": (
        _RouteTemplate("httpx", "http_probe"),
        _RouteTemplate("katana", "site_crawl"),
        _RouteTemplate("official_site_extractor", "official_site_extraction"),
    ),
    "profile_url": (
        _RouteTemplate("profile_parser", "profile_metadata"),
    ),
}

COMPANY_ROUTE_MATRIX: tuple[_RouteTemplate, ...] = (
    _RouteTemplate(
        "company_osint",
        "role_agent",
        agent_role="enterprise_intel_agent",
        output_contract="entities,evidence,relationships: company_name, website, phone, email, address, business_scope",
    ),
    _RouteTemplate(
        "social_profile_search",
        "role_agent",
        agent_role="social_intel_agent",
        output_contract="entities,evidence,relationships: public_profiles, bio_snippets, locations, associated_links",
    ),
    _RouteTemplate(
        "contact_discovery",
        "role_agent",
        agent_role="contact_discovery_agent",
        output_contract="entities,evidence,relationships: verified_phones, emails, contact_pages, ownership_boundaries",
    ),
    _RouteTemplate(
        "supply_chain_mapping",
        "role_agent",
        agent_role="supply_chain_agent",
        output_contract="entities,evidence,relationships: upstream, downstream, partners, shared_addresses, industry_neighbors",
    ),
    _RouteTemplate(
        "purchase_intent_assessment",
        "role_agent",
        agent_role="purchase_intent_agent",
        output_contract="entities,evidence,claims: purchase_category, demand_fit, procurement_stage, buying_signals",
    ),
    _RouteTemplate("company_news", "news_discovery"),
    _RouteTemplate(
        "official_site_search",
        "official_site_discovery",
        output_contract="entities,evidence,relationships: official_site_candidates, website_titles, source_snippets",
        required_config=("OFFICIAL_SITE_SEARCH_BASE_URL",),
    ),
    _RouteTemplate(
        "company_news_monitoring",
        "role_agent",
        agent_role="news_intel_agent",
        output_contract="entities,evidence,relationships,claims: news_title, published_at, source_media, news_url, business_event, risk_signal, buying_signal",
    ),
    _RouteTemplate(
        "cross_verification",
        "analysis_agent",
        agent_role="cross_verification_agent",
        output_contract=(
            "claims,evidence,relationships: conflicts, duplicate_entities, source_rank, "
            "admiralty_code, confidence_adjustments, deception_noise_check"
        ),
        depends_on="enterprise_intel,social_intel,contact_discovery,supply_chain,purchase_intent,news_intel",
    ),
    _RouteTemplate(
        "analysis_judgement",
        "analysis_agent",
        agent_role="analysis_judgement_agent",
        output_contract=(
            "claims,graph_slots,report: PIR, ACH, BLUF, estimative_language, buyer_rating, "
            "risk_summary, followup_recommendation, directed_collection, mature_profile"
        ),
        depends_on="cross_verification",
    ),
)

SPARSE_LEAD_ROUTE_MATRIX: tuple[_RouteTemplate, ...] = (
    _RouteTemplate(
        "lead_anchor_extraction",
        "lead_intake",
        output_contract="entities,evidence,relationships: platform anchors, visible buyer fields, privacy state",
    ),
    _RouteTemplate(
        "constrained_query_planning",
        "search_planning",
        agent_role="search_planning_agent",
        output_contract="claims,evidence: constrained query matrix, exclusion notes, search priority",
        depends_on="lead_anchor_extraction",
    ),
    _RouteTemplate(
        "candidate_business_discovery",
        "role_agent",
        agent_role="enterprise_intel_agent",
        output_contract="entities,evidence,relationships: candidate companies, public records, websites, business scope",
        depends_on="constrained_query_planning",
    ),
    _RouteTemplate(
        "official_site_search",
        "official_site_discovery",
        output_contract="entities,evidence,relationships: official_site_candidates, website_titles, source_snippets",
        depends_on="candidate_business_discovery",
        required_config=("OFFICIAL_SITE_SEARCH_BASE_URL",),
    ),
    _RouteTemplate(
        "rfq_category_analysis",
        "role_agent",
        agent_role="purchase_intent_agent",
        output_contract="entities,evidence,claims: purchase categories, RFQ intent signals, RFQ noise signals",
        depends_on="lead_anchor_extraction",
    ),
    _RouteTemplate(
        "identity_match_review",
        "analysis_agent",
        agent_role="cross_verification_agent",
        output_contract=(
            "claims,evidence,relationships: record_confidence, identity_match_confidence, "
            "field_interpretation_confidence, candidate_status, mismatch_signals"
        ),
        depends_on="candidate_business_discovery,rfq_category_analysis",
    ),
    _RouteTemplate(
        "analysis_judgement",
        "analysis_agent",
        agent_role="analysis_judgement_agent",
        output_contract="claims,graph_slots,report: PIR, ACH, BLUF, risk_summary, directed_collection",
        depends_on="identity_match_review",
    ),
)

QUICK_TOOL_ALLOWLIST = {
    "sherlock",
    "theharvester",
    "subfinder",
    "httpx",
    "katana",
    "official_site_extractor",
    "phoneinfoga",
    "socialscan",
}
STANDARD_EXCLUDED_TOOLS = {"reconng"}


def build_intel_plan(
    target_type: str,
    target_value: str,
    strategy_name: str,
    registry: ToolRegistry | None = None,
    runtime_env: dict[str, str] | None = None,
    respect_tool_health: bool = False,
) -> IntelPlan:
    registry = registry or default_tool_registry()
    runtime_env = os.environ if runtime_env is None else runtime_env
    normalized_value = normalize_target(target_type, target_value)
    health_by_tool = (
        {
            item["name"]: item
            for item in build_tool_health_report(registry=registry, env=runtime_env).get("tools", [])
        }
        if respect_tool_health
        else {}
    )

    templates = _templates_for(target_type, strategy_name)
    routes: list[IntelRoute] = []
    skipped: list[IntelRoute] = []
    for priority, template in enumerate(templates, start=1):
        route = _route_from_template(template, target_type, normalized_value, priority)
        skip_reason = _skip_reason(route, template, registry, runtime_env, health_by_tool)
        if skip_reason:
            skipped.append(_with_skip_reason(route, skip_reason))
        else:
            routes.append(route)

    return IntelPlan(
        target_type=target_type,
        target_value=normalized_value,
        strategy_name=strategy_name,
        routes=routes,
        skipped_routes=skipped,
    )


def _templates_for(target_type: str, strategy_name: str) -> tuple[_RouteTemplate, ...]:
    if target_type == "company":
        if strategy_name == "quick":
            return (COMPANY_ROUTE_MATRIX[0], COMPANY_ROUTE_MATRIX[2], COMPANY_ROUTE_MATRIX[-1])
        if strategy_name == "standard":
            return (*COMPANY_ROUTE_MATRIX[:5], COMPANY_ROUTE_MATRIX[6], COMPANY_ROUTE_MATRIX[-1])
        return COMPANY_ROUTE_MATRIX
    if target_type == "sparse_lead":
        if strategy_name == "quick":
            return (
                SPARSE_LEAD_ROUTE_MATRIX[0],
                SPARSE_LEAD_ROUTE_MATRIX[1],
                SPARSE_LEAD_ROUTE_MATRIX[-1],
            )
        if strategy_name == "standard":
            return (
                SPARSE_LEAD_ROUTE_MATRIX[0],
                SPARSE_LEAD_ROUTE_MATRIX[1],
                SPARSE_LEAD_ROUTE_MATRIX[2],
                SPARSE_LEAD_ROUTE_MATRIX[3],
                SPARSE_LEAD_ROUTE_MATRIX[5],
                SPARSE_LEAD_ROUTE_MATRIX[-1],
            )
        return SPARSE_LEAD_ROUTE_MATRIX
    templates = ROUTE_MATRIX.get(target_type, ())
    if strategy_name == "quick":
        return tuple(template for template in templates if template.tool_name in QUICK_TOOL_ALLOWLIST)
    if strategy_name == "standard":
        return tuple(template for template in templates if template.tool_name not in STANDARD_EXCLUDED_TOOLS)
    return templates


def _route_from_template(template: _RouteTemplate, target_type: str, target_value: str, priority: int) -> IntelRoute:
    return IntelRoute(
        tool_name=template.tool_name,
        target_type=target_type,
        target_value=target_value,
        priority=priority,
        agent_role=template.agent_role,
        output_contract=template.output_contract,
        depends_on=template.depends_on,
        source_tier=template.source_tier,
    )


def _skip_reason(
    route: IntelRoute,
    template: _RouteTemplate,
    registry: ToolRegistry,
    runtime_env,
    health_by_tool: dict[str, dict],
) -> str:
    if route.agent_role != "tool_agent":
        return ""
    try:
        tool = registry.get(route.tool_name)
    except KeyError:
        return "missing_tool_definition"
    if not tool.enabled_by_default and route.tool_name != "ghunt":
        return "disabled_by_default"
    if route.target_type not in tool.accepts:
        return "target_not_accepted"
    for key in template.required_config:
        if not str(runtime_env.get(key, "")).strip():
            return f"missing_config:{key}"
    health_skip = _tool_health_skip_reason(route, health_by_tool)
    if health_skip:
        return health_skip
    return ""


def _tool_health_skip_reason(route: IntelRoute, health_by_tool: dict[str, dict]) -> str:
    item = health_by_tool.get(route.tool_name)
    if not item:
        return ""
    status = str(item.get("status") or "")
    if status not in {MISSING_CONFIG, MISSING_EXECUTABLE, CREDENTIAL_BLOCKED}:
        return ""
    reason = str(item.get("reason") or status)
    return f"tool_unavailable:{status}:{reason}"


def _with_skip_reason(route: IntelRoute, skip_reason: str) -> IntelRoute:
    return IntelRoute(
        tool_name=route.tool_name,
        target_type=route.target_type,
        target_value=route.target_value,
        priority=route.priority,
        agent_role=route.agent_role,
        output_contract=route.output_contract,
        depends_on=route.depends_on,
        source_tier=route.source_tier,
        skip_reason=skip_reason,
    )
