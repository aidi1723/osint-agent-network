# Temporary Closure - 2026-07-06

> Superseded for current project status by
> [STAGE_CLOSURE_2026-07-07.md](STAGE_CLOSURE_2026-07-07.md). Keep this file as
> the historical closure record for the 2026-07-06 queue/runtime phase.

This document is the temporary closure record for the current 情报官 /
OSINT Agent Network phase. It supersedes earlier handoff summaries for current
runtime behavior, queue execution, documentation alignment, and verification
status.

## Closure Status

Temporary closure is acceptable for this phase.

The project now has:

- task creation and investigation detail APIs;
- local role-agent execution and external Agent write-back protocol;
- real-tool health checks and health-aware initial planning;
- official-site discovery through a SearXNG-compatible layer;
- URL site-collection priority for `httpx`, `katana`, and
  `official_site_extractor`;
- SQLite-backed recoverable background `/run-jobs` queue;
- gap-to-tool follow-up planning for concrete missing evidence;
- completion-policy decisions for strict, limited, blocked, failed, and
  continue-collection outcomes;
- normalized official website URL/domain cross-verification;
- quality gate, cross-verification, graph output, and whitepaper report flow;
- system status, healthcheck, backup, and production readiness scripts;
- public-release privacy rules and GPLv3 license alignment.

## Latest Runtime Behavior

`POST /api/investigations/<id>/run-jobs` no longer runs as a synchronous long
request. It enqueues a background worker run and returns immediately with
`mode: "background"`.

The queue is now backed by SQLite:

- accepted queue requests are stored in `worker_queue_runs`;
- duplicate active requests for the same investigation are rejected as
  `ALREADY_QUEUED` or `ALREADY_RUNNING`;
- queued requests can be recovered after API process restart;
- stale `RUNNING` queue rows can be released and claimed again;
- `/api/system/status` exposes queue depth, running investigation id, recent
  runs, and recent errors.

Large real tasks should still use bounded `max_jobs` batches and be monitored
through investigation detail plus `/api/system/status`.

## Verification Evidence

Latest full verification:

```text
bash scripts/verify.sh
backend: 411 tests OK
regression smoke: 4 cases / 0 failed
frontend: Vitest 2 files / 9 tests
frontend build: passed
```

Targeted queue coverage includes:

- `backend/tests/test_persistent_job_queue.py`
- `backend/tests/test_job_queue.py`
- `backend/tests/test_system_status.py`
- `backend/tests/test_agent_protocol.py`
- `backend/tests/test_worker.py`

Privacy check:

- added-line diff scan produced no output before the latest implementation
  push;
- no tokens, private hostnames, local absolute deployment paths, or raw task
  identifiers were added to public docs in this closure pass.

## GitHub Sync

Latest pushed implementation commits:

- `3802170 docs: design persistent background queue`
- `1e5ad65 docs: plan persistent background queue`
- `b6d9f2d Add persistent background queue`

Current expected repository state:

```text
main...origin/main
```

## Documents Aligned

Current source-of-truth entry points:

- [README.md](../README.md)
- [docs/FINAL_HANDOFF.md](FINAL_HANDOFF.md)
- [docs/STAGE_CLOSURE_2026-07-07.md](STAGE_CLOSURE_2026-07-07.md)
- [docs/PROJECT_PACKAGE.md](PROJECT_PACKAGE.md)
- [docs/UPDATE_LOG.md](UPDATE_LOG.md)
- [docs/N100_DEPLOYMENT_RUNBOOK.md](N100_DEPLOYMENT_RUNBOOK.md)
- [docs/REAL_TOOL_ENABLEMENT.md](REAL_TOOL_ENABLEMENT.md)
- [docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md](N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md)

Design and implementation records:

- [docs/superpowers/specs/2026-07-06-gap-to-tool-followup-planner-design.md](superpowers/specs/2026-07-06-gap-to-tool-followup-planner-design.md)
- [docs/superpowers/plans/2026-07-06-gap-to-tool-followup-planner.md](superpowers/plans/2026-07-06-gap-to-tool-followup-planner.md)
- [docs/superpowers/specs/2026-07-06-evidence-shortfall-completion-policy-design.md](superpowers/specs/2026-07-06-evidence-shortfall-completion-policy-design.md)
- [docs/superpowers/plans/2026-07-06-evidence-shortfall-completion-policy.md](superpowers/plans/2026-07-06-evidence-shortfall-completion-policy.md)
- [docs/superpowers/specs/2026-07-06-background-job-queue-design.md](superpowers/specs/2026-07-06-background-job-queue-design.md)
- [docs/superpowers/plans/2026-07-06-background-job-queue.md](superpowers/plans/2026-07-06-background-job-queue.md)
- [docs/superpowers/specs/2026-07-06-persistent-background-queue-design.md](superpowers/specs/2026-07-06-persistent-background-queue-design.md)
- [docs/superpowers/plans/2026-07-06-persistent-background-queue.md](superpowers/plans/2026-07-06-persistent-background-queue.md)

## Remaining Optional Work

The next phase is defined in
[NEXT_PHASE_ROADMAP_2026-07-06.md](NEXT_PHASE_ROADMAP_2026-07-06.md).
These are optional next phases, not blockers for this temporary closure:

- collect more real public-safe tool artifacts and parser fixtures;
- add bundled report downloads and export audit records;
- implement permission tiers and audit logs;
- add evidence URL/source rank/review-state product fields;
- consider an external broker only if multi-host worker execution becomes
  necessary.

## Closure Decision

The current phase can stop here temporarily. The system has moved from
synchronous manual job execution to a SQLite-backed recoverable queue, and the
public documentation now reflects that state.
