# Next Phase Roadmap - 2026-07-06

This document defines the next working direction after the temporary closure in
[TEMPORARY_CLOSURE_2026-07-06.md](TEMPORARY_CLOSURE_2026-07-06.md).

The current platform baseline is closed for now: `/run-jobs` is backed by a
SQLite recoverable queue, official-site discovery and URL site collection are
working, and full verification passes. The next phase should focus on product
quality, evidence usability, and operational governance rather than another
large orchestration rewrite.

## Direction

The next phase should improve how useful and reviewable the output is after the
system already completes tasks reliably.

Primary direction:

- turn more real public-safe tool output into stable parser fixtures;
- make reports easier to export and hand off;
- add permission tiers and audit trails for production operations;
- improve evidence review fields so analysts can rank, confirm, or reject
  findings without losing provenance.

Avoid expanding infrastructure unless there is a concrete multi-host worker
need. The current SQLite-backed queue is sufficient for the single-host N100
deployment model.

## Priority Order

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

### P2 - Report Export Package

Goal:

Make investigation output easier to deliver outside the web UI.

Tasks:

- Add HTML report export using the existing structured report content.
- Add PDF export after HTML output is stable.
- Include BLUF, PIR answers, EEI matrix, quality gate, evidence appendix,
  source-backed facts, ACH/I&W, and next collection actions.
- Add redaction safeguards for private tokens, local paths, and deployment
  details.
- Add tests for report sections and export file creation.

Acceptance:

- A completed investigation can produce an HTML report from the API or script.
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

Start with **P1 - Real Sample Regression Pack**.

Reason:

- It raises confidence in the real OSINT pipeline without changing production
  architecture.
- It protects recent improvements to official-site discovery and URL
  collection.
- It creates safer test data for later report export and evidence review work.

## Verification Baseline For Every Next-Phase Task

Every task in this roadmap should finish with:

```text
bash scripts/verify.sh
```

Expected:

- backend tests pass;
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

Implemented first-stage report export for completed investigations:

- structured report JSON;
- Markdown report;
- self-contained HTML report.

Protected behavior:

- export reuses the existing structured report and quality assessment;
- HTML output includes BLUF, PIR answers, EEI coverage, quality gate,
  source-backed facts, evidence appendix, ACH/I&W, gaps, and next actions;
- export responses apply redaction before returning content;
- missing investigations return `404`.

Verification:

- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v`
- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_*.py' -v`
- `bash scripts/verify.sh`
- added-line privacy scan from `docs/PUBLIC_REPOSITORY_MAINTENANCE.md`

Deferred:

- PDF export remains a follow-up after the HTML contract is stable.

## P2b Progress - PDF Report Export

Implemented PDF report export for completed investigations:

- `GET /api/investigations/{id}/report.pdf`;
- PDF rendering from the same redacted structured report payload as JSON, Markdown, and HTML;
- explicit `503` response when the PDF dependency is unavailable;
- PDF text verification for required report sections.

Protected behavior:

- PDF export does not parse HTML or read the database directly;
- existing JSON, Markdown, and HTML report endpoints remain unchanged;
- generated report content keeps redaction safeguards for tokens, local paths, private hosts, and private service URLs.

Only the PDF/report unit tests are recorded as completed so far:

- `PYTHONPATH=backend uv run --project backend python3 -m unittest discover -s backend/tests -p 'test_report_pdf_export.py' -v`
- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v`

Pending Task 6 final checks:

- `bash scripts/verify.sh`
- PDF render check with `pdftoppm` when available
- added-line privacy scan from `docs/PUBLIC_REPOSITORY_MAINTENANCE.md`
