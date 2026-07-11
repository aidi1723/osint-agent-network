# Public Release Readiness

This repository is prepared for public release under GNU GPL v3.

Latest engineering closure: [STAGE_CLOSURE_2026-07-07.md](STAGE_CLOSURE_2026-07-07.md).

Latest verified baseline (2026-07-11 security-hardening closure):

- `bash scripts/verify.sh` passed before and after integration.
- Backend unittest discovery: `731 tests OK`.
- Regression smoke: `4` cases / `0` failed.
- Frontend helper checks, Vitest `45` tests, and the Vite 8.1.4 production build passed.
- Official-registry production and full npm audits each reported `0` vulnerabilities.
- Public release self-scan and final personal-path scan produced no findings.

## GPLv3 release gate

The selected license is `GPL-3.0-only`. Do not publish a release if `LICENSE`,
`frontend/package.json`, or README license wording drifts away from GNU GPL v3.
`EULA.md` must not add extra distribution, modification, or redistribution
restrictions that conflict with GPLv3.

## Required Pre-Publish Checks

- Run `bash scripts/verify.sh`.
- Run `python3 scripts/production_readiness.py` against the intended deployment environment.
- Run `python3 scripts/runtime_inventory.py` and review the runtime inventory before packaging.
- Run `python3 scripts/public_release_check.py`; it must pass only when the repository uses GNU GPL v3 and `frontend/package.json` declares `GPL-3.0-only`.
- Confirm `.env`, API tokens, cookies, screenshots, SQLite databases, reports, and job artifacts are not included in the public repository package.
- Follow [PUBLIC_REPOSITORY_MAINTENANCE.md](PUBLIC_REPOSITORY_MAINTENANCE.md) for privacy-hygiene scan rules and low-risk residue policy.
- Review `THIRD_PARTY_NOTICES.md`, `frontend/package-lock.json`, and vendored/generated assets before publishing.

## Authentication Release Gate

- The frontend build and `.env.example` must not contain `VITE_ADMIN_API_TOKEN` or any management credential. Browser administrators authenticate through `/api/auth/login` and receive an `HttpOnly`, `SameSite=Strict` session Cookie.
- Production must terminate TLS before the application, set `OSINT_COOKIE_SECURE=true`, define exact HTTPS `CORS_ALLOWED_ORIGINS`, and provide both `ADMIN_API_TOKEN` and `READ_API_TOKEN`; operators should keep the two values distinct. `production_readiness.py` must reject missing management/read credentials, an insecure Cookie setting, disabled authentication, or enabled legacy Agent-token mode.
- Browser sessions are process-local and intentionally require login again after an API restart. Non-browser administration retains explicit HTTP Authorization compatibility for management and read credentials.
- Every external Agent must use its own one-time-issued token and an explicit `role_tier`. Re-registering the same stable `agent_name` rotates the credential. Production must keep `OSINT_ALLOW_LEGACY_AGENT_TOKEN=false`; a shared `AGENT_API_TOKEN` is not a production identity boundary.
- Before release, run both official-registry npm audits and require zero high or critical vulnerabilities: `npm audit --omit=dev --registry=https://registry.npmjs.org` and `npm audit --registry=https://registry.npmjs.org`.

## License Notes

GNU GPL v3 is a strong copyleft license. Distributed derivative works must stay
GPL-compatible, which protects the project against closed redistribution but can
reduce adoption by commercial products that cannot accept GPL obligations.

This document is an engineering release checklist, not legal advice. Treat final
publication as an owner/legal approval item.

See [OPEN_SOURCE_LICENSE_OPTIONS.md](OPEN_SOURCE_LICENSE_OPTIONS.md) for the
license choice record.
