# Safe HTTP Fake-IP Allowance Design

**Date:** 2026-07-11

**Status:** Approved for specification review

## Goal

Allow the N100 production deployment to fetch explicitly approved public websites when its transparent proxy maps those hostnames into `198.18.0.0/15`, without broadly disabling the existing SSRF protections. Preserve complete public-page content for extraction, then apply the existing normalization, evidence, quality, and reporting stages after collection.

## Context

The hardened real-search verification completed `subfinder`, two `httpx` jobs, and `katana`, but `official_site_extractor` partially failed. N100 system DNS and an explicit public DNS query both returned a non-global address in `198.18.0.0/15`. External tools traversed the host's transparent proxy successfully, while the internal safe HTTP client correctly rejected the reserved address.

The compatibility requirement is limited to this fake-IP proxy behavior. It does not justify allowing loopback, private, link-local, multicast, unspecified, documentation, cloud metadata, or arbitrary reserved destinations.

## Options Considered

### 1. Exact Host And CIDR Double Allowlist - Selected

Permit a DNS-resolved address only when both conditions hold:

- the normalized hostname exactly matches an operator-configured hostname;
- the resolved address belongs to an operator-configured subnet within `198.18.0.0/15`.

This is the smallest change that supports the current N100 network while preserving an auditable boundary.

### 2. CIDR-Only Allowance - Rejected

Permit every hostname that resolves into `198.18.0.0/15`. This is operationally simple but delegates all destination safety to the transparent proxy and weakens protection against attacker-controlled hostnames.

### 3. Unrestricted Fetch Followed By Cleaning - Rejected

Fetch every destination and discard unsafe content afterward. Content cleaning cannot undo an SSRF request or its side effects. This mode would require a separate disposable fetch gateway with no production credentials, no host filesystem access, and enforced network isolation; it is outside this change.

## Configuration

Add two optional environment variables:

```text
OSINT_SAFE_HTTP_FAKE_IP_CIDRS=
OSINT_SAFE_HTTP_FAKE_IP_HOSTS=
```

Rules:

- Empty or missing values preserve the current strict behavior.
- Values are comma-separated and whitespace-trimmed.
- CIDRs must be IPv4 subnets wholly contained by `198.18.0.0/15`.
- The parser rejects malformed CIDRs, IPv6 ranges, broader ranges, and all unrelated ranges.
- Hostnames use normalized IDNA ASCII form, lowercase, and no trailing dot.
- Host entries must be exact DNS hostnames. Wildcards, URL syntax, ports, paths, credentials, and IP literals are rejected.
- Invalid non-empty configuration fails closed. It does not silently discard unsafe entries while enabling the remaining entries.

Production configuration will contain the original target hostname and each observed redirect hostname, including a `www` hostname only when the real redirect requires it. Real values remain in N100 `.env` and never enter source control, command output, or public documentation.

## Validation Model

### Default Path

`validate_public_url` continues to accept globally routable addresses and reject all other address classes. Existing callers and deployments without the new variables retain identical behavior.

### Fake-IP Path

For a DNS hostname, a non-global address is accepted only when:

1. the hostname exactly matches `OSINT_SAFE_HTTP_FAKE_IP_HOSTS`;
2. the address belongs to one of `OSINT_SAFE_HTTP_FAKE_IP_CIDRS`;
3. that configured subnet has already passed the `198.18.0.0/15` containment check.

Every DNS answer must be independently acceptable. A response mixing an approved fake address with any unapproved private, reserved, or malformed address fails closed.

### Literal Addresses

Non-global IP literals remain blocked even when they belong to an approved fake-IP subnet. The exception applies only to DNS hostnames so an operator authorizes a hostname identity, not direct access to the proxy address space.

### Redirects

Each redirect target is parsed and resolved again. A redirect to a different hostname requires its own exact hostname entry. Redirects to literals, unlisted fake-IP hostnames, private addresses, invalid ports, or credentialed URLs remain blocked.

### Connection Pinning

The accepted fake address is pinned by the existing connector exactly like a public address. HTTPS continues to use the original hostname for SNI and certificate verification; HTTP continues to use the original hostname in the `Host` header.

## Component Changes

### `backend/app/core/safe_http.py`

- Add a small immutable allowance value that contains validated fake-IP networks and exact hostnames.
- Add a strict environment parser for the two variables.
- Extend URL validation and bounded fetch functions with an optional allowance argument.
- Keep the default argument equivalent to no allowance.
- Apply the same allowance on every redirect validation.

### `backend/app/tools/official_site_extractor.py`

- Load the fake-IP allowance when running the internal official-site fetch.
- Pass it to `safe_fetch`.
- Keep error output sanitized and keep the existing response-size, redirect, and timeout limits.

Other internal HTTP consumers remain strict unless explicitly migrated in a later reviewed change. This task only changes the official-site extraction path needed by the verified production workflow.

### Environment And Documentation

- Add empty, documented variables to `.env.example`.
- Update the N100 runbook with the double-allowlist constraints and the warning that content cleaning does not replace destination controls.
- Update the deployment closure report with the final retest evidence and residual risk.

## Content Processing

The network allowance does not suppress or pre-filter public page text. After the bounded fetch succeeds, the current official-site parser performs normalization and extraction for organization, URL, email, phone, business scope, address, and conservative public decision-maker candidates.

Existing evidence provenance, fact promotion, quality assessment, completion policy, and report rendering remain unchanged. The system must not treat an extracted value as verified merely because the network request was allowed.

## Error Handling And Auditability

- Invalid configuration produces a sanitized fetch failure and no request.
- An unlisted hostname or out-of-range address produces the existing generic blocked-fetch behavior.
- Errors must not expose the target, credentials, private paths, or configured hostname list.
- Tool events may state that a configured fake-IP allowance was used, but public reports record only that the controlled allowance was enabled, never its real hostname values.
- The existing fetch timeout, maximum response size, redirect limit, DNS-answer cap, and connection pinning remain mandatory.

## Test Strategy

Implementation follows red-green-refactor.

Required failing tests before production code:

- default configuration still rejects `198.18.0.0/15`;
- matching exact hostname plus matching contained CIDR accepts a DNS-resolved fake address;
- matching CIDR without matching hostname rejects;
- matching hostname with an out-of-range address rejects;
- direct fake-IP literal rejects;
- mixed allowed fake and unapproved private answers reject;
- redirect to an unlisted hostname rejects;
- redirect to a separately listed hostname succeeds;
- malformed, broader, unrelated, IPv6, wildcard-host, URL-host, and IP-host configuration fails closed;
- the official-site adapter passes the validated allowance to `safe_fetch` without leaking configuration or targets on error.

Verification layers:

1. targeted safe HTTP and official-site adapter tests;
2. complete backend suite;
3. agent governance and four regression cases;
4. public release scan and `git diff --check`;
5. frontend checks, 45 frontend tests, and production build;
6. remote tests, service restart, health check, and production readiness;
7. a new bounded real investigation selected from the previous successful target without exporting its value.

## Deployment And Real-Search Acceptance

Before deployment:

- back up source, `.env`, database, jobs, artifacts, and reports;
- synchronize source without `--delete` and without overwriting runtime state;
- add the exact fake-IP CIDR and target/redirect hostnames to N100 `.env` without printing them.

Acceptance criteria:

- API and Web services are active with restart count zero;
- production readiness is `ready=true` and `severity=ok`;
- the new investigation reaches `COMPLETED`;
- quality score is at least `72`;
- failed and blocked job counts are both zero;
- `subfinder`, domain and URL `httpx`, `katana`, and `official_site_extractor` complete;
- source-backed organization, official URL, contact, and business-scope fields exist;
- a no-work rerun preserves terminal status and summary;
- no real target, contact value, token, private path, or production artifact is added to Git.

If the extractor can fetch but the live site no longer exposes enough public evidence, the run is reported as a content/evidence limitation rather than weakening destination controls further.

## Rollback

Rollback requires both layers:

1. remove the two N100 environment values and restart the API to restore strict behavior immediately;
2. restore the pre-deploy source archive if the code itself must be reverted.

Runtime evidence remains protected unless an operator explicitly requests data rollback.

## Residual Risk

The transparent proxy, not the application, ultimately maps an approved fake address to an upstream destination. Exact hostname authorization reduces exposure but cannot provide the same independent destination proof as real public DNS plus direct IP pinning. The long-term stronger design is a controlled egress gateway that resolves and validates upstream destinations outside the fake-IP layer.
