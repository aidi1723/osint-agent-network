# N100 Hardened Deployment And Real Search Closure - 2026-07-11

## Scope

This report closes the hardened deployment and real public-information search verification performed on 2026-07-11.

Public identifiers are intentionally anonymized:

- production host: `<production-host>`
- deployment directory: `<production-path>`
- original public target: `<original-public-target>`
- verification investigation: `<verification-investigation-id>`
- backup root: `<production-backup-root>`

No credential, real target, contact value, private address, or production artifact is included in this document.

## Executive Conclusion

The hardened application release was deployed successfully and the production services are healthy. Authentication hardening, secure-cookie configuration, dependency alignment, backend tests, frontend tests, regression checks, production build, health checks, and readiness checks passed.

The final repeated real search reached the end-to-end intelligence design goal after two narrowly scoped fixes:

- final status: `COMPLETED`
- quality score: `78.1 / 100`
- completed jobs: `5`
- failed jobs: `0`
- blocked jobs: `0`
- stable empty rerun: passed

The initial hardened retest stopped at `NEEDS_REVIEW`, score `44.5`, because N100's transparent network layer returned a reserved fake address and the internal safe fetcher rejected it. A default-off double allowlist now requires both an exact configured hostname and an IPv4 subnet contained by `198.18.0.0/15`. Literal addresses, unrelated private/reserved ranges, unlisted hosts, and unlisted redirect hosts remain blocked.

After official-site extraction succeeded, the quality score returned to `78.1`, but two phone numbers from the same official source were incorrectly treated as contradictory. Cross verification now permits multiple contact values from the same source family while preserving conflicts between different source families. The strict completion policy then passed with no remaining blockers.

## Deployment Evidence

Release source before the deployment-specific packaging fix:

- base commit: `71c72cc72b6d6337aa6e5ac98598f3fddd8e64f0`

Protected state:

- `.env`, SQLite data, job artifacts, reports, frontend production environment, and the operator-maintained closure log were excluded from source synchronization.
- synchronization used `rsync` without `--delete`.
- runtime backup: `<production-backup-root>/20260711-180918`
- source archive: `<production-backup-root>/predeploy-20260711-180918-source.tar.gz`
- pre-hardening environment backup: `<production-backup-root>/.env.pre-security-hardening-20260711-180918`
- final pre-fake-IP source and environment backup timestamp: `20260711-185807`

Production security settings confirmed after deployment:

```text
APP_ENV=production
OSINT_COOKIE_SECURE=true
OSINT_ALLOW_LEGACY_AGENT_TOKEN=false
ADMIN_API_TOKEN=<configured-admin-token>
READ_API_TOKEN=<configured-read-token>
OFFICIAL_SITE_SEARCH_BASE_URL=configured
OSINT_SAFE_HTTP_FAKE_IP_CIDRS=<configured-benchmark-subnet>
OSINT_SAFE_HTTP_FAKE_IP_HOSTS=<configured-exact-hosts>
```

Secret values were preserved and were never printed or copied into the repository.

## Packaging Defect Fixed During Deployment

The documented editable backend install initially failed in the populated production workspace because setuptools automatic discovery treated the ignored runtime directory `backend/data/` as a second top-level package.

The release now declares explicit package discovery:

```toml
[tool.setuptools.packages.find]
include = ["app*"]
exclude = ["data*", "tests*"]
```

A release-artifact regression test verifies this boundary. After the fix, the editable backend install completed and the PDF dependencies were available to the system Python used by the existing N100 service.

Frontend dependency resolution confirmed:

- Vite `8.1.4`
- `@vitejs/plugin-react` `6.0.3`
- `undici` `7.28.0`
- npm audit result: zero reported vulnerabilities

## Verification Results

Final remote runtime-source verification:

- controlled-fetch and adapter tests: `67 / 67` passed
- cross-verification and completion-policy tests: `77 / 77` passed
- backend unit tests: `745 / 745` passed
- agent governance manifest: passed
- regression smoke cases: `4 / 4` passed
- frontend helper and UI-copy checks: passed
- frontend Vitest: `45 / 45` passed
- frontend production build: passed with Vite `8.1.4`

The public-release scanner was not run against the production runtime directory because that directory intentionally has no Git metadata and contains protected `.env`, database, logs, reports, job artifacts, and build output. Without a Git index the scanner correctly falls back to scanning the whole directory and rejects those production-only files. Public-release validation is instead run against the local Git source tree, where the release boundary is authoritative.

Service restart and readiness:

- API service: `active`, `running`, restart count `0`
- Web service: `active`, `running`, restart count `0`
- health check: API `ok`, database `ok`, Web `ok`
- schema versions: `4`
- production readiness: `ready=true`, `severity=ok`
- authentication, secure cookie, legacy-token rejection, backup timer, and tool-health endpoint checks: `ok`
- tool health: `18` total, `10` ready, `7` requiring attention

The first health request was issued immediately after systemd restart and reached the API before it had bound its port. A repeated check after startup completed passed, and both services remained at restart count zero.

## Real Search Evidence

The verification process selected the latest prior completed domain investigation whose successful history contained all of `subfinder`, `httpx`, `katana`, and `official_site_extractor`. The seed stayed in N100 process memory and was not exported.

The fresh quick investigation used bounded execution with at most six jobs per worker round.

Observed terminal evidence:

| Criterion | Result | Evidence |
| --- | --- | --- |
| Investigation reaches `COMPLETED` | Met | Final status `COMPLETED` |
| Quality score is at least `72` | Met | `78.1` |
| Failed jobs equal `0` | Met | No `FAILED` jobs |
| Blocked jobs equal `0` | Met | No `BLOCKED` jobs |
| `subfinder` completes | Met | One completed job |
| domain and URL `httpx` complete | Met | Two completed jobs |
| `katana` completes | Met | One completed job |
| `official_site_extractor` completes | Met | One completed job |
| Source-backed official URLs exist | Met | Four source-backed URL entities |
| Source-backed organization/contact/business fields exist | Met | One organization, two phones, and one business-scope entity |
| Empty rerun preserves terminal state and summary | Met | Status and summary remained unchanged |

The final run produced two domain/subdomain entities, four URL entities, one organization, two phones, and one business-scope entity. Evidence included two HTTP probes, one passive subdomain-discovery record, one official identity record, two official contact records, and one official business-scope record. Four facts were linked to source evidence. Real values are intentionally omitted.

## Root Cause And Security Decision

The official-site extractor uses the internal safe HTTP client. That client resolves every target, rejects non-public addresses, pins the validated public address for the connection, repeats validation after redirects, and limits redirects, response size, and timeout.

On N100:

- system DNS returned a non-global reserved address for the public target;
- an explicit query to a public DNS server was intercepted and also returned a non-global reserved address;
- `httpx` and `katana` succeeded through the host's transparent network path;
- the internal safe fetcher rejected the reserved address before connecting.

Allowing the reserved range globally would weaken SSRF protection and could permit access to network-local services hidden behind the same address space. No global bypass was added.

Implemented control:

1. Both the exact hostname list and the fake-IP CIDR list must be non-empty and valid; partial configuration fails closed.
2. Configured CIDRs must be IPv4 subnets wholly contained by `198.18.0.0/15`.
3. Hostnames are exact IDNA-normalized matches. Wildcards, URLs, credentials, ports, and IP host entries are invalid.
4. Direct non-global IP literals remain blocked even inside the configured subnet.
5. Every redirect repeats hostname, DNS-answer, address-class, timeout, size, and connection-pinning validation.
6. Only the official-site extractor loads this exception. Other safe HTTP consumers remain strict.

The final live-page smoke fetched bounded HTML and extracted one organization, two phones, one business scope, and four evidence items before the full investigation was run.

## Additional Finding: Multi-Value Contact Semantics

Cross verification previously treated every distinct value as a contradiction, including two phone numbers emitted by the same official-site source. The fix distinguishes source families:

- multiple phone or email values from the same source family may coexist;
- different contact values from different source families still produce a conflict;
- fact-level conflicts and conflicts for company identity, official website, and other single-value fields remain unchanged.

The new regression test reproduces the same-official-source two-phone case, while the existing official-versus-directory email conflict test continues to pass.

## Residual Risks

- The exact-host allowance reduces exposure but still depends on the transparent proxy to map an approved fake address to the intended upstream destination. A separately controlled egress gateway remains the stronger long-term architecture.
- Seven optional tools still require configuration or installation. Health-aware planning correctly skips known unavailable routes.
- Secure browser cookies require HTTPS. Until TLS termination is installed, operator browser access should use a localhost SSH tunnel; production cookie security must not be weakened for plaintext LAN access.
- A production runtime tree is not a clean public release tree. Public release scanning must remain attached to the Git source boundary or a clean release staging directory.
- N100's configured backup root is inside `data/`, so an unqualified `scripts/backup.sh` invocation attempts to copy data into its own descendant. This deployment used an explicit external backup root. Production configuration should be corrected before relying on the default backup command.

## Rollback

If the deployed source must be rolled back:

1. Stop the API and Web user services.
2. Restore source from the pre-fake-IP source archive with timestamp `20260711-185807`.
3. Restore runtime state from `<production-backup-root>/20260711-180918` only if runtime rollback is explicitly required.
4. Restore the pre-fake-IP environment backup or remove the two fake-IP variables to disable the exception immediately.
5. Restart both services, then run the health and production-readiness checks.

The current deployment does not require rollback: service health, release verification, controlled official-site fetching, and the real-search acceptance criteria pass.
