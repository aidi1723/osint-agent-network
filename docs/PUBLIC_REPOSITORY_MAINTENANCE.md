# Public Repository Maintenance

This repository can stay public as long as obvious operational secrets and
runtime artifacts are kept out of Git. The maintenance goal is pragmatic: remove
clear exposure, avoid future accidental commits, and do not rewrite public Git
history unless there is a real security reason.

## Risk Policy

Treat these as acceptable low-risk residue:

- Historical generic development notes that do not include usable credentials.
- Placeholder hostnames such as `<production-host>` or `production-host.local`.
- Documentation example IPs from reserved documentation ranges such as
  `192.0.2.10`.
- Generic install paths such as `/opt/osint-agent-network`,
  `/var/backups/osint-agent-network`, and `/path/to/osint-agent-network`.

Treat these as blockers before publishing:

- Real API tokens, Bearer tokens, cookies, private keys, SSH keys, or passwords.
- `.env`, `frontend/.env.production`, local shell profiles, or credential files.
- SQLite databases, screenshots, reports, job artifacts, logs, backups, or
  compressed runtime packages.
- Real private LAN addresses, personal home-directory paths, personal usernames,
  or machine names in current tracked files.
- Customer, lead, investigation, or third-party account data that was not meant
  to be public.

Do not rewrite public Git history for low-risk residue. Consider history rewrite
only if a real secret, active credential, private customer dataset, or sensitive
infrastructure endpoint was committed.

## Protected Files

The repository should keep these ignored:

- `.env`
- `frontend/.env.production`
- `data/*.sqlite`
- `data/jobs/`
- `data/artifacts/`
- `data/screenshots/`
- `data/snapshots/`
- `reports/*`
- `frontend/dist/`
- `frontend/node_modules/`

If a new runtime directory is added, update `.gitignore` before running the
tooling that writes files there.

## Pre-Publish Check

The automated checker reports stable rule IDs with repository-relative paths and
line numbers. It never includes a matched credential value in its output:

| Rule ID | Blocks |
| --- | --- |
| `LICENSE_FILE` | Missing or incomplete GNU GPL v3 license text. |
| `LICENSE_FRONTEND` | Frontend metadata other than `GPL-3.0-only`. |
| `LICENSE_BACKEND` | Backend metadata other than `GPL-3.0-only`. |
| `PUBLIC_PERSONAL_PATH` | Personal `/Users/<name>/` or `/home/<name>/` paths. |
| `PUBLIC_PRIVATE_NETWORK` | Addresses in `10/8`, `172.16/12`, or `192.168/16`. |
| `PUBLIC_CREDENTIAL_VALUE` | Credential assignments with non-placeholder values. |
| `PUBLIC_RUNTIME_ARTIFACT` | Tracked databases, environment files, or runtime-output paths. |

The scanner reads the NUL-delimited Git index when available. For non-Git fixture
directories it uses a sorted filesystem walk that excludes `.git`, virtual
environments, dependency directories, and cache directories. It scans only
strict UTF-8 text and skips binary data and symlinks.

Run these commands before pushing a public release branch:

```bash
git status --short
PYTHONPATH=backend backend/.venv/bin/python -m unittest \
  backend.tests.test_public_release_check backend.tests.test_production_readiness -v
python3 scripts/public_release_check.py
```

Variable names such as `ADMIN_API_TOKEN` are acceptable when no value is present.
Explicit placeholders such as `<token>`, `<your-token>`, `${READ_API_TOKEN}`,
`placeholder`, and `<production-host>` are acceptable. Shell-generated values in
documentation are also allowed because they do not publish a credential.

Reserved documentation addresses such as `192.0.2.10`, generic `/opt`, `/var`,
and `/path/to` paths, and the non-personal `/home/osint` service-account path are
allowed. An ellipsized path such as `/home/aidi/...` is treated as a documented
placeholder; a concrete path below that home directory is still blocked.

Intentional security-test fixtures and historical audit evidence use exact path,
rule ID, and full-line SHA-256 signatures in `SELF_SCAN_ALLOWLIST` inside
`scripts/public_release_check.py`. Do not add directory-wide, file-wide, or
rule-wide exceptions. Moving an unchanged line keeps the exception valid; any
content change invalidates it, and new adjacent matches remain blocking.

For stronger confidence, run the project verification suite:

```bash
bash scripts/verify.sh
python3 scripts/runtime_inventory.py
```

`runtime_inventory.py` is a review aid. It may report local runtime files; those
files should remain outside the public package.

## Documentation Rules

- Use `/path/to/osint-agent-network` for local checkout examples.
- Use `/opt/osint-agent-network` for server install examples.
- Use `/var/backups/osint-agent-network` for server backup examples.
- Use `<production-host>` for host-specific shell examples.
- Use `production-host.local` when a syntactically valid hostname is required in
  code or config examples.
- Use `192.0.2.10` for documentation-only LAN-style examples.
- Keep real deployment IPs, usernames, host aliases, and home-directory paths in
  private notes, not in tracked public files.

## Response Levels

Use this decision table when a privacy concern is found:

| Finding | Action |
| --- | --- |
| Variable name only, no value | Leave it or clarify as placeholder. |
| Generic placeholder or documentation IP | Leave it. |
| Personal path, private host, or LAN IP in current tracked file | Replace with a generic placeholder. |
| Local runtime artifact is untracked | Add or confirm `.gitignore`; do not commit it. |
| Real credential in current worktree | Remove it, rotate the credential, and verify no commit contains it. |
| Real credential already pushed | Rotate immediately, then consider Git history rewrite and force push. |

## Routine Maintenance

During normal development:

1. Keep `.env` and production frontend env files local.
2. Keep generated data, screenshots, reports, and logs out of Git.
3. Prefer generic examples in docs and tests.
4. Run the pre-publish scan before release commits.
5. Record any intentional public operational detail in
   `docs/PUBLIC_RELEASE_READINESS.md`.

This document is an engineering maintenance rule, not a legal or security audit.
When in doubt about a real credential or customer dataset, treat it as a blocker
until reviewed by the repository owner.
