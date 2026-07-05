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
            auth_config={"required": True, "missing": ["READ_API_TOKEN"]},
        )

        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"]["auth_tokens"], "fail")
        self.assertIn("missing_auth_tokens=READ_API_TOKEN", result["warnings"])

    def test_auth_config_status_requires_tokens_in_production(self):
        status = auth_config_status(
            {
                "APP_ENV": "production",
                "ADMIN_API_TOKEN": "admin",
                "AGENT_API_TOKEN": "agent",
                "READ_API_TOKEN": "",
            }
        )

        self.assertTrue(status["required"])
        self.assertEqual(status["missing"], ["READ_API_TOKEN"])

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
