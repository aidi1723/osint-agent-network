# Persistent Background Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist background `/run-jobs` requests in SQLite so queued work can survive API process restarts.

**Architecture:** Add a `worker_queue_runs` SQLite table and queue persistence methods on `SQLiteStore`. Update `BackgroundJobQueue` to use those methods when available and keep the current in-memory behavior for fallback stores.

**Tech Stack:** Python standard library `sqlite3`, `threading`, `unittest`, existing `SQLiteStore`, existing `BackgroundJobQueue`, existing `run_investigation_jobs()`.

---

### Task 1: SQLite Queue Store Contract

**Files:**
- Modify: `backend/app/services/store.py`
- Modify: `backend/tests/test_system_status.py`
- Create: `backend/tests/test_persistent_job_queue.py`

- [ ] **Step 1: Write failing schema and enqueue tests**

Add `backend/tests/test_persistent_job_queue.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_persistent_job_queue.py' -v`

Expected: FAIL because `worker_queue_snapshot()` and `enqueue_worker_run()` do not exist.

- [ ] **Step 3: Implement schema and enqueue/snapshot**

In `SQLiteStore._init_schema()`, create `worker_queue_runs` with fields from the design and record schema migration `20260706_persistent_background_queue`. Implement:

```python
def enqueue_worker_run(self, investigation_id: str, max_jobs: int | None = None) -> dict
def worker_queue_snapshot(self, limit: int = 20) -> dict
```

Return response keys compatible with `BackgroundJobQueue.enqueue()`: `accepted`, `mode`, `status`, `investigation_id`, `max_jobs`, `queue_depth`, and `running`.

- [ ] **Step 4: Run tests to verify pass**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_persistent_job_queue.py' -v`

Expected: PASS.

### Task 2: Claim, Complete, Fail, and Stale Recovery

**Files:**
- Modify: `backend/app/services/store.py`
- Modify: `backend/tests/test_persistent_job_queue.py`

- [ ] **Step 1: Write failing lifecycle tests**

Extend `PersistentJobQueueStoreTests` with tests for:

```python
def test_claim_complete_and_recent_run_snapshot(self): ...
def test_fail_records_recent_error(self): ...
def test_stale_running_run_is_requeued_and_claimed(self): ...
```

Expected behaviors:

- `claim_next_worker_run("worker-a", stale_after_seconds=1800)` moves oldest queued row to `RUNNING`.
- `complete_worker_run(queue_id, summary)` records terminal summary counters and exposes `recent_runs`.
- `fail_worker_run(queue_id, "boom")` records short error text and exposes `recent_errors`.
- a stale running row becomes claimable again when `stale_after_seconds=0`.

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_persistent_job_queue.py' -v`

Expected: FAIL because claim/complete/fail methods do not exist.

- [ ] **Step 3: Implement lifecycle methods**

Add:

```python
def claim_next_worker_run(self, worker_id: str, stale_after_seconds: int = 1800) -> dict | None
def complete_worker_run(self, queue_id: str, summary: dict) -> dict | None
def fail_worker_run(self, queue_id: str, error: str) -> dict | None
```

Use transactions and `_now()` timestamps. Keep summary JSON limited to worker counters.

- [ ] **Step 4: Run tests to verify pass**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_persistent_job_queue.py' -v`

Expected: PASS.

### Task 3: Persistent Queue Runner Path

**Files:**
- Modify: `backend/app/services/job_queue.py`
- Modify: `backend/tests/test_job_queue.py`
- Modify: `backend/tests/test_system_status.py`

- [ ] **Step 1: Write failing queue runner tests**

Add tests verifying:

```python
def test_queue_uses_persistent_store_methods_when_available(self): ...
def test_persistent_queue_survives_new_queue_instance(self): ...
```

The restart simulation should create a queued row with one `SQLiteStore`, instantiate a new `BackgroundJobQueue` with a fake worker, call `ensure_running(store)`, wait for idle, and assert the durable row completed.

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_job_queue.py' -v`

Expected: FAIL because `BackgroundJobQueue` does not use persistent store methods.

- [ ] **Step 3: Implement persistent path**

In `BackgroundJobQueue`:

- add `worker_id`;
- add `ensure_running(store=None)`;
- detect persistent stores with `enqueue_worker_run`, `claim_next_worker_run`, `complete_worker_run`, `fail_worker_run`, and `worker_queue_snapshot`;
- process persistent queues by repeatedly claiming rows from the store;
- keep in-memory fallback unchanged for object stores.

- [ ] **Step 4: Update system status default behavior**

Make `BackgroundJobQueue.snapshot(store=None)` use `store.worker_queue_snapshot()` when a persistent store is passed. Update `system_status_payload()` to call `worker_queue.snapshot(store_obj)`.

- [ ] **Step 5: Run tests to verify pass**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_job_queue.py' -v && PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_system_status.py' -v`

Expected: PASS.

### Task 4: Docs, Verification, and Commit

**Files:**
- Modify: `README.md`
- Modify: `docs/REAL_TOOL_ENABLEMENT.md`
- Modify: `docs/N100_DEPLOYMENT_RUNBOOK.md`
- Modify: `docs/UPDATE_LOG.md`

- [ ] **Step 1: Update docs**

Document that the background queue is SQLite-backed and recoverable after process restart. Mention bounded `max_jobs` remains recommended.

- [ ] **Step 2: Run targeted tests**

Run: `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_persistent_job_queue.py' -v && PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_job_queue.py' -v && PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_system_status.py' -v && PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_worker.py' -v`

Expected: PASS.

- [ ] **Step 3: Run full verification**

Run: `bash scripts/verify.sh`

Expected: PASS.

- [ ] **Step 4: Privacy scan new diff**

Run the project diff privacy scan described in `docs/PUBLIC_REPOSITORY_MAINTENANCE.md` against added lines only.

Expected: no output.

- [ ] **Step 5: Commit and push**

Run:

```bash
git add README.md backend/app/services/store.py backend/app/services/job_queue.py backend/app/main.py backend/tests/test_persistent_job_queue.py backend/tests/test_job_queue.py backend/tests/test_system_status.py docs/REAL_TOOL_ENABLEMENT.md docs/N100_DEPLOYMENT_RUNBOOK.md docs/UPDATE_LOG.md docs/superpowers/plans/2026-07-06-persistent-background-queue.md
git commit -m "Add persistent background queue"
git push origin main
```

Expected: commit and push succeed after verification.
