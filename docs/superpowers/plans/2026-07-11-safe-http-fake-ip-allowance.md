# Safe HTTP Fake-IP Allowance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a default-off exact-host plus `198.18.0.0/15`-subnet allowance for the official-site safe fetch path, deploy it to N100, and rerun the anonymized real-search acceptance test.

**Architecture:** Parse two strict environment variables into an immutable allowance object. `safe_fetch` passes that object through every URL and redirect validation; only DNS hostnames that exactly match the configured host set may use configured IPv4 subnets contained by `198.18.0.0/15`. The official-site adapter is the only consumer enabled in this change, while all other callers retain strict defaults.

**Tech Stack:** Python 3.11+, `ipaddress`, `socket`, `unittest`, systemd user services, SSH, rsync, SQLite-backed worker queue, React/Vite.

---

### Task 1: Add RED Tests For Strict Fake-IP Configuration

**Files:**
- Modify: `backend/tests/test_safe_http.py`

- [ ] **Step 1: Add imports and configuration parser tests**

Import `FakeIpAllowance`, `InvalidFakeIpConfiguration`, and `fake_ip_allowance_from_env`. Add tests that specify the public API:

```python
def test_empty_fake_ip_configuration_preserves_strict_default(self):
    allowance = fake_ip_allowance_from_env({})
    self.assertEqual(allowance, FakeIpAllowance())
    with self.assertRaises(BlockedNetworkTarget):
        validate_public_url(
            "https://example.com/",
            resolver=resolver_for("198.18.100.99"),
            fake_ip_allowance=allowance,
        )

def test_parses_exact_hosts_and_contained_fake_ip_subnets(self):
    allowance = fake_ip_allowance_from_env({
        "OSINT_SAFE_HTTP_FAKE_IP_CIDRS": "198.18.0.0/16, 198.19.0.0/16",
        "OSINT_SAFE_HTTP_FAKE_IP_HOSTS": "Example.COM., www.example.com",
    })
    self.assertEqual(
        tuple(str(network) for network in allowance.networks),
        ("198.18.0.0/16", "198.19.0.0/16"),
    )
    self.assertEqual(allowance.hosts, frozenset({"example.com", "www.example.com"}))

def test_invalid_fake_ip_configuration_fails_closed(self):
    invalid = (
        {"OSINT_SAFE_HTTP_FAKE_IP_CIDRS": "198.18.0.0/14", "OSINT_SAFE_HTTP_FAKE_IP_HOSTS": "example.com"},
        {"OSINT_SAFE_HTTP_FAKE_IP_CIDRS": "127.0.0.0/8", "OSINT_SAFE_HTTP_FAKE_IP_HOSTS": "example.com"},
        {"OSINT_SAFE_HTTP_FAKE_IP_CIDRS": "2001:db8::/32", "OSINT_SAFE_HTTP_FAKE_IP_HOSTS": "example.com"},
        {"OSINT_SAFE_HTTP_FAKE_IP_CIDRS": "198.18.0.0/15", "OSINT_SAFE_HTTP_FAKE_IP_HOSTS": "*.example.com"},
        {"OSINT_SAFE_HTTP_FAKE_IP_CIDRS": "198.18.0.0/15", "OSINT_SAFE_HTTP_FAKE_IP_HOSTS": "https://example.com"},
        {"OSINT_SAFE_HTTP_FAKE_IP_CIDRS": "198.18.0.0/15", "OSINT_SAFE_HTTP_FAKE_IP_HOSTS": "198.18.100.99"},
        {"OSINT_SAFE_HTTP_FAKE_IP_CIDRS": "198.18.0.0/15", "OSINT_SAFE_HTTP_FAKE_IP_HOSTS": ""},
    )
    for environ in invalid:
        with self.subTest(environ=environ), self.assertRaises(InvalidFakeIpConfiguration):
            fake_ip_allowance_from_env(environ)
```

- [ ] **Step 2: Run the targeted tests and verify RED**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_safe_http.SafeHttpValidationTests
```

Expected: import failure because the new allowance API does not exist.

### Task 2: Add RED Tests For Host-And-CIDR Validation

**Files:**
- Modify: `backend/tests/test_safe_http.py`

- [ ] **Step 1: Add a test helper and exact validation tests**

Add:

```python
def fake_ip_allowance(*hosts):
    return fake_ip_allowance_from_env({
        "OSINT_SAFE_HTTP_FAKE_IP_CIDRS": "198.18.0.0/15",
        "OSINT_SAFE_HTTP_FAKE_IP_HOSTS": ",".join(hosts),
    })
```

Add tests:

```python
def test_accepts_fake_ip_only_for_exact_allowed_dns_hostname(self):
    target = validate_public_url(
        "https://example.com/",
        resolver=resolver_for("198.18.100.99"),
        fake_ip_allowance=fake_ip_allowance("example.com"),
    )
    self.assertEqual(target.validated_ips, ("198.18.100.99",))

def test_rejects_fake_ip_when_hostname_is_not_allowlisted(self):
    with self.assertRaises(BlockedNetworkTarget):
        validate_public_url(
            "https://other.example.com/",
            resolver=resolver_for("198.18.100.99"),
            fake_ip_allowance=fake_ip_allowance("example.com"),
        )

def test_rejects_direct_fake_ip_literal_even_when_network_is_configured(self):
    with self.assertRaises(BlockedNetworkTarget):
        validate_public_url(
            "https://198.18.100.99/",
            fake_ip_allowance=fake_ip_allowance("example.com"),
        )

def test_rejects_mixed_allowed_fake_and_private_answers(self):
    with self.assertRaises(BlockedNetworkTarget):
        validate_public_url(
            "https://example.com/",
            resolver=resolver_for("198.18.100.99", "::1"),
            fake_ip_allowance=fake_ip_allowance("example.com"),
        )
```

- [ ] **Step 2: Add redirect revalidation tests**

Use the existing fake connector pattern to assert that an initial listed host redirecting to an unlisted fake-IP host raises `BlockedNetworkTarget`, and that listing both exact hosts returns the final bounded response. Verify connector calls remain pinned to the resolved fake address and retain the original hostname.

- [ ] **Step 3: Run the targeted tests and verify RED**

Run the same `SafeHttpValidationTests` command. Expected: tests fail because `validate_public_url` and `safe_fetch` do not accept `fake_ip_allowance`.

### Task 3: Implement The Minimal Safe HTTP Allowance

**Files:**
- Modify: `backend/app/core/safe_http.py`
- Test: `backend/tests/test_safe_http.py`

- [ ] **Step 1: Add the immutable value and strict parser**

Add an exception, immutable value, constants, and parser:

```python
class InvalidFakeIpConfiguration(SafeHttpError):
    pass

@dataclass(frozen=True)
class FakeIpAllowance:
    networks: tuple[ipaddress.IPv4Network, ...] = ()
    hosts: frozenset[str] = frozenset()

_FAKE_IP_SUPERNET = ipaddress.ip_network("198.18.0.0/15")

def fake_ip_allowance_from_env(environ: Mapping[str, str] | None = None) -> FakeIpAllowance:
    environ = os.environ if environ is None else environ
    raw_cidrs = str(environ.get("OSINT_SAFE_HTTP_FAKE_IP_CIDRS", "")).strip()
    raw_hosts = str(environ.get("OSINT_SAFE_HTTP_FAKE_IP_HOSTS", "")).strip()
    if not raw_cidrs and not raw_hosts:
        return FakeIpAllowance()
    if not raw_cidrs or not raw_hosts:
        raise InvalidFakeIpConfiguration("invalid fake-IP allowance configuration")
    # Parse every comma-separated value, normalize exact IDNA hostnames, reject
    # literals/wildcards/URL syntax, and require every IPv4 subnet to be a
    # subnet of _FAKE_IP_SUPERNET. Any invalid item raises the same message.
```

Import `os`. Reuse `_valid_hostname` and `_literal_address`; do not introduce URL or wildcard host matching.

- [ ] **Step 2: Extend validation without changing defaults**

Add the optional keyword argument to both functions:

```python
def validate_public_url(
    url: str,
    resolver: Resolver = socket.getaddrinfo,
    *,
    deadline: float | None = None,
    fake_ip_allowance: FakeIpAllowance | None = None,
) -> ValidatedTarget:
```

For literals, retain the existing global-address test regardless of allowance. For DNS answers, accept an address when `_is_global_address(address)` is true, or when the normalized hostname is an exact configured host and the address belongs to a configured fake-IP subnet. Reject if any answer fails.

- [ ] **Step 3: Revalidate every redirect**

Add `fake_ip_allowance` to `safe_fetch` and pass it to every `validate_public_url` call inside the redirect loop. Do not change redirect count, timeout, response size, header validation, or connection pinning.

- [ ] **Step 4: Run targeted safe HTTP tests and verify GREEN**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_safe_http
```

Expected: all safe HTTP tests pass.

- [ ] **Step 5: Commit the safe HTTP behavior**

```bash
git add backend/app/core/safe_http.py backend/tests/test_safe_http.py
git commit -m "feat: allow controlled fake-ip fetches"
```

### Task 4: Enable Only Official-Site Extraction

**Files:**
- Modify: `backend/tests/test_tool_adapters.py`
- Modify: `backend/app/tools/official_site_extractor.py`

- [ ] **Step 1: Write the failing adapter test**

Patch `fake_ip_allowance_from_env` to return a sentinel allowance and patch `safe_fetch`. Run the adapter, then assert:

```python
safe_fetch_mock.assert_called_once_with(
    "https://example.com/",
    timeout_seconds=5,
    max_bytes=MAX_HTML_BYTES,
    headers={
        "User-Agent": "osint-agent-network/1.0 (+official-site-extractor)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
    },
    fake_ip_allowance=allowance,
)
```

Also add a test where configuration parsing raises `InvalidFakeIpConfiguration`; assert return code `1`, empty artifact, and exact sanitized error `official site fetch failed`.

- [ ] **Step 2: Run the adapter tests and verify RED**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_tool_adapters.OfficialSiteExtractorAdapterTests
```

Expected: failure because the adapter does not load or pass the allowance.

- [ ] **Step 3: Implement the minimal adapter integration**

Import `fake_ip_allowance_from_env`, load it immediately before the fetch, and pass it as `fake_ip_allowance=allowance`. Keep the existing `except (NormalizationError, SafeHttpError)` block so invalid configuration fails closed with sanitized output.

- [ ] **Step 4: Run adapter and safe HTTP tests and verify GREEN**

Run both targeted unittest modules. Expected: all pass.

- [ ] **Step 5: Commit adapter integration**

```bash
git add backend/app/tools/official_site_extractor.py backend/tests/test_tool_adapters.py
git commit -m "feat: enable fake-ip allowance for official sites"
```

### Task 5: Document Configuration And Security Boundary

**Files:**
- Modify: `.env.example`
- Modify: `docs/N100_DEPLOYMENT_RUNBOOK.md`
- Modify: `backend/tests/test_release_artifacts.py`

- [ ] **Step 1: Write the failing release-artifact test**

Assert `.env.example` contains empty assignments for both variables and the runbook states exact-host matching, `198.18.0.0/15` containment, default-off behavior, literal-IP rejection, and per-redirect revalidation.

- [ ] **Step 2: Run release-artifact tests and verify RED**

```bash
python3 -m unittest backend.tests.test_release_artifacts
```

Expected: failure because the variables and runbook guidance are absent.

- [ ] **Step 3: Add public-safe configuration documentation**

Add:

```text
OSINT_SAFE_HTTP_FAKE_IP_CIDRS=
OSINT_SAFE_HTTP_FAKE_IP_HOSTS=
```

Document that both variables are required to enable the exception, CIDRs are restricted to subnets of `198.18.0.0/15`, hosts are exact matches, literals remain blocked, redirects are rechecked, and post-fetch cleaning cannot replace destination controls. Do not add real hostnames.

- [ ] **Step 4: Run release tests and public scan**

```bash
python3 -m unittest backend.tests.test_release_artifacts
python3 scripts/public_release_check.py
git diff --check
```

Expected: all exit `0`, no blockers.

- [ ] **Step 5: Commit documentation**

```bash
git add .env.example docs/N100_DEPLOYMENT_RUNBOOK.md backend/tests/test_release_artifacts.py
git commit -m "docs: describe controlled fake-ip allowance"
```

### Task 6: Run Full Local Verification And Integrate

**Files:**
- Verify: all changed files

- [ ] **Step 1: Run the full verification gate**

```bash
bash scripts/verify.sh
```

Expected: backend suite, four regression cases, frontend helper checks, 45 frontend tests, and Vite 8.1.4 build pass.

- [ ] **Step 2: Review scope and secrets**

Run `git status --short`, `git diff --check`, and `python3 scripts/public_release_check.py`. Confirm the operator-maintained closure log remains outside all commits and no target hostname or production address is present.

- [ ] **Step 3: Merge the isolated implementation branch into local `main`**

Use the finishing-development workflow, perform a non-interactive merge after verification, and rerun `git status --short`. Preserve the user's existing maintenance-log modification.

### Task 7: Back Up And Deploy To N100

**Files:**
- Deploy: tracked source files changed by Tasks 3-5
- Preserve remotely: `.env`, `data/`, `reports/`, artifacts, frontend build output until rebuilt

- [ ] **Step 1: Create new timestamped backups**

Back up the N100 runtime, source tree, and `.env` without printing contents. Confirm backup paths exist.

- [ ] **Step 2: Derive the confidential exact-host list on N100**

Select the prior production target in remote process memory. Combine its normalized hostname with redirect hostnames observed in the latest successful `httpx`/`katana` records. Validate that every item is an exact DNS hostname; do not print or export the values.

- [ ] **Step 3: Update only the two environment keys**

Set `OSINT_SAFE_HTTP_FAKE_IP_CIDRS=198.18.0.0/15` and set `OSINT_SAFE_HTTP_FAKE_IP_HOSTS` to the derived comma-separated exact host list. Preserve all other keys byte-for-byte and report only whether each key is configured.

- [ ] **Step 4: Synchronize source without deleting runtime state**

Use `rsync -az` with the established exclusions for Git metadata, `.env`, data, reports, artifacts, frontend environment, dependencies, build output, Playwright output, and the operator-maintained closure log.

- [ ] **Step 5: Run remote targeted and full applicable verification**

Run safe HTTP, adapter, and release-artifact tests, then the backend suite, regression smoke, frontend tests, and build. Run the public release scanner only against the local Git source tree, not the Git-less production runtime tree.

- [ ] **Step 6: Restart and verify services**

Restart both systemd user services. Poll until the API binds, then run health and production readiness. Require both services `active`, restart count zero, `ready=true`, and `severity=ok`.

### Task 8: Rerun The Real Search And Close Evidence

**Files:**
- Modify: `docs/N100_HARDENED_DEPLOYMENT_REAL_SEARCH_CLOSURE_2026-07-11.md`

- [ ] **Step 1: Create a fresh bounded investigation**

Use the previous successful target only in N100 process memory. Create a new quick investigation, run at most six jobs per round, and poll the persistent worker queue until idle before each next round.

- [ ] **Step 2: Capture anonymized acceptance metrics**

Record status, score, job counts, tool status counts, evidence kinds, and source-backed field-type counts. Never print target values, entity values, contacts, tokens, or paths.

- [ ] **Step 3: Verify empty-rerun stability**

After terminal completion, enqueue one no-work bounded run. Require status and summary hashes to remain unchanged.

- [ ] **Step 4: Compare against every acceptance criterion**

Classify `COMPLETED`, score at least `72`, zero failed/blocked jobs, completed official-site chain, source-backed organization/URL/contact/business fields, and stable rerun as met or not met. Report live-site evidence limitations honestly rather than expanding the network exception.

- [ ] **Step 5: Update, scan, and commit the closure report**

Update only public-safe evidence and residual risk. Run `git diff --check`, release-artifact tests, public scan, and relevant full verification. Commit the report without staging the user maintenance log.

- [ ] **Step 6: Synchronize the final report and compare checksums**

Sync the report to N100, compare local and remote SHA-256 values, and perform one final service/health/readiness check.
