import unittest

from app.core.normalization import normalize_target, NormalizationError
from app.core.registry import default_tool_registry
from app.core.social_risk import build_social_risk_report
from app.core.verification import (
    EvidenceSignal,
    admiralty_code,
    estimate_probability_language,
    score_entity,
)
from app.core.planner import StrategyProfile, plan_initial_jobs, plan_followup_jobs
from app.core.inference import plan_progressive_jobs


class NormalizationTests(unittest.TestCase):
    def test_normalizes_domains_emails_usernames_and_phones(self):
        self.assertEqual(normalize_target("domain", " Example.COM "), "example.com")
        self.assertEqual(normalize_target("email", " Admin@Example.COM "), "admin@example.com")
        self.assertEqual(normalize_target("username", " Admin_007 "), "Admin_007")
        self.assertEqual(normalize_target("phone", " +63 917-123-4567 "), "+639171234567")

    def test_normalizes_public_profile_urls(self):
        self.assertEqual(
            normalize_target("profile_url", " https://github.com/Admin?tab=repositories "),
            "https://github.com/Admin",
        )
        self.assertEqual(
            normalize_target("url", "https://example.com/path?utm_source=test"),
            "https://example.com/path",
        )

    def test_rejects_private_or_non_http_profile_urls(self):
        with self.assertRaises(NormalizationError):
            normalize_target("profile_url", "javascript:alert(1)")
        with self.assertRaises(NormalizationError):
            normalize_target("profile_url", "http://localhost/admin")

    def test_normalizes_sparse_lead_human_readable_seed(self):
        self.assertEqual(
            normalize_target("sparse_lead", "  Sample Lead / member-redacted  "),
            "Sample Lead / member-redacted",
        )

        with self.assertRaises(NormalizationError):
            normalize_target("sparse_lead", "x" * 501)

    def test_rejects_unsafe_username(self):
        with self.assertRaises(NormalizationError):
            normalize_target("username", "admin;rm")


class RegistryTests(unittest.TestCase):
    def test_registry_selects_tools_for_domain_and_username(self):
        registry = default_tool_registry()

        domain_tools = {tool.name for tool in registry.accepting("domain")}
        username_tools = {tool.name for tool in registry.accepting("username")}

        self.assertIn("theharvester", domain_tools)
        self.assertIn("amass", domain_tools)
        self.assertIn("sherlock", username_tools)
        self.assertNotIn("amass", username_tools)

    def test_registry_selects_social_enrichment_tools(self):
        registry = default_tool_registry()

        username_tools = {tool.name for tool in registry.accepting("username")}
        email_tools = {tool.name for tool in registry.accepting("email")}
        profile_tools = {tool.name for tool in registry.accepting("profile_url")}

        self.assertIn("maigret", username_tools)
        self.assertIn("socialscan", username_tools)
        self.assertIn("socialscan", email_tools)
        self.assertIn("profile_parser", profile_tools)


class VerificationTests(unittest.TestCase):
    def test_admiralty_code_combines_source_reliability_and_information_credibility(self):
        result = admiralty_code(source_reliability="official_website", credibility=0.84)

        self.assertEqual(result["code"], "A-2")
        self.assertEqual(result["source_reliability"], "A")
        self.assertEqual(result["information_credibility"], "2")
        self.assertEqual(result["probability_language"], "很有可能")

    def test_probability_language_uses_estimate_ranges(self):
        self.assertEqual(estimate_probability_language(0.93), "几乎可以肯定")
        self.assertEqual(estimate_probability_language(0.72), "很有可能")
        self.assertEqual(estimate_probability_language(0.55), "有可能")
        self.assertEqual(estimate_probability_language(0.35), "可能性较低")
        self.assertEqual(estimate_probability_language(0.12), "很不可能")

    def test_scores_cross_verified_asset_higher_than_single_noisy_hit(self):
        strong = score_entity(
            base_prior=0.1,
            signals=[
                EvidenceSignal(tool="amass", kind="tool_hit", weight=0.50),
                EvidenceSignal(tool="theharvester", kind="tool_hit", weight=0.30),
                EvidenceSignal(tool="dns", kind="dns_resolves", weight=0.25),
            ],
        )
        weak = score_entity(
            base_prior=0.1,
            signals=[EvidenceSignal(tool="sherlock", kind="profile_exists", weight=0.35)],
        )

        self.assertEqual(strong.status, "VERIFIED")
        self.assertEqual(weak.status, "WEAK")
        self.assertGreater(strong.score, weak.score)

    def test_negative_evidence_can_contradict_positive_signal(self):
        result = score_entity(
            base_prior=0.1,
            signals=[
                EvidenceSignal(tool="sherlock", kind="profile_exists", weight=0.35),
                EvidenceSignal(tool="ghunt", kind="negative_result", weight=-0.45, negative=True),
            ],
        )

        self.assertEqual(result.status, "CONTRADICTED")
        self.assertLess(result.score, 0.35)


class SocialRiskTests(unittest.TestCase):
    def test_builds_category_scores_and_top_signals(self):
        report = build_social_risk_report(
            entities=[
                {
                    "type": "profile_url",
                    "value": "https://github.com/admin",
                    "source_tool": "maigret",
                    "confidence": 0.4,
                },
                {
                    "type": "profile_url",
                    "value": "https://x.com/admin",
                    "source_tool": "sherlock",
                    "confidence": 0.35,
                },
                {
                    "type": "declared_location",
                    "value": "Singapore",
                    "source_tool": "profile_parser",
                    "confidence": 0.25,
                },
                {
                    "type": "bio_snippet",
                    "value": "crypto betting operator",
                    "source_tool": "profile_parser",
                    "confidence": 0.25,
                },
            ],
            evidence=[
                {
                    "entity_value": "https://github.com/admin",
                    "evidence_kind": "social_profile_exists",
                    "source_tool": "maigret",
                },
                {
                    "entity_value": "crypto betting operator",
                    "evidence_kind": "public_profile_metadata",
                    "source_tool": "profile_parser",
                },
            ],
            relationships=[
                {
                    "from_value": "admin",
                    "to_value": "https://github.com/admin",
                    "relationship_type": "username_has_social_profile",
                },
                {
                    "from_value": "admin",
                    "to_value": "https://x.com/admin",
                    "relationship_type": "username_has_social_profile",
                },
            ],
            declared_region="Hong Kong",
        )

        self.assertGreaterEqual(report["overall_risk_score"], 25)
        self.assertIn("business_content_risk", report["category_scores"])
        self.assertTrue(report["review_required"])
        self.assertTrue(
            any(signal["kind"] == "business_risk_keyword" for signal in report["top_risk_signals"])
        )
        self.assertTrue(
            any(signal["kind"] == "location_conflict" for signal in report["top_risk_signals"])
        )

    def test_weak_public_footprint_raises_uncertainty(self):
        report = build_social_risk_report(
            entities=[
                {
                    "type": "email",
                    "value": "admin@example.com",
                    "source_tool": "socialscan",
                    "confidence": 0.35,
                }
            ],
            evidence=[],
            relationships=[],
        )

        self.assertGreaterEqual(report["category_scores"]["evidence_uncertainty"], 50)
        self.assertTrue(
            any(signal["kind"] == "weak_public_footprint" for signal in report["top_risk_signals"])
        )


class PlannerTests(unittest.TestCase):
    def test_initial_domain_deep_strategy_queues_harvester_and_amass(self):
        registry = default_tool_registry()
        jobs = plan_initial_jobs(
            seed_type="domain",
            seed_value="example.com",
            strategy=StrategyProfile.deep(),
            registry=registry,
        )

        planned_tools = {job.tool_name for job in jobs}
        self.assertIn("theharvester", planned_tools)
        self.assertIn("amass", planned_tools)

    def test_email_followup_derives_username_and_domain_jobs(self):
        registry = default_tool_registry()
        jobs = plan_followup_jobs(
            entity_type="email",
            entity_value="admin@example.com",
            depth=1,
            strategy=StrategyProfile.standard(),
            registry=registry,
            already_planned=set(),
        )

        job_keys = {(job.tool_name, job.target_type, job.target_value) for job in jobs}
        self.assertIn(("sherlock", "username", "admin"), job_keys)
        self.assertIn(("theharvester", "domain", "example.com"), job_keys)

    def test_initial_username_strategy_queues_sherlock_and_maigret(self):
        registry = default_tool_registry()
        jobs = plan_initial_jobs(
            seed_type="username",
            seed_value="Admin_007",
            strategy=StrategyProfile.standard(),
            registry=registry,
        )

        planned_tools = {job.tool_name for job in jobs}
        self.assertIn("sherlock", planned_tools)
        self.assertIn("maigret", planned_tools)
        self.assertIn("socialscan", planned_tools)

    def test_initial_email_strategy_queues_socialscan_ghunt_and_username_tools(self):
        registry = default_tool_registry()
        jobs = plan_initial_jobs(
            seed_type="email",
            seed_value="Admin@example.com",
            strategy=StrategyProfile.standard(),
            registry=registry,
            runtime_env={
                "SPIDERFOOT_BASE_URL": "http://127.0.0.1:5001",
                "PHONEINFOGA_BASE_URL": "http://127.0.0.1:5000",
                "RECONNG_COMMAND": "/opt/recon-ng/recon-ng",
            },
        )

        job_keys = {(job.tool_name, job.target_type, job.target_value) for job in jobs}
        self.assertIn(("socialscan", "email", "admin@example.com"), job_keys)
        self.assertIn(("spiderfoot", "email", "admin@example.com"), job_keys)
        self.assertNotIn(("reconng", "email", "admin@example.com"), job_keys)
        self.assertNotIn(("sherlock", "username", "admin"), job_keys)
        self.assertNotIn(("maigret", "username", "admin"), job_keys)

    def test_company_strategy_queues_role_based_intelligence_jobs(self):
        registry = default_tool_registry()
        jobs = plan_initial_jobs(
            seed_type="company",
            seed_value="Sample Hospitality LLC / Sample Contact",
            strategy=StrategyProfile.deep(),
            registry=registry,
        )

        roles = {job.agent_role for job in jobs}
        tools = {job.tool_name for job in jobs}
        self.assertIn("enterprise_intel_agent", roles)
        self.assertIn("social_intel_agent", roles)
        self.assertIn("contact_discovery_agent", roles)
        self.assertIn("supply_chain_agent", roles)
        self.assertIn("purchase_intent_agent", roles)
        self.assertIn("news_intel_agent", roles)
        self.assertIn("cross_verification_agent", roles)
        self.assertIn("analysis_judgement_agent", roles)
        self.assertIn("company_osint", tools)
        self.assertIn("company_news", tools)
        self.assertIn("social_profile_search", tools)
        self.assertIn("company_news_monitoring", tools)
        self.assertIn("analysis_judgement", tools)
        analysis_job = next(job for job in jobs if job.tool_name == "analysis_judgement")
        self.assertEqual(analysis_job.depth, 2)
        self.assertIn("claims", analysis_job.output_contract)
        self.assertIn("graph_slots", analysis_job.output_contract)

    def test_sparse_lead_deep_strategy_queues_role_based_intake_jobs(self):
        registry = default_tool_registry()
        jobs = plan_initial_jobs(
            seed_type="sparse_lead",
            seed_value="Sample Lead / member-redacted",
            strategy=StrategyProfile.deep(),
            registry=registry,
        )

        tools = [job.tool_name for job in jobs]
        roles = {job.agent_role for job in jobs}

        self.assertEqual(
            tools,
            [
                "lead_anchor_extraction",
                "constrained_query_planning",
                "candidate_business_discovery",
                "rfq_category_analysis",
                "identity_match_review",
                "analysis_judgement",
            ],
        )
        self.assertIn("tool_agent", roles)
        self.assertIn("search_planning_agent", roles)
        self.assertIn("enterprise_intel_agent", roles)
        self.assertIn("purchase_intent_agent", roles)
        self.assertIn("cross_verification_agent", roles)
        analysis_job = next(job for job in jobs if job.tool_name == "analysis_judgement")
        self.assertIn("ACH", analysis_job.output_contract)
        self.assertIn("identity_match_review", analysis_job.depends_on)

    def test_sparse_lead_quick_strategy_limits_to_intake_planning_and_analysis(self):
        registry = default_tool_registry()
        jobs = plan_initial_jobs(
            seed_type="sparse_lead",
            seed_value="Sample Lead / member-redacted",
            strategy=StrategyProfile.quick(),
            registry=registry,
        )

        self.assertEqual(
            [job.tool_name for job in jobs],
            ["lead_anchor_extraction", "constrained_query_planning", "analysis_judgement"],
        )

    def test_profile_url_followup_queues_profile_parser(self):
        registry = default_tool_registry()
        jobs = plan_followup_jobs(
            entity_type="profile_url",
            entity_value="https://github.com/admin?tab=repositories",
            depth=0,
            strategy=StrategyProfile.standard(),
            registry=registry,
            already_planned=set(),
        )

        self.assertEqual(
            {(job.tool_name, job.target_type, job.target_value) for job in jobs},
            {("profile_parser", "profile_url", "https://github.com/admin")},
        )

    def test_url_followup_queues_site_crawl_and_official_site_extraction(self):
        registry = default_tool_registry()
        jobs = plan_progressive_jobs(
            entities=[{"type": "url", "value": "https://example-target.test"}],
            relationships=[],
            depth=0,
            strategy=StrategyProfile.standard(),
            registry=registry,
            already_planned=set(),
        )

        job_keys = {(job.tool_name, job.target_type, job.target_value) for job in jobs}
        self.assertIn(("katana", "url", "https://example-target.test"), job_keys)
        self.assertIn(("official_site_extractor", "url", "https://example-target.test"), job_keys)

    def test_quick_url_followup_keeps_site_crawl_and_official_site_extraction(self):
        registry = default_tool_registry()
        jobs = plan_progressive_jobs(
            entities=[{"type": "url", "value": "https://example-target.test"}],
            relationships=[],
            depth=0,
            strategy=StrategyProfile.quick(),
            registry=registry,
            already_planned=set(),
        )

        job_keys = {(job.tool_name, job.target_type, job.target_value) for job in jobs}
        self.assertIn(("katana", "url", "https://example-target.test"), job_keys)
        self.assertIn(("official_site_extractor", "url", "https://example-target.test"), job_keys)

    def test_progressive_inference_expands_website_email_phone_and_news(self):
        registry = default_tool_registry()
        jobs = plan_progressive_jobs(
            entities=[
                {"type": "domain", "value": "buyer-example.com"},
                {"type": "email", "value": "sales@buyer-example.com"},
                {"type": "phone", "value": "+1 212 555 0123"},
                {"type": "external_link", "value": "https://buyer-example.com/news/project"},
                {"type": "organization", "value": "Buyer Example LLC"},
            ],
            relationships=[],
            depth=0,
            strategy=StrategyProfile.deep(),
            registry=registry,
            already_planned=set(),
            runtime_env={
                "SPIDERFOOT_BASE_URL": "http://127.0.0.1:5001",
                "PHONEINFOGA_BASE_URL": "http://127.0.0.1:5000",
                "RECONNG_COMMAND": "/opt/recon-ng/recon-ng",
            },
        )

        job_keys = {(job.tool_name, job.target_type, job.target_value) for job in jobs}
        self.assertIn(("profile_parser", "profile_url", "https://buyer-example.com/news/project"), job_keys)
        self.assertIn(("phoneinfoga", "phone", "+12125550123"), job_keys)
        self.assertIn(("theharvester", "domain", "buyer-example.com"), job_keys)
        self.assertIn(("socialscan", "email", "sales@buyer-example.com"), job_keys)
        self.assertIn(("company_news", "company", "Buyer Example LLC"), job_keys)
        email_job = next(job for job in jobs if job.tool_name == "socialscan" and job.target_type == "email")
        self.assertEqual(email_job.depends_on, "inferred_from:email:sales@buyer-example.com")

    def test_progressive_inference_skips_already_planned_jobs(self):
        registry = default_tool_registry()
        jobs = plan_progressive_jobs(
            entities=[{"type": "domain", "value": "buyer-example.com"}],
            relationships=[],
            depth=0,
            strategy=StrategyProfile.deep(),
            registry=registry,
            already_planned={("theharvester", "domain", "buyer-example.com")},
        )

        self.assertNotIn(
            ("theharvester", "domain", "buyer-example.com"),
            {(job.tool_name, job.target_type, job.target_value) for job in jobs},
        )


if __name__ == "__main__":
    unittest.main()
