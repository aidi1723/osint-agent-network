# Background Job Queue Design

## Context

The current `POST /api/investigations/{id}/run-jobs` endpoint executes
`run_investigation_jobs()` inside the request thread. This is acceptable for
small bounded batches, but real investigations can chain many collectors and
site follow-ups. Long synchronous requests make production runs fragile because
the caller must remain connected until the batch finishes.

The existing worker core is already useful and should stay intact:

- `run_investigation_jobs()` owns job priority, dependency checks, follow-up
  planning, quality assessment, risk report generation, and final investigation
  status.
- Store implementations already support atomic job claiming through
  `claim_job_for_worker()`.
- Investigation detail already exposes job status and events for progress
  polling.

## Decision

Implement an in-process background queue as the first production step.

`POST /api/investigations/{id}/run-jobs` should enqueue a background execution
request and return quickly. A single local queue runner should process accepted
investigations sequentially by calling the existing `run_investigation_jobs()`.

This phase intentionally does not add Redis, Celery, or a new persistent queue
table. SQLite-backed persistent queue recovery is a future upgrade once the
basic asynchronous behavior is proven on the current deployment.

## API Behavior

### Enqueue Run

Endpoint:

```text
POST /api/investigations/{id}/run-jobs
```

Request body remains compatible:

```json
{
  "max_jobs": 6
}
```

Successful response should be immediate and shaped like:

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

If the same investigation is already queued or running, the endpoint should not
enqueue a duplicate. It should return:

```json
{
  "accepted": false,
  "mode": "background",
  "status": "ALREADY_QUEUED",
  "investigation_id": "<id>",
  "max_jobs": 6,
  "queue_depth": 1,
  "running": "<id-or-null>"
}
```

The endpoint should still return `404` for missing investigations.

## Queue Runner

Create a small service module with a single responsibility: manage background
execution requests for local worker runs.

The runner should:

- Hold pending requests in memory.
- Start one daemon worker thread on first enqueue.
- Execute one investigation at a time to avoid SQLite write contention and
  duplicated tool execution.
- Deduplicate by investigation id across both pending and running work.
- Call `run_investigation_jobs(store, investigation_id, max_jobs=...)`.
- Record recent completed runs and recent errors for status reporting.
- Keep failures inside the worker thread so the API process does not crash.

The queue request should store only operational fields:

- investigation id
- requested `max_jobs`
- enqueue timestamp

No target seed values, tokens, hostnames, local paths, or private deployment
details should be logged by the queue itself.

## Status Visibility

Extend `GET /api/system/status` with a `worker` section:

```json
{
  "worker": {
    "mode": "in_process",
    "queue_depth": 0,
    "running": null,
    "pending": [],
    "recent_runs": [],
    "recent_errors": []
  }
}
```

The `pending` list should include investigation ids and max job limits only.
The `recent_runs` list should include investigation id, started/completed/
failed/blocked counts, and timestamps. The `recent_errors` list should include
investigation id, timestamp, and a short error string.

Investigation detail remains the main progress surface for job-by-job status,
events, evidence, quality score, and final report.

## Error Handling

Queue-level errors should not bypass existing worker status handling.

- Missing investigation during enqueue returns `404`.
- Duplicate enqueue returns a non-error response with `accepted: false`.
- Exceptions raised while processing a queued request are captured in
  `recent_errors` and logged as an investigation event when possible.
- Existing worker behavior for blocked tools, failed jobs, partial failures,
  quality-gate downgrades, and report refresh remains unchanged.

## Testing

Add focused tests before implementation:

- Queue accepts a run and returns before executing the worker body.
- Duplicate enqueue for the same investigation is rejected while pending or
  running.
- The background runner calls the worker and records a recent run.
- Worker exceptions are captured without killing the queue thread.
- `system_status_payload()` exposes worker queue state.
- The `/run-jobs` API route returns the new background response shape.

Existing worker tests should continue to validate the synchronous
`run_investigation_jobs()` execution core directly.

## Non-Goals

- No Redis/Celery in this phase.
- No multi-process distributed worker coordination.
- No persistent queue recovery after process restart.
- No cancellation of a currently executing local tool process beyond the
  existing task cancellation lifecycle.
- No frontend redesign; the current polling surfaces should continue to work
  through investigation detail and system status.

## Future Upgrade Path

The SQLite-backed queue table upgrade is covered by
`2026-07-06-persistent-background-queue-design.md`. After that phase, the next
upgrade should be considered only if multi-host workers require an external
broker. The queue runner interface should keep enqueue/status/process
boundaries clear so future persistence or broker changes do not require
rewriting `run_investigation_jobs()`.
