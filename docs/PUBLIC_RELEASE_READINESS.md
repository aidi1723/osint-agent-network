# Public Release Readiness

This repository is prepared for public release under GNU GPL v3.

Latest engineering closure: [STAGE_CLOSURE_2026-07-07.md](STAGE_CLOSURE_2026-07-07.md).

Latest verified baseline:

- `bash scripts/verify.sh` passed.
- Backend unittest discovery: `411 tests OK`.
- Regression smoke: `4` cases / `0` failed.
- Frontend helper checks, Vitest `9` tests, and production build passed.
- Added-line privacy scan before the latest push produced no matches.

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

## License Notes

GNU GPL v3 is a strong copyleft license. Distributed derivative works must stay
GPL-compatible, which protects the project against closed redistribution but can
reduce adoption by commercial products that cannot accept GPL obligations.

This document is an engineering release checklist, not legal advice. Treat final
publication as an owner/legal approval item.

See [OPEN_SOURCE_LICENSE_OPTIONS.md](OPEN_SOURCE_LICENSE_OPTIONS.md) for the
license choice record.
