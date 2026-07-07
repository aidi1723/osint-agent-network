# Capability Baseline - 2026-07-07

This document records the current capability baseline for OSINT Agent Network /
情报官 at formal stage closure. It is the concise capability map for operators,
engineers, and future development sessions.

## Stage Status

The project is stage-closed and ready for continued operation and incremental
optimization.

Latest verified baseline:

- `bash scripts/verify.sh` passed.
- Backend unittest discovery: `411 tests OK`.
- Regression smoke: `4` cases / `0` failed.
- Frontend helper checks passed.
- Vitest: `2` files / `9` tests passed.
- Frontend production build passed.
- Public-release license check passed with `GPL-3.0-only`.

## 1. Task And Agent Orchestration

Supported target types:

- `company`
- `sparse_lead`
- `domain`
- `subdomain`
- `email`
- `username`
- `phone`
- `ip`
- `url`
- `profile_url`

Current orchestration capabilities:

- Create investigations from the web UI or API.
- Generate role-agent and tool-agent job queues by target type and strategy.
- Run local role agents for collection, verification, and reporting.
- Accept external Agent write-back through the documented Agent protocol.
- Persist entities, evidence, relationships, evidence records, facts,
  hypotheses, reports, and worker events.
- Keep structured data as the source of graph and report output; reports alone
  are not considered sufficient evidence.

## 2. Background Execution

`POST /api/investigations/<id>/run-jobs` no longer depends on a synchronous
long request.

Current queue capabilities:

- SQLite-backed background worker queue.
- Immediate API response with background execution mode.
- Duplicate active request protection.
- Running investigation visibility through `/api/system/status`.
- Queue recovery after API process restart.
- Stale running-row release and reclaim behavior.
- Bounded execution through `max_jobs` batches.

## 3. Tool Planning And Collection

Current tool-facing capabilities:

- Tool health reporting through `/api/tools/health`.
- Tool route planning through `/api/tools/plan` and `agent_client plan-tools`.
- Health-aware planning for missing config, missing executable, disabled, or
  credential-blocked tools.
- Safe blocked-job semantics: unavailable tools become `BLOCKED` with an
  explanation instead of generic task failures.

Implemented and covered tool adapters include:

- `official_site_search`
- `httpx`
- `katana`
- `official_site_extractor`
- `subfinder`
- Sherlock
- Maigret
- Socialscan
- theHarvester
- Amass
- SpiderFoot
- Recon-ng
- GHunt
- PhoneInfoga
- Profile Parser
- Company News
- Upkuajing customs/supply-chain API proxy

The core short-run website evidence chain is:

```text
official_site_search -> httpx(url) -> katana(url) -> official_site_extractor(url)
```

## 4. Gap-To-Tool Follow-Up Planning

The system can now explain why an investigation is not complete and decide what
to do next.

Current outputs:

- `gap_analysis`: concrete blockers, missing evidence, and manual-review hints.
- `gap_tool_plan`: ready, unavailable, attempted, exhausted, or blocked tool
  actions mapped to gaps.
- `gap_followup_summary`: counts and queue/blocking summary.

Worker behavior:

- Queues ready, non-duplicate, budget-safe follow-up jobs.
- Records blocked tools and follow-up decisions in events.
- Avoids repeating unavailable or already-attempted actions.

Report behavior:

- Structured reports include `## 卡点与补采计划`.

## 5. Completion Policy

The system now has deterministic completion-policy output instead of relying
only on a single status field.

Supported modes:

- `strict`
- `limited`
- `continue_collection`
- `ready_for_human_decision`
- `blocked_by_environment`
- `failed`

Current safeguards:

- Missing official website, source-backed evidence ledger, fact pool, BLUF
  report, high-risk review, or unresolved contradiction cannot be silently
  waived.
- Limited completion is allowed only when the evidence floor is satisfied and
  remaining limitations are acceptable.
- Environment-blocked tasks do not loop indefinitely when useful tools are
  unavailable.
- Worker summaries expose `completion_policy` and `completion_mode`.
- Reports include completion mode, remaining blockers, acceptable limitations,
  and operator next actions.

## 6. Evidence, Facts, And Cross-Verification

Current evidence model:

- Entities, evidence, relationships, evidence records, facts, hypotheses, and
  report outputs are stored together in investigation detail.
- Confirmed facts require source-backed evidence.
- Admiralty Code is used for source/reliability discipline.
- Cross-verification rows summarize candidate value, supporting source
  families, contradicting source families, linked evidence, linked facts,
  status, confidence, and rationale.

Current cross-verification improvements:

- Official website URL/domain variants are normalized to hostname for support
  lookup, linked evidence, linked facts, and contradiction checks.
- Equivalent values such as `example.test`, `https://example.test`, and
  `https://www.example.test/` no longer create false conflicts.
- Real conflicting website candidates include the candidate domain and source
  family in the rationale.
- `httpx` evidence is classified as the `tool` source family.

## 7. Report And Export

Current report capabilities:

- Structured investigation report.
- Markdown report endpoint.
- HTML report endpoint.
- PDF report endpoint.
- BLUF, PIR, quality gate, completion policy, gap-to-tool plan, EEI coverage,
  cross-verification summary, confirmed facts, evidence appendix, ACH/I&W,
  intelligence gaps, and next actions.
- Export redaction for tokens, local paths, and deployment-specific details.
- CJK-safe PDF rendering through the configured PDF stack.

## 8. Web Workbench

Current frontend capabilities:

- Investigation creation.
- Investigation list and detail views.
- Agent/job queue view.
- Graph view with fixed business/decision-maker evidence slots.
- Report view.
- Risk and quality review surfaces.
- System status view.
- Tool health visibility.
- Supply-chain analysis panel.
- Intelligence aggregation panel.

## 9. Deployment And Operations

Current deployment capabilities:

- Local Python/Node development run.
- Docker Compose run.
- Script-managed native run through `scripts/start.sh`, `scripts/status.sh`,
  and `scripts/stop.sh`.
- User-level systemd service model for single-host deployment.
- Healthcheck script.
- Production-readiness script.
- Runtime inventory script.
- Backup script and backup timer.
- Public-release license check.
- Public repository maintenance rules and privacy scan workflow.

Current operational assumptions:

- SQLite queue and database are the default for the single-host deployment
  model.
- External queue brokers are not needed unless multi-host workers become
  necessary.
- Runtime artifacts, `.env`, databases, screenshots, reports, tokens, and
  private task data must stay out of Git.

## 10. Public Release And License

Current release posture:

- License: GNU GPL v3, `GPL-3.0-only`.
- `LICENSE`, README wording, and `frontend/package.json` are aligned.
- Public release readiness document exists.
- Public repository maintenance rules define acceptable placeholders, blockers,
  scan commands, and response levels.

## Current Limits And Next-Stage Work

The following items are not blockers for stage closure, but are the strongest
next-stage improvements:

- P3 permission tiers and audit logs for management actions, rejected writes,
  retries, archive/delete, and run enqueue events.
- P4 evidence review fields: source rank, human review status, reviewer note,
  and reviewed timestamp.
- More public-safe actual-task regression samples with tracked completion rate,
  false-conflict rate, follow-up hit rate, and manual-intervention reasons.
- Optional bundled export package if operators need Markdown, HTML, PDF, and
  appendices in one archive.
- External queue broker interface only if multi-host worker execution becomes a
  real requirement.

## Closure Statement

At this stage, the project has moved beyond prototype status. It is a
verifiable, deployable, evidence-oriented OSINT workbench with background
execution, gap-aware follow-up planning, completion policy, cross-verification,
structured reporting, and public-release documentation. Future work should start
from the roadmap rather than reopening completed implementation threads.
