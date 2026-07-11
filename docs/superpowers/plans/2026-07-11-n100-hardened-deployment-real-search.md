# N100 Hardened Deployment And Real Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the verified security-hardening release to N100 without overwriting runtime state, rerun the original production public-information target, and record whether the deployed system still reaches its design gates.

**Architecture:** Treat the local `main` commit as the immutable source payload and the existing N100 `.env`, SQLite database, reports, artifacts, and backups as protected runtime state. Back up first, synchronize source with explicit exclusions, align dependencies and security settings, verify before restart, then create a new bounded investigation from the prior successful production target without writing that target into public repository documents.

**Tech Stack:** SSH, rsync, systemd user services, Python 3.12, SQLite, React/Vite, npm, OSINT Agent Network HTTP API, ProjectDiscovery tools, internal SearXNG-compatible search.

---

### Task 1: Freeze The Release And Protect Runtime State

**Files:**
- Verify: `docs/SECURITY_AUDIT_REMEDIATION_2026-07-10.md`
- Create after evidence: `docs/N100_HARDENED_DEPLOYMENT_REAL_SEARCH_CLOSURE_2026-07-11.md`
- Preserve: `.env`, `data/`, `reports/`, `frontend/.env.production`, `PROJECT_CLOSURE_MAINTENANCE_LOG.md`

- [x] **Step 1: Record the local release commit and dirty-file boundary**

Run `git rev-parse HEAD` and `git status --short` from the repository root.

Expected: release commit includes `71c72cc`; only the user-maintained closure log is modified.

- [x] **Step 2: Confirm N100 services and actual working directories**

Run `systemctl --user is-active` and `systemctl --user show -p WorkingDirectory` through `ssh n100`.

Expected: API and Web are active under `<production-path>` and `<production-path>/frontend`.

- [x] **Step 3: Back up runtime data and the pre-deploy source tree**

Run the repository backup script, then create a timestamped source archive under the existing N100 backup root. Do not print `.env` or archive contents.

Expected: both commands exit `0` and the backup paths exist.

### Task 2: Synchronize Source And Harden Production Configuration

**Files:**
- Deploy: tracked source under the repository root
- Preserve remotely: `.env`, `data/`, `reports/`, `frontend/node_modules/`, `frontend/dist/`

- [x] **Step 1: Synchronize source with explicit exclusions**

Use `rsync -az` over SSH without `--delete`. Exclude Git metadata, local worktrees, runtime data, reports, artifacts, environment files, generated frontend output, Playwright output, and the user-maintained closure log.

Expected: source files reach `<production-path>` while remote runtime timestamps and secrets remain intact.

- [x] **Step 2: Add required non-secret security settings without changing tokens**

Update only these `.env` keys on N100, after a timestamped `.env` backup:

```text
OSINT_COOKIE_SECURE=true
OSINT_ALLOW_LEGACY_AGENT_TOKEN=false
```

Expected: `ADMIN_API_TOKEN`, `READ_API_TOKEN`, OSINT tool paths, and search endpoint values remain unchanged and are never printed.

- [x] **Step 3: Align backend and frontend dependencies**

Install the backend editable package into the Python environment used by the existing service and run `npm install` from the frontend directory. N100 uses system Python rather than `backend/.venv`; the deployment therefore used a user-level editable install with the externally-managed-environment override.

Expected: Vite resolves to 8.1.4, `@vitejs/plugin-react` to 6.0.3, and `undici` to 7.28.0.

### Task 3: Verify And Restart N100

**Files:**
- Verify: `scripts/verify.sh`
- Verify: `scripts/healthcheck.sh`
- Verify: `scripts/production_readiness.py`

- [x] **Step 1: Run the complete remote verification before restart**

Run `bash scripts/verify.sh` from `<production-path>`.

Actual: 732 backend tests, four regression cases, 45 frontend tests, UI checks, and production build passed. The public release scan was run in the local Git source tree rather than the Git-less production runtime tree.

- [x] **Step 2: Restart API and Web user services**

Run `systemctl --user daemon-reload` followed by restart of both services.

Expected: both services become `active` and do not enter a restart loop.

- [x] **Step 3: Run health and production readiness**

Run `bash scripts/healthcheck.sh` and `PYTHONPATH=backend python3 scripts/production_readiness.py`.

Expected: API, database, Web, backup script, verification script, and authentication configuration are healthy; `ready=true`.

### Task 4: Rerun The Original Actual Public-Information Search

**Files:**
- Read remotely: production SQLite investigation history
- Write remotely: a new investigation, jobs, evidence, entities, facts, and report

- [x] **Step 1: Select the prior production design-goal target without exporting it**

Select the latest completed domain investigation that previously passed the quality gate and completed the `subfinder`, `httpx`, `katana`, and `official_site_extractor` chain. Keep the target only in remote process memory.

Expected: exactly one prior target is selected; public documentation records only `<original-public-target>`.

- [x] **Step 2: Create a fresh quick investigation and enqueue bounded work**

Use the server-side administrator credential to create the investigation, then enqueue at most six jobs per round. Poll the investigation and worker queue until each round is idle before deciding whether another round is required.

Expected: no token or target is printed; the new investigation ID is retained for evidence collection.

- [x] **Step 3: Capture terminal evidence and stability**

Capture status, quality score, summary, job counts by status/tool, source-backed facts, evidence kinds, and completion policy. Re-enqueue once after terminal completion to verify empty-queue stability.

Actual: `NEEDS_REVIEW`, quality score `44.5`, failed jobs `0`, blocked jobs `0`, and stable empty rerun. `subfinder`, two `httpx` jobs, and `katana` completed; `official_site_extractor` partially failed because N100 DNS returned a reserved fake address that the SSRF-safe fetcher correctly rejected.

### Task 5: Close Documentation And Deployment

**Files:**
- Create: `docs/N100_HARDENED_DEPLOYMENT_REAL_SEARCH_CLOSURE_2026-07-11.md`
- Modify only if evidence changes: `docs/PUBLIC_RELEASE_READINESS.md`

- [x] **Step 1: Compare actual evidence with each design criterion**

Classify every criterion as met, partially met, or not met. Separate application defects from missing tools, TLS termination, external-search variability, and evidence-quality limitations.

- [x] **Step 2: Write the final closure report without secrets or real target values**

Record commit IDs, backup evidence, dependency versions, verification counts, service/readiness results, anonymized investigation evidence, residual risks, and rollback instructions.

- [x] **Step 3: Run release checks and commit the report**

Run `git diff --check`, `python3 scripts/public_release_check.py`, and the release-document tests. Commit only the new plan/report and intended release-document changes; leave the user's maintenance log unstaged.

- [x] **Step 4: Synchronize the finalized public-safe documentation to N100**

Rsync only the finalized documentation files, then confirm local and N100 checksums match.

Expected: N100 contains the closure report, runtime services remain active, and no secrets or personal paths are added to the repository.
