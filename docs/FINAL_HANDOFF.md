# Final Handoff

Updated: 2026-05-22

This is the closing document for the current OSINT Agent Network / 情报官 delivery.

## Delivered State

The platform baseline is complete and deployed on n100.

Stable resident services:

- `osint-agent-network-api.service`
- `osint-agent-network-web.service`
- `osint-agent-network-backup.timer`

On-demand tools:

- SpiderFoot
- PhoneInfoga
- theHarvester
- Amass
- Maigret
- Socialscan
- Recon-ng
- GHunt remains disabled by design until explicitly approved and configured

## What Was Verified

- Backend tests pass.
- Frontend helper checks pass.
- Vite build passes.
- `scripts/verify.sh` passes.
- `scripts/healthcheck.sh` passes.
- `scripts/production_readiness.py` returns `ready: true`.
- n100 services are active.
- Backup timer is enabled.
- 2026-05-22 security hardening and n100 redeploy notes are recorded in [docs/UPDATE_LOG.md](UPDATE_LOG.md).

## Operational Rules

- Keep the platform baseline resident.
- Start REST-backed collectors only when a task explicitly needs them.
- Set `SPIDERFOOT_BASE_URL` and `PHONEINFOGA_BASE_URL` only for on-demand runs.
- Preserve artifacts after each run.
- Do not store cookies, tokens, or API keys in the repository.

## Current Tool State

The tool health layer reports the exact state of each tool, but tool attention is informational for the mature baseline. It is used to tell operators what can be enabled next, not to block platform readiness.

## Next Optional Enhancements

- More live tool samples and parser regression fixtures.
- PDF/HTML report export.
- Permission tiers and audit logs.
- Evidence URL, source rank, and human review state fields.

## Entry Points

- [README.md](../README.md)
- [docs/UPDATE_LOG.md](UPDATE_LOG.md)
- [docs/PROJECT_PACKAGE.md](PROJECT_PACKAGE.md)
- [docs/N100_DEPLOYMENT_RUNBOOK.md](N100_DEPLOYMENT_RUNBOOK.md)
- [docs/REAL_TOOL_ENABLEMENT.md](REAL_TOOL_ENABLEMENT.md)
