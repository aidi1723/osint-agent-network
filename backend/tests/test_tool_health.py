import os
import unittest
from unittest.mock import patch

from app.core.registry import ToolDefinition, ToolRegistry
from app.core.tool_health import build_tool_health_report


class ToolHealthTests(unittest.TestCase):
    def test_reports_internal_parser_tools_as_ready_without_external_executable(self):
        registry = ToolRegistry(
            [
                ToolDefinition(
                    name="lead_anchor_extraction",
                    display_name="Lead Anchor Extraction",
                    execution_mode="artifact_parser",
                    accepts=("sparse_lead",),
                    produces=("platform",),
                    requires_credentials=False,
                    default_timeout_seconds=30,
                    base_confidence=0.9,
                )
            ]
        )

        report = build_tool_health_report(registry=registry, env={})

        self.assertEqual(report["summary"]["ready"], 1)
        self.assertEqual(report["tools"][0]["status"], "ready")
        self.assertEqual(report["tools"][0]["reason"], "internal adapter")

    def test_reports_missing_executable_for_cli_tool_with_configured_command(self):
        registry = ToolRegistry(
            [
                ToolDefinition(
                    name="amass",
                    display_name="OWASP Amass",
                    execution_mode="sync_cli",
                    accepts=("domain",),
                    produces=("subdomain",),
                    requires_credentials=False,
                    default_timeout_seconds=120,
                    base_confidence=0.5,
                )
            ]
        )

        with patch("app.core.tool_health.shutil.which", return_value=None):
            report = build_tool_health_report(registry=registry, env={"AMASS_COMMAND": "amass"})

        item = report["tools"][0]
        self.assertEqual(item["status"], "missing_executable")
        self.assertEqual(item["command"], "amass")
        self.assertIn("AMASS_COMMAND", item["env_checked"])

    def test_reports_rest_tool_missing_config_without_network_probe(self):
        registry = ToolRegistry(
            [
                ToolDefinition(
                    name="spiderfoot",
                    display_name="SpiderFoot",
                    execution_mode="async_rest",
                    accepts=("domain",),
                    produces=("email",),
                    requires_credentials=True,
                    default_timeout_seconds=1800,
                    base_confidence=0.3,
                )
            ]
        )

        report = build_tool_health_report(registry=registry, env={})

        item = report["tools"][0]
        self.assertEqual(item["status"], "missing_config")
        self.assertIn("SPIDERFOOT_BASE_URL", item["env_checked"])

    def test_spiderfoot_api_key_is_optional_when_base_url_is_configured(self):
        registry = ToolRegistry(
            [
                ToolDefinition(
                    name="spiderfoot",
                    display_name="SpiderFoot",
                    execution_mode="async_rest",
                    accepts=("domain",),
                    produces=("email",),
                    requires_credentials=True,
                    default_timeout_seconds=1800,
                    base_confidence=0.3,
                )
            ]
        )

        report = build_tool_health_report(
            registry=registry,
            env={"SPIDERFOOT_BASE_URL": "http://127.0.0.1:5001"},
        )

        self.assertEqual(report["tools"][0]["status"], "ready")
        self.assertEqual(report["summary"]["ready"], 1)

    def test_phoneinfoga_is_on_demand_when_base_url_is_configured_without_api_key(self):
        registry = ToolRegistry(
            [
                ToolDefinition(
                    name="phoneinfoga",
                    display_name="PhoneInfoga",
                    execution_mode="sync_rest",
                    accepts=("phone",),
                    produces=("phone",),
                    requires_credentials=False,
                    default_timeout_seconds=120,
                    base_confidence=0.45,
                )
            ]
        )

        report = build_tool_health_report(
            registry=registry,
            env={"PHONEINFOGA_BASE_URL": "http://127.0.0.1:5000"},
        )

        self.assertEqual(report["tools"][0]["status"], "ready")
        self.assertEqual(report["tools"][0]["reason"], "on-demand endpoint configured")

    def test_reports_disabled_tool_separately_from_missing_credentials(self):
        registry = ToolRegistry(
            [
                ToolDefinition(
                    name="ghunt",
                    display_name="GHunt",
                    execution_mode="sync_cli",
                    accepts=("email",),
                    produces=("real_name",),
                    requires_credentials=True,
                    default_timeout_seconds=180,
                    base_confidence=0.55,
                    enabled_by_default=False,
                )
            ]
        )

        report = build_tool_health_report(registry=registry, env={})

        self.assertEqual(report["tools"][0]["status"], "disabled")
        self.assertEqual(report["summary"]["disabled"], 1)

    def test_environment_defaults_do_not_mutate_process_environment(self):
        before = dict(os.environ)

        build_tool_health_report()

        self.assertEqual(dict(os.environ), before)


if __name__ == "__main__":
    unittest.main()
