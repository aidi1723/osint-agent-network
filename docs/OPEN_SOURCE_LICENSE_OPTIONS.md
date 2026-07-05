# Open Source License Decision

Selected license: GNU GPL v3, SPDX identifier `GPL-3.0-only`.

This note records the engineering decision for public release. It is not legal
advice.

## Decision

GPLv3 was selected because it is a strong copyleft license. It allows public
use, study, modification, and redistribution, while requiring distributed
derivative works to remain GPL-compatible.

## Practical Effect

- `LICENSE` contains the full GNU GPL v3 text.
- `frontend/package.json` uses `GPL-3.0-only`.
- `scripts/public_release_check.py` intentionally rejects MIT, Apache-2.0,
  proprietary, and source-available metadata for this repository.
- Third-party dependencies remain governed by their own licenses and notices.

## Pre-Publish Checks

- Run `python3 scripts/public_release_check.py`.
- Run `bash scripts/verify.sh`.
- Confirm runtime data, secrets, screenshots, local databases, reports, and
  generated artifacts are excluded from the public repository.
