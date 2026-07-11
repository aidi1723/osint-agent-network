import unittest
from unittest.mock import patch
from urllib.error import URLError

from scripts.production_readiness import _get_json, auth_config_status, evaluate_readiness


class ProductionReadinessTests(unittest.TestCase):
    def test_evaluate_readiness_accepts_healthy_services_and_records_tool_attention_as_info(self):
        result = evaluate_readiness(
            api_health={"status": "ok"},
            system_status={
                "database": {"status": "ok", "schema_version_count": 2},
                "scripts": {
                    "backup": {"present": True},
                    "healthcheck": {"present": True},
                    "verify": {"present": True},
                },
                "tools": {"health": {"total": 12, "ready": 5, "attention_required": 6}},
            },
            tool_health={"summary": {"total": 12, "ready": 5, "attention_required": 6}},
            web_ok=True,
            backup_timer_status="enabled",
        )

        self.assertTrue(result["ready"])
        self.assertEqual(result["severity"], "ok")
        self.assertEqual(result["checks"]["api"], "ok")
        self.assertEqual(result["checks"]["backup_timer"], "ok")
        self.assertIn("tool_attention=6", result["info"])

    def test_evaluate_readiness_blocks_on_api_database_or_web_failure(self):
        result = evaluate_readiness(
            api_health={"status": "down"},
            system_status={"database": {"status": "error"}, "scripts": {}},
            tool_health={"summary": {"total": 0, "ready": 0, "attention_required": 0}},
            web_ok=False,
            backup_timer_status="disabled",
        )

        self.assertFalse(result["ready"])
        self.assertEqual(result["severity"], "fail")
        self.assertEqual(result["checks"]["api"], "fail")
        self.assertEqual(result["checks"]["database"], "fail")
        self.assertEqual(result["checks"]["web"], "fail")
        self.assertEqual(result["checks"]["backup_timer"], "fail")

    def test_evaluate_readiness_blocks_production_missing_auth_tokens(self):
        result = evaluate_readiness(
            api_health={"status": "ok"},
            system_status={
                "database": {"status": "ok"},
                "scripts": {
                    "backup": {"present": True},
                    "healthcheck": {"present": True},
                    "verify": {"present": True},
                },
                "tools": {"health": {"total": 12, "ready": 5, "attention_required": 0}},
            },
            tool_health={"summary": {"total": 12, "ready": 5, "attention_required": 0}},
            web_ok=True,
            backup_timer_status="enabled",
            auth_config=auth_config_status(
                {
                    "APP_ENV": "production",
                    "ADMIN_API_TOKEN": "admin",
                    "READ_API_TOKEN": "",
                    "OSINT_COOKIE_SECURE": "true",
                    "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "false",
                }
            ),
        )

        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"]["auth_tokens"], "fail")
        self.assertIn("missing_auth_tokens=READ_API_TOKEN", result["warnings"])

    def test_auth_config_status_requires_tokens_in_production(self):
        status = auth_config_status(
            {
                "APP_ENV": "production",
                "ADMIN_API_TOKEN": "admin",
                "READ_API_TOKEN": "",
                "OSINT_COOKIE_SECURE": "true",
                "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "false",
            }
        )

        self.assertTrue(status["required"])
        self.assertEqual(status["missing"], ["READ_API_TOKEN"])

    def test_secure_production_auth_does_not_require_global_agent_token(self):
        status = auth_config_status(
            {
                "APP_ENV": "production",
                "ADMIN_API_TOKEN": "admin",
                "READ_API_TOKEN": "read",
                "OSINT_COOKIE_SECURE": "true",
                "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "false",
            }
        )

        self.assertEqual(status["missing"], [])
        self.assertTrue(status["required"])
        self.assertTrue(status["cookie_secure"])
        self.assertFalse(status["legacy_agent_token"])
        self.assertFalse(status["auth_disabled"])

    def test_production_blocks_explicitly_disabled_auth(self):
        status = auth_config_status(
            {
                "APP_ENV": "production",
                "OSINT_REQUIRE_AUTH": "false",
                "ADMIN_API_TOKEN": "admin",
                "READ_API_TOKEN": "read",
                "OSINT_COOKIE_SECURE": "true",
                "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "false",
            }
        )

        self.assertTrue(status["production"])
        self.assertTrue(status["auth_disabled"])
        self.assertEqual(status["checks"]["auth_required"], "fail")

    def test_production_blocks_missing_or_false_secure_cookie(self):
        missing = auth_config_status(
            {
                "APP_ENV": "production",
                "ADMIN_API_TOKEN": "admin",
                "READ_API_TOKEN": "read",
            }
        )
        false = auth_config_status(
            {
                "APP_ENV": "production",
                "ADMIN_API_TOKEN": "admin",
                "READ_API_TOKEN": "read",
                "OSINT_COOKIE_SECURE": "false",
            }
        )

        self.assertEqual(missing["checks"]["cookie_secure"], "fail")
        self.assertEqual(false["checks"]["cookie_secure"], "fail")

    def test_production_blocks_legacy_shared_agent_token_mode(self):
        status = auth_config_status(
            {
                "APP_ENV": "production",
                "ADMIN_API_TOKEN": "admin",
                "READ_API_TOKEN": "read",
                "OSINT_COOKIE_SECURE": "true",
                "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "true",
            }
        )

        self.assertEqual(status["checks"]["legacy_agent_token"], "fail")

    def test_evaluate_readiness_exposes_stable_production_auth_checks(self):
        result = evaluate_readiness(
            api_health={"status": "ok"},
            system_status={
                "database": {"status": "ok"},
                "scripts": {
                    "backup": {"present": True},
                    "healthcheck": {"present": True},
                    "verify": {"present": True},
                },
            },
            tool_health={"summary": {"total": 1, "ready": 1, "attention_required": 0}},
            web_ok=True,
            backup_timer_status="enabled",
            auth_config=auth_config_status(
                {
                    "APP_ENV": "production",
                    "OSINT_REQUIRE_AUTH": "false",
                    "ADMIN_API_TOKEN": "admin",
                    "READ_API_TOKEN": "read",
                    "OSINT_COOKIE_SECURE": "false",
                    "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "true",
                }
            ),
        )

        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"]["auth_required"], "fail")
        self.assertEqual(result["checks"]["cookie_secure"], "fail")
        self.assertEqual(result["checks"]["legacy_agent_token"], "fail")
        self.assertIn("production_auth_explicitly_disabled", result["warnings"])
        self.assertIn("secure_cookie_required", result["warnings"])
        self.assertIn("legacy_agent_token_forbidden", result["warnings"])

    def test_nonproduction_defaults_remain_usable(self):
        status = auth_config_status({})

        self.assertFalse(status["production"])
        self.assertFalse(status["required"])
        self.assertEqual(status["missing"], [])
        self.assertEqual(status["checks"], {
            "auth_required": "ok",
            "cookie_secure": "ok",
            "legacy_agent_token": "ok",
        })

    def test_nonproduction_explicit_auth_still_validates_admin_and_read_tokens(self):
        status = auth_config_status({"OSINT_REQUIRE_AUTH": "true"})

        self.assertTrue(status["required"])
        self.assertEqual(status["missing"], ["ADMIN_API_TOKEN", "READ_API_TOKEN"])

    def test_production_aliases_and_true_variants_share_security_policy(self):
        for app_env in ("prod", " production ", "PROD", "Production"):
            for true_value in ("1", "true", "YES", " on "):
                with self.subTest(app_env=app_env, true_value=true_value):
                    status = auth_config_status(
                        {
                            "APP_ENV": app_env,
                            "ADMIN_API_TOKEN": "admin",
                            "READ_API_TOKEN": "read",
                            "OSINT_COOKIE_SECURE": true_value,
                        }
                    )
                    self.assertTrue(status["production"])
                    self.assertEqual(status["missing"], [])
                    self.assertEqual(status["checks"]["auth_required"], "ok")
                    self.assertEqual(status["checks"]["cookie_secure"], "ok")
                    legacy_status = auth_config_status(
                        {
                            "APP_ENV": app_env,
                            "ADMIN_API_TOKEN": "admin",
                            "READ_API_TOKEN": "read",
                            "OSINT_COOKIE_SECURE": "true",
                            "OSINT_ALLOW_LEGACY_AGENT_TOKEN": true_value,
                        }
                    )
                    self.assertEqual(
                        legacy_status["checks"]["legacy_agent_token"], "fail"
                    )

    def test_production_false_variants_disable_auth_and_secure_cookie(self):
        for false_value in ("0", "false", "NO", " off "):
            with self.subTest(false_value=false_value):
                status = auth_config_status(
                    {
                        "APP_ENV": "production",
                        "OSINT_REQUIRE_AUTH": false_value,
                        "ADMIN_API_TOKEN": "admin",
                        "READ_API_TOKEN": "read",
                        "OSINT_COOKIE_SECURE": false_value,
                        "OSINT_ALLOW_LEGACY_AGENT_TOKEN": false_value,
                    }
                )
                self.assertEqual(status["checks"]["auth_required"], "fail")
                self.assertEqual(status["checks"]["cookie_secure"], "fail")
                self.assertEqual(status["checks"]["legacy_agent_token"], "ok")

    def test_nonproduction_auth_true_variants_require_management_tokens(self):
        for true_value in ("1", "true", "YES", " on "):
            with self.subTest(true_value=true_value):
                status = auth_config_status({"OSINT_REQUIRE_AUTH": true_value})
                self.assertTrue(status["required"])
                self.assertEqual(
                    status["missing"], ["ADMIN_API_TOKEN", "READ_API_TOKEN"]
                )

    def test_readiness_diagnostics_do_not_expose_token_values(self):
        admin_secret = "admin-secret-that-must-not-leak"
        read_secret = "read-secret-that-must-not-leak"
        status = auth_config_status(
            {
                "APP_ENV": "production",
                "ADMIN_API_TOKEN": admin_secret,
                "READ_API_TOKEN": read_secret,
                "OSINT_REQUIRE_AUTH": "false",
                "OSINT_COOKIE_SECURE": "false",
                "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "true",
            }
        )

        diagnostic = repr(status)
        self.assertNotIn(admin_secret, diagnostic)
        self.assertNotIn(read_secret, diagnostic)

    def test_get_json_sends_read_token_when_provided(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b'{"status":"ok"}'

        def fake_urlopen(request, timeout):
            captured["authorization"] = request.headers.get("Authorization")
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("scripts.production_readiness.urlopen", fake_urlopen):
            payload = _get_json("http://127.0.0.1:8088/api/system/status", token="read-secret")

        self.assertEqual(payload, {"status": "ok"})
        self.assertEqual(captured["authorization"], "Bearer read-secret")
        self.assertEqual(captured["timeout"], 10)

    def test_get_json_returns_error_payload_when_endpoint_is_unavailable(self):
        with patch("scripts.production_readiness.urlopen", side_effect=URLError("connection refused")):
            payload = _get_json("http://127.0.0.1:8088/api/health")

        self.assertEqual(payload["status"], "error")
        self.assertIn("connection refused", payload["error"])


if __name__ == "__main__":
    unittest.main()
