# Persistent Background Queue Design

## Context

The current background queue solved the immediate long-request problem:
`POST /api/investigations/{id}/run-jobs` returns quickly and a local daemon
thread calls the existing `run_investigation_jobs()` worker core.

That queue is still process-local. Pending queue requests and recent queue
history live only in memory. If the API process restarts, accepted queue
requests can be lost and an in-flight request has no durable queue-level record
for recovery. The underlying investigation jobs remain in SQLite, but the
operator must manually enqueue another run.

The next reliability upgrade should make the queue recoverable without adding a
new external service.

## Decision

Add a SQLite-backed queue table and adapt `BackgroundJobQueue` to use it when
the active store supports queue persistence.

The existing in-memory queue behavior remains available for tests and stores
without persistence. The default production path uses `SQLiteStore`, so it
should persist queue requests, claim them atomically, and recover unfinished
requests after process restart.

Redis, Celery, and multi-host workers remain out of scope for this phase.

## Goals

- Preserve the current API shape for `/run-jobs`.
- Persist accepted background run requests in SQLite.
- Deduplicate queue requests by investigation id while a request is `QUEUED` or
  `RUNNING`.
- Let a restarted API process resume durable `QUEUED` requests.
- Requeue stale durable `RUNNING` requests after a configurable timeout.
- Keep queue records privacy-light: investigation id, max job limit, status,
  timestamps, worker id, summary counters, and short error text only.
- Keep `run_investigation_jobs()` unchanged as the execution core.

## Non-Goals

- No external broker.
- No parallel execution.
- No multi-process distributed locking beyond SQLite atomic updates.
- No frontend redesign.
- No durable storage of seed values, target values, raw tool output, API tokens,
  local paths, or deployment hostnames in queue records.

## Queue Table

Add a SQLite table named `worker_queue_runs`:

```sql
CREATE TABLE IF NOT EXISTS worker_queue_runs (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    max_jobs INTEGER,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    worker_id TEXT NOT NULL DEFAULT '',
    heartbeat_at TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT ''
);
```

Status values:

- `QUEUED`: accepted and waiting.
- `RUNNING`: claimed by the local queue runner.
- `COMPLETED`: worker finished and returned a summary.
- `FAILED`: queue-level exception occurred.
- `CANCELLED`: reserved for future cancellation support.

SQLite should not rely on a broad `UNIQUE(investigation_id, status)` constraint
because terminal history can contain multiple completed runs for the same
investigation. The implementation should:

- enforce active dedupe in `enqueue_worker_run()` with a transaction checking
  `status IN ('QUEUED', 'RUNNING')`;
- keep terminal rows for recent history.

## Store Interface

Add queue persistence methods to `SQLiteStore`:

- `enqueue_worker_run(investigation_id, max_jobs) -> dict`
- `claim_next_worker_run(worker_id, stale_after_seconds) -> dict | None`
- `complete_worker_run(queue_id, summary) -> dict | None`
- `fail_worker_run(queue_id, error) -> dict | None`
- `worker_queue_snapshot(limit=20) -> dict`

The methods should be transaction-safe:

- enqueue checks that the investigation exists;
- enqueue returns `accepted: false` if an active queue row already exists;
- claim first releases stale `RUNNING` rows back to `QUEUED`, then atomically
  moves the oldest `QUEUED` row to `RUNNING`;
- complete/fail only update rows currently owned by the caller's queue id.

`MemoryStore` can optionally provide a simple in-memory equivalent for tests,
but it does not need restart recovery.

## Queue Runner Behavior

`BackgroundJobQueue` should support two backends:

1. Persistent backend when the store has the queue persistence methods.
2. Current in-memory backend as fallback.

Persistent path:

- `/run-jobs` calls `queue.enqueue(store, investigation_id, max_jobs)`.
- `enqueue()` persists the request through `store.enqueue_worker_run()`.
- `enqueue()` starts the daemon thread if it is not alive.
- The daemon loop calls `store.claim_next_worker_run(worker_id, stale_after_seconds)`.
- Each claimed row calls `run_investigation_jobs(store, investigation_id,
  max_jobs=max_jobs)`.
- The daemon records `COMPLETED` or `FAILED` through the store.
- The loop exits when no claimable durable rows remain.

Recovery path:

- On API startup, the queue runner should be able to start and claim existing
  `QUEUED` rows.
- A stale `RUNNING` row should be requeued if its `heartbeat_at` or `started_at`
  is older than `WORKER_QUEUE_STALE_SECONDS`, default `1800`.
- A non-stale `RUNNING` row is treated as active and shown in status.

For this phase, startup can be lazy: the first enqueue or first system status
call may start the queue runner. A future phase can add explicit autorun during
server startup if production testing shows it is needed.

## API Behavior

`POST /api/investigations/{id}/run-jobs` keeps the current background response
shape:

```json
{
  "accepted": true,
  "mode": "background",
  "status": "QUEUED",
  "investigation_id": "<id>",
  "max_jobs": 6,
  "queue_depth": 1,
  "running": null
}
```

Duplicate active enqueue returns:

```json
{
  "accepted": false,
  "mode": "background",
  "status": "ALREADY_QUEUED",
  "investigation_id": "<id>",
  "max_jobs": 6,
  "queue_depth": 1,
  "running": null
}
```

If the active duplicate is already running, status should be
`ALREADY_RUNNING`.

`GET /api/system/status` should continue returning the `worker` section. With
SQLite persistence, this section should be based on `worker_queue_runs` plus
the runner's local thread state:

```json
{
  "mode": "sqlite",
  "queue_depth": 2,
  "running": "<investigation-id-or-null>",
  "pending": [],
  "recent_runs": [],
  "recent_errors": []
}
```

## Error Handling

- Missing investigation returns `404` before enqueue.
- Duplicate active queue row returns a non-error `accepted: false`.
- Worker exceptions mark the queue row `FAILED` and write an investigation
  event when possible.
- Tool-level failures remain owned by `run_investigation_jobs()` and job
  statuses.
- Queue errors should not crash the API server thread.

## Migration and Rollback

Migration is additive:

- create `worker_queue_runs`;
- record a schema migration version such as
  `20260706_persistent_background_queue`;
- do not mutate existing investigation, job, evidence, or report rows.

Rollback:

- Existing app versions can ignore the extra table.
- If rollback is needed, leave the table in place and redeploy the previous app
  commit.
- No source data is lost because queue rows do not own investigation results.

## Testing

Add tests before implementation:

- SQLite schema includes `worker_queue_runs` and migration version.
- Enqueue persists a queue row and rejects duplicate active rows.
- Claim moves the oldest queued row to running.
- Complete records summary counters and exposes recent runs.
- Fail records short error text and exposes recent errors.
- Stale running rows are released and can be claimed after timeout.
- `BackgroundJobQueue` uses the persistent store path when available.
- Simulated restart: create a queued row with one queue instance, create a new
  queue instance using the same SQLite database, then verify it claims and
  completes the row.
- `/api/system/status` reports persistent queue state.
- Existing `run_investigation_jobs()` tests remain unchanged.

## Documentation Updates

Update:

- `README.md`: current maturity should mention recoverable SQLite queue.
- `docs/REAL_TOOL_ENABLEMENT.md`: larger tasks use durable background queue
  with bounded `max_jobs`.
- `docs/N100_DEPLOYMENT_RUNBOOK.md`: queue status and restart recovery checks.
- `docs/UPDATE_LOG.md`: record the persistent queue upgrade and verification.

## Open Risks

- SQLite locking is adequate for the current single-process N100 deployment,
  but not a multi-host worker cluster.
- Restarting while a tool subprocess is running can leave tool-side artifacts
  partially written. Recovery should re-run the bounded worker batch; adapter
  parsers and job claim guards must continue to handle already terminal jobs.
- Lazy startup recovery means a queued durable row may wait until an API status
  or enqueue interaction wakes the runner. Explicit startup autorun can be
  added later.
