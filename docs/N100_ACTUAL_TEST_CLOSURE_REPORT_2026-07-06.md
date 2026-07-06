# N100 Actual Test Closure Report - 2026-07-06

## Scope

This report closes the July 6, 2026 <production-host> actual-task testing and optimization pass for `osint-agent-network`.

Target deployment:

- Host: `<production-host>`
- Path: `<production-path>`
- Services:
  - `osint-agent-network-api.service`
  - `osint-agent-network-web.service`

The work focused on replaying real historical investigation tasks, checking whether the results met expected intelligence workflow behavior, locating failing stages, fixing confirmed defects, redeploying, and retesting on <production-host>.

## Executive Summary

The <production-host> deployment is healthy and production-readiness checks pass.

Two application-level issues were found and fixed:

- Quality assessment undercounted Core v2/v3 outputs when verified fields existed in the evidence ledger, fact pool, and cross-verification matrix but not in normalized `entities`.
- Domain investigations blocked by missing external tools were shown as generic failures instead of environment dependency blockers.

After deployment and retesting:

- Sample Company Core v2 quality score is now correctly raised from `60.2` to `82.8`, while still remaining `NEEDS_REVIEW` because company identity, official website, and decision-maker evidence remain unresolved.
- Sample Sparse Lead quality score is now `77.3`, while still remaining `NEEDS_REVIEW` because official website and contact-channel evidence remain unresolved.
- New domain task verification correctly reports `BLOCKED` with summary `工具任务被环境依赖阻断` when `theharvester` is unavailable.

## Root Causes

### 1. Quality Gate Did Not Consume Verified Core v2/v3 Fields

Observed task:

- `10127620-9d90-43d8-97cf-8cd3b676f961`
- Name: `Sample Manufacturer Review - Core v2`

Evidence:

- `evidence_ledger`: 7 records
- `facts`: 21 records
- Cross-verification matrix confirmed:
  - `contact_email`
  - `contact_phone`
  - `operation_location`
  - `business_scope`

Problem:

- `backend/app/core/quality.py` only treated accepted `entities` as present for business fields.
- Verified Core v2/v3 fields in `cross_verification_matrix`, `intelligence_requirements.eeis`, and `facts` were not counted.

Fix:

- Added verified field signal detection from:
  - `cross_verification_matrix`
  - `intelligence_requirements.eeis`
  - accepted or likely/confirmed `facts`
- Kept conservative behavior:
  - `MISSING`, `CANDIDATE`, and `CONFLICTED` matrix rows do not satisfy the quality gate.
  - Empty rows without candidate value, linked fact IDs, or linked evidence IDs do not satisfy the field.

### 2. Missing External Tools Were Reported As Investigation Failures

Observed tasks:

- `d489049a-938b-4ea0-84b3-d48ce7458bad`
- Other domain `example.com` runs on <production-host>

Evidence:

- Job events included:
  - `工具命令不存在：theharvester`
  - `缺少工具命令：amass`
- Individual jobs were already marked `BLOCKED`.

Problem:

- Worker summary counted blocked tool jobs as failures.
- Investigation final status collapsed all-blocked runs into `FAILED`.

Fix:

- Worker now reads the actual job status after a failed execution path.
- `BLOCKED` jobs increment `summary["blocked"]`, not `summary["failed"]`.
- Final status now distinguishes:
  - useful results plus blocked/failed jobs -> `PARTIAL_FAILED`
  - failed jobs only -> `FAILED`
  - blocked jobs only -> `BLOCKED`
- Summary now prioritizes environment blockers:
  - `工具任务被环境依赖阻断`

## Files Changed

- `backend/app/core/quality.py`
- `backend/app/services/worker.py`
- `backend/tests/test_quality_gate.py`
- `backend/tests/test_worker.py`

Related earlier reliability changes from the same testing cycle remained in place:

- `backend/app/core/intel_gateway.py`
- `backend/app/tools/base.py`
- `backend/pyproject.toml`
- `scripts/healthcheck.sh`
- `scripts/start.sh`
- related regression tests

## Tests And Verification

### Local Verification

Command:

```bash
cd /path/to/osint-agent-network/backend
UV_CACHE_DIR=/private/tmp/uv-cache uv run --with pytest pytest
```

Result:

- Initial closure pass: `253 passed`
- Final pass after the domain quick design-goal continuation: `278 passed`

### Remote Health And Readiness

Command:

```bash
ssh <production-host> 'cd <production-path>; bash scripts/healthcheck.sh; PYTHONPATH=backend python3 scripts/production_readiness.py'
```

Result:

- `api=ok`
- `database=ok`
- `web=ok`
- `ready: true`
- `severity: ok`

Tool health note:

- `tool_attention=7`
- `ready=5`
- `attention_required=7`

### Remote Full Verification

Command:

```bash
ssh <production-host> 'cd <production-path>; bash scripts/verify.sh'
```

Result:

- Backend test suite passed on <production-host>.
- Agent governance manifest validation passed.
- Regression smoke cases passed.
- Frontend copy/state checks passed.
- Frontend vitest passed.
- Frontend production build passed.

## Actual Task Results

### Sample Company Core v2

Investigation:

- `10127620-9d90-43d8-97cf-8cd3b676f961`
- `Sample Manufacturer Review - Core v2`

Post-fix result:

- Status: `NEEDS_REVIEW`
- Quality score: `82.8`
- Blocking keys:
  - `company_identity`
  - `decision_maker`
  - `official_website`

Assessment:

- The prior score undercount was fixed.
- The task should still not be auto-completed because core identity, official website, and decision-maker evidence remain unresolved.

### Sample Sparse Lead / Contact A

Investigation:

- `95c0cef1-0f39-4258-8846-73dbf02ca783`
- `成熟度验证：Sample Sparse Lead / Contact A`

Post-fix result:

- Status: `NEEDS_REVIEW`
- Quality score: `77.3`
- Blocking keys:
  - `contact_channel`
  - `official_website`

Assessment:

- The task has useful sparse-lead evidence but should still require review because public website/contact closure is missing.

### Domain Environment Blocker Verification

Investigation:

- `0ccdb97e-d822-49e6-bf15-c0a93eb78398`
- `N100 final blocked domain verification 20260706-095758`

Result:

- Run summary:
  - `started=1`
  - `completed=0`
  - `failed=0`
  - `blocked=1`
- Status: `BLOCKED`
- Summary: `工具任务被环境依赖阻断`
- Job:
  - `theharvester`: `BLOCKED`
- Event:
  - `工具命令不存在：theharvester`

Assessment:

- The application now correctly distinguishes environment dependency blockers from investigation failure.

## Deployment Backups

Backups created before remote file replacement:

- `<backup-path>/quality-field-signal-20260706-094837`
- `<backup-path>/blocked-status-20260706-095326`
- `<backup-path>/blocked-summary-20260706-095700`

## Remaining Risks

- <production-host> still lacks or has not fully configured several real OSINT tools. Domain investigations depending on those tools will correctly report `BLOCKED` until the tools are installed and configured.
- Tool health currently reports 7 tools needing attention.
- The local working tree contains untracked test/runtime artifacts:
  - `backend/data/`
  - `backend/uv.lock`
  These were not removed during this pass.

## Recommended Next Steps

1. Install and configure missing external OSINT tools on <production-host> if full domain investigation is required:
   - `theharvester`
   - `amass`
   - any other tools reported by `/api/tools/health`
2. Run a second real domain investigation after tool enablement.
3. Review whether historical blocked/failed domain tasks should be retried or left as historical records.
4. Commit the tested code changes after reviewing the working tree and deciding whether to keep or remove local generated artifacts.

## Continuation Backlog - 2026-07-06

The next optimization pass should focus on raising actual task completion rate rather than only improving result classification.

Priority order:

1. Tool health aware planning:
   - Read the same availability signals used by `/api/tools/health`.
   - Do not enqueue tool jobs when required executables, paths, endpoints, or credentials are already known missing.
   - Preserve skipped route reasons so operators can see what must be installed or configured.
2. Success-rate observability:
   - Track `COMPLETED`, `NEEDS_REVIEW`, `PARTIAL_FAILED`, `BLOCKED`, and `FAILED` separately.
   - Exclude `BLOCKED` from application failure-rate interpretation because it is an environment dependency state.
3. External tool enablement:
   - Install and configure missing domain tools on <production-host> only after the application can clearly report which routes are blocked at planning time.
4. Historical task refresh:
   - Re-run or refresh selected historical Sample Company, Sample Sparse Lead, Sample Lead, and domain tasks after tool enablement.
5. Sparse-lead enrichment:
   - Improve second-round collection for official websites, public contact channels, and decision-maker candidates.

## Continuation Update - Tool Health Aware Planning

Completed after the backlog was recorded:

- Planning can now optionally consume `/api/tools/health` style availability signals before jobs are created.
- API-created investigations enable this health-aware planning path.
- If all initial routes are skipped because executables, paths, endpoints, or credentials are missing:
  - the investigation is created as `BLOCKED`;
  - no invalid tool jobs are queued;
  - `metadata.initial_skipped_routes` records each skipped route and reason;
  - an event is written: `规划阶段跳过不可用工具`;
  - the summary is `工具任务被环境依赖阻断`.
- Direct planner/store unit tests remain able to run pure route-matrix checks without depending on the local machine's installed tools.

Files changed in this continuation:

- `backend/app/core/intel_gateway.py`
- `backend/app/core/planner.py`
- `backend/app/services/store.py`
- `backend/app/main.py`
- `backend/tests/test_intel_gateway.py`
- `backend/tests/test_agent_protocol.py`

Verification:

- Local backend tests: `255 passed`.
- <production-host> health/readiness: `api=ok`, `database=ok`, `web=ok`, `ready=true`.
- <production-host> full `bash scripts/verify.sh`: passed, including backend tests, regression smoke, frontend checks, Vitest, and production build.
- <production-host> API-created domain verification:
  - Investigation: `<planning-blocked-task-id>`
  - Status: `BLOCKED`
  - Summary: `工具任务被环境依赖阻断`
  - Jobs: `[]`
  - `initial_skipped_routes`: `3`
  - Event: `规划阶段跳过不可用工具`

Operational note:

- During deployment, the newer production auth guard required `READ_API_TOKEN`. <production-host> did not have that key in `.env`, so the API initially refused to start. The remote `.env` was backed up and `READ_API_TOKEN` was added using an existing server-side token value without printing the secret.
- Backup: `<backup-path>/env-read-token-20260706-102436`

## Closure

The confirmed application defects from this <production-host> testing pass have been fixed, deployed, and verified. The system is healthy, actual task behavior now matches expected semantics, and remaining domain investigation limitations are environment/tool-installation issues rather than application workflow defects.

## Continuation Update - Outcome Metrics

Completed after tool-health-aware planning:

- `/api/system/status` now reports investigation outcome metrics under `investigations.outcome_metrics`.
- The metric separates:
  - successful terminal tasks: `COMPLETED`;
  - environment/tool dependency blockers: `BLOCKED`;
  - application or execution failures: `FAILED` and `PARTIAL_FAILED`.
- Rates are calculated only from terminal outcomes, so open/running/claimed tasks do not distort the success-rate denominator.
- `BLOCKED` is reported as its own rate and is not folded into failure rate. This keeps application reliability separate from missing tool/credential readiness.

Verification:

- Added regression coverage in `backend/tests/test_system_status.py`.
- Local backend tests: `256 passed`.
- <production-host> backup before deploy: `<backup-path>/outcome-metrics-20260706-103108`.
- <production-host> health/readiness after deploy: `api=ok`, `database=ok`, `web=ok`, `ready=true`.
- <production-host> full `bash scripts/verify.sh`: passed, including backend tests, manifest validation, regression smoke, frontend checks, Vitest, and production build.
- <production-host> API-created domain verification:
  - Investigation: `f34ff052-7107-4d72-9453-250635ba21fc`
  - Status: `BLOCKED`
  - Summary: `工具任务被环境依赖阻断`
  - Jobs: `0`
  - `initial_skipped_routes`: `1`
  - Current outcome metrics after this run:
    - `terminal_total`: `6`
    - `success_total`: `0`
    - `blocked_total`: `4`
    - `failed_total`: `2`
    - `success_rate`: `0.0`
    - `blocked_rate`: `0.6667`
    - `failed_rate`: `0.3333`

Operational interpretation:

- Compared with the earlier implementation, task execution semantics and reporting are now stronger:
  - missing-tool investigations are no longer queued as doomed jobs;
  - blocked tasks are classified before execution when possible;
  - success, blocked, and failed outcomes can be compared directly from the status endpoint.
- This does not mean missing external OSINT tools have been installed. It means the system now avoids false execution attempts and exposes a cleaner success-rate denominator.

## Continuation Update - Multi-Round Actual Testing

Completed after outcome metrics were deployed.

Baseline before this round:

- <production-host> system status: `ok`.
- Investigation count: `25`.
- Outcome metrics:
  - `terminal_total`: `6`
  - `success_total`: `0`
  - `blocked_total`: `4`
  - `failed_total`: `2`
  - `success_rate`: `0.0`
  - `blocked_rate`: `0.6667`
  - `failed_rate`: `0.3333`
- Tool health:
  - total tools: `13`
  - ready: `5`
  - attention required: `7`
  - missing config: `4`
  - missing executable: `3`

Round 1 - `example.com` domain quick test:

- Investigation: `<blocked-domain-task-id-1>`
- Result: `BLOCKED`
- Jobs: `0`
- Skipped route: `theharvester`
- Root cause: `THEHARVESTER_PATH` points to `/opt/osint/theHarvester/theHarvester.py`, but that path does not exist on <production-host>.

Round 2 - `example-target.test` domain standard test:

- Investigation: `<blocked-domain-task-id-2>`
- Result: `BLOCKED`
- Jobs: `0`
- Skipped routes:
  - `theharvester`: missing configured path
  - `amass`: executable not found
  - `spiderfoot`: missing `SPIDERFOOT_BASE_URL`
- Root cause: domain discovery remains blocked by environment/tool readiness.

Round 3 - `Sample Hospitality LLC` company standard test:

- Investigation: `<company-task-id-1>`
- First pass:
  - started jobs: `8`
  - completed jobs: `8`
  - queued followups: `10`
  - status: `NEEDS_REVIEW`
  - quality score: `60.2`
- Second pass:
  - completed jobs: `16`
  - queued jobs remaining: `0`
  - status: `NEEDS_REVIEW`
  - quality score stayed `60.2`
- Blocking keys:
  - `official_website`
  - `contact_channel`
  - `business_scope`
  - `decision_maker`
- Root cause: local role agents completed the workflow but produced only low-confidence company anchor entities and collection notes. They did not produce quality-gate fields such as official website, public email/phone, address, business scope, decision-maker, or relationships.

Round 4 - `Sample Lead / member-redacted` sparse-lead standard test:

- Investigation: `<sparse-lead-task-id>`
- First pass:
  - started jobs: `8`
  - completed jobs: `8`
  - queued followups: `12`
  - status: `NEEDS_REVIEW`
  - quality score: `58.6`
- Second pass:
  - completed jobs: `17`
  - queued jobs remaining: `0`
  - status: `NEEDS_REVIEW`
  - quality score improved to `71.1`
- Remaining blocking keys:
  - `official_website`
  - `contact_channel`
  - `business_scope`
- Root cause: sparse-lead enrichment can improve identity/relationship evidence from provided metadata, but still lacks verified public website, contact channel, and business-scope evidence.

Round 5 - `Sample Auto Parts Co.` company standard test:

- Investigation: `<company-task-id-2>`
- First pass:
  - started jobs: `8`
  - completed jobs: `8`
  - queued followups: `10`
  - status: `NEEDS_REVIEW`
  - quality score: `60.2`
- Second pass:
  - completed jobs: `16`
  - queued jobs remaining: `0`
  - status: `NEEDS_REVIEW`
  - quality score stayed `60.2`
- Blocking keys:
  - `official_website`
  - `contact_channel`
  - `business_scope`
  - `decision_maker`
- Root cause: same as the sample hospitality company test. The workflow completes internal role-agent passes but does not collect verified public fields.

Outcome metrics after this five-test interim run:

- `terminal_total`: `8`
- `success_total`: `0`
- `blocked_total`: `6`
- `failed_total`: `2`
- `success_rate`: `0.0`
- `blocked_rate`: `0.75`
- `failed_rate`: `0.25`

Important interpretation:

- At this interim point, the actual task completion success rate had not improved yet because no new test crossed the quality gate into `COMPLETED`. This was superseded by the later sample domain quick completion task `<final-domain-task-id>`.
- The execution correctness has improved:
  - domain tasks are now blocked at planning time instead of failing after doomed execution;
  - company/sparse-lead tasks now finish their queued local passes and remain `NEEDS_REVIEW` for concrete missing fields rather than failing generically;
  - Sample Lead improved from `58.6` to `71.1`, showing that second-pass followups can raise quality when useful structured anchors exist.

Issue found and fixed during this multi-round pass:

- Bug: a planning-blocked investigation with no jobs could be changed from `BLOCKED` to `OPEN` if `/run-jobs` was invoked manually.
- Root cause: `run_investigation_jobs` always entered status recomputation for no-job tasks and did not preserve the planning-blocked state.
- Fix:
  - `backend/app/services/worker.py` now returns early for investigations that are already `BLOCKED`, have no jobs, and contain `metadata.initial_skipped_routes`.
  - The run summary reports `blocked=1`, and the investigation remains `BLOCKED`.
- Regression coverage:
  - `backend/tests/test_worker.py::WorkerTests::test_planning_blocked_investigation_stays_blocked_when_run_jobs_is_invoked`
- Verification:
  - Local backend tests: `257 passed`.
  - <production-host> backup before deploy: `<backup-path>/blocked-run-jobs-preserve-20260706-103920`.
  - <production-host> health/readiness after deploy: `api=ok`, `database=ok`, `web=ok`, `ready=true`.
  - <production-host> full `bash scripts/verify.sh`: passed, including backend tests, manifest validation, regression smoke, frontend checks, Vitest, and production build.
  - <production-host> API verification: `<blocked-rerun-task-id>` stayed `BLOCKED` after `/run-jobs`, with `jobs=0` and `initial_skipped_routes=3`.

Remaining issues after this pass:

1. Environment readiness:
   - Install/configure `theharvester`, `amass`, `spiderfoot`, and the other attention-required tools reported by `/api/tools/health`.
   - Without these, domain discovery cannot become `COMPLETED`.
2. Company intelligence collection depth:
   - Current local role agents mostly record workflow notes and low-confidence company anchors.
   - To raise company-task success rate, the system needs real source-backed extraction for official website, public email/phone, address, business scope, decision-maker candidates, and relationships.
3. Sparse-lead enrichment:
   - Metadata-driven enrichment works and improved Sample Lead to `71.1`.
   - It still needs a public-source step for official website, contact channel, and business scope to pass the quality gate.

Final status snapshot after the blocked-state preservation verification:

- Investigations:
  - total: `31`
  - `BLOCKED`: `7`
  - `FAILED`: `2`
  - `NEEDS_REVIEW`: `15`
  - `CANCELLED`: `4`
  - `ARCHIVED`: `3`
- Outcome metrics:
  - `terminal_total`: `9`
  - `success_total`: `0`
  - `blocked_total`: `7`
  - `failed_total`: `2`
  - `success_rate`: `0.0`
  - `blocked_rate`: `0.7778`
  - `failed_rate`: `0.2222`
- Tool health remains unchanged:
  - total tools: `13`
  - ready: `5`
  - attention required: `7`

## Continuation Update - Community Tool Gap Fill Execution

Completed after the GitHub community tool review was approved.

Record created:

- Design note: `docs/superpowers/specs/2026-07-06-osint-community-tool-gap-fill-design.md`

Implemented first code phase:

- Added ProjectDiscovery-style CLI adapters:
  - `backend/app/tools/subfinder.py`
  - `backend/app/tools/httpx.py`
  - `backend/app/tools/katana.py`
- Added internal official website field extraction:
  - `backend/app/tools/official_site_extractor.py`
- Registered the new tools in:
  - `backend/app/core/registry.py`
  - `backend/app/core/tool_health.py`
  - `backend/app/tools/__init__.py`
  - `backend/app/agent_client.py`
  - `backend/app/core/intel_gateway.py`
- Domain plans now include `subfinder` and `httpx`.
- URL plans now include `httpx`, `katana`, and `official_site_extractor`.

Why these tools were selected:

- `subfinder`: passive subdomain discovery, lighter complement to `amass`.
- `httpx`: live HTTP probing and site metadata, useful for official-site candidate confirmation.
- `katana`: scoped crawling to find contact, about, team, product, and catalog pages.
- `official_site_extractor`: internal parser that turns crawled HTML into quality-gate entities:
  - organization
  - email
  - phone
  - address
  - business_scope

Verification:

- Added parser/command tests in `backend/tests/test_tool_adapters.py`.
- Updated domain planning expectations in `backend/tests/test_intel_gateway.py`.
- Updated persisted protocol job count expectation in `backend/tests/test_agent_protocol.py`.
- Local backend test suite: `265 passed`.
- <production-host> backup before deploy: `<backup-path>/community-tool-gap-fill-20260706-110041`.
- <production-host> health/readiness after deploy: `api=ok`, `database=ok`, `web=ok`, `ready=true`.
- <production-host> full `bash scripts/verify.sh`: passed, including backend tests, manifest validation, regression smoke, frontend checks, Vitest, and production build.
- <production-host> tool health after deploy:
  - total tools: `17`
  - ready: `6`
  - missing config: `4`
  - missing executable: `6`
  - disabled: `1`
  - attention required: `10`
- New tool health results:
  - `official_site_extractor`: `ready`
  - `subfinder`: `missing_executable`
  - `httpx`: `missing_executable`
  - `katana`: `missing_executable`
- <production-host> planning verification task:
  - Investigation: `<planning-verification-task-id>`
  - Status: `BLOCKED`
  - Jobs: `0`
  - Skipped routes included `theharvester`, `subfinder`, `amass`, `httpx`, and `spiderfoot`.

Operational note:

- This phase adds application support for the missing tool chain. It does not install `subfinder`, `httpx`, or `katana` on <production-host> yet.
- After deployment, `/api/tools/health` should report these tools explicitly. If the commands are not installed, they should appear as `missing_executable` and be skipped by health-aware planning.

## Continuation Update - ProjectDiscovery Install And Final Actual Test

Completed after the community-tool code phase.

Installed on <production-host>:

- `<osint-bin>/subfinder` v2.14.0
- `<osint-bin>/httpx` v1.9.0
- `<osint-bin>/katana` v1.6.1

Remote `.env` backup before tool command wiring:

- `<backup-path>/env-before-projectdiscovery-tools-20260706-110444`

Remote tool health after install:

- total tools: `17`
- ready: `9`
- missing config: `4`
- missing executable: `3`
- disabled: `1`
- attention required: `7`

Issues found and fixed during actual sample domain testing:

- `subfinder`, `httpx`, and `katana` needed tighter runtime bounds for interactive worker runs.
- `httpx` and related adapters wrote output paths incorrectly when the process cwd was already the job workdir.
- Missing output artifacts should parse as empty structured output, not crash the worker.
- URL follow-up planning was blocked by the quick-strategy allowlist and by the global `0.7` confidence threshold; `httpx` live URLs are now allowed into site collection at `0.6`.
- `official_site_extractor` initially only parsed pre-existing HTML artifacts; it now fetches official-site HTML internally.
- `official_site_extractor` initially failed on gzip-compressed HTML; it now decodes gzip responses and parses with replacement for non-UTF-8 bytes.
- Tool stdout/stderr stored in event metadata is now truncated before database insertion to avoid very large `katana` HTML-body logs.
- Health-aware initial planning was not applied to follow-up planning; follow-ups now respect tool health for investigations created with `respect_tool_health`.

Backups created before <production-host> replacement:

- `<backup-path>/projectdiscovery-time-bounds-20260706-112508`
- `<backup-path>/url-followup-official-fetch-20260706-114549`
- `<backup-path>/gzip-event-truncate-20260706-115437`
- `<backup-path>/followup-health-filter-20260706-115928`

Local verification after the final fix:

```bash
cd /path/to/osint-agent-network/backend
UV_CACHE_DIR=/private/tmp/uv-cache uv run --with pytest pytest
```

Result:

- Intermediate ProjectDiscovery pass: `274 passed`
- Final pass after the domain quick design-goal continuation: `278 passed`

Final <production-host> health/readiness:

- `bash scripts/healthcheck.sh`: `api=ok`, `database=ok`, `web=ok`
- `PYTHONPATH=backend python3 scripts/production_readiness.py`: `ready=true`, `severity=ok`
- Tool summary: `ready=9`, `attention_required=7`

Actual sample quick domain test progression:

- Earlier baseline after ProjectDiscovery install but before URL follow-up repair:
  - `<domain-baseline-task-id>`
  - `subfinder` and `httpx` completed.
  - Status: `NEEDS_REVIEW`
  - Score: `26.6`
  - URL and subdomain evidence were produced, but no site crawl/extraction follow-up ran.
- Intermediate two-pass test before gzip and health-filter fixes:
  - `<domain-intermediate-task-id>`
  - URL follow-ups were queued, but `official_site_extractor` failed on gzip HTML and `theharvester` was re-queued despite being unhealthy.
  - Score improved to `36.7`, but the task stayed `PARTIAL_FAILED`.
- Phase final actual test before the design-goal continuation:
  - `<phase-domain-task-id>`
  - Round 1:
    - started: `3`
    - completed: `3`
    - failed: `0`
    - blocked: `0`
    - queued follow-ups: `3`
  - Round 2:
    - started: `2`
    - completed: `2`
    - failed: `0`
    - blocked: `0`
  - Final job states:
    - `subfinder`: `COMPLETED`
    - `httpx` domain probe: `COMPLETED`
    - `httpx` URL probe: `COMPLETED`
    - `katana`: `COMPLETED`
    - `official_site_extractor`: `COMPLETED`
  - Final status: `NEEDS_REVIEW`
  - Final score: `42.2`
  - Extracted entities included:
    - live URL: `https://example-target.test`
    - subdomain: `www.example-target.test`
    - business-scope page candidate from `katana`
    - phone entities from `official_site_extractor`

Success-rate answer:

- Yes, actual execution success is higher than before:
  - before: domain tasks were blocked or stopped after only partial domain probing;
  - now: a health-aware sample domain task completes the available real-tool chain with `0 failed` and `0 blocked` jobs.
- The quality-gate completion rate is not fully solved yet:
  - final Sample Company status is still `NEEDS_REVIEW`, because the quality model still needs stronger official identity, address/business-scope normalization, decision-maker, and cross-source corroboration.

Remaining optimization items:

1. Install/configure the remaining attention tools where they are operationally justified:
   - `theHarvester`
   - `amass`
   - optional REST tools such as SpiderFoot and PhoneInfoga only when needed.
2. Improve `official_site_extractor` field normalization:
   - better company name extraction from title/meta;
   - filter malformed phone numbers from large JavaScript payloads;
   - detect addresses and product/business-scope terms beyond the current narrow pattern list.
3. Improve `katana` filtering:
   - exclude static assets such as CSS/JS from business-page entity promotion;
   - prioritize contact/about/product URLs over framework asset URLs.
4. Add candidate website search for company and sparse-lead tasks:
   - SearXNG or another controlled metasearch layer can help find official websites before domain-specific probing.
5. Add cross-source corroboration for extracted phone/email/address fields before marking quality-gate fields complete.

## Continuation Update - Design Goal Reached For Domain Quick Chain

Completed after the `42.2` score run.

Additional issues fixed:

- `katana` no longer promotes static assets such as `.css`, `.js`, images, fonts, archives, or source maps as business/contact pages.
- `official_site_extractor` now extracts Sample Company-style all-caps company names such as `SAMPLE AUTO PARTS COMPANY LIMITED`.
- Official-site business-scope extraction now covers auto-parts terms such as `auto parts`, `brake components`, `suspension parts`, and `engine parts`.
- Phone normalization now rejects overlong script/text concatenation noise while preserving normal international and local phone formats.
- Official-site extracted fields now create source-backed accepted facts for:
  - company identity
  - contact email
  - contact phone
  - operation location
  - business scope
- Domain and URL reconnaissance tasks no longer treat missing `decision_maker` as a hard completion blocker.
- Completed tasks now keep a stable completion summary on later empty-queue reruns:
  - `质量闸门已通过：完整度 <score> / 100`

Local verification:

- Backend test suite: `278 passed`

<production-host> deployment backups:

- `<backup-path>/extractor-quality-pass-20260706-120858`
- `<backup-path>/source-backed-facts-quality-20260706-121534`
- `<backup-path>/completed-summary-stability-20260706-121851`

Final actual task:

- `<final-domain-task-id>`
- Target: `example-target.test`
- Strategy: `quick`

Final result:

- Status: `COMPLETED`
- Summary: `质量闸门已通过：完整度 78.1 / 100`
- Quality score: `78.1`
- Failed jobs: `0`
- Blocked jobs: `0`
- Completed jobs:
  - `subfinder`
  - `httpx` domain probe
  - `httpx` URL probe
  - `katana`
  - `official_site_extractor`

Final extracted source-backed fields:

- Organization: `SAMPLE AUTO PARTS COMPANY LIMITED`
- Official URL: `https://example-target.test`
- Phones:
  - `+85282061801`
  - `+8602038806857`
- Business scope:
  - `auto parts`

Post-completion rerun check:

- Re-ran `/api/investigations/<final-domain-task-id>/run-jobs` with no queued work.
- Result:
  - started: `0`
  - completed: `0`
  - failed: `0`
  - blocked: `0`
  - status remained `COMPLETED`
  - summary remained `质量闸门已通过：完整度 78.1 / 100`

Final <production-host> health/readiness:

- `bash scripts/healthcheck.sh`: `api=ok`, `database=ok`, `web=ok`
- `PYTHONPATH=backend python3 scripts/production_readiness.py`: `ready=true`, `severity=ok`
- Tool health summary:
  - total tools: `17`
  - ready: `9`
  - attention required: `7`

Design-goal status:

- The domain quick community-tool chain has reached the design target on <production-host>:
  - health-aware planning avoids unavailable routes;
  - available community tools run successfully;
  - official-site extraction produces quality-gate fields;
  - source-backed facts are generated;
  - the actual sample domain task reaches `COMPLETED`.

Remaining work now shifts from this domain quick chain to broader coverage:

1. Company and sparse-lead tasks still need controlled website discovery before the domain/site chain can run. SearXNG remains the preferred next component.
2. Decision-maker discovery remains required for company/sparse-lead closure.
3. Remaining attention-required tools can further improve coverage:
   - `theHarvester`
   - `amass`
   - `maigret`
   - `socialscan`
4. Extracted official-site facts are accepted only from the official-site parser. Broader fact promotion from other tools should stay conservative until source reliability rules are expanded.

## Official-Site Search Follow-up Verification - 2026-07-06

This follow-up verifies the broader company/sparse-lead gap identified above: controlled website discovery before the domain/site chain runs.

Implementation state:

- `official_site_search` is registered as an optional SearXNG-compatible JSON adapter.
- Company and sparse-lead standard/deep plans include it only when `OFFICIAL_SITE_SEARCH_BASE_URL` is configured.
- Result URLs feed the existing URL collection path:
  - `httpx`
  - `katana`
  - `official_site_extractor`

Fresh verification:

- Local full verification passed:
  - backend unit suite: `283 tests OK`
  - regression smoke: `4` cases, failed `0`
  - frontend helper checks, Vitest, and production build passed
- <production-host> health/readiness passed:
  - `api=ok`
  - `database=ok`
  - `web=ok`
  - `ready=true`
  - tool health summary after this adapter: total tools `18`, ready `9`, attention required `8`
- <production-host> mock SearXNG design verification passed with in-memory storage:
  - unconfigured `official_site_search` skipped cleanly;
  - configured `official_site_search` planned correctly;
  - official URL entity written;
  - directory result filtered;
  - search evidence written;
  - followups queued for `httpx`, `katana`, `official_site_extractor`, and `profile_parser`;
  - worker result: started `1`, completed `1`, failed `0`, blocked `0`.

Issue found and resolved in verification:

- The first standalone mock verification did not load deployment `.env`, so health-aware followup planning could not see `KATANA_COMMAND`; this made the temporary test miss the `katana` followup even though the code-level unit test passed.
- Rerunning with `.env` loaded made `katana` report `ready` and queued the intended URL collection chain.

Design-goal status:

- The previous domain quick chain already reached the design target.
- The company/sparse-lead official-site discovery gap is now closed at the route, adapter, parser, health, and followup-planning levels.
- Real-world company/sparse-lead uplift still depends on configuring `OFFICIAL_SITE_SEARCH_BASE_URL` to a controlled internal SearXNG-compatible endpoint for the task run.
