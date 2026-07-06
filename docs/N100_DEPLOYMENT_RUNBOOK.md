# N100 Deployment Runbook

Version: 1.2
Updated: 2026-07-06
Target host: `<production-host>`
Target path: `/opt/osint-agent-network`

This runbook is the handoff document for deploying and upgrading OSINT Agent Network / 情报官 on <production-host>. The latest actual-task closure record is [N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md](N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md). Earlier deployment details are recorded in [N100_DEPLOYMENT_LOG_2026-07-02.md](N100_DEPLOYMENT_LOG_2026-07-02.md) and [FINAL_CLOSURE_AND_N100_DEPLOYMENT_2026-07-04.md](FINAL_CLOSURE_AND_N100_DEPLOYMENT_2026-07-04.md).

Current <production-host> actual path used by the latest live tests: `<production-path>`. Older command examples that use `/opt/osint-agent-network` are deployment templates; substitute the real host path when operating the current <production-host> instance.

## 1. Current Completion Status

The project is ready for <production-host> deployment as a staged production build.

Verified capabilities:

- React/Vite web UI opens on port `3008`.
- Python API opens on port `8088`.
- SQLite persistence works at `data/osint.sqlite`.
- Investigation creation, queue execution, entity/evidence/relationship writes, quality gate, graph, and whitepaper report all work.
- Worker follows an intelligence-cycle workflow: intake, first verification, limited directed expansion, deep enrichment when justified, final analysis.
- Low-confidence tool findings do not automatically expand into more jobs.
- Heavy tools are staged behind verification and budget gates.
- Management write routes support bearer-token protection.
- Browser clients can send `Authorization` through CORS.
- Final verification passes:

```bash
bash scripts/verify.sh
```

Expected final result as of 2026-07-06:

```text
Backend tests pass
Regression smoke: case_count=4, failed=0
ui state checks passed
graph helper checks passed
investigation bundle checks passed
sparse lead helper checks passed
core v3 helper checks passed
system status helper checks passed
vite build ... built
```

The 2026-07-06 <production-host> actual-task verification additionally confirmed:

- Local backend verification: `278 passed`.
- <production-host> full verification passed through `bash scripts/verify.sh`.
- Historical Sample Company Core v2 quality score: `82.8`, still `NEEDS_REVIEW` due unresolved identity, website, and decision-maker blockers.
- Historical Sample Sparse Lead quality score: `77.3`, still `NEEDS_REVIEW` due unresolved website and contact-channel blockers.
- Missing external commands produce investigation status `BLOCKED` with summary `工具任务被环境依赖阻断`.
- ProjectDiscovery domain quick chain reached the current design target on <production-host> in task `<final-domain-task-id>`: `COMPLETED`, `78.1 / 100`, failed jobs `0`, blocked jobs `0`.
- Final live chain completed: `subfinder`, `httpx`, `katana`, and `official_site_extractor`.

## 2. Deployment Options

Use one of these modes:

- `scripts/start.sh`: quickest native startup for manual operation.
- User-level systemd: recommended for persistent <production-host> service.
- Docker Compose: available, but native startup is simpler for this project because the OSINT tools often live on the host filesystem.

Recommended <production-host> mode: user-level systemd after a successful native smoke test.

## 3. Files And Directories

On <production-host>:

```text
/opt/osint-agent-network
  backend/
  frontend/
  data/
  reports/
  docs/
  scripts/
  .env
```

Backup target:

```text
/var/backups/osint-agent-network
```

Important persistent files:

- `data/osint.sqlite`
- `data/jobs/`
- `data/artifacts/`
- `data/snapshots/`
- `reports/`
- `.env` kept outside git history

## 4. Environment Configuration

Create or update:

```bash
cd /opt/osint-agent-network
cp .env.example .env
```

Minimum <production-host> settings:

```bash
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8088
WEB_PORT=3008
OSINT_DB_PATH=/opt/osint-agent-network/data/osint.sqlite

AGENT_API_TOKEN=<strong-agent-token>
ADMIN_API_TOKEN=<strong-admin-token>
READ_API_TOKEN=<strong-read-token>

OSINT_LLM_BASE_URL=http://192.0.2.10:6780/v1
OSINT_LLM_API_KEY=<redacted>
OSINT_LLM_MODEL=gpt-5.4
OSINT_LLM_TIMEOUT=30
```

Frontend build-time token:

```bash
cd /opt/osint-agent-network/frontend
cat > .env.production <<'EOF'
VITE_API_BASE_URL=http://192.0.2.10:8088
VITE_ADMIN_API_TOKEN=<same-value-as-ADMIN_API_TOKEN>
EOF
```

If the web UI is only used locally on <production-host>, `VITE_API_BASE_URL=http://127.0.0.1:8088` is acceptable. For LAN browser access, use `http://192.0.2.10:8088`.

## 5. Optional OSINT Tool Configuration

The app can run without every OSINT tool installed or resident. Missing tools become `BLOCKED` jobs with visible queue hints. For stronger real-world enrichment, configure these as they become available and start heavier REST tools only when a task needs them:

```bash
SHERLOCK_COMMAND=python3
SHERLOCK_MODULE=sherlock_project

THEHARVESTER_COMMAND=python3
THEHARVESTER_PATH=/opt/osint/theHarvester/theHarvester.py
THEHARVESTER_SOURCES=all
THEHARVESTER_LIMIT=500

AMASS_COMMAND=amass
AMASS_PASSIVE=true

SUBFINDER_COMMAND=<osint-bin>/subfinder
HTTPX_COMMAND=<osint-bin>/httpx
KATANA_COMMAND=<osint-bin>/katana
OFFICIAL_SITE_SEARCH_BASE_URL=

SPIDERFOOT_BASE_URL=
SPIDERFOOT_API_KEY=

PHONEINFOGA_BASE_URL=
PHONEINFOGA_API_KEY=

GHUNT_COMMAND=ghunt
GHUNT_COOKIE_PATH=

RECONNG_COMMAND=/opt/osint-tools/recon-ng/recon-ng
```

Do not commit `.env`, cookies, API keys, tokens, or tool credentials.

For the current <production-host> real-tool wiring and remaining install list, see `docs/REAL_TOOL_ENABLEMENT.md`.

## 6. Native Deployment

Install dependencies:

```bash
cd /opt/osint-agent-network/frontend
npm install
npm run build
```

Run full verification:

```bash
cd /opt/osint-agent-network
bash scripts/verify.sh
```

Start services:

```bash
cd /opt/osint-agent-network
bash scripts/start.sh
```

Check status:

```bash
bash scripts/status.sh
curl -sS http://127.0.0.1:8088/api/health
set -a; . ./.env; set +a
TOKEN="${READ_API_TOKEN:-${ADMIN_API_TOKEN:-${AGENT_API_TOKEN:-}}}"
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8088/api/system/status
curl -sS http://127.0.0.1:8088/api/tools/health
curl -sS http://127.0.0.1:3008/ | head
python3 scripts/production_readiness.py
python3 scripts/runtime_inventory.py
```

## 6.1 Standard Upgrade Procedure

Use this procedure for incremental upgrades from the local workstation.

1. Verify locally:

```bash
cd /path/to/osint-agent-network
bash scripts/verify.sh
```

2. Create a remote pre-deploy backup:

```bash
ssh <production-host> 'mkdir -p /var/backups/osint-agent-network && cd /home/osint/apps && tar \
  --exclude=osint-agent-network/frontend/node_modules \
  --exclude=osint-agent-network/frontend/dist \
  --exclude=osint-agent-network/data/jobs \
  --exclude=osint-agent-network/data/artifacts \
  --exclude=osint-agent-network/data/*.sqlite \
  --exclude=osint-agent-network/reports \
  -czf /var/backups/osint-agent-network/predeploy-$(date +%Y%m%d-%H%M%S).tar.gz \
  osint-agent-network'
```

3. Sync code while preserving runtime state and secrets:

```bash
rsync -az \
  --exclude '.env' \
  --exclude '.DS_Store' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache/' \
  --exclude '.mypy_cache/' \
  --exclude '.ruff_cache/' \
  --exclude 'frontend/node_modules/' \
  --exclude 'frontend/dist/' \
  --exclude 'frontend/.vite/' \
  --exclude 'frontend/.env.production' \
  --exclude 'frontend.zip' \
  --exclude '.playwright-cli/' \
  --exclude 'frontend/.playwright-cli/' \
  --exclude 'output/' \
  --exclude 'data/*.sqlite' \
  --exclude 'data/*.sqlite-*' \
  --exclude 'data/*.db' \
  --exclude 'data/*.log' \
  --exclude 'data/*.pid' \
  --exclude 'data/jobs/' \
  --exclude 'data/artifacts/' \
  --exclude 'reports/' \
  ./ <production-host>:/opt/osint-agent-network/
```

4. Build and verify remotely:

```bash
ssh <production-host> 'cd /opt/osint-agent-network/frontend && npm install && npm run build'
ssh <production-host> 'cd /opt/osint-agent-network && bash scripts/verify.sh'
```

5. Restart services and run readiness:

```bash
ssh <production-host> 'systemctl --user restart osint-agent-network-api.service osint-agent-network-web.service'
ssh <production-host> 'cd /opt/osint-agent-network && python3 scripts/production_readiness.py'
```

6. Confirm access:

```bash
curl -sS http://192.0.2.10:8088/api/health
curl -sS http://192.0.2.10:3008/ | head
```

Stop services:

```bash
bash scripts/stop.sh
```

## 7. User-Level Systemd Deployment

Create service directory:

```bash
mkdir -p ~/.config/systemd/user
```

Create `~/.config/systemd/user/osint-agent-network-api.service`:

```ini
[Unit]
Description=OSINT Agent Network API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/osint-agent-network
EnvironmentFile=/opt/osint-agent-network/.env
Environment=PYTHONPATH=/opt/osint-agent-network/backend
ExecStart=/usr/bin/python3 -m app.main
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

Create `~/.config/systemd/user/osint-agent-network-web.service`:

```ini
[Unit]
Description=OSINT Agent Network Web UI
After=osint-agent-network-api.service
Wants=osint-agent-network-api.service

[Service]
Type=simple
WorkingDirectory=/opt/osint-agent-network/frontend
ExecStart=/usr/bin/npm run preview -- --host 0.0.0.0 --port 3008
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now osint-agent-network-api.service
systemctl --user enable --now osint-agent-network-web.service
```

Install the backup timer:

```bash
cp deploy/systemd/osint-agent-network-backup.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now osint-agent-network-backup.timer
systemctl --user list-timers | grep osint-agent-network-backup
```

Check:

```bash
systemctl --user status osint-agent-network-api.service osint-agent-network-web.service
journalctl --user -u osint-agent-network-api.service -n 100 --no-pager
journalctl --user -u osint-agent-network-web.service -n 100 --no-pager
```

Optional boot persistence:

```bash
loginctl enable-linger "$USER"
```

## 8. Smoke Test After Deployment

Run the deployment health checks:

```bash
cd /opt/osint-agent-network
bash scripts/healthcheck.sh
python3 scripts/production_readiness.py
```

The readiness script exits `0` when the mature deployment baseline is usable. It may return `"severity": "warn"` when optional OSINT tools need installation, credentials, or endpoint configuration; that warning is acceptable for the platform baseline, but should be cleared as real collection tools are brought online.

Run:

```bash
curl -sS http://127.0.0.1:8088/api/health
curl -sS http://127.0.0.1:8088/api/system/status
curl -sS http://192.0.2.10:8088/api/health
curl -sS http://127.0.0.1:3008/ | head
bash scripts/healthcheck.sh
```

Expected:

- API returns `{"status":"ok","service":"osint-agent-network"}`.
- Web returns an HTML document with title `皇城司 HCS`.

Then open:

```text
http://192.0.2.10:3008/
```

Manual UI checklist:

- Task pool loads.
- Existing investigations render.
- Detail page shows graph, queue, quality gate, and whitepaper.
- Whitepaper appears before the quality gate and has enough vertical room.
- Queue panel explains blocked/waiting/running states.

## 9. Functional Smoke Test

Create a sparse lead test task from the UI or API.

API example:

```bash
curl -sS -X POST http://127.0.0.1:8088/api/investigations \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"<production-host> smoke sparse lead",
    "seed_type":"sparse_lead",
    "seed_value":"Sample Lead / member-redacted",
    "strategy":"quick",
    "metadata":{
      "platform":"Alibaba",
      "lead_display_name":"Sample Lead",
      "member_id":"member-redacted",
      "country_region":"IN",
      "registration_year":"2023",
      "company_name_raw":"Sample Lead",
      "privacy_state":"email_phone_hidden",
      "categories":["Induction Cookers"],
      "recent_rfqs":["2200W Electric Cook Top"]
    }
  }'
```

Enqueue background worker run:

```bash
curl -sS -X POST http://127.0.0.1:8088/api/investigations/<id>/run-jobs \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  -d '{}'
```

Expected:

- The API returns immediately with `mode: "background"` and `accepted: true`.
- `/api/system/status` shows worker queue depth, running investigation id, recent runs, and recent errors.
- Poll `/api/investigations/<id>` for job-level progress.
- `lead_anchor_extraction` completes.
- `constrained_query_planning` completes.
- `analysis_judgement` completes for quick mode.
- Investigation status becomes `NEEDS_REVIEW`.
- Entities, evidence, relationships, quality gate, and whitepaper are visible.

Delete smoke task after testing:

```bash
curl -sS -X POST http://127.0.0.1:8088/api/investigations/<id>/delete \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ADMIN_API_TOKEN"
```

## 10. Backup And Restore

Backup:

```bash
cd /opt/osint-agent-network
bash scripts/backup.sh
```

Manual backup equivalent:

```bash
mkdir -p /var/backups/osint-agent-network/$(date +%Y%m%d-%H%M%S)
rsync -az \
  /opt/osint-agent-network/data/ \
  /var/backups/osint-agent-network/$(date +%Y%m%d-%H%M%S)/data/
```

Restore:

```bash
systemctl --user stop osint-agent-network-api.service osint-agent-network-web.service
rsync -az /var/backups/osint-agent-network/<backup-id>/data/ \
  /opt/osint-agent-network/data/
systemctl --user start osint-agent-network-api.service osint-agent-network-web.service
```

## 11. Rollback

If a new deployment fails:

1. Stop services.
2. Restore previous app directory or previous release archive.
3. Restore `data/` from backup if the database migrated unexpectedly.
4. Run `bash scripts/verify.sh`.
5. Start services again.

Commands:

```bash
systemctl --user stop osint-agent-network-api.service osint-agent-network-web.service
cd /home/osint/apps
mv osint-agent-network osint-agent-network.failed.$(date +%Y%m%d-%H%M%S)
mv osint-agent-network.previous osint-agent-network
cd osint-agent-network
bash scripts/verify.sh
systemctl --user start osint-agent-network-api.service osint-agent-network-web.service
```

## 12. Known Operational Notes

- `scripts/start.sh` is suitable for normal shell use. In some Codex sandbox sessions, background processes may not align with PID files; systemd is preferred on <production-host>.
- Missing external tools are not fatal. They should show as `BLOCKED` jobs and appear in the queue panel.
- A run where every executed tool job is blocked by missing commands or credentials should finish as investigation status `BLOCKED`, not `FAILED`.
- `ADMIN_API_TOKEN` protects management write routes. If enabled, the web build must include `VITE_ADMIN_API_TOKEN`.
- `AGENT_API_TOKEN` protects `/api/agent/*` writeback routes.
- `NEEDS_REVIEW` is a terminal review state, not an active-running state.
- Whitepaper is the primary operator report area; quality gate remains visible but secondary.

## 13. Final Acceptance Criteria

The deployment is accepted when all are true:

- `bash scripts/verify.sh` passes.
- API health passes on localhost and LAN IP.
- Web UI opens on LAN IP.
- A quick sparse-lead smoke task can run and produce `NEEDS_REVIEW`.
- A domain task with an intentionally missing command produces `BLOCKED` and a visible environment-dependency summary.
- Queue panel shows job status correctly.
- Whitepaper and quality gate render in the intended order.
- Investigation detail returns `intelligence_requirements` and `cross_verification_matrix`.
- Whitepaper includes PIR answers, cross-verification summary, ACH/I&W, gaps, and directed collection.
- `/api/system/status` reports database status `ok`.
- `bash scripts/healthcheck.sh` passes.
- `bash scripts/backup.sh` creates a timestamped backup directory.
- `data/osint.sqlite` is backed up.
- Tokens are configured outside git.
