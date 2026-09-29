import unittest

from app.core.intel_gateway import build_intel_plan
from app.core.planner import StrategyProfile, plan_initial_jobs
from app.core.registry import default_tool_registry


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
        )

        self.assertEqual(plan.routes, [])
        self.assertEqual(plan.skipped_routes[0].tool_name, "phoneinfoga")
        self.assertEqual(plan.skipped_routes[0].skip_reason, "missing_config:PHONEINFOGA_BASE_URL")

    def test_domain_route_excludes_social_identity_tools(self):
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
            ["socialscan", "spiderfoot", "reconng"],
        )
        self.assertIn("ghunt", {route.tool_name for route in plan.skipped_routes})

    def test_email_route_adds_ghunt_when_google_cookie_is_configured(self):
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
        plan = build_intel_plan(
            target_type="domain",
            target_value="example.com",
            strategy_name="standard",
            registry=default_tool_registry(),
            runtime_env={},
        )

        self.assertEqual([route.tool_name for route in plan.routes], ["theharvester", "amass"])
        skipped = {route.tool_name: route.skip_reason for route in plan.skipped_routes}
        self.assertEqual(skipped["spiderfoot"], "missing_config:SPIDERFOOT_BASE_URL")
        self.assertEqual(skipped["reconng"], "missing_config:RECONNG_COMMAND")

    def test_company_route_uses_role_agents_not_raw_tool_blast(self):
        plan = build_intel_plan(
            target_type="company",
            target_value="Family Hospitality LLC / Faiz Chaudhry",
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

    def test_initial_email_jobs_stay_on_email_tools(self):
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
                ("reconng", "email", "buyer@example.com"),
            },
        )


if __name__ == "__main__":
    unittest.main()
