# Gap-to-Tool Follow-up Planner Design

## Context

The project can already create investigations, run jobs through the
SQLite-backed background queue, assess quality gates, and export Markdown,
HTML, and PDF reports. When a task ends as `NEEDS_REVIEW` or `BLOCKED`, the
system currently shows useful signals such as `missing_keys`, `blocking_keys`,
`collection_gaps`, and queued gap follow-up jobs.

The remaining product gap is operator clarity and automatic next-step
discipline. A reviewer should not have to infer why a task stopped or which
tool should run next. The system should explain:

- where the task is stuck;
- what evidence is still required;
- which available tools can try to collect that evidence;
- which tools were already attempted;
- which tools are unavailable because of missing commands, configuration, or
  credentials;
- when the remaining work requires manual review rather than more automation.

This feature extends the existing `gap_followups` and worker flow. It should
not introduce a parallel orchestration system.

## Decision

Add a deterministic Gap-to-Tool planning layer that turns quality gaps and
intelligence-memory gaps into:

- `gap_analysis`: human-readable gap explanations and evidence requirements;
- `gap_tool_plan`: tool-level follow-up candidates with health and attempt
  state;
- `gap_followup_summary`: aggregate counts for queued, blocked, exhausted, and
  manually reviewed gaps;
- report sections that explain blockers and next collection actions.

The worker should queue only safe, ready, non-duplicate follow-up jobs. It
should record unavailable or exhausted tools as evidence of the current
boundary, not as generic task failure.

## Goals

- Make every `NEEDS_REVIEW` task explain specific blockers.
- Map each blocker to required evidence types.
- Map each evidence need to existing tools and role-agent jobs.
- Use tool health to separate runnable actions from configuration blockers.
- Avoid duplicate follow-up jobs.
- Record attempted, blocked, ready, queued, and exhausted states.
- Surface the plan in API detail, structured reports, and worker events.
- Keep all data privacy-safe: no tokens, raw private task IDs, local absolute
  paths, deployment hostnames, or private targets in fixtures or docs.

## Non-Goals

- No new external queue broker.
- No paid API integration.
- No browser automation.
- No new LLM requirement.
- No claim that all gaps can always be filled automatically.
- No weakening of quality gates. A weak or single-source finding must remain a
  candidate until verified.

## Core Data Contract

### `gap_analysis`

Each item describes one investigation gap:

```json
{
  "gap_key": "decision_maker",
  "label": "Decision maker candidate",
  "severity": "blocking",
  "current_state": "No accepted person, title, or profile evidence is linked to the company.",
  "missing_evidence": [
    "Official team/about/contact page naming a responsible person",
    "Public profile or news item linking the person to the company",
    "Independent evidence for title or purchasing authority"
  ],
  "why_it_matters": "The task cannot be completed without a reviewable person or role responsible for commercial follow-up.",
  "manual_review_hint": "If automated tools do not find a public profile, ask the operator to inspect the company website, public directories, or CRM context."
}
```

Required fields:

- `gap_key`
- `label`
- `severity`
- `current_state`
- `missing_evidence`
- `why_it_matters`
- `manual_review_hint`

Allowed severities:

- `blocking`: prevents `COMPLETED`.
- `important`: does not always block completion, but materially improves
  confidence.
- `optional`: useful follow-up, not required for completion.

### `gap_tool_plan`

Each item describes a possible collection action:

```json
{
  "gap_key": "official_website",
  "tool_name": "official_site_search",
  "agent_role": "tool_agent",
  "target_type": "company",
  "target_value": "Example Manufacturing LLC",
  "status": "ready",
  "reason": "Find official website candidates before crawling pages.",
  "expected_evidence": [
    "official_site_candidate",
    "website_title",
    "source_snippet"
  ],
  "depends_on": "completed:analysis_judgement;gap:official_website"
}
```

Allowed statuses:

- `ready`: can be queued automatically.
- `queued`: already queued by this planning pass.
- `already_attempted`: an equivalent job already exists or completed.
- `missing_config`: tool requires missing configuration.
- `missing_executable`: command is not available.
- `credential_blocked`: credential or cookie is missing.
- `disabled`: tool is disabled by registry.
- `exhausted`: all known tools for this gap were attempted or unavailable.

### `gap_followup_summary`

```json
{
  "total_gaps": 3,
  "blocking_gaps": 2,
  "ready": 2,
  "queued": 1,
  "already_attempted": 1,
  "blocked_by_config": 1,
  "exhausted": 0,
  "manual_review_required": 1
}
```

## Gap Keys

The first implementation should support these keys:

- `official_website`
- `decision_maker`
- `contact_channel`
- `contact_email`
- `contact_phone`
- `business_scope`
- `operation_location`
- `purchase_intent`
- `cross_verification`
- `evidence_ledger`
- `fact_pool`

The planner should also tolerate unknown gap keys by emitting a conservative
manual-review item with no automatic jobs.

## Tool Mapping

### Official Website

Evidence needed:

- official domain or URL;
- page title or snippet that ties the site to the target;
- source URL;
- confidence and source type.

Tools:

- `official_site_search`
- `httpx`
- `katana`
- `official_site_extractor`

### Contact Channel

Evidence needed:

- email or phone;
- source URL;
- visible company/site context;
- relationship between contact and target.

Tools:

- `official_site_extractor`
- `contact_discovery`
- `theharvester`
- `socialscan` for email/account signals where relevant.

### Decision Maker

Evidence needed:

- person name;
- role/title;
- source URL;
- link to the target company;
- independent confirmation when available.

Tools:

- `official_site_extractor`
- `social_profile_search`
- `profile_parser`
- `company_news`
- `company_news_monitoring`

### Business Scope

Evidence needed:

- product/service category;
- official or high-quality source;
- relationship to the target.

Tools:

- `company_osint`
- `official_site_extractor`
- `candidate_business_discovery` for sparse leads.
- `rfq_category_analysis` for sparse leads with RFQ context.

### Operation Location

Evidence needed:

- address, declared region, or operating footprint;
- source URL;
- source confidence.

Tools:

- `company_osint`
- `official_site_extractor`
- `supply_chain_mapping`

### Purchase Intent

Evidence needed:

- RFQ, buying signal, category match, news event, customs overlap, or public
  procurement signal;
- date or freshness marker when available;
- source URL and confidence.

Tools:

- `rfq_category_analysis`
- `purchase_intent_assessment`
- `company_news_monitoring`
- `customs_supply_chain` where configured and legally appropriate.

### Cross Verification, Evidence Ledger, Fact Pool

Evidence needed:

- at least one source-backed candidate;
- evidence records with source URLs or source types;
- facts linked to evidence IDs;
- matrix rows with `CONFIRMED`, `LIKELY`, or `SUPPORTED` status.

Tools:

- `cross_verification`
- `identity_match_review` for sparse leads.
- `analysis_judgement` after follow-up collection.

## Worker Flow

1. Worker finishes a bounded run.
2. Worker builds or refreshes `quality_assessment`.
3. Planner reads:
   - `quality_assessment.missing_keys`;
   - `quality_assessment.blocking_keys`;
   - `intelligence_memory.collection_gaps`;
   - current jobs;
   - tool health.
4. Planner emits `gap_analysis`, `gap_tool_plan`, and
   `gap_followup_summary`.
5. Worker queues only `ready` actions, respecting:
   - no duplicate `(tool_name, target_type, target_value, gap_key)`;
   - current max job budget;
   - priority: `blocking` before `important` before `optional`;
   - low-cost tools before heavy tools.
6. Worker records an event summarizing queued and blocked follow-up actions.
7. Report rendering includes the latest gap plan.

## API And Report Output

Investigation detail should include:

- `gap_analysis`
- `gap_tool_plan`
- `gap_followup_summary`

Reports should include a section named:

```text
## 卡点与补采计划
```

The section should list:

- each blocking gap;
- required evidence;
- ready tools;
- already attempted tools;
- unavailable tools and reasons;
- manual review hint.

## Error Handling

- If no known mapping exists for a gap, mark it as manual review required.
- If all mapped tools are unavailable, mark the gap as blocked by environment,
  not as investigation failure.
- If all mapped tools already ran and the gap remains open, mark it as
  exhausted and explain the remaining evidence need.
- If tool health cannot be loaded, keep automatic queuing conservative and
  emit an event describing the planner limitation.

## Privacy And Publication Rules

- Do not store API tokens, cookies, bearer tokens, local absolute paths,
  deployment hostnames, private IPs, raw private task names, or private target
  values in fixtures or public docs.
- Use public-safe examples such as `Example Manufacturing LLC`, `example.com`,
  and `example-target.test`.
- Tool plan records may store tool names, gap keys, statuses, and redacted
  reasons.

## Verification

Required local verification:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_gap_to_tool_planner.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_worker.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_quality_gate.py' -v
bash scripts/verify.sh
```

Required N100 verification after implementation:

- run `bash scripts/verify.sh`;
- create a public-safe company task;
- enqueue a bounded `/run-jobs` batch;
- confirm the task detail includes `gap_analysis`, `gap_tool_plan`, and
  `gap_followup_summary`;
- confirm the report explains blockers and next evidence needs;
- confirm unavailable tools are listed as environment/config blockers.

## Acceptance Criteria

- `NEEDS_REVIEW` results name concrete gaps rather than only returning a score.
- The report states what evidence is missing for each blocking gap.
- The planner identifies which tools can try to fill each gap.
- Unavailable tools are listed with specific health reasons.
- Duplicate gap follow-up jobs are not queued.
- Ready follow-up jobs are queued within budget.
- Exhausted gaps receive a manual review hint.
- Full verification passes.

## Unresolved Assumptions

- The first version will remain deterministic and does not require an LLM.
- The planner will use existing tool health rather than adding new probes.
- The first version will not persist a separate database table for gap plans;
  it can compute from investigation detail and store concise events/report
  content. Persistence can be revisited if operators need historical gap-plan
  snapshots.
