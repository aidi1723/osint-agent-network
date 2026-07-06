from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    display_name: str
    execution_mode: str
    accepts: tuple[str, ...]
    produces: tuple[str, ...]
    requires_credentials: bool
    default_timeout_seconds: int
    base_confidence: float
    enabled_by_default: bool = True


class ToolRegistry:
    def __init__(self, tools: list[ToolDefinition]):
        self._tools = {tool.name: tool for tool in tools}

    def all(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolDefinition:
        return self._tools[name]

    def accepting(self, target_type: str) -> list[ToolDefinition]:
        return [
            tool
            for tool in self._tools.values()
            if tool.enabled_by_default and target_type in tool.accepts
        ]


_cached_registry: ToolRegistry | None = None


def default_tool_registry() -> ToolRegistry:
    global _cached_registry
    if _cached_registry is not None:
        return _cached_registry
    _cached_registry = ToolRegistry(
        [
            ToolDefinition(
                name="sherlock",
                display_name="Sherlock",
                execution_mode="sync_cli",
                accepts=("username",),
                produces=("profile_url", "social_account"),
                requires_credentials=False,
                default_timeout_seconds=120,
                base_confidence=0.35,
            ),
            ToolDefinition(
                name="maigret",
                display_name="Maigret",
                execution_mode="sync_cli",
                accepts=("username",),
                produces=(
                    "social_profile",
                    "profile_url",
                    "platform_account",
                    "bio_snippet",
                    "profile_image_url",
                    "declared_location",
                    "external_link",
                ),
                requires_credentials=False,
                default_timeout_seconds=300,
                base_confidence=0.40,
            ),
            ToolDefinition(
                name="socialscan",
                display_name="socialscan",
                execution_mode="sync_cli",
                accepts=("email", "username"),
                produces=("platform_account", "social_profile", "negative_result"),
                requires_credentials=False,
                default_timeout_seconds=120,
                base_confidence=0.35,
            ),
            ToolDefinition(
                name="profile_parser",
                display_name="Public Profile Parser",
                execution_mode="artifact_parser",
                accepts=("profile_url",),
                produces=(
                    "bio_snippet",
                    "profile_image_url",
                    "declared_location",
                    "external_link",
                    "interest_tag",
                    "age_claim",
                ),
                requires_credentials=False,
                default_timeout_seconds=60,
                base_confidence=0.25,
            ),
            ToolDefinition(
                name="official_site_search",
                display_name="Official Site Search",
                execution_mode="sync_rest",
                accepts=("company", "sparse_lead"),
                produces=("url", "website_title"),
                requires_credentials=False,
                default_timeout_seconds=90,
                base_confidence=0.58,
            ),
            ToolDefinition(
                name="official_site_extractor",
                display_name="Official Site Extractor",
                execution_mode="artifact_parser",
                accepts=("url",),
                produces=("organization", "email", "phone", "address", "business_scope"),
                requires_credentials=False,
                default_timeout_seconds=60,
                base_confidence=0.72,
            ),
            ToolDefinition(
                name="theharvester",
                display_name="theHarvester",
                execution_mode="sync_cli",
                accepts=("domain",),
                produces=("email", "subdomain", "url"),
                requires_credentials=False,
                default_timeout_seconds=600,
                base_confidence=0.35,
            ),
            ToolDefinition(
                name="amass",
                display_name="OWASP Amass",
                execution_mode="async_cli",
                accepts=("domain",),
                produces=("subdomain", "ip", "dns_record"),
                requires_credentials=False,
                default_timeout_seconds=1200,
                base_confidence=0.50,
            ),
            ToolDefinition(
                name="subfinder",
                display_name="ProjectDiscovery subfinder",
                execution_mode="sync_cli",
                accepts=("domain",),
                produces=("subdomain",),
                requires_credentials=False,
                default_timeout_seconds=600,
                base_confidence=0.48,
            ),
            ToolDefinition(
                name="httpx",
                display_name="ProjectDiscovery httpx",
                execution_mode="sync_cli",
                accepts=("domain", "subdomain", "url"),
                produces=("url", "website_title", "technology"),
                requires_credentials=False,
                default_timeout_seconds=300,
                base_confidence=0.62,
            ),
            ToolDefinition(
                name="katana",
                display_name="ProjectDiscovery katana",
                execution_mode="sync_cli",
                accepts=("url",),
                produces=("url", "contact_page", "business_scope_page"),
                requires_credentials=False,
                default_timeout_seconds=600,
                base_confidence=0.50,
            ),
            ToolDefinition(
                name="spiderfoot",
                display_name="SpiderFoot",
                execution_mode="async_rest",
                accepts=("domain", "subdomain", "ip", "email", "username"),
                produces=("email", "subdomain", "ip", "profile_url", "url"),
                requires_credentials=True,
                default_timeout_seconds=1800,
                base_confidence=0.30,
            ),
            ToolDefinition(
                name="ghunt",
                display_name="GHunt",
                execution_mode="sync_cli",
                accepts=("email",),
                produces=("real_name", "profile_url", "app_footprint"),
                requires_credentials=True,
                default_timeout_seconds=180,
                base_confidence=0.55,
                enabled_by_default=False,
            ),
            ToolDefinition(
                name="phoneinfoga",
                display_name="PhoneInfoga",
                execution_mode="sync_rest",
                accepts=("phone",),
                produces=("phone", "url", "profile_url"),
                requires_credentials=False,
                default_timeout_seconds=120,
                base_confidence=0.45,
            ),
            ToolDefinition(
                name="reconng",
                display_name="Recon-ng",
                execution_mode="resource_script",
                accepts=("domain", "email", "company"),
                produces=("email", "subdomain", "contact"),
                requires_credentials=True,
                default_timeout_seconds=900,
                base_confidence=0.35,
            ),
            ToolDefinition(
                name="company_news",
                display_name="Company News",
                execution_mode="sync_cli",
                accepts=("company",),
                produces=(
                    "news_article",
                    "news_summary",
                    "published_at",
                    "external_link",
                    "news_buying_signal",
                    "news_risk_signal",
                ),
                requires_credentials=False,
                default_timeout_seconds=180,
                base_confidence=0.42,
            ),
            ToolDefinition(
                name="lead_anchor_extraction",
                display_name="Lead Anchor Extraction",
                execution_mode="artifact_parser",
                accepts=("sparse_lead",),
                produces=(
                    "platform",
                    "platform_account",
                    "platform_member_id",
                    "country_region",
                    "registration_year",
                    "company_name_raw",
                    "privacy_state",
                    "purchase_category",
                    "rfq_text",
                ),
                requires_credentials=False,
                default_timeout_seconds=30,
                base_confidence=0.90,
            ),
            ToolDefinition(
                name="customs_supply_chain",
                display_name="海关供应链分析",
                execution_mode="sync_rest",
                accepts=("company",),
                produces=(
                    "company",
                    "supplier_to_customer",
                    "trade_relationship",
                    "trade_partner",
                ),
                requires_credentials=True,
                default_timeout_seconds=60,
                base_confidence=0.85,
            ),
        ]
    )
    return _cached_registry
