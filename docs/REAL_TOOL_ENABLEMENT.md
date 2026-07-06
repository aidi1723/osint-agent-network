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

## Official-Site Search Design Verification - 2026-07-06

A <production-host> mock SearXNG verification was run with a local JSON endpoint and an in-memory investigation store. The mock endpoint returned one official candidate and one third-party directory candidate for `Sample Auto Parts Co.`.

Passed checks:

- `OFFICIAL_SITE_SEARCH_BASE_URL` absent: `official_site_search` is skipped cleanly during health-aware planning.
- `OFFICIAL_SITE_SEARCH_BASE_URL` present: `official_site_search` is included in the company standard plan.
- Official candidate URL normalized from `https://www.example-target.test/about?utm_source=test` to `https://www.example-target.test/about`.
- Directory candidate `directory.example` was filtered out.
- Evidence kind `official_site_search_result` was written.
- Followups queued:
  - `httpx`
  - `katana`
  - `official_site_extractor`
  - `profile_parser`
  - domain quick expansion for `example-target.test`
- Worker result:
  - started: `1`
  - completed: `1`
  - failed: `0`
  - blocked: `0`
  - queued followups: `6`

Verification finding:

- A first standalone mock run did not load deployment `.env`, so health-aware planning could not see `KATANA_COMMAND` and skipped the external crawler followup. Loading `.env` before the mock run made `httpx`, `katana`, `official_site_extractor`, `official_site_search`, and `profile_parser` all report `ready`.

Conclusion:

- `official_site_search` is ready for controlled internal SearXNG-backed company and sparse-lead discovery.
- Keep `OFFICIAL_SITE_SEARCH_BASE_URL` empty in the default public/package environment and set it only in the task runner environment when official-site discovery is required.

## Real SearXNG Enablement - 2026-07-06

<production-host> now has a controlled internal SearXNG-compatible endpoint for real official-site discovery.

Operational setup:

- Bind SearXNG to loopback only.
- Enable JSON output in SearXNG settings:

```yaml
search:
  formats:
    - html
    - json
```

- Set only the production task environment to:

```bash
OFFICIAL_SITE_SEARCH_BASE_URL=http://127.0.0.1:<internal-search-port>/search
```

Do not put production hostnames, paths, tokens, cookies, or real lead data in repository files.

Verification evidence:

- Before enabling JSON, `format=json` returned HTTP `403`.
- After enabling JSON, the same endpoint returned HTTP `200` with a JSON `results` array.
- Tool health moved to:
  - total tools: `18`;
  - ready: `10`;
  - attention required: `7`;
  - `official_site_search`: `ready`.
- Public-safe real endpoint adapter checks for `Example Domain`:
  - company target returned only `https://example.com/` as the URL candidate;
  - sparse-lead target returned only `https://example.com/` as the URL candidate.
- Public-safe API checks confirmed that `official_site_search` writes `official_site_search_result` evidence and queues URL followups.

Hardening added after real testing:

- Third-party result filtering for forums, wiki/content sites, social platforms, blogs, directories, and domain-registration pages.
- Generic company-name stopwords are not used as strong hostname evidence.
- Root URLs normalize to a trailing slash for followup deduplication.
- `SUBFINDER_RESULT_LIMIT` caps passive subdomain output, default `300`, to keep reports and synchronous API responses bounded.

Runbook note:

- For larger real tasks, run `/api/investigations/<id>/run-jobs` in bounded batches.
- A future background worker remains recommended for long collector chains, because the current endpoint is synchronous.
- After official-site search queues multiple URL candidates, bounded runs prioritize one URL evidence chain first: `httpx(url)`, `katana(url)`, then `official_site_extractor(url)`. Domain expansion remains queued behind the active URL group.
