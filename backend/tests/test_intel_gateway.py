import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app.core.intel_gateway import build_intel_plan
from app.core.planner import StrategyProfile, plan_initial_jobs
from app.core.registry import default_tool_registry
from app.services.store import MemoryStore


@contextmanager
def available_external_commands():
    with (
        patch("app.core.tool_health.shutil.which", return_value="/usr/bin/tool"),
        patch("app.core.tool_health.Path.exists", return_value=True),
    ):
        yield


class IntelGatewayTests(unittest.TestCase):
    def test_phone_route_uses_only_phoneinfoga(self):
        plan = build_intel_plan(
            target_type="phone",
            target_value="+1 212 555 0123",
            strategy_name="standard",
            registry=default_tool_registry(),
            runtime_env={"PHONEINFOGA_BASE_URL": "http://127.0.0.1:5000"},
        )

        self.assertEqual([route.tool_name for route in plan.routes], ["phoneinfoga"])
        self.assertEqual(plan.routes[0].target_value, "+12125550123")

    def test_phone_route_skips_phoneinfoga_until_explicitly_configured(self):
        plan = build_intel_plan(
            target_type="phone",
            target_value="+1 212 555 0123",
                strategy_name="standard",
                registry=default_tool_registry(),
                runtime_env={},
                respect_tool_health=True,
            )

        self.assertEqual(plan.routes, [])
        self.assertEqual(plan.skipped_routes[0].tool_name, "phoneinfoga")
        self.assertEqual(plan.skipped_routes[0].skip_reason, "missing_config:PHONEINFOGA_BASE_URL")

    def test_domain_route_excludes_social_identity_tools(self):
        with available_external_commands():
            plan = build_intel_plan(
                target_type="domain",
                target_value="Example.COM",
                strategy_name="deep",
                registry=default_tool_registry(),
                runtime_env={
                    "SPIDERFOOT_BASE_URL": "http://127.0.0.1:5001",
                    "RECONNG_COMMAND": "/opt/recon-ng/recon-ng",
                },
            )

        tools = {route.tool_name for route in plan.routes}
        self.assertIn("theharvester", tools)
        self.assertIn("amass", tools)
        self.assertIn("spiderfoot", tools)
        self.assertIn("reconng", tools)
        self.assertTrue(tools.isdisjoint({"sherlock", "maigret", "socialscan", "phoneinfoga", "ghunt"}))

    def test_email_route_skips_ghunt_without_google_cookie(self):
        with available_external_commands():
            plan = build_intel_plan(
                target_type="email",
                target_value="Buyer@Example.COM",
                strategy_name="standard",
                registry=default_tool_registry(),
                runtime_env={
                    "SPIDERFOOT_BASE_URL": "http://127.0.0.1:5001",
                    "RECONNG_COMMAND": "/opt/recon-ng/recon-ng",
                },
            )

        self.assertEqual(
            [route.tool_name for route in plan.routes],
            ["socialscan", "spiderfoot"],
        )
        self.assertIn("ghunt", {route.tool_name for route in plan.skipped_routes})

    def test_standard_domain_route_excludes_reconng_even_when_configured(self):
        with available_external_commands():
            plan = build_intel_plan(
                target_type="domain",
                target_value="example.com",
                strategy_name="standard",
                registry=default_tool_registry(),
                runtime_env={
                    "SPIDERFOOT_BASE_URL": "http://127.0.0.1:5001",
                    "RECONNG_COMMAND": "/opt/recon-ng/recon-ng",
                },
            )

        self.assertEqual(
            [route.tool_name for route in plan.routes],
            ["theharvester", "subfinder", "amass", "httpx", "spiderfoot"],
        )
        self.assertNotIn("reconng", {route.tool_name for route in plan.routes})

    def test_email_route_adds_ghunt_when_google_cookie_is_configured(self):
        with available_external_commands():
            plan = build_intel_plan(
                target_type="email",
                target_value="buyer@example.com",
                strategy_name="standard",
                registry=default_tool_registry(),
                runtime_env={
                    "SPIDERFOOT_BASE_URL": "http://127.0.0.1:5001",
                    "RECONNG_COMMAND": "/opt/recon-ng/recon-ng",
                    "GHUNT_COOKIE_PATH": "/secure/ghunt.cookies",
                },
            )

        self.assertIn("ghunt", [route.tool_name for route in plan.routes])

    def test_unconfigured_service_tools_are_skipped_with_reason(self):
        with available_external_commands():
            plan = build_intel_plan(
                target_type="domain",
                target_value="example.com",
                strategy_name="standard",
                registry=default_tool_registry(),
                runtime_env={},
                respect_tool_health=True,
            )

        self.assertEqual([route.tool_name for route in plan.routes], ["theharvester", "subfinder", "amass", "httpx"])
        skipped = {route.tool_name: route.skip_reason for route in plan.skipped_routes}
        self.assertEqual(skipped["spiderfoot"], "missing_config:SPIDERFOOT_BASE_URL")
        self.assertNotIn("reconng", skipped)

    def test_unavailable_cli_tools_are_skipped_before_job_creation(self):
        with (
            patch("app.core.tool_health.shutil.which", side_effect=lambda command: "/usr/bin/python3" if command == "python3" else None),
            patch("app.core.tool_health.Path.exists", return_value=False),
        ):
            plan = build_intel_plan(
                target_type="domain",
                target_value="example.com",
                strategy_name="standard",
                registry=default_tool_registry(),
                runtime_env={},
                respect_tool_health=True,
            )

        self.assertEqual(plan.routes, [])
        skipped = {route.tool_name: route.skip_reason for route in plan.skipped_routes}
        self.assertIn("theharvester", skipped)
        self.assertIn("amass", skipped)
        self.assertTrue(skipped["theharvester"].startswith("tool_unavailable:missing_config"))
        self.assertTrue(skipped["amass"].startswith("tool_unavailable:missing_executable"))

    def test_create_investigation_records_planning_blockers_when_all_routes_skipped(self):
        store = MemoryStore()

        with (
            patch("app.core.tool_health.shutil.which", side_effect=lambda command: "/usr/bin/python3" if command == "python3" else None),
            patch("app.core.tool_health.Path.exists", return_value=False),
        ):
            investigation = store.create_investigation(
                name="blocked domain",
                seed_type="domain",
                seed_value="example.com",
                strategy_name="standard",
                respect_tool_health=True,
            )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(detail["status"], "BLOCKED")
        self.assertEqual(detail["summary"], "工具任务被环境依赖阻断")
        self.assertEqual(detail["jobs"], [])
        self.assertTrue(detail["metadata"]["initial_skipped_routes"])
        self.assertTrue(any("规划阶段跳过不可用工具" in event["message"] for event in detail["events"]))

    def test_company_route_uses_role_agents_not_raw_tool_blast(self):
        plan = build_intel_plan(
            target_type="company",
            target_value="Sample Hospitality LLC / Sample Contact",
            strategy_name="deep",
            registry=default_tool_registry(),
            runtime_env={},
        )

        tools = {route.tool_name for route in plan.routes}
        roles = {route.agent_role for route in plan.routes}
        self.assertIn("enterprise_intel_agent", roles)
        self.assertIn("news_intel_agent", roles)
        self.assertIn("analysis_judgement_agent", roles)
        self.assertIn("company_osint", tools)
        self.assertIn("company_news", tools)
        self.assertIn("company_news_monitoring", tools)
        self.assertIn("analysis_judgement", tools)
        self.assertTrue(tools.isdisjoint({"sherlock", "maigret", "socialscan", "spiderfoot", "reconng"}))
        verification_job = next(route for route in plan.routes if route.tool_name == "cross_verification")
        analysis_job = next(route for route in plan.routes if route.tool_name == "analysis_judgement")
        self.assertIn("admiralty_code", verification_job.output_contract)
        self.assertIn("ACH", analysis_job.output_contract)
        self.assertIn("BLUF", analysis_job.output_contract)
        self.assertIn("directed_collection", analysis_job.output_contract)

    def test_company_standard_route_adds_configured_official_site_search(self):
        plan = build_intel_plan(
            target_type="company",
            target_value="Sample Auto Parts Co.",
            strategy_name="standard",
            registry=default_tool_registry(),
            runtime_env={"OFFICIAL_SITE_SEARCH_BASE_URL": "http://search.local/search"},
            respect_tool_health=True,
        )

        self.assertIn("official_site_search", [route.tool_name for route in plan.routes])
        search_route = next(route for route in plan.routes if route.tool_name == "official_site_search")
        self.assertEqual(search_route.target_type, "company")
        self.assertEqual(search_route.source_tier, "official_site_discovery")

    def test_sparse_lead_standard_route_skips_unconfigured_official_site_search(self):
        plan = build_intel_plan(
            target_type="sparse_lead",
            target_value="Sample Lead / member-redacted",
            strategy_name="standard",
            registry=default_tool_registry(),
            runtime_env={},
            respect_tool_health=True,
        )

        skipped = {route.tool_name: route.skip_reason for route in plan.skipped_routes}
        self.assertEqual(skipped["official_site_search"], "missing_config:OFFICIAL_SITE_SEARCH_BASE_URL")

    def test_initial_email_jobs_stay_on_email_tools(self):
        with available_external_commands():
            jobs = plan_initial_jobs(
                seed_type="email",
                seed_value="Buyer@Example.COM",
                strategy=StrategyProfile.standard(),
                registry=default_tool_registry(),
                runtime_env={
                    "SPIDERFOOT_BASE_URL": "http://127.0.0.1:5001",
                    "RECONNG_COMMAND": "/opt/recon-ng/recon-ng",
                },
            )

        self.assertEqual(
            {(job.tool_name, job.target_type, job.target_value) for job in jobs},
            {
                ("socialscan", "email", "buyer@example.com"),
                ("spiderfoot", "email", "buyer@example.com"),
            },
        )


if __name__ == "__main__":
    unittest.main()
