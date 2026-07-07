# Next Phase Roadmap - 2026-07-06

This document defines the next working direction after the temporary closure in
[TEMPORARY_CLOSURE_2026-07-06.md](TEMPORARY_CLOSURE_2026-07-06.md).

Current status update, 2026-07-07:

- The latest closure record is
  [STAGE_CLOSURE_2026-07-07.md](STAGE_CLOSURE_2026-07-07.md).
- `/run-jobs` is backed by a SQLite recoverable queue.
- Official-site discovery and URL site collection are working.
- Gap-to-tool planning, completion policy, report rendering, public-safe parser
  fixtures, and official website URL/domain cross-verification normalization
  have been implemented.
- Full verification passes with backend `411 tests OK`, regression smoke
  `4` cases / `0` failed, frontend helper checks, Vitest, and production build.

The next phase should focus on product quality, evidence usability, and
operational governance rather than another large orchestration rewrite.

## Direction

The next phase should improve how useful and reviewable the output is after the
system already completes tasks reliably.

Primary direction:

- turn `NEEDS_REVIEW` and `BLOCKED` outcomes into concrete gap explanations,
  evidence requirements, and tool-driven follow-up plans;
- turn more real public-safe tool output into stable parser fixtures;
- make reports easier to export and hand off;
- add permission tiers and audit trails for production operations;
- improve evidence review fields so analysts can rank, confirm, or reject
  findings without losing provenance.

Avoid expanding infrastructure unless there is a concrete multi-host worker
need. The current SQLite-backed queue is sufficient for the single-host N100
deployment model.

## Priority Order

### P0 - Gap-to-Tool Automatic Follow-up Planner

Goal:

Make every incomplete investigation explain where it is stuck, what evidence is
missing, which existing tools can try to fill the gap, and which tools are
blocked by configuration or prior attempts.

Design and execution documents:

- [docs/superpowers/specs/2026-07-06-gap-to-tool-followup-planner-design.md](superpowers/specs/2026-07-06-gap-to-tool-followup-planner-design.md)
- [docs/superpowers/plans/2026-07-06-gap-to-tool-followup-planner.md](superpowers/plans/2026-07-06-gap-to-tool-followup-planner.md)

Tasks:

- Add `gap_analysis` to describe concrete blockers, missing evidence, and
  manual review hints.
- Add `gap_tool_plan` to map gaps to ready, unavailable, already attempted, or
  exhausted tools.
- Use tool health to explain `missing_config`, `missing_executable`, and
  `credential_blocked` states.
- Queue only ready, non-duplicate, budget-safe follow-up jobs.
- Add report output for `卡点与补采计划`.
- Keep the first implementation deterministic and use existing worker,
  registry, tool health, and report modules.

Acceptance:

- `NEEDS_REVIEW` task detail names specific gaps and required evidence.
- The report explains blockers, attempted tools, unavailable tools, and next
  actions.
- Ready tools are queued automatically within budget.
- Unknown or exhausted gaps include manual-review guidance.
- `bash scripts/verify.sh` passes.

Progress:

- Implemented `gap_analysis`, `gap_tool_plan`, and `gap_followup_summary` in
  investigation detail.
- Added deterministic tool mapping with `ready`, `missing_config`,
  `missing_executable`, `credential_blocked`, `disabled`, and
  `already_attempted` states.
- Worker gap follow-up planning now uses tool health, queues only ready
  non-duplicate jobs, and records queued plus blocked follow-up actions in
  events.
- Structured reports now include `## 卡点与补采计划`, listing blockers,
  missing evidence, ready tools, attempted tools, unavailable tools, and manual
  review hints.
- Status: complete for the current backend/report scope.

Verification:

- `PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v`
- `PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_quality_gate.py' -v`
- `PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_worker.py' -v`
- `bash scripts/verify.sh`: backend 338 tests passed, regression smoke 4 cases
  / 0 failed, frontend Vitest 9 tests passed, production build passed.

### P1 - Real Sample Regression Pack

Goal:

Build a stronger fixture library from public-safe real outputs so future parser
changes are tested against realistic artifacts.

Tasks:

- Collect sanitized public-safe artifacts for:
  - `official_site_search`
  - `httpx`
  - `katana`
  - `official_site_extractor`
  - `subfinder`
  - selected company/sparse-lead role-agent outputs
- Store fixtures under `backend/tests/fixtures/` using generic target names.
- Add parser regression tests for each fixture.
- Add one end-to-end smoke case that proves official-site URL evidence becomes
  entities, evidence records, relationships, and source-backed facts.

Acceptance:

- Fixtures contain no private target names, tokens, internal hostnames, or local
  paths.
- `bash scripts/verify.sh` passes.
- Regression tests fail if a parser drops important official-site evidence.

Progress:

- Public-safe fixtures now cover `official_site_search`, `httpx`, `katana`,
  `official_site_extractor`, `subfinder`, and role-agent sparse-lead output.
- Fixture regression tests protect official-site candidate linkage, live URL
  metadata, relevant business/contact pages, identity/contact/scope extraction,
  passive subdomain relationships, and public-safe role-agent output shape.
- Status: complete for the initial fixture pack; continue adding samples as
  optional regression hardening.

### P2 - Report Export Package

Goal:

Make investigation output easier to deliver outside the web UI.

Completed:

- HTML, Markdown, and PDF report endpoints using structured report content.
- BLUF, PIR answers, EEI matrix, quality gate, evidence appendix,
  source-backed facts, ACH/I&W, and next collection actions.
- Redaction safeguards for private tokens, local paths, and deployment
  details.
- Tests for report sections, dependency-missing behavior, redaction, and CJK
  PDF text.

Remaining:

- Add a bundled export package only if operators need Markdown, HTML, PDF, and
  evidence appendices in one download.
- Add export audit records after P3 audit logging exists.

Acceptance:

- A completed investigation can produce HTML, Markdown, and PDF reports from the API.
- Export tests verify required sections.
- Privacy scan of generated sample report passes.

### P3 - Permission Tiers And Audit Logs

Goal:

Make production operations safer by distinguishing read, management, and agent
write actions with durable audit events.

Tasks:

- Define permission tiers:
  - read-only status/detail access;
  - investigation management;
  - agent write-back;
  - destructive archive/delete actions.
- Add audit events for:
  - task creation;
  - run enqueue;
  - retry/reopen/cancel/archive/delete;
  - rejected authorization attempts;
  - agent write-back validation failures.
- Add tests for audit records and authorization boundaries.
- Document operational review steps in the deployment runbook.

Acceptance:

- Management actions produce audit events.
- Rejected write-back payloads are visible for operator review.
- Existing token behavior remains backward compatible unless explicitly
  migrated.

### P4 - Evidence Review Fields

Goal:

Improve analyst review quality without weakening evidence discipline.

Tasks:

- Add evidence review fields:
  - `source_url`
  - source rank or reliability score;
  - review status: `candidate`, `confirmed`, `rejected`, `needs_review`;
  - reviewer note;
  - reviewed timestamp.
- Surface review status in API detail and graph/report helpers.
- Keep automated confidence separate from human review status.
- Add migration and regression tests.

Acceptance:

- Analysts can distinguish machine confidence from human review state.
- Existing reports still render for older records.
- Review fields do not promote weak claims into confirmed facts automatically.

### P5 - External Queue Broker Readiness

Goal:

Prepare for, but not yet implement, Redis/Celery or another broker if multi-host
workers become necessary.

Tasks:

- Define the broker interface that would replace SQLite queue claim methods.
- Document when an external broker is justified:
  - multiple worker hosts;
  - high queue volume;
  - strict scheduling or retry requirements.
- Keep current SQLite queue as the default.

Acceptance:

- Architecture note exists.
- No new runtime dependency is introduced in this phase.

## Recommended First Task

Start with **P3 - Permission Tiers And Audit Logs**, then continue into **P4 -
Evidence Review Fields**.

Reason:

- P0/P1/P2 backend/report work is already implemented for the current closure.
- P3 improves production accountability for management actions, rejected
  write-back payloads, retries, archive/delete actions, and run enqueue events.
- P4 improves analyst usability by separating machine confidence from human
  review status without weakening evidence discipline.
- Neither P3 nor P4 requires a new queue architecture.

## Verification Baseline For Every Next-Phase Task

Every task in this roadmap should finish with:

```text
bash scripts/verify.sh
```

Expected:

- backend tests pass; the current baseline is `411 tests OK`;
- frontend helper checks pass;
- Vitest passes;
- frontend production build passes.

Before publishing or pushing:

- run added-line privacy scan from
  [PUBLIC_REPOSITORY_MAINTENANCE.md](PUBLIC_REPOSITORY_MAINTENANCE.md);
- verify no tokens, private hostnames, local absolute paths, or raw private task
  identifiers are added.

## Not In The Next Immediate Phase

Do not start these unless a separate decision is made:

- multi-host worker orchestration;
- Redis/Celery deployment;
- authenticated browser collection;
- paid API integrations;
- destructive data-retention changes;
- UI redesign beyond small review/export controls.

## P1 Progress - Real Sample Regression Pack

Implemented public-safe file-level parser fixtures for:

- `official_site_search`
- `httpx`
- `katana`
- `official_site_extractor`
- `subfinder`
- role-agent sparse-lead summary output

Protected behavior:

- official-site candidates remain linked to company targets;
- live URLs keep title, technology, and probe evidence;
- crawler output keeps relevant business/contact pages and filters noise;
- official-site HTML yields identity, contact, scope, address, evidence, and
  relationships;
- passive subdomains keep source evidence and root-domain relationships;
- role-agent output has a public-safe documented fixture shape.

Verification:

- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_tool_adapters.py' -v`
- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_tool_fixture_regressions.py' -v`
- `bash scripts/verify.sh`
- added-line privacy scan

## P2 Progress - Report Export Package

Implemented:

- structured Markdown report payload;
- HTML report endpoint;
- PDF report endpoint at `/api/investigations/{id}/report.pdf`;
- token, local-path, and deployment-detail redaction for exported reports;
- CJK-safe PDF rendering with `reportlab`;
- unit and API coverage for PDF success, missing investigation, missing
  dependency, redaction, and CJK text extraction.

Production retest on <production-host> confirmed:

- live public-safe investigation creation works;
- bounded `/run-jobs` enqueue returns immediately in background mode;
- live PDF export returns HTTP `200`, `application/pdf`, and a valid `%PDF`
  body when the API is started with `backend/.venv/bin/python`.

Remaining P2 work:

- add a packaged download flow if operators need to export Markdown, HTML, PDF,
  and evidence appendices together;
- add an operator-facing export audit record after P3 audit logs exist;
- keep report fixtures public-safe and privacy-scanned before publishing.

Verification:

- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v`
- `PYTHONPATH=backend uv run --project backend python3 -m unittest discover -s backend/tests -p 'test_report_pdf_export.py' -v`
- `bash scripts/verify.sh`
- added-line privacy scan from `docs/PUBLIC_REPOSITORY_MAINTENANCE.md`
