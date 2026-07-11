import unittest
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import scripts.production_readiness as readiness
from scripts.production_readiness import _get_json, auth_config_status, evaluate_readiness


class ProductionReadinessTests(unittest.TestCase):
    def test_evaluate_readiness_normalizes_malformed_endpoint_shapes(self):
        malformed_cases = (
            ([], {}, {}),
            (None, {"database": [], "scripts": None, "tools": None}, {"summary": []}),
            ("ok", {"database": "ok", "scripts": {"backup": []},
                    "tools": {"health": "ready"}}, {"summary": "ready"}),
            ({"status": "ok"}, {"database": {"status": "ok"},
             "scripts": {}, "tools": {"health": {"total": "many"}}},
             {"summary": {"total": {"count": 1}, "ready": None}}),
        )
        for api_health, system_status, tool_health in malformed_cases:
            with self.subTest(api_health=api_health, system_status=system_status):
                result = evaluate_readiness(
                    api_health=api_health,
                    system_status=system_status,
                    tool_health=tool_health,
                    web_ok=True,
                    backup_timer_status="enabled",
                )
                self.assertFalse(result["ready"])
                self.assertEqual(result["severity"], "fail")
                self.assertIn("fail", result["checks"].values())

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

            def read(self, size=-1):
                return b'{"status":"ok"}'[:size]

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

        self.assertEqual(
            payload, {"status": "error", "error": "connection_error"}
        )

    def test_get_json_rejects_non_object_json_at_boundary(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, size=-1):
                return self.payload[:size]

        for payload in (b"[]", b"null", b'"ok"', b"7"):
            with self.subTest(payload=payload):
                with patch(
                    "scripts.production_readiness.urlopen",
                    return_value=FakeResponse(payload),
                ):
                    result = _get_json("http://127.0.0.1:8088/api/health")
                self.assertEqual(
                    result, {"status": "error", "error": "invalid_json_shape"}
                )

    def test_get_json_bounds_response_and_stabilizes_decode_categories(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload
                self.read_sizes = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, size=-1):
                self.read_sizes.append(size)
                return self.payload[:size]

        cases = (
            (b"x" * 17, "response_too_large"),
            (b"\xff", "invalid_utf8"),
            (b"{", "invalid_json"),
            (b"[]", "invalid_json_shape"),
        )
        for payload, category in cases:
            with self.subTest(category=category):
                response = FakeResponse(payload)
                with (
                    patch.object(readiness, "READINESS_MAX_JSON_BYTES", 16,
                                 create=True),
                    patch("scripts.production_readiness.urlopen", return_value=response),
                ):
                    result = _get_json("http://127.0.0.1:8088/api/health")
                self.assertEqual(result, {"status": "error", "error": category})
                self.assertEqual(response.read_sizes, [17])

    def test_get_json_never_reflects_authenticated_error_bodies_or_network_reasons(self):
        fixture_value = "read-" + "credential-that-must-not-leak"
        body_value = "Bearer " + fixture_value + " arbitrary-private-body"
        http_error = HTTPError(
            "https://example.invalid/api", 401, "unauthorized", {},
            BytesIO(body_value.encode("utf-8")),
        )
        with patch("scripts.production_readiness.urlopen", side_effect=http_error):
            http_result = _get_json(
                "https://example.invalid/api", token=fixture_value
            )

        network_reason = "failed URL user:" + fixture_value + "@example.invalid"
        with patch(
            "scripts.production_readiness.urlopen",
            side_effect=URLError(network_reason),
        ):
            network_result = _get_json(
                "https://user:" + fixture_value + "@example.invalid/api",
                token=fixture_value,
            )

        self.assertEqual(
            http_result, {"status": "error", "error": "http_error:401"}
        )
        self.assertEqual(
            network_result, {"status": "error", "error": "connection_error"}
        )
        diagnostic = repr((http_result, network_result))
        self.assertNotIn(fixture_value, diagnostic)
        self.assertNotIn(body_value, diagnostic)
        self.assertNotIn(network_reason, diagnostic)

    def test_main_json_never_reflects_authenticated_http_error_content(self):
        fixture_value = "read-" + "main-json-credential"
        body_value = "Bearer " + fixture_value + " private-response-body"

        def deny_request(_request, timeout):
            self.assertEqual(timeout, 10)
            raise HTTPError(
                "https://example.invalid/api", 401, "unauthorized", {},
                BytesIO(body_value.encode("utf-8")),
            )

        output = StringIO()
        with (
            patch.dict(
                readiness.os.environ,
                {"READ_API_TOKEN": fixture_value},
                clear=True,
            ),
            patch("scripts.production_readiness._load_env"),
            patch("scripts.production_readiness.urlopen", side_effect=deny_request),
            patch("scripts.production_readiness._web_ok", return_value=False),
            patch("scripts.production_readiness._backup_timer_status",
                  return_value="disabled"),
            redirect_stdout(output),
        ):
            status = readiness.main()

        diagnostic = output.getvalue()
        self.assertEqual(status, 1)
        self.assertNotIn(fixture_value, diagnostic)
        self.assertNotIn(body_value, diagnostic)


if __name__ == "__main__":
    unittest.main()
