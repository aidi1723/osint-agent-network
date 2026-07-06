import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.store import SQLiteStore


class PersistentJobQueueStoreTests(unittest.TestCase):
    def test_sqlite_schema_includes_worker_queue_runs(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            versions = {item["version"] for item in store.schema_versions()}
            snapshot = store.worker_queue_snapshot()

        self.assertIn("20260706_persistent_background_queue", versions)
        self.assertEqual(snapshot["mode"], "sqlite")
        self.assertEqual(snapshot["queue_depth"], 0)
        self.assertIsNone(snapshot["running"])
        self.assertEqual(snapshot["pending"], [])

    def test_enqueue_worker_run_persists_and_deduplicates_active_request(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = store.create_investigation("Queue", "company", "Example LLC", "quick")

            first = store.enqueue_worker_run(investigation.id, max_jobs=4)
            second = store.enqueue_worker_run(investigation.id, max_jobs=4)
            snapshot = store.worker_queue_snapshot()

        self.assertTrue(first["accepted"])
        self.assertFalse(second["accepted"])
        self.assertEqual(second["status"], "ALREADY_QUEUED")
        self.assertEqual(snapshot["queue_depth"], 1)
        self.assertEqual(snapshot["pending"][0]["investigation_id"], investigation.id)
        self.assertEqual(snapshot["pending"][0]["max_jobs"], 4)

    def test_claim_complete_and_recent_run_snapshot(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = store.create_investigation("Queue", "company", "Example LLC", "quick")
            store.enqueue_worker_run(investigation.id, max_jobs=2)

            claimed = store.claim_next_worker_run("worker-a", stale_after_seconds=1800)
            running_snapshot = store.worker_queue_snapshot()
            completed = store.complete_worker_run(
                claimed["id"],
                {"started": 2, "completed": 1, "failed": 0, "blocked": 1, "queued_followups": 3},
            )
            final_snapshot = store.worker_queue_snapshot()

        self.assertEqual(claimed["investigation_id"], investigation.id)
        self.assertEqual(claimed["status"], "RUNNING")
        self.assertEqual(claimed["worker_id"], "worker-a")
        self.assertEqual(running_snapshot["running"], investigation.id)
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(final_snapshot["queue_depth"], 0)
        self.assertIsNone(final_snapshot["running"])
        self.assertEqual(final_snapshot["recent_runs"][0]["investigation_id"], investigation.id)
        self.assertEqual(final_snapshot["recent_runs"][0]["completed"], 1)
        self.assertEqual(final_snapshot["recent_runs"][0]["blocked"], 1)
        self.assertEqual(final_snapshot["recent_runs"][0]["queued_followups"], 3)

    def test_fail_records_recent_error(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = store.create_investigation("Queue", "company", "Example LLC", "quick")
            store.enqueue_worker_run(investigation.id, max_jobs=1)
            claimed = store.claim_next_worker_run("worker-a", stale_after_seconds=1800)

            failed = store.fail_worker_run(claimed["id"], "boom with private context")
            snapshot = store.worker_queue_snapshot()

        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(snapshot["recent_errors"][0]["investigation_id"], investigation.id)
        self.assertIn("boom", snapshot["recent_errors"][0]["error"])

    def test_stale_running_run_is_requeued_and_claimed(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = store.create_investigation("Queue", "company", "Example LLC", "quick")
            store.enqueue_worker_run(investigation.id, max_jobs=1)
            first_claim = store.claim_next_worker_run("worker-a", stale_after_seconds=1800)

            second_claim = store.claim_next_worker_run("worker-b", stale_after_seconds=0)
            snapshot = store.worker_queue_snapshot()

        self.assertEqual(second_claim["id"], first_claim["id"])
        self.assertEqual(second_claim["worker_id"], "worker-b")
        self.assertEqual(snapshot["running"], investigation.id)


if __name__ == "__main__":
    unittest.main()
