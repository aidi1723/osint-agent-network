# Worker And Risk Review Design

Date: 2026-05-19
Project: OSINT Agent Network

## Purpose

Connect planned jobs to an executable worker loop and expose a review-focused UI for social risk results. The first version keeps execution controlled: operators can run an investigation queue manually, and an optional background loop can be enabled through environment configuration later.

## Scope

First version:

- Add a backend worker service that executes queued jobs for one investigation on demand.
- Add a POST API endpoint: `/api/investigations/{id}/run-jobs`.
- Keep job execution inside the current lightweight HTTP backend and SQLite/MemoryStore architecture.
- Parse adapter artifacts into existing entities, evidence, and relationships.
- Queue follow-up jobs from parsed entities, respecting depth and budget limits.
- Generate a social risk report when social enrichment evidence exists.
- Add UI controls and panels for queue execution and risk review.

Out of scope for the first version:

- Redis, Celery, or external queue services.
- Concurrent multi-process workers.
- Long-running streaming output.
- Automatic execution by default on server startup.
- Automatic customer blocking or restriction.

## Runtime Behavior

Manual execution is the default path:

```text
UI button
  -> POST /api/investigations/{id}/run-jobs
  -> worker claims QUEUED jobs for that investigation
  -> adapter runs or parses artifact
  -> normalized results are written to store
  -> follow-up jobs are appended
  -> risk summary is calculated
  -> investigation detail refreshes
```

Optional background execution can be added behind:

```text
OSINT_WORKER_AUTORUN=true
```

The first implementation may expose the config but should keep manual execution as the stable operator path.

## Job Statuses

Use these statuses for jobs:

- `QUEUED`: ready to run.
- `RUNNING`: worker is executing it.
- `COMPLETED`: adapter ran and parsed successfully.
- `PARTIAL_FAILED`: command failed but useful artifact data was parsed.
- `FAILED`: command or parser failed with no useful result.
- `BLOCKED`: executable, credentials, or required artifact is missing.
- `SKIPPED`: budget or deduplication prevented execution.

Investigation status mapping:

- Any run starts by setting investigation to `RUNNING`.
- If at least one job completed and risk review is available: `NEEDS_REVIEW`.
- If all planned jobs completed and no review is needed: `COMPLETED`.
- If some jobs fail or block but useful data exists: `PARTIAL_FAILED`.
- If no job produced useful data: `FAILED`.

## Worker Responsibilities

`app.services.worker` should expose:

```python
run_investigation_jobs(
    store,
    investigation_id: str,
    max_jobs: int | None = None,
    artifact_root: Path | None = None,
) -> dict
```

The result should include:

```json
{
  "investigation_id": "...",
  "started": 4,
  "completed": 3,
  "failed": 1,
  "blocked": 0,
  "queued_followups": 5,
  "risk_report": {}
}
```

Worker steps:

1. Load investigation detail.
2. Build `already_planned` from existing jobs.
3. Pick `QUEUED` jobs for the investigation.
4. Mark each job `RUNNING`.
5. Resolve adapter by `tool_name`.
6. Execute adapter or parse artifact.
7. Write entities, evidence, and relationships to store.
8. Mark job terminal status.
9. Generate follow-up jobs from new entities.
10. Stop when job budget or depth budget is reached.
11. Build social risk report from current detail.
12. Save summary/report fields and investigation status.

## Adapter Execution Rules

- Each job gets a working directory under `data/jobs/{investigation_id}/{job_id}`.
- CLI tools use argument arrays, never shell interpolation.
- If adapter has a `run()` method, call it.
- Otherwise call `build_command()` and `run_tool_command()`.
- If expected artifact exists after a non-zero return code, attempt parsing and mark `PARTIAL_FAILED`.
- If executable is missing, mark `BLOCKED` with an event.
- If parser fails, mark `FAILED` with an event.
- Keep stdout/stderr excerpts in event metadata in first version.

## Store Additions

Add methods to MemoryStore and SQLiteStore:

- `list_jobs(investigation_id)`
- `update_job_status(job_id, status)`
- `add_jobs(investigation_id, planned_jobs)`

Add derived detail fields in `get_investigation()`:

- `job_counts`
- `risk_report`

The first version can store `risk_report` as JSON in `report_markdown` only if schema changes are too large, but preferred implementation is to add a nullable `risk_report_json` column to SQLite and an optional `risk_report` field in memory.

## Risk Report Rules

Run social risk scoring when any entity type is one of:

- `profile_url`
- `social_profile`
- `platform_account`
- `bio_snippet`
- `declared_location`
- `interest_tag`
- `risk_signal`

If no social evidence exists, return an empty or low-risk report with `review_required=false`.

## UI Design

Follow `DESIGN.md`: dense, calm, operational, no marketing layout.

Add to selected investigation detail:

- Queue controls:
  - Run queued jobs
  - Retry failed jobs later
  - Cancel remains existing behavior
- Job status strip:
  - queued, running, completed, failed, blocked
- Risk review panel:
  - overall score and level
  - five category scores
  - top risk signals
  - public profile summary
- Evidence list stays tabular and compact.

Visual tone:

- Use compact panels with 8px radius.
- Use amber/red only for review risk, not decoration.
- Use monospace for entity values, URLs, and IDs.
- Keep all risk language cautious: `疑似`, `公开声明`, `需要复核`.

## Validation

Backend tests:

- `run_investigation_jobs` executes queued jobs using a fake adapter.
- Worker writes entities, evidence, and relationships.
- Worker queues profile URL follow-up jobs.
- Worker marks missing adapters or commands as blocked/failed.
- `/api/investigations/{id}/run-jobs` returns run summary.
- Investigation detail includes `job_counts` and `risk_report`.

Frontend checks:

- Build succeeds.
- UI renders run queue button.
- UI renders risk summary when `risk_report` is present.
- Existing investigation creation and action controls remain available.

## First-Version Defaults

- Manual run is enabled.
- Background autorun is not enabled by default.
- Worker runs jobs sequentially.
- Worker caps one manual run at investigation `max_jobs`.
- Risk report is generated after each manual run.
- Tool healthcheck endpoints can come after this phase.
