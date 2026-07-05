# N100 Deployment Log - 2026-07-02 Reliability Upgrade

## Summary

- Date: 2026-07-02
- Target host: `<production-host>`
- Target IP: `192.0.2.10`
- Target path: `/opt/osint-agent-network`
- Service mode: user-level systemd
- Result: deployed and verified

This deployment promoted the reliability fixes for customs supply-chain errors, intelligence aggregation contracts, frontend error states, CSS validity, and production readiness authorization.

## Changes Deployed

- Customs supply-chain API preserves upstream/configuration error status instead of returning empty successful results.
- Product intelligence extracts products from `trade_relationship` evidence.
- Social intelligence enriches profiles through `profile_has_*` relationships.
- Frontend panels surface backend error details through shared API helpers.
- CSS syntax warning was removed.
- `production_readiness.py` sends read authorization for protected status endpoints.

## Backup

Created before sync:

```text
/var/backups/osint-agent-network/predeploy-20260702-163837.tar.gz
```

Backup command pattern:

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

## Sync Command

Run from local project root:

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

Preserved on remote:

- `.env`
- `frontend/.env.production`
- `data/osint.sqlite`
- `data/jobs/`
- `data/artifacts/`
- `reports/`

## Remote Build And Verification

Build:

```bash
ssh <production-host> 'cd /opt/osint-agent-network/frontend && npm install && npm run build'
```

Observed:

```text
npm install: completed
npm audit: 4 vulnerabilities (2 low, 2 high)
Vite build: completed
CSS syntax warnings: none
```

Full verification:

```bash
ssh <production-host> 'cd /opt/osint-agent-network && bash scripts/verify.sh'
```

Observed:

```text
Ran 110 tests ... OK
Regression smoke: case_count=4, failed=0
Frontend checks: passed
Vite build: passed
```

Production readiness:

```bash
ssh <production-host> 'cd /opt/osint-agent-network && python3 scripts/production_readiness.py'
```

Observed:

```text
ready=true
severity=ok
api/database/web/backup/tool health=ok
tool_attention=7
```

`tool_attention=7` is informational for optional/on-demand OSINT tools.

## Services

Installed/refreshed:

```bash
ssh <production-host> 'mkdir -p ~/.config/systemd/user && \
  cp /opt/osint-agent-network/deploy/systemd/osint-agent-network-api.service ~/.config/systemd/user/ && \
  cp /opt/osint-agent-network/deploy/systemd/osint-agent-network-web.service ~/.config/systemd/user/ && \
  systemctl --user daemon-reload && \
  systemctl --user enable --now osint-agent-network-api.service osint-agent-network-web.service'
```

Final restart:

```bash
ssh <production-host> 'systemctl --user restart osint-agent-network-api.service osint-agent-network-web.service'
```

Final status:

```text
osint-agent-network-api.service: active/enabled
osint-agent-network-web.service: active/enabled
Listening: 0.0.0.0:8088, 0.0.0.0:3008
```

## Final Health Check

Observed:

```text
API health: {"status": "ok", "service": "osint-agent-network"}
Database status: ok
Web head: <!doctype html>
```

Access:

- Web UI: `http://192.0.2.10:3008/`
- API health: `http://192.0.2.10:8088/api/health`

## Issue Fixed During Deployment

`scripts/production_readiness.py` initially failed with `401 Unauthorized` because it loaded `.env` but did not attach read authorization to `/api/system/status`.

Fix:

- Read token order: `READ_API_TOKEN`, then `ADMIN_API_TOKEN`, then `AGENT_API_TOKEN`.
- `_get_json()` now sends `Authorization: Bearer <token>` when a token is provided.
- `backend/tests/test_production_readiness.py` verifies this behavior.

After the fix:

```text
backend.tests.test_production_readiness: 3 tests OK
production_readiness.py: ready=true
```

## Next Upgrade Checklist

1. Run local verification:

```bash
cd /path/to/osint-agent-network
bash scripts/verify.sh
```

2. Create remote backup with the backup command pattern above.

3. Sync with the safe rsync command above.

4. Build and verify remotely:

```bash
ssh <production-host> 'cd /opt/osint-agent-network/frontend && npm install && npm run build'
ssh <production-host> 'cd /opt/osint-agent-network && bash scripts/verify.sh'
```

5. Restart and run readiness:

```bash
ssh <production-host> 'systemctl --user restart osint-agent-network-api.service osint-agent-network-web.service'
ssh <production-host> 'cd /opt/osint-agent-network && python3 scripts/production_readiness.py'
```

6. Confirm access:

```bash
curl -sS http://192.0.2.10:8088/api/health
curl -sS http://192.0.2.10:3008/ | head
```

## Rollback Notes

If a future deployment fails after service restart, inspect logs first:

```bash
ssh <production-host> 'journalctl --user -u osint-agent-network-api.service -n 80 --no-pager'
ssh <production-host> 'journalctl --user -u osint-agent-network-web.service -n 80 --no-pager'
```

Restore from backup only after confirming `.env`, `data/`, and `reports/` preservation. Avoid copying old runtime data over current investigation data unless that is intentional.

