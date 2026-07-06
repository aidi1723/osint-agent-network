# Final Handoff

Updated: 2026-07-06

This is the closing document for the current OSINT Agent Network / 情报官 delivery.

## Delivered State

The platform baseline is complete and deployed on <production-host>. The latest actual <production-host> task-test closure is recorded in [docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md](N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md).

Stable resident services:

- `osint-agent-network-api.service`
- `osint-agent-network-web.service`
- `osint-agent-network-backup.timer`

On-demand tools:

- Tool availability is reported by `/api/tools/health`.
- Missing or unconfigured tools are expected to produce `BLOCKED` jobs, not generic investigation failures.
- GHunt remains disabled by design until explicitly approved and configured.

## What Was Verified

- Local backend tests passed: `278 passed`.
- <production-host> `scripts/verify.sh` passed.
- <production-host> frontend helper checks, Vitest, and Vite production build passed.
- <production-host> `scripts/healthcheck.sh` passed.
- <production-host> `scripts/production_readiness.py` returns `ready: true`.
- <production-host> services are active.
- Backup timer is enabled.
- 2026-07-06 actual-task testing, ProjectDiscovery tool-chain closure, quality-gate fixes, and blocked-tool semantics are recorded in [docs/UPDATE_LOG.md](UPDATE_LOG.md).

## Latest Actual Task Findings

- Historical company/sparse-lead actual tasks now finish local role-agent passes and remain `NEEDS_REVIEW` only for concrete missing fields such as official website, contact channel, and decision-maker evidence.
- Missing or unconfigured external commands, such as `theharvester`, report `BLOCKED` with summary `工具任务被环境依赖阻断` instead of generic failures.
- The <production-host> sample domain quick chain reached the current design target in task `<final-domain-task-id>`.
- Final domain quick result: `COMPLETED`, summary `质量闸门已通过：完整度 78.1 / 100`, failed jobs `0`, blocked jobs `0`.
- Completed live chain: `subfinder`, `httpx`, `katana`, and `official_site_extractor`.

## Operational Rules

- Keep the platform baseline resident.
- Start REST-backed collectors only when a task explicitly needs them.
- Set `SPIDERFOOT_BASE_URL` and `PHONEINFOGA_BASE_URL` only for on-demand runs.
- Preserve artifacts after each run.
- Do not store cookies, tokens, or API keys in the repository.

## Current Tool State

The tool health layer reports the exact state of each tool. Tool attention is informational for the mature baseline, but a task that depends on a missing command or credential should be treated as `BLOCKED` until the tool is installed or configured.

Latest <production-host> readiness snapshot:

- `scripts/healthcheck.sh`: `api=ok`, `database=ok`, `web=ok`.
- `scripts/production_readiness.py`: `ready=true`, `severity=ok`.
- Tool health: `ready=9`, `attention_required=7`.

## Next Optional Enhancements

- Broader company/sparse-lead official website search, such as a controlled SearXNG layer.
- Decision-maker discovery and corroboration for company/sparse-lead tasks.
- More live tool samples and parser regression fixtures.
- PDF/HTML report export.
- Permission tiers and audit logs.
- Evidence URL, source rank, and human review state fields.

## Entry Points

- [README.md](../README.md)
- [docs/UPDATE_LOG.md](UPDATE_LOG.md)
- [docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md](N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md)
- [docs/PROJECT_PACKAGE.md](PROJECT_PACKAGE.md)
- [docs/N100_DEPLOYMENT_RUNBOOK.md](N100_DEPLOYMENT_RUNBOOK.md)
- [docs/REAL_TOOL_ENABLEMENT.md](REAL_TOOL_ENABLEMENT.md)
