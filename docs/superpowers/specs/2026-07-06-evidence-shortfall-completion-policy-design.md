# Evidence Shortfall Completion Policy Design

## Context

The project can now run investigations through the background worker, explain
evidence gaps with `gap_analysis`, map gaps to tools with `gap_tool_plan`, and
record `gap_followup_summary` in task detail, reports, and worker events.

The next product problem is not whether the system can continue collecting. It
can. The problem is how to decide what to do when the system has already tried
reasonable automatic collection and some evidence remains missing.

The system needs rules that say:

- keep collecting when there are ready, non-duplicate tools;
- stop automatic looping when available tools are exhausted or blocked;
- allow limited completion only for low-risk evidence shortfalls;
- keep strict completion for fully supported results;
- never mark weak or unverified evidence as full completion.

## Decision

Add a deterministic completion-policy layer between the quality gate and final
worker status selection.

The existing quality gate remains the strict authority for full completion. The
new policy only decides how to classify incomplete cases after considering gap
analysis, tool plan status, attempted jobs, and evidence coverage.

The first implementation should not add a database migration or broad status
enum change. Instead, it should expose a structured `completion_policy` object
in investigation detail, reports, and worker summaries. The persisted task
status can continue using the existing values:

- `COMPLETED`
- `NEEDS_REVIEW`
- `BLOCKED`
- `FAILED`
- `PARTIAL_FAILED`

Limited completion can be represented as:

- persisted status: `COMPLETED`
- `completion_policy.completion_mode`: `limited`

Human-decision-ready cases can be represented as:

- persisted status: `NEEDS_REVIEW`
- `completion_policy.completion_mode`: `ready_for_human_decision`

## Goals

- Increase useful automatic task closure without lowering evidence quality.
- Avoid endless automatic reruns when no ready follow-up action remains.
- Distinguish strict completion, limited completion, human-decision-ready, and
  environment-blocked outcomes.
- Explain exactly which evidence is still missing and why the system did or did
  not complete the task.
- Keep privacy-safe records: no tokens, private hostnames, local paths, private
  task IDs, or private targets in fixtures and docs.

## Non-Goals

- Do not weaken the strict quality gate.
- Do not treat single weak evidence as confirmed.
- Do not create a new external queue, broker, or LLM dependency.
- Do not add browser automation.
- Do not add a database status migration in the first pass.
- Do not claim that every investigation can be completed automatically.

## Core Contract

Add a computed object named `completion_policy`:

```json
{
  "recommended_status": "COMPLETED",
  "completion_mode": "limited",
  "strict_completion_ready": false,
  "limited_completion_ready": true,
  "auto_exhausted": true,
  "manual_decision_required": false,
  "environment_blocked": false,
  "reason": "Core company identity, official website, business scope, and contact channel are present; decision-maker evidence remains unresolved.",
  "remaining_blockers": ["decision_maker"],
  "acceptable_limitations": ["decision_maker"],
  "operator_next_actions": [
    "Manually verify decision-maker from official team page, public profile, or trusted directory."
  ],
  "evidence_floor": {
    "identity": true,
    "official_website": true,
    "business_scope": true,
    "contact_channel": true,
    "evidence_ledger": true,
    "cross_verification": true
  }
}
```

Required fields:

- `recommended_status`
- `completion_mode`
- `strict_completion_ready`
- `limited_completion_ready`
- `auto_exhausted`
- `manual_decision_required`
- `environment_blocked`
- `reason`
- `remaining_blockers`
- `acceptable_limitations`
- `operator_next_actions`
- `evidence_floor`

Allowed `completion_mode` values:

- `strict`: quality gate is fully satisfied.
- `limited`: low-risk missing evidence remains, but the result is usable with
  explicit limitations.
- `continue_collection`: ready automatic follow-up tools still exist.
- `ready_for_human_decision`: automatic collection is exhausted, but core
  completion evidence is still insufficient.
- `blocked_by_environment`: required automatic routes are blocked by missing
  config, executables, disabled tools, or credentials.
- `failed`: execution failed in a way unrelated to evidence insufficiency.

## Evidence Floor

Limited completion is only allowed when the evidence floor is satisfied.

For company and sparse-lead commercial investigations, the first evidence floor
is:

- company or organization identity is present;
- official website/domain or trusted source boundary is present;
- business scope is present;
- at least one contact channel is present, or a trusted official contact page
  exists;
- evidence ledger has source-backed records;
- facts exist and are linked to evidence;
- cross-verification has at least one `CONFIRMED`, `LIKELY`, or `SUPPORTED`
  row.

For domain or URL investigations:

- organization or site identity is present when discoverable;
- live URL or official site source exists;
- business scope or site purpose is present when discoverable;
- evidence ledger has source-backed records;
- cross-verification has at least one supported row.

For email or username investigations:

- target identity or account existence has source-backed evidence;
- at least one profile/contact/source record exists;
- evidence ledger has source-backed records;
- risk summary is available.

## Rule Table

### Strict Completion

If `quality_assessment.completion_ready` is true:

- `recommended_status`: `COMPLETED`
- `completion_mode`: `strict`
- `manual_decision_required`: false
- `auto_exhausted`: irrelevant but may be false

### Continue Collection

If strict completion is false and `gap_followup_summary.ready > 0`:

- `recommended_status`: `NEEDS_REVIEW`
- `completion_mode`: `continue_collection`
- worker should queue ready non-duplicate follow-up jobs within budget;
- report should say automatic collection is still available.

### Limited Completion

If strict completion is false, evidence floor is satisfied, and remaining
blockers are limited to acceptable limitations:

- `recommended_status`: `COMPLETED`
- `completion_mode`: `limited`
- `limited_completion_ready`: true
- `manual_decision_required`: false
- report must explicitly list limitations.

Initial acceptable limitations:

- `decision_maker` missing for company/sparse-lead tasks when identity,
  official website/source boundary, business scope, contact channel, evidence
  ledger, facts, and cross-verification are present.
- `purchase_intent` missing when the task is identity/contact verification
  rather than buyer-intent qualification.
- `contact_phone` missing when a source-backed email or official contact page
  exists.
- `contact_email` missing when a source-backed phone or official contact page
  exists.

Non-acceptable limitations:

- `company_identity`
- `official_website` for company/sparse-lead investigations;
- `evidence_ledger`
- `fact_pool`
- `cross_verification`
- no BLUF/report
- unresolved contradiction or high-risk conflict

### Ready For Human Decision

If strict completion is false, limited completion is false, and no ready
automatic tool remains:

- `recommended_status`: `NEEDS_REVIEW`
- `completion_mode`: `ready_for_human_decision`
- `auto_exhausted`: true
- `manual_decision_required`: true
- report should list required evidence and the exact human decision needed.

### Blocked By Environment

If no ready tool remains and one or more blocking gaps map only to unavailable
tools:

- `recommended_status`: `BLOCKED` if no useful evidence was collected;
- `recommended_status`: `NEEDS_REVIEW` if useful evidence exists but missing
  environment tools prevent closure;
- `completion_mode`: `blocked_by_environment`
- `environment_blocked`: true
- report should list missing commands, config, disabled tools, or credentials.

## Integration Points

### New Module

Create:

```text
backend/app/core/completion_policy.py
```

Core API:

```python
def build_completion_policy(detail: dict) -> dict:
    pass
```

The function should read:

- `quality_assessment`
- `gap_analysis`
- `gap_tool_plan`
- `gap_followup_summary`
- `entities`
- `facts`
- `evidence_ledger`
- `cross_verification_matrix`
- `intelligence_requirements`
- `hypothesis_analysis`
- `risk_report`
- `jobs`

### Store Detail

Investigation detail should include:

- `completion_policy`

Apply to both `MemoryStore` and `SQLiteStore` detail builders after
`quality_assessment`, `gap_analysis`, `gap_tool_plan`, and
`gap_followup_summary` are computed.

### Worker

Worker final status logic should use `completion_policy`:

- strict -> `COMPLETED`
- limited -> `COMPLETED` with `completion_mode=limited`
- continue_collection -> keep `NEEDS_REVIEW` and queue follow-ups
- ready_for_human_decision -> `NEEDS_REVIEW`
- blocked_by_environment -> `BLOCKED` only when useful evidence is absent;
  otherwise `NEEDS_REVIEW`

The worker summary should include:

- `completion_policy`
- `completion_mode`

### Report

Structured reports should add completion-policy lines in the quality section or
near `## 卡点与补采计划`:

- completion mode;
- why the task did or did not complete;
- acceptable limitations;
- remaining blockers;
- operator next actions.

### API/UI

No new endpoint is required.

Existing investigation detail should expose `completion_policy`. The frontend
can later display it in the quality/gap area, but the first implementation can
be backend/report-only.

## Testing

Add focused backend tests:

- strict quality-ready detail returns `completion_mode=strict`.
- ready gap tools returns `completion_mode=continue_collection`.
- evidence floor satisfied but decision-maker missing returns
  `completion_mode=limited` and `recommended_status=COMPLETED`.
- missing official website or evidence ledger never limited-completes.
- all mapped tools unavailable and no useful evidence returns
  `blocked_by_environment`.
- all mapped tools unavailable but useful evidence exists returns
  `ready_for_human_decision` or `blocked_by_environment` with
  `recommended_status=NEEDS_REVIEW`.
- worker uses limited completion policy without changing strict quality gate.
- report includes completion mode, limitations, and next actions.

Required verification:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_completion_policy.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_worker.py' -v
PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_quality_gate.py' -v
bash scripts/verify.sh
```

## Acceptance Criteria

- The system can explicitly distinguish strict completion, limited completion,
  continued collection, human-decision-ready, and environment-blocked cases.
- Limited completion is possible only when the evidence floor is satisfied.
- Missing official website/source boundary, evidence ledger, fact pool, or
  cross-verification cannot be waived for full or limited completion.
- Reports explain limitations rather than hiding them.
- Worker no longer loops uselessly when tools are exhausted.
- Full verification passes.

## Open Follow-up

After backend behavior is stable, add a compact frontend display for
`completion_policy` in the quality/gap area. This is intentionally left out of
the first implementation to keep the rule engine focused and testable.
