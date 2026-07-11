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

The repeated real search did **not** reach the end-to-end intelligence design goal in the current N100 network environment:

- final status: `NEEDS_REVIEW`
- quality score: `44.5 / 100`
- completed jobs: `4`
- partially failed jobs: `1`
- failed jobs: `0`
- blocked jobs: `0`
- stable empty rerun: passed

The domain discovery, HTTP probing, and crawling stages completed. The internal official-site extractor refused the target because N100's transparent network layer returned a non-global reserved address during DNS validation. External tools could traverse the transparent network path, but the internal SSRF-safe fetcher correctly rejected that address. As a result, organization, contact, and business-scope evidence was not extracted and the quality gate remained open.

This is an operational network compatibility gap, not evidence that the SSRF guard should be weakened. The production release is healthy, but the original real-search acceptance target remains unmet until N100 provides a resolver or controlled egress path that yields and pins real public addresses.

## Deployment Evidence

Release source before the deployment-specific packaging fix:

- base commit: `71c72cc72b6d6337aa6e5ac98598f3fddd8e64f0`

Protected state:

- `.env`, SQLite data, job artifacts, reports, frontend production environment, and the operator-maintained closure log were excluded from source synchronization.
- synchronization used `rsync` without `--delete`.
- runtime backup: `<production-backup-root>/20260711-180918`
- source archive: `<production-backup-root>/predeploy-20260711-180918-source.tar.gz`
- pre-hardening environment backup: `<production-backup-root>/.env.pre-security-hardening-20260711-180918`

Production security settings confirmed after deployment:

```text
APP_ENV=production
OSINT_COOKIE_SECURE=true
OSINT_ALLOW_LEGACY_AGENT_TOKEN=false
ADMIN_API_TOKEN=configured
READ_API_TOKEN=configured
OFFICIAL_SITE_SEARCH_BASE_URL=configured
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

Remote runtime-source verification:

- backend unit tests: `732 / 732` passed
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
| Investigation reaches `COMPLETED` | Not met | Final status `NEEDS_REVIEW` |
| Quality score is at least `72` | Not met | `44.5` |
| Failed jobs equal `0` | Met | No `FAILED` jobs |
| Blocked jobs equal `0` | Met | No `BLOCKED` jobs |
| `subfinder` completes | Met | One completed job |
| domain and URL `httpx` complete | Met | Two completed jobs |
| `katana` completes | Met | One completed job |
| `official_site_extractor` completes | Not met | One `PARTIAL_FAILED` job |
| Source-backed official URLs exist | Met | Four source-backed URL entities |
| Source-backed organization/contact/business fields exist | Not met | No organization, phone, email, or business-scope field extracted |
| Empty rerun preserves terminal state and summary | Met | Status and summary remained unchanged |

The run produced two domain/subdomain entities, four URL entities, two HTTP-probe evidence items, and one passive subdomain-discovery evidence item. Real values are intentionally omitted.

## Root Cause And Security Decision

The official-site extractor uses the internal safe HTTP client. That client resolves every target, rejects non-public addresses, pins the validated public address for the connection, repeats validation after redirects, and limits redirects, response size, and timeout.

On N100:

- system DNS returned a non-global reserved address for the public target;
- an explicit query to a public DNS server was intercepted and also returned a non-global reserved address;
- `httpx` and `katana` succeeded through the host's transparent network path;
- the internal safe fetcher rejected the reserved address before connecting.

Allowing the reserved range globally would weaken SSRF protection and could permit access to network-local services hidden behind the same address space. No such bypass was added.

Approved remediation direction:

1. Configure the N100 network layer to bypass fake-address DNS mapping for the API service or for public OSINT targets, while retaining the transparent egress path.
2. Alternatively provide a trusted fetch gateway that resolves public DNS independently, rejects private/reserved destinations on every redirect, pins validated addresses, limits response size and time, and returns only bounded public content.
3. Rerun the same anonymized acceptance procedure after the network change. Do not add `198.18.0.0/15` or another reserved/private range to the application allowlist.

## Residual Risks

- The real-search completion target is still open until safe official-site fetching works in the N100 network environment.
- Seven optional tools still require configuration or installation. Health-aware planning correctly skips known unavailable routes.
- Secure browser cookies require HTTPS. Until TLS termination is installed, operator browser access should use a localhost SSH tunnel; production cookie security must not be weakened for plaintext LAN access.
- A production runtime tree is not a clean public release tree. Public release scanning must remain attached to the Git source boundary or a clean release staging directory.

## Rollback

If the deployed source must be rolled back:

1. Stop the API and Web user services.
2. Restore source from `<production-backup-root>/predeploy-20260711-180918-source.tar.gz`.
3. Restore runtime state from `<production-backup-root>/20260711-180918` only if runtime rollback is explicitly required.
4. Restore the environment backup only if the two security settings must be reverted for incident recovery; do not revert them for routine compatibility.
5. Restart both services, then run the health and production-readiness checks.

The current deployment does not require rollback: service health and release verification pass. The unresolved item is the network egress/DNS compatibility needed for the safe official-site stage.
