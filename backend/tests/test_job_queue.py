import threading
import unittest

from app.services.job_queue import BackgroundJobQueue


class BackgroundJobQueueTests(unittest.TestCase):
    def test_enqueue_returns_before_worker_runs_and_deduplicates_pending(self):
        release = threading.Event()
        calls = []

        def worker(store, investigation_id, max_jobs=None):
            calls.append((investigation_id, max_jobs))
            release.wait(timeout=2)
            return {"started": 1, "completed": 1, "failed": 0, "blocked": 0}

        queue = BackgroundJobQueue(worker_func=worker)

        first = queue.enqueue(store=object(), investigation_id="task-1", max_jobs=3)
        second = queue.enqueue(store=object(), investigation_id="task-1", max_jobs=3)
        snapshot = queue.snapshot()

        self.assertTrue(first["accepted"])
        self.assertFalse(second["accepted"])
        self.assertIn(second["status"], {"ALREADY_QUEUED", "ALREADY_RUNNING"})
        self.assertIn(snapshot["running"], [None, "task-1"])
        release.set()
        queue.wait_until_idle(timeout=2)
        self.assertEqual(calls, [("task-1", 3)])

    def test_completed_run_is_recorded_without_sensitive_target_details(self):
        def worker(store, investigation_id, max_jobs=None):
            return {
                "started": 2,
                "completed": 1,
                "failed": 0,
                "blocked": 1,
                "queued_followups": 3,
                "target_value": "private seed should not be copied",
            }

        queue = BackgroundJobQueue(worker_func=worker)

        queue.enqueue(store=object(), investigation_id="task-2", max_jobs=5)
        self.assertTrue(queue.wait_until_idle(timeout=2))
        snapshot = queue.snapshot()

        self.assertEqual(snapshot["queue_depth"], 0)
        self.assertIsNone(snapshot["running"])
        self.assertEqual(len(snapshot["recent_runs"]), 1)
        recent = snapshot["recent_runs"][0]
        self.assertEqual(recent["investigation_id"], "task-2")
        self.assertEqual(recent["max_jobs"], 5)
        self.assertEqual(recent["started"], 2)
        self.assertEqual(recent["completed"], 1)
        self.assertEqual(recent["blocked"], 1)
        self.assertEqual(recent["queued_followups"], 3)
        self.assertNotIn("target_value", recent)

    def test_worker_error_is_recorded_and_queue_continues(self):
        calls = []

        def worker(store, investigation_id, max_jobs=None):
            calls.append(investigation_id)
            if investigation_id == "task-error":
                raise RuntimeError("boom with private context")
            return {"started": 1, "completed": 1, "failed": 0, "blocked": 0}

        queue = BackgroundJobQueue(worker_func=worker)

        queue.enqueue(store=object(), investigation_id="task-error", max_jobs=1)
        queue.enqueue(store=object(), investigation_id="task-ok", max_jobs=1)
        self.assertTrue(queue.wait_until_idle(timeout=2))
        snapshot = queue.snapshot()

        self.assertEqual(calls, ["task-error", "task-ok"])
        self.assertEqual(snapshot["recent_errors"][0]["investigation_id"], "task-error")
        self.assertIn("boom", snapshot["recent_errors"][0]["error"])
        self.assertEqual(snapshot["recent_runs"][0]["investigation_id"], "task-ok")


if __name__ == "__main__":
    unittest.main()
