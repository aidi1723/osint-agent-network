import unittest

from scripts.production_readiness import evaluate_readiness


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

    def test_evaluate_readiness_does_not_treat_missing_local_timer_as_ready(self):
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
            tool_health={"summary": {"total": 2, "ready": 1, "attention_required": 1}},
            web_ok=True,
            backup_timer_status="unknown-local",
        )

        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"]["backup_timer"], "fail")


if __name__ == "__main__":
    unittest.main()
