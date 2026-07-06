# Background Job Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `/api/investigations/{id}/run-jobs` from a synchronous long request into a quick in-process background queue enqueue.

**Architecture:** Add `app.services.job_queue` as a small queue runner around the existing `run_investigation_jobs()` worker core. `main.py` enqueues requests and exposes queue state through `/api/system/status`; existing direct worker tests continue to validate execution behavior.

**Tech Stack:** Python standard library `threading`, `collections.deque`, existing `http.server` API, `unittest`, existing `MemoryStore` and `SQLiteStore`.

---

### Task 1: Queue Runner Unit Tests

**Files:**
- Create: `backend/tests/test_job_queue.py`
- Create later: `backend/app/services/job_queue.py`

- [ ] **Step 1: Write failing queue acceptance and dedupe tests**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_job_queue.py' -v`

Expected: FAIL because `app.services.job_queue` does not exist.

- [ ] **Step 3: Implement minimal `BackgroundJobQueue`**

Create `backend/app/services/job_queue.py` with `BackgroundJobQueue`, `QueueRequest`, `enqueue()`, `_run_loop()`, `snapshot()`, and `wait_until_idle()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_job_queue.py' -v`

Expected: PASS.

### Task 2: Queue Completion and Error Tests

**Files:**
- Modify: `backend/tests/test_job_queue.py`
- Modify: `backend/app/services/job_queue.py`

- [ ] **Step 1: Add failing recent run and recent error tests**

Add tests verifying successful worker summaries appear in `recent_runs`, and exceptions appear in `recent_errors` without killing later queue processing.

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_job_queue.py' -v`

Expected: FAIL until recent run/error capture is implemented.

- [ ] **Step 3: Implement recent run and error capture**

Keep only a bounded recent history, redact queue records to investigation ids, max job limits, timestamps, and worker summary counters.

- [ ] **Step 4: Run tests to verify pass**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_job_queue.py' -v`

Expected: PASS.

### Task 3: API and System Status Tests

**Files:**
- Modify: `backend/tests/test_system_status.py`
- Modify: `backend/tests/test_agent_protocol.py`
- Modify later: `backend/app/main.py`

- [ ] **Step 1: Add failing system status worker section test**

Extend `test_system_status_payload_reports_database_tasks_and_scripts` to pass a fake worker queue object whose `snapshot()` returns a known queue state, then assert `payload["worker"]`.

- [ ] **Step 2: Add failing `/run-jobs` background response test**

Add an API test that patches `app.main.job_queue.enqueue`, posts to `/api/investigations/{id}/run-jobs`, and asserts `accepted`, `mode`, `status`, and `investigation_id` are returned without invoking synchronous execution.

- [ ] **Step 3: Run tests to verify failure**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_system_status.py' -v && PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_agent_protocol.py' -v`

Expected: FAIL because `system_status_payload()` has no worker queue parameter and `/run-jobs` still calls the worker synchronously.

- [ ] **Step 4: Implement API wiring**

Modify `backend/app/main.py` to import a module-level `job_queue`, use it in `/run-jobs`, pass it into `system_status_payload()`, and add a `worker` section.

- [ ] **Step 5: Run tests to verify pass**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_system_status.py' -v && PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_agent_protocol.py' -v`

Expected: PASS.

### Task 4: Documentation and Verification

**Files:**
- Modify: `docs/REAL_TOOL_ENABLEMENT.md`
- Modify: `docs/N100_DEPLOYMENT_RUNBOOK.md`
- Modify: `README.md`

- [ ] **Step 1: Update docs**

Replace wording that says `/run-jobs` is synchronous with background-queue wording. Keep private deployment details out of public docs.

- [ ] **Step 2: Run targeted tests**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_job_queue.py' -v && PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_system_status.py' -v && PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_worker.py' -v && PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_agent_protocol.py' -v`

Expected: PASS.

- [ ] **Step 3: Run full verification**

Run: `bash scripts/verify.sh`

Expected: PASS.

- [ ] **Step 4: Privacy scan new diff**

Run the project diff privacy scan described in `docs/PUBLIC_REPOSITORY_MAINTENANCE.md` against added lines only.

Expected: no output.

- [ ] **Step 5: Commit**

Run: `git add backend/app/main.py backend/app/services/job_queue.py backend/tests/test_job_queue.py backend/tests/test_system_status.py backend/tests/test_agent_protocol.py docs/REAL_TOOL_ENABLEMENT.md docs/N100_DEPLOYMENT_RUNBOOK.md README.md docs/superpowers/plans/2026-07-06-background-job-queue.md && git commit -m "Add background job queue"`

Expected: commit succeeds.
