# Real Tool Enablement Checklist

Updated: 2026-07-06

This document tracks the <production-host> real OSINT tool layer after the mature platform baseline has landed. The platform baseline does not require real OSINT tools to stay resident in the background. Keep API/Web/backup timer running; start heavier collectors only when an investigation route actually needs them.

## Current <production-host> Status

Already wired for on-demand use:

- `sherlock`: command configured as `python3`. The health check only verifies the command layer; run a live adapter job before treating Sherlock collection as fully proven.
- `profile_parser`: internal artifact parser.
- `official_site_extractor`: internal official-site HTML fetcher/parser for organization, contact, address, and business-scope fields. Confirmed on <production-host> after gzip-response handling.
- `official_site_search`: optional SearXNG-compatible official-site candidate search for `company` and `sparse_lead` tasks. It stays disabled until `OFFICIAL_SITE_SEARCH_BASE_URL` is configured.
- `lead_anchor_extraction`: internal sparse-lead parser.
- `company_news`: command configured as `python3`; falls back to public RSS behavior when optional packages are absent.
- `subfinder`: installed at `<osint-bin>/subfinder` and wired through `SUBFINDER_COMMAND`.
- `httpx`: installed at `<osint-bin>/httpx` and wired through `HTTPX_COMMAND`.
- `katana`: installed at `<osint-bin>/katana` and wired through `KATANA_COMMAND`.
- `phoneinfoga`: adapter supports `PHONEINFOGA_BASE_URL`; leave it empty by default and set it only for phone-enrichment runs.
- `spiderfoot`: adapter supports `SPIDERFOOT_BASE_URL`; leave it empty by default and set it only for SpiderFoot-enrichment runs. API key is optional for the local no-auth instance.
- `reconng`: installed at `/opt/osint-tools/recon-ng/recon-ng` and wired through `RECONNG_COMMAND`.

Still requiring install or path configuration:

- `maigret`: executable not found.
- `socialscan`: executable not found.
- `amass`: executable not found.
- `theHarvester`: expected path `/opt/osint/theHarvester/theHarvester.py` does not exist.

Disabled by design:

- `ghunt`: disabled in the registry because it requires account/session material. Enable only after legal and operational approval, and keep cookies outside the repository.

## <production-host> Environment Lines

Default `.env` should keep REST-backed tools disabled:

```bash
SPIDERFOOT_BASE_URL=
PHONEINFOGA_BASE_URL=
OFFICIAL_SITE_SEARCH_BASE_URL=
RECONNG_COMMAND=/opt/osint-tools/recon-ng/recon-ng
SUBFINDER_COMMAND=<osint-bin>/subfinder
HTTPX_COMMAND=<osint-bin>/httpx
KATANA_COMMAND=<osint-bin>/katana
```

When a task explicitly needs one of these tools, set the URL temporarily or in the task runner environment:

```bash
SPIDERFOOT_BASE_URL=http://127.0.0.1:5001
PHONEINFOGA_BASE_URL=http://127.0.0.1:5000
OFFICIAL_SITE_SEARCH_BASE_URL=http://127.0.0.1:8080/search
```

## Recommended Install Order

1. `theHarvester`: improves domain-to-email/subdomain discovery and is directly useful for company/domain cases.
2. `amass`: improves passive subdomain and DNS expansion.
3. `maigret`: improves username-to-profile coverage.
4. `socialscan`: improves email/username account existence checks.
5. Optional REST services: SpiderFoot and PhoneInfoga when a task specifically needs them.

## Resident Service Policy

Keep resident:

- `osint-agent-network-api.service`
- `osint-agent-network-web.service`
- `osint-agent-network-backup.timer`

Do not keep resident by default:

- SpiderFoot
- PhoneInfoga
- Any other heavy collector service

When a task needs a REST-backed tool, start the service, set the matching `*_BASE_URL`, run the task, preserve the artifact, then clear the URL and stop the service if no other active task needs it.

## Acceptance Commands

After each install or `.env` update:

```bash
cd /opt/osint-agent-network
systemctl --user restart osint-agent-network-api.service
python3 scripts/production_readiness.py
python3 - <<'PY'
import json, urllib.request
payload = json.loads(urllib.request.urlopen("http://127.0.0.1:8088/api/tools/health", timeout=10).read().decode())
print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
for item in payload["tools"]:
    if item["status"] != "ready":
        print(f"{item['name']}: {item['status']} - {item['reason']}")
PY
```

The platform baseline is acceptable when `production_readiness.py` returns `ready: true`. `tool_attention` is informational for on-demand tools; it shows what must be installed or started before using specific collectors, but it does not block the mature platform baseline.

## <production-host> Actual Test Note - 2026-07-06

ProjectDiscovery tools are now proven in a real sample domain task:

- Earlier proof task: `<phase-domain-task-id>`
- Final completion task: `<final-domain-task-id>`
- Completed available chain:
  - `subfinder`
  - `httpx` domain probe
  - `httpx` URL probe
  - `katana`
  - `official_site_extractor`
- Failed jobs: `0`
- Blocked jobs: `0`
- Score improved from the earlier `26.6` domain-probe-only result to `78.1`.
- Final status: `COMPLETED`

Remaining quality-gate work is now broader company/sparse-lead coverage, not basic execution of the ProjectDiscovery domain quick chain.
