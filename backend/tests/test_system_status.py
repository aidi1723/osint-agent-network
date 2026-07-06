import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.main import system_status_payload
from app.services.store import SQLiteStore


class SystemStatusTests(unittest.TestCase):
    def test_sqlite_store_records_schema_versions(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            versions = store.schema_versions()

        version_ids = {item["version"] for item in versions}

        self.assertIn("20260522_core_v3", version_ids)
        self.assertIn("20260522_stability_pack", version_ids)

    def test_system_status_payload_reports_database_tasks_and_scripts(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scripts = root / "scripts"
            scripts.mkdir()
            for name in ("backup.sh", "healthcheck.sh"):
                path = scripts / name
                path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
                path.chmod(0o755)
            store = SQLiteStore(str(root / "data" / "osint.sqlite"))
            store.create_investigation("Stable", "company", "Stable LLC", "quick")

            payload = system_status_payload(store_obj=store, root_dir=str(root))

        self.assertEqual(payload["service"], "osint-agent-network")
        self.assertEqual(payload["database"]["status"], "ok")
        self.assertGreaterEqual(payload["database"]["schema_version_count"], 2)
        self.assertEqual(payload["investigations"]["total"], 1)
        self.assertTrue(payload["scripts"]["backup"]["present"])
        self.assertTrue(payload["scripts"]["healthcheck"]["present"])
        self.assertGreaterEqual(payload["tools"]["registered"], 1)
        self.assertIn("health", payload["tools"])
        self.assertGreaterEqual(payload["tools"]["health"]["total"], 1)

    def test_system_status_payload_reports_worker_queue_state(self):
        class FakeQueue:
            def snapshot(self):
                return {
                    "mode": "in_process",
                    "queue_depth": 1,
                    "running": "task-running",
                    "pending": [{"investigation_id": "task-pending", "max_jobs": 4}],
                    "recent_runs": [{"investigation_id": "task-done", "completed": 2}],
                    "recent_errors": [],
                }

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = SQLiteStore(str(root / "data" / "osint.sqlite"))

            payload = system_status_payload(store_obj=store, root_dir=str(root), worker_queue=FakeQueue())

        self.assertEqual(payload["worker"]["mode"], "in_process")
        self.assertEqual(payload["worker"]["queue_depth"], 1)
        self.assertEqual(payload["worker"]["running"], "task-running")
        self.assertEqual(payload["worker"]["pending"][0]["investigation_id"], "task-pending")
        self.assertEqual(payload["worker"]["recent_runs"][0]["investigation_id"], "task-done")

    def test_system_status_payload_reports_investigation_outcome_metrics(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = SQLiteStore(str(root / "data" / "osint.sqlite"))
            open_task = store.create_investigation("Open", "company", "Open LLC", "quick")
            completed_task = store.create_investigation("Done", "company", "Done LLC", "quick")
            blocked_task = store.create_investigation("Blocked", "company", "Blocked LLC", "quick")
            failed_task = store.create_investigation("Failed", "company", "Failed LLC", "quick")
            store.set_investigation_status(open_task.id, "OPEN")
            store.set_investigation_status(completed_task.id, "COMPLETED")
            store.set_investigation_status(blocked_task.id, "BLOCKED")
            store.set_investigation_status(failed_task.id, "FAILED")

            payload = system_status_payload(store_obj=store, root_dir=str(root))

        self.assertEqual(
            payload["investigations"]["outcome_metrics"],
            {
                "terminal_total": 3,
                "success_total": 1,
                "blocked_total": 1,
                "failed_total": 1,
                "success_rate": 0.3333,
                "blocked_rate": 0.3333,
                "failed_rate": 0.3333,
            },
        )


if __name__ == "__main__":
    unittest.main()
