# Update Log

## 2026-05-24 - Intelligence Maturity Gate And n100 Workflow Closure

Scope:

- Closed the current 皇城司 / OSINT Agent Network maturity phase on `n100`.
- Focused on turning sparse lead handling into a reusable workflow capability, not a one-off fix for the ZAWIJA / Nswana Mukuma test case.
- Strengthened the intelligence lifecycle around evidence ledger, fact pool, cross-verification, directed gap follow-up, and completion gating.

Changes:

- **Role-agent evidence ledger writeback**: Local role agents now write `evidence_ledger` records for collection notes using stable `hcs://role-agent/...` source URLs. This lets cross-verification promote role-agent findings into structured facts instead of leaving them as loose notes.
- **Tool evidence ledger writeback**: Parsed tool evidence now writes evidence ledger records in addition to legacy evidence rows. Tool-derived public findings can now participate in fact promotion, ACH scoring, and report appendices.
- **Cross-verification predicate matching**: Fixed false positives where generic statements such as `email_hidden_phone_hidden` could satisfy email or phone fields. Field matching now respects fact predicates instead of arbitrary statement substrings.
- **Fact deduplication**: Memory and SQLite stores now deduplicate facts by `(investigation_id, subject, predicate, object_value)`. Duplicate claims merge evidence IDs and preserve the stronger status, confidence, and Admiralty code.
- **SQLite duplicate cleanup**: Added migration-time cleanup for existing duplicate fact rows and a unique claim index to prevent future duplication.
- **Sparse lead candidate enrichment**: Sparse lead metadata now produces reusable candidate entities:
  - `lead_display_name` becomes an `identity` candidate and relationship.
  - `categories` become `business_scope` candidates and relationships.
  - `privacy_state` remains privacy metadata and is not converted into email or phone entities.
- **Directed gap follow-up preserved**: Weak platform identity candidates no longer close the `decision_maker` gap. The system keeps planning second-round jobs such as `social_profile_search`, `contact_discovery`, `company_news_monitoring`, `supply_chain_mapping`, and verification/reanalysis jobs when core gaps remain.
- **Completion gate tightened**: Quality score and completion readiness are now separated. A task can score above the numeric threshold and still remain `NEEDS_REVIEW` if it lacks core business closure:
  - official website/domain,
  - at least one public contact channel,
  - decision-maker signal,
  - existing required evidence/fact/PIR/cross-verification/report gates.

Regression coverage:

- Added tests for role-agent evidence ledger writeback and evidence-backed fact promotion.
- Added tests for tool evidence ledger writeback.
- Added tests preventing privacy-state strings from satisfying contact fields.
- Added MemoryStore and SQLiteStore fact deduplication tests, including migration cleanup.
- Added sparse lead enrichment tests for business scope and decision-maker candidates.
- Added tests that weak platform identity keeps the decision-maker collection gap open.
- Added a high-score-but-incomplete quality gate regression so missing website/contact/decision-maker fields block completion readiness.
- Updated sparse lead second-round workflow expectations to require directed follow-up planning.

Local verification:

- `bash scripts/verify.sh` passed.
- Backend: `Ran 107 tests ... OK`.
- Regression smoke: 4 cases, 0 failures.
- Frontend checks passed:
  - UI copy checks,
  - graph helper checks,
  - investigation bundle checks,
  - sparse lead helper checks,
  - core v3 helper checks,
  - system status helper checks,
  - Vite config checks.
- Frontend TypeScript compilation and Vite production build passed.

Deployment result on n100:

- Backend maturity patch synced to `/home/aidi/apps/osint-agent-network`.
- API restarted on port `8088`.
- `GET http://127.0.0.1:8088/api/health` returned `{"status": "ok", "service": "osint-agent-network"}`.
- Remote regression subset passed on n100.
- LAN checks passed:
  - `http://10.0.0.184:3008/` returned HTTP 200.
  - `http://10.0.0.184:8088/api/health` returned OK.
- Local machine ports `3008` and `8088` had no project processes running after closure.

Workflow validation task:

- Created and ran n100 task `95c0cef1-0f39-4258-8846-73dbf02ca783`.
- Name: `成熟度验证：ZAWIJA / Nswana Mukuma`.
- Final queue state:
  - 16 completed jobs,
  - 0 queued,
  - 0 running,
  - 0 failed,
  - 0 blocked.
- Final intelligence state:
  - 13 evidence ledger records,
  - 11 facts,
  - 32 entities,
  - 12 relationships,
  - quality score `72.7`.
- Final gate state:
  - `completion_ready: false`,
  - status remains `NEEDS_REVIEW`,
  - blocking keys: `official_website`, `contact_channel`, `decision_maker`.

Closure decision:

- This phase is closed as a deployable maturity checkpoint.
- The internal workflow now completes, records evidence, promotes facts, plans follow-up collection, and refuses to mark weakly supported investigations as complete.
- The project should not yet be described as fully mature in the real-world intelligence sense until live external collection sources are connected and validated at scale.

Next phase boundary:

- Prioritize real external source enablement and parser fixtures:
  - official website/domain discovery,
  - public contact discovery,
  - registry/company directory sources,
  - news and litigation sources,
  - social/profile verification sources.
- Preserve the current completion gate behavior: weak or platform-only evidence should remain reviewable but not closure-ready.

---

## 2026-05-23 - API Boundary And Frontend Error-State Patch

Scope:

- Fixed issues found during the full project review and redeployed the patch to `n100`.
- Focused on request-body error handling, Agent heartbeat authorization, and frontend API error reporting.

Changes:

- **Request body hard stop**: `_read_json()` now raises a structured request error for oversized or malformed JSON bodies. Oversized requests return a single `413` response and no longer continue into business logic after writing an error response.
- **Invalid JSON response**: Malformed JSON now returns `400 {"detail": "invalid json body"}` instead of silently becoming an empty object.
- **Heartbeat authorization**: `/api/agents/heartbeat` now requires management write authorization when `ADMIN_API_TOKEN` or `AGENT_API_TOKEN` is configured.
- **Agent route matching**: Agent protocol routes now match `/api/agent/` explicitly, avoiding accidental treatment of `/api/agents/*` management routes as Agent writeback routes.
- **Frontend API helper**: Added `fetchJson()` so non-2xx API responses throw backend `detail` messages instead of being treated as successful empty payloads.
- **Frontend error state**: Dashboard refresh, auto-refresh detail loading, and task detail loading now surface authorization and server errors instead of misreporting API status as online.

Regression coverage:

- Added backend tests for heartbeat write authorization and oversized request-body handling.
- Added frontend tests for non-2xx JSON error propagation and successful JSON parsing.

Local verification:

- `bash scripts/verify.sh` passed with 97 backend tests, regression smoke, frontend helper checks, TypeScript compilation, and Vite build.
- `npm test` passed with 2 test files and 6 frontend tests.

Deployment result on n100:

- Code synced to `/home/aidi/apps/osint-agent-network`.
- Remote verification and service health checks completed successfully.

---

## 2026-05-23 - Stability, Efficiency and Accuracy Fixes

Scope:

- Full project review covering execution logic stability, efficiency, and intelligence accuracy.
- Fixed race conditions, resource leaks, performance bottlenecks, false-positive matching, and API security gaps.
- Cleaned up unused dependencies in both backend and frontend.

### Stability fixes

- **Atomic job claiming**: Added `claim_job_for_worker()` to both MemoryStore and SQLiteStore. Uses compare-and-swap (`UPDATE ... WHERE status='QUEUED'`) to prevent two workers from executing the same job concurrently.
- **Worker wall-clock deadline**: The worker loop now enforces a maximum runtime (default 1 hour, configurable via `WORKER_MAX_WALL_SECONDS`). Prevents indefinite thread blocking on large investigations.
- **Subprocess orphan prevention**: `run_tool_command` now uses `os.setsid` to create a process group. On timeout, `os.killpg` kills the entire process tree instead of just the parent, preventing orphan child processes from tools like amass or spiderfoot.
- **Request body safety**: `_read_json` now catches `json.JSONDecodeError` (returns empty dict instead of 500) and enforces a 10 MB body size limit (`MAX_REQUEST_BODY_BYTES`), returning 413 on overflow.

### Efficiency fixes

- **Derived computation moved out of lock**: Added `get_investigation_raw()` method that returns data without computing graph, quality assessment, or intelligence memory. `get_investigation()` now reads raw data under lock, then computes derived fields outside the lock. This eliminates lock contention from CPU-intensive operations.
- **Worker uses lightweight reads**: The worker's inner loop now calls `get_investigation_raw()` instead of `get_investigation()`, avoiding redundant graph/quality computation on every iteration.
- **Registry caching**: `default_tool_registry()` now caches the singleton at module level. Previously it reconstructed the full registry on every call.

### Intelligence accuracy fixes

- **Word-boundary matching in cross-verification**: Ledger snippet matching changed from substring (`value in snippet`) to regex word-boundary (`\b...\b`). Short values (< 4 characters like "IT", "US") are excluded from ledger matching entirely to prevent false-positive source attribution.
- **Normalization before contradiction detection**: New `_normalize_for_comparison()` function normalizes values by field type before comparing (domains: strip www/protocol/trailing slash; phones: strip formatting; emails: lowercase). Prevents format-only differences from being flagged as CONFLICTED.
- **Source-authority-weighted best value selection**: `_best_value()` now weights candidates by source family authority (official/registry=3, news/directory=2, social/tool/operator=1). A single official source now outweighs two tool-only sources.
- **Gmail duplicate planning removed**: Fixed `plan_followup_jobs` where Gmail addresses were added to the candidate list twice, causing redundant planning computation.

### API security hardening

- **CORS restriction**: Replaced `Access-Control-Allow-Origin: *` with a whitelist from `CORS_ALLOWED_ORIGINS` env var (defaults to localhost:3008, 10.0.0.184:3008). Only matching origins receive CORS headers.
- **Startup auth warning**: The server now prints a visible warning when no `AGENT_API_TOKEN` or `ADMIN_API_TOKEN` is configured.
- **Agent registration requires auth**: `/api/agents/register` now requires write authorization (previously exempt). Prevents unauthenticated agent registration.

### Dependency cleanup

- **backend/pyproject.toml**: Removed `fastapi`, `uvicorn`, `sqlalchemy`, `pydantic` (declared but never used; server uses stdlib `http.server` + `sqlite3`).
- **frontend/package.json**: Moved `@vitejs/plugin-react`, `jsdom`, `typescript`, `vite` to `devDependencies`. Removed `@types/marked` (marked v18 ships its own types).

### Frontend fix

- **Auto-refresh useEffect**: Removed `investigations` from the dependency array and switched to a ref. Prevents the 8-second polling interval from being torn down and recreated on every data refresh.

### Verification

- Backend: 191 tests passed.
- Frontend: TypeScript compilation + Vite build passed. UI copy check and graph helper tests passed.
- Integration checks: atomic claim, registry caching, CORS helper, normalization, weighted best-value, short-value filtering all verified programmatically.

### Configuration notes

- New env vars (all optional):
  - `WORKER_MAX_WALL_SECONDS`: Worker loop time limit (default 3600).
  - `MAX_REQUEST_BODY_BYTES`: Request body size limit (default 10485760).
  - `CORS_ALLOWED_ORIGINS`: Comma-separated allowed origins for CORS (default: localhost + LAN).
- After deploying to n100, restart both services and verify with `bash scripts/healthcheck.sh`.

---

## 2026-05-22 - Security Hardening And n100 Redeploy

Scope:

- Reviewed the full project and fixed the issues found in the review.
- Redeployed the updated project to `n100`.
- Kept remote runtime data intact: `.env`, SQLite database, logs, job artifacts, reports, and `frontend/.env.production` were not overwritten during sync.

Security and reliability changes:

- Added read-side authorization for sensitive API routes. The API now checks `READ_API_TOKEN`, then falls back to `ADMIN_API_TOKEN` or `AGENT_API_TOKEN`.
- Kept `/api/health` and `/api/tools/health` available for unauthenticated health checks.
- Added management authorization to `POST /api/investigations`.
- Updated the web app so read and write API calls include the configured `VITE_ADMIN_API_TOKEN`.
- Replaced regex-only report HTML filtering with a DOM whitelist sanitizer before `dangerouslySetInnerHTML`.
- Added regression coverage for unsafe report HTML, including unquoted `javascript:` URLs and unsafe tags.
- Made the Vite dev API proxy configurable through `VITE_DEV_API_PROXY_TARGET`.
- Updated Docker Compose so the web container proxies API calls to `http://api:8088`.
- Added `.dockerignore` to keep local databases, logs, PID files, `node_modules`, builds, Playwright output, reports, and zip artifacts out of Docker build context.

Verification:

- Local `bash scripts/verify.sh` passed.
- n100 `bash scripts/verify.sh` passed.
- n100 backend test result: `Ran 91 tests ... OK`.
- n100 regression smoke result: `case_count: 4`, `failed: 0`.
- n100 frontend checks passed, including `vite config checks passed`.
- n100 Vite production build passed.

Deployment result on n100:

- Code synced to `/home/aidi/apps/osint-agent-network`.
- Frontend dependencies installed with `npm install`; result included `found 0 vulnerabilities`.
- Restarted user services:
  - `osint-agent-network-api.service`
  - `osint-agent-network-web.service`
- Both services reported `active`.
- `GET http://127.0.0.1:8088/api/health` returned `{"status": "ok", "service": "osint-agent-network"}`.
- Authorized `GET /api/investigations` returned 8 investigations.
- Unauthorized `GET /api/investigations` returned HTTP `401` with `unauthorized read request`.
- `GET http://127.0.0.1:3008/` returned the web HTML.

Operational notes:

- Keep `frontend/.env.production` aligned with `ADMIN_API_TOKEN`, because the web app now sends the token on read and write API requests.
- Public LAN access to the API should still be treated as sensitive. Token protection is now enforced for sensitive reads, but reverse-proxy access controls remain recommended for wider exposure.
- Do not commit or package `.env`, SQLite files, job artifacts, logs, cookies, API keys, or tool credentials.
