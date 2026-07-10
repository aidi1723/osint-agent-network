# Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all eight findings from the 2026-07-10 audit with regression tests, secure migration behavior, and verified desktop/mobile UX.

**Architecture:** Add focused authentication, agent-principal, and safe-fetch modules around the existing HTTP handler and SQLite store. Keep the dashboard architecture intact while extracting small frontend auth and graph-state helpers. Make release and router correctness deterministic through repository-level validators and evaluation fixtures.

**Tech Stack:** Python 3.11+ standard library, SQLite, React 19, TypeScript, Vite, Vitest, Playwright CLI, Bash verification scripts.

---

## Repository And File Map

`osint-agent-network` changes:

- `backend/app/core/browser_auth.py`: in-memory administrator sessions, cookie parsing, CSRF, and Origin checks.
- `backend/app/core/agent_auth.py`: agent token hashing, principal resolution, route-to-role policy, and claim checks.
- `backend/app/core/safe_http.py`: validated DNS resolution, pinned HTTP(S) connections, redirects, and limits.
- `backend/app/main.py`: route integration only; security decisions delegate to the focused modules.
- `backend/app/services/store.py`: agent credential/role migration and scoped lookup/ownership methods.
- `backend/app/agent_client.py`: registration role and one-time token workflow.
- `frontend/src/auth.ts`, `frontend/src/components/AdminLogin.tsx`: cookie-session client behavior and login surface.
- `frontend/src/main.tsx`: auth gate, credentialed requests, CSRF headers, and actionable empty state.
- `frontend/src/components/HcsTemplateGraph.tsx`, `frontend/src/graph-labels.ts`, `frontend/src/styles.css`: graph detail and label fixes.
- `scripts/public_release_check.py`: repository policy and license checks.
- `backend/tests/test_browser_auth.py`, `test_agent_identity_auth.py`, `test_safe_http.py`, `test_public_release_check.py`: backend regressions.
- `frontend/src/auth.test.ts`, `frontend/src/graph-labels.test.ts`, `frontend/scripts/test-responsive-css.ts`: frontend regressions.
- `.env.example`, deployment docs, and audit remediation record: migration and operational instructions.

`safe-agent-skills` changes:

- `src/onecode_skill_sanitizer/router.py`: specific Chinese code-review signals.
- `tests/test_router.py`, `tests/test_registry_cli.py`: routing regressions.
- `evals/router-quality.json`: real Chinese project-audit evaluation case.

## Task 1: Create The Remediation Ledger

**Files:**
- Create: `docs/SECURITY_AUDIT_REMEDIATION_2026-07-10.md`
- Reference: `docs/superpowers/specs/2026-07-10-security-hardening-design.md`

- [ ] **Step 1: Write the remediation ledger**

Create a table containing the eight IDs `SEC-01` through `UI-01`, their original
reproduction, target test, implementation status, verification evidence, and
residual risk. Start every implementation status as `planned` and update each row
immediately after its targeted green test.

- [ ] **Step 2: Verify the ledger contains every finding**

Run:

```bash
rg -n 'SEC-01|SEC-02|SEC-03|REL-01|REL-02|DEP-01|RTR-01|UI-01' \
  docs/SECURITY_AUDIT_REMEDIATION_2026-07-10.md
```

Expected: all eight IDs are present exactly once in the table.

- [ ] **Step 3: Commit the record**

```bash
git add docs/SECURITY_AUDIT_REMEDIATION_2026-07-10.md
git commit -m "docs: record security audit remediation"
```

## Task 2: Add Administrator Session Primitives

**Files:**
- Create: `backend/app/core/browser_auth.py`
- Create: `backend/tests/test_browser_auth.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing session and CSRF tests**

Add tests using an injected clock and token generator:

```python
def test_login_creates_http_only_secure_session():
    manager = BrowserSessionManager(
        admin_token="admin-secret",
        secure_cookie=True,
        now=lambda: 1000.0,
        token_urlsafe=lambda size: f"token-{size}",
    )
    result = manager.login("admin-secret")
    assert result.csrf_token == "token-32"
    assert "HttpOnly" in result.set_cookie
    assert "SameSite=Strict" in result.set_cookie
    assert "Secure" in result.set_cookie


def test_mutation_requires_matching_csrf_and_allowed_origin():
    manager, session = logged_in_manager()
    assert manager.authorize_session(
        {"Cookie": session.cookie, "X-CSRF-Token": "wrong", "Origin": "https://hcs.test"},
        allowed_origins=["https://hcs.test"],
        mutation=True,
    ) is None
```

Also cover wrong login input, expiry at eight hours, logout revocation, malformed
cookies, non-mutating session reads, and development cookies without `Secure`.

- [ ] **Step 2: Run the tests and verify RED**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_browser_auth -v
```

Expected: import failure for `app.core.browser_auth`.

- [ ] **Step 3: Implement the minimal session manager**

Implement immutable `LoginResult(csrf_token, set_cookie)` and
`BrowserPrincipal(role, session_id)` records. Implement
`BrowserSessionManager.login(supplied_token)`, `session_payload(headers)`,
`authorize_session(headers, allowed_origins, mutation)`, and `logout(headers)`.
`login` must compare the configured secret, generate separate session and CSRF
values, store their timestamps under a lock, and return only CSRF plus the cookie.
`authorize_session` must parse the cookie, expire stale sessions, and apply both
Origin and CSRF checks for mutations. `logout` must delete the matching session
and return an immediately expired cookie.

Use `secrets.token_urlsafe(32)`, `hmac.compare_digest`, a lock-protected session
dictionary, an eight-hour absolute expiry, and cookie name `osint_admin_session`.
Never include credentials in exception text.

- [ ] **Step 4: Add environment defaults**

Add:

```dotenv
OSINT_COOKIE_SECURE=false
OSINT_SESSION_TTL_SECONDS=28800
OSINT_ALLOW_LEGACY_AGENT_TOKEN=false
```

Keep development defaults usable; production readiness will enforce secure mode.

- [ ] **Step 5: Run targeted tests and verify GREEN**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_browser_auth -v
```

Expected: all browser-auth tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/browser_auth.py backend/tests/test_browser_auth.py .env.example
git commit -m "feat: add secure administrator sessions"
```

## Task 3: Integrate Browser Sessions Into The API And Frontend

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_agent_auth.py`
- Create: `frontend/src/auth.ts`
- Create: `frontend/src/auth.test.ts`
- Create: `frontend/src/components/AdminLogin.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/scripts/check-chinese-ui.mjs`

- [ ] **Step 1: Write failing HTTP auth-route tests**

Add server tests for:

```python
status, payload, headers = post_json(
    "/api/auth/login",
    {"admin_token": "admin-secret"},
    env={"APP_ENV": "production", "ADMIN_API_TOKEN": "admin-secret"},
)
self.assertEqual(status, 200)
self.assertIn("HttpOnly", headers["Set-Cookie"])
self.assertNotIn("admin-secret", json.dumps(payload))
```

Verify a cookie-authenticated POST without CSRF is 403, a matching same-origin
request succeeds, `/api/auth/session` reports authenticated state, logout revokes
the session, and existing admin/read Bearer behavior still passes.

- [ ] **Step 2: Run backend RED**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest \
  backend.tests.test_browser_auth backend.tests.test_agent_auth -v
```

Expected: auth routes return 404 or session requests remain unauthorized.

- [ ] **Step 3: Integrate auth routes and principal checks**

In `main.py`, instantiate one `BrowserSessionManager`, add login/session/logout
routes, and replace boolean-only management authorization with a helper that
accepts either valid Bearer credentials or a valid browser session. Require CSRF
and allowed Origin only when cookie authentication is used for a mutation.

Return security headers on every response:

```text
Cache-Control: no-store
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
```

- [ ] **Step 4: Run backend GREEN**

Run the command from Step 2.

Expected: all auth tests pass, including existing Bearer compatibility.

- [ ] **Step 5: Write failing frontend auth tests**

Create pure helper tests:

```typescript
it("uses credentials and csrf without a bearer token", () => {
  expect(requestOptions("POST", "csrf-1")).toEqual({
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": "csrf-1" },
  });
});

it("does not expose a Vite token contract", () => {
  expect(authEnvironmentKeys()).not.toContain("VITE_ADMIN_API_TOKEN");
});
```

- [ ] **Step 6: Run frontend RED**

```bash
cd frontend
npm test -- src/auth.test.ts
```

Expected: `auth.ts` is missing.

- [ ] **Step 7: Implement frontend auth gate**

Implement `loadSession`, `login`, `logout`, and `requestOptions` in `auth.ts`.
Remove `adminApiToken`, `jsonHeaders`, and `apiHeaders` bearer construction from
`main.tsx`. Gate the dashboard behind `AdminLogin` only when the session endpoint
reports authentication is required. Hold CSRF only in React state and send
`credentials: "include"` for API calls.

- [ ] **Step 8: Run frontend GREEN and asset canary check**

```bash
cd frontend
npm test -- src/auth.test.ts
VITE_ADMIN_API_TOKEN=audit-canary-admin-token npm run build
! rg -n 'audit-canary-admin-token' dist
```

Expected: tests pass, build passes, and the canary is absent.

- [ ] **Step 9: Commit**

```bash
git add backend/app/main.py backend/tests/test_agent_auth.py \
  frontend/src/auth.ts frontend/src/auth.test.ts frontend/src/components/AdminLogin.tsx \
  frontend/src/main.tsx frontend/src/styles.css frontend/scripts/check-chinese-ui.mjs
git commit -m "feat: replace browser bearer token with sessions"
```

## Task 4: Add Per-Agent Credentials And Store Migration

**Files:**
- Create: `backend/app/core/agent_auth.py`
- Create: `backend/tests/test_agent_identity_auth.py`
- Modify: `backend/app/services/store.py`
- Modify: `backend/tests/test_store_dedup.py`

- [ ] **Step 1: Write failing credential-store tests**

Test both `MemoryStore` and `SQLiteStore`:

```python
registration = store.register_agent(
    agent_name="reader-1",
    agent_type="codex",
    capabilities=["company"],
    role_tier="reader",
)
self.assertIn("agent_token", registration)
self.assertNotIn("agent_token", store.list_agents()[0])
self.assertIsNotNone(store.resolve_agent_token(registration["agent_token"]))
self.assertIsNone(store.resolve_agent_token("wrong"))
```

Verify the database stores a 64-character hash instead of the plaintext token,
rotation invalidates the old token, invalid tiers fail, and migration is
idempotent for an existing database.

- [ ] **Step 2: Run store RED**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest \
  backend.tests.test_agent_identity_auth backend.tests.test_store_dedup -v
```

Expected: `role_tier`, `agent_token`, and lookup methods are missing.

- [ ] **Step 3: Implement agent credential records**

Extend the agent model/table with `role_tier`, `token_hash`, `token_created_at`,
and `disabled_at`. Add:

```python
def hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
```

Add `resolve_agent_token(token)` to hash the input and query a non-disabled agent,
`rotate_agent_token(agent_id)` to replace the stored hash and return the new token
once, and `agent_has_investigation_access(agent_id, investigation_id,
required_tier)` to compare role tier and require either the investigation claim or
a matching claimed job.

Registration returns a dictionary with a one-time `agent_token`; all normal row
serializers omit `token_hash` and plaintext tokens.

- [ ] **Step 4: Run store GREEN**

Run the command from Step 2.

Expected: all credential and migration cases pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/agent_auth.py backend/app/services/store.py \
  backend/tests/test_agent_identity_auth.py backend/tests/test_store_dedup.py
git commit -m "feat: add scoped agent credentials"
```

## Task 5: Enforce Agent Route Roles And Ownership

**Files:**
- Modify: `backend/app/core/agent_auth.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/agent_client.py`
- Modify: `backend/tests/test_agent_identity_auth.py`
- Modify: `backend/tests/test_agent_client.py`
- Modify: `backend/tests/test_agent_protocol.py`

- [ ] **Step 1: Write failing authorization matrix tests**

Build registered reader, verifier, reporter, and tool principals. Verify:

```python
self.assertEqual(post_as(reader, "/api/agent/facts", fact_payload).status, 403)
self.assertEqual(post_as(verifier, "/api/agent/facts", fact_payload).status, 201)
self.assertEqual(post_as(reporter, complete_path, complete_payload).status, 200)
self.assertEqual(post_as(unregistered, complete_path, complete_payload).status, 401)
self.assertEqual(
    post_as(reporter, complete_path, {**complete_payload, "agent_id": "forged"}).status,
    403,
)
```

Add claim-ownership tests: a reporter with no claimed matching job receives 409;
the reporter that owns the matching job succeeds. Verify legacy shared token is
rejected in production unless `OSINT_ALLOW_LEGACY_AGENT_TOKEN=true`.

- [ ] **Step 2: Run authorization RED**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest \
  backend.tests.test_agent_identity_auth backend.tests.test_agent_protocol -v
```

Expected: shared-token handlers accept at least one wrong-role or forged request.

- [ ] **Step 3: Implement `AgentPrincipal` route enforcement**

Define:

```python
@dataclass(frozen=True)
class AgentPrincipal:
    agent_id: str
    role_tier: str
    capabilities: Sequence[str]

AGENT_ACTION_TIERS = {
    "entities": {"reader"},
    "evidence": {"reader"},
    "evidence_records": {"reader"},
    "relationships": {"reader"},
    "facts": {"verifier"},
    "hypotheses": {"verifier"},
    "score_hypotheses": {"verifier"},
    "complete_task": {"reporter"},
}
```

Resolve the bearer token once at the start of `/api/agent/*`, attach the
principal for the request, reject body identity mismatches, and pass the
principal ID to store mutations. Check matching task/job claims before mutation.

- [ ] **Step 4: Update CLI registration and token usage**

Add required `--role-tier` to `register`, use an administrator registration token
for registration, and print the one-time agent credential without writing it to
disk. Update help text to use the issued token for claim/write commands.

- [ ] **Step 5: Run targeted GREEN**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest \
  backend.tests.test_agent_identity_auth backend.tests.test_agent_client \
  backend.tests.test_agent_protocol -v
```

Expected: all new and existing protocol tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/agent_auth.py backend/app/main.py backend/app/agent_client.py \
  backend/tests/test_agent_identity_auth.py backend/tests/test_agent_client.py \
  backend/tests/test_agent_protocol.py
git commit -m "fix: enforce agent identity and role boundaries"
```

## Task 6: Implement SSRF-Safe Official-Site Fetching

**Files:**
- Create: `backend/app/core/safe_http.py`
- Create: `backend/tests/test_safe_http.py`
- Modify: `backend/app/core/normalization.py`
- Modify: `backend/app/tools/official_site_extractor.py`
- Modify: `backend/tests/test_tool_adapters.py`

- [ ] **Step 1: Write failing address-policy tests**

Cover literals and resolved addresses:

```python
for url in (
    "http://127.1/",
    "http://2130706433/",
    "http://10.0.0.1/",
    "http://172.16.0.1/",
    "http://192.168.1.1/",
    "http://169.254.169.254/",
    "http://[::1]/",
    "http://[fc00::1]/",
):
    with self.subTest(url=url):
        with self.assertRaises(BlockedNetworkTarget):
            validate_public_url(url, resolver=fake_resolver)
```

Test a hostname resolving to mixed public/private answers is rejected, ports
other than 80/443 are rejected, userinfo is rejected, and a public address is
accepted.

- [ ] **Step 2: Write failing redirect and limit tests**

Use injected fake connector responses to test safe public success, redirect to
private target rejection, five-hop limit, timeout mapping, and maximum body size.
Assert the fake connector is never called for blocked URLs.

- [ ] **Step 3: Run SSRF RED**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest backend.tests.test_safe_http -v
```

Expected: `app.core.safe_http` is missing.

- [ ] **Step 4: Implement resolver and pinned connectors**

Implement:

```python
class SafeHttpError(Exception):
    pass


class InvalidHttpTarget(SafeHttpError):
    pass


class BlockedNetworkTarget(SafeHttpError):
    pass


class RedirectLimitExceeded(SafeHttpError):
    pass


class ResponseTooLarge(SafeHttpError):
    pass
```

Implement `validate_public_url(url, resolver=socket.getaddrinfo)` to return a
`ValidatedTarget` containing scheme, original hostname, validated IPs, port, and
request path. Implement `safe_fetch(url, timeout_seconds, max_bytes,
max_redirects=5, resolver=socket.getaddrinfo, connector=connect_pinned)` to call
that validator before every connection, request through the injected connector,
read at most `max_bytes + 1`, and repeat on redirect until success or the limit.

Use custom `HTTPConnection`/`HTTPSConnection` subclasses that connect to the
validated IP while retaining original Host and TLS `server_hostname`. Disable
automatic redirects and validate each `Location`.

- [ ] **Step 5: Integrate extractor and early normalization**

Replace `urllib.request.urlopen` in `OfficialSiteExtractorAdapter.run` with
`safe_fetch`. Map `SafeHttpError` to a stable failed `ToolRunResult`. Extend
`normalize_target` to reject private IP literals with `ipaddress` while leaving
DNS enforcement in `safe_http`.

- [ ] **Step 6: Run targeted GREEN and original reproduction**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest \
  backend.tests.test_safe_http backend.tests.test_core backend.tests.test_tool_adapters -v
PYTHONPATH=backend backend/.venv/bin/python -c \
  "from app.core.normalization import normalize_target; normalize_target('url','http://127.1/')"
```

Expected: tests pass; the final command exits non-zero with a private URL error
before any connection.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/safe_http.py backend/app/core/normalization.py \
  backend/app/tools/official_site_extractor.py backend/tests/test_safe_http.py \
  backend/tests/test_tool_adapters.py
git commit -m "fix: block private-network official site fetches"
```

## Task 7: Strengthen Public Release And Production Readiness Gates

**Files:**
- Modify: `scripts/public_release_check.py`
- Modify: `backend/tests/test_public_release_check.py`
- Modify: `scripts/production_readiness.py`
- Modify: `backend/tests/test_production_readiness.py`
- Modify: `backend/pyproject.toml`
- Modify: `docs/PUBLIC_REPOSITORY_MAINTENANCE.md`
- Modify during final integration only: `PROJECT_CLOSURE_MAINTENANCE_LOG.md`

- [ ] **Step 1: Write failing release-policy tests**

Add temporary fixture repositories for backend license mismatch, `/home/alice/`
and `/Users/alice/` paths, `192.168.1.20`, a credential assignment, tracked
SQLite/runtime artifacts, documentation IP `192.0.2.10`, generic `/opt` paths,
and placeholder tokens. Assert blockers contain stable IDs and relative paths.

- [ ] **Step 2: Run release RED**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m unittest \
  backend.tests.test_public_release_check backend.tests.test_production_readiness -v
```

Expected: private-path and backend-license fixtures incorrectly pass.

- [ ] **Step 3: Implement deterministic repository scanning**

Add an immutable `ReleaseFinding(rule_id, path, line, summary)` record. Implement
`tracked_files(root)` to use NUL-delimited `git ls-files` with a sorted filesystem
fallback, `scan_public_text(relative_path, text)` to return findings for every
policy pattern after allowlist checks, and `evaluate_public_release(root)` to
combine file findings with all three license declarations into the existing JSON
result.

Use `git ls-files -z` when `.git` is present, filesystem fallback for fixtures,
UTF-8 text only, explicit allowlists for documentation networks/placeholders,
and non-zero readiness when findings exist. Include backend `pyproject.toml` in
license consistency.

- [ ] **Step 4: Enforce secure production auth settings**

Update production readiness to block missing admin/read tokens, insecure cookies,
or legacy shared agent-token mode. Do not require a global agent token after
per-agent credentials are implemented.

- [ ] **Step 5: Align GPL metadata**

Change:

```toml
license = "GPL-3.0-only"
```

Update maintenance policy documentation with the automated rule IDs.

- [ ] **Step 6: Run targeted GREEN**

Run the command from Step 2 and:

```bash
python3 scripts/public_release_check.py
```

Expected: all tests pass and the clean feature worktree reports ready.

- [ ] **Step 7: Commit**

```bash
git add scripts/public_release_check.py scripts/production_readiness.py \
  backend/tests/test_public_release_check.py backend/tests/test_production_readiness.py \
  backend/pyproject.toml docs/PUBLIC_REPOSITORY_MAINTENANCE.md
git commit -m "fix: enforce public release security policy"
```

## Task 8: Update Frontend Build Dependencies

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: Record the pre-update audit failure**

```bash
cd frontend
npm audit --json --registry=https://registry.npmjs.org
```

Expected: high advisories include Vite and/or affected transitive dependencies.

- [ ] **Step 2: Update only affected build packages**

```bash
npm install --save-dev vite@latest @vitejs/plugin-react@latest \
  --registry=https://registry.npmjs.org
```

Review package and lockfile changes; do not accept unrelated major package
changes and do not use `--force`.

- [ ] **Step 3: Verify audits, tests, and build**

```bash
npm audit --omit=dev --json --registry=https://registry.npmjs.org
npm audit --json --registry=https://registry.npmjs.org
npm test
npm run build
```

Expected: both audits contain zero high/critical findings; tests and build pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "build: update vulnerable frontend tooling"
```

## Task 9: Repair Chinese Code-Review Routing In `safe-agent-skills`

**Files:**
- Modify: `src/onecode_skill_sanitizer/router.py`
- Modify: `tests/test_router.py`
- Modify: `tests/test_registry_cli.py`
- Modify: `evals/router-quality.json`

- [ ] **Step 1: Create the isolated router worktree**

```bash
cd /Users/aidi/情报官/safe-agent-skills
git worktree add /tmp/safe-agent-security-hardening -b fix/chinese-code-review-routing
```

Expected: current dirty `.gitignore` remains untouched.

- [ ] **Step 2: Write failing router unit and evaluation cases**

Add:

```python
def test_build_task_profile_detects_chinese_project_audit(self):
    profile = build_task_profile(
        "审核当前目录软件项目，检查代码质量、安全性、测试、构建与可维护性"
    )
    self.assertEqual(profile["task_type"], "code_review")
```

Add the same request to `evals/router-quality.json` with expected scenario
`code-review-hardening`. Add negative cases for `审核 UI 响应式设计` and
`审核社媒文案` to prove the bare word is not overmatched.

- [ ] **Step 3: Run router RED**

```bash
cd /tmp/safe-agent-security-hardening
PYTHONPATH=src python3 -m unittest tests.test_router -v
PYTHONPATH=src python3 -m onecode_skill_sanitizer router-eval \
  --eval evals/router-quality.json --registry catalog --bundles bundles/index.json
```

Expected: the Chinese project-audit case selects `website_build` before the fix.

- [ ] **Step 4: Add specific compound signals**

Extend only the `code_review` profile signals with:

```python
"代码审核", "项目审核", "安全审计", "代码质量", "可维护性", "项目安全性"
```

Do not add bare `审核` or change tie-breaking globally.

- [ ] **Step 5: Run router GREEN and full verification**

```bash
PYTHONPATH=src python3 -m unittest tests.test_router tests.test_registry_cli -v
bash scripts/verify.sh
```

Expected: targeted and full safe-agent tests pass.

- [ ] **Step 6: Commit in the router repository**

```bash
git add src/onecode_skill_sanitizer/router.py tests/test_router.py \
  tests/test_registry_cli.py evals/router-quality.json
git commit -m "fix: route Chinese project audits to code review"
```

## Task 10: Fix Graph Details, Labels, And Empty State

**Files:**
- Create: `frontend/src/graph-labels.ts`
- Create: `frontend/src/graph-labels.test.ts`
- Modify: `frontend/src/components/HcsTemplateGraph.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/scripts/test-responsive-css.ts`
- Modify: `frontend/scripts/check-chinese-ui.mjs`

- [ ] **Step 1: Write failing compact-label tests**

```typescript
it("compacts long graph labels without losing the full title", () => {
  expect(compactGraphLabel("Example Manufacturing Company", 12)).toBe("Example Man…");
  expect(compactGraphLabel("短名称", 12)).toBe("短名称");
});
```

- [ ] **Step 2: Write failing graph-state and responsive checks**

Extract and test `nextSelectedNode(current, clicked)` so initial state is null,
first activation opens, and repeated activation closes. Extend responsive CSS
checks to require `.hcs-node-detail { position: static; }` in the 620px block and
to forbid the detail from occupying the SVG overlay layer on mobile.

- [ ] **Step 3: Run UI RED**

```bash
cd frontend
npm test -- src/graph-labels.test.ts
node --experimental-strip-types scripts/test-responsive-css.ts
```

Expected: helper file is missing and mobile detail remains absolute.

- [ ] **Step 4: Implement graph interaction**

Use `useState<string | null>(null)`, toggle selection, render details only when a
node is selected, and add a Lucide `X` icon button with `aria-label="关闭节点详情"`.
Use `compactGraphLabel` in fixed SVG nodes and include `<title>` with full values.

- [ ] **Step 5: Implement mobile detail flow and empty state**

At 620px and below, set detail position to static and place it after the scrollable
graph viewport. When `selected` is absent, render an actionable empty-state band
and set the operations `<details>` to `defaultOpen={!selected}` so task creation is
visible without an extra click.

- [ ] **Step 6: Run targeted GREEN**

```bash
npm test -- src/graph-labels.test.ts
node --experimental-strip-types scripts/test-responsive-css.ts
npm run check:ui-copy
npm run build
```

Expected: all targeted checks and production build pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/graph-labels.ts frontend/src/graph-labels.test.ts \
  frontend/src/components/HcsTemplateGraph.tsx frontend/src/main.tsx \
  frontend/src/styles.css frontend/scripts/test-responsive-css.ts \
  frontend/scripts/check-chinese-ui.mjs
git commit -m "fix: make graph details responsive and actionable"
```

## Task 11: Update Operations Documentation And Remediation Status

**Files:**
- Modify: `README.md`
- Modify: `docs/AGENT_PROTOCOL.md`
- Modify: `docs/PROJECT_PACKAGE.md`
- Modify: `docs/PUBLIC_RELEASE_READINESS.md`
- Modify: `docs/SECURITY_AUDIT_REMEDIATION_2026-07-10.md`

- [ ] **Step 1: Document browser migration**

Remove instructions that build `VITE_ADMIN_API_TOKEN`. Document login, TLS
termination, secure cookies, local development override, logout-on-restart, and
Bearer compatibility for non-browser administration.

- [ ] **Step 2: Document agent migration**

Document required `role_tier`, one-time token handling, re-registration/rotation,
claim ownership, 401/403/409 meanings, and disabled production legacy mode.

- [ ] **Step 3: Mark all remediation rows implemented**

For every finding, record the regression test name, implementation commit, and
targeted green command. Do not mark final verification complete yet.

- [ ] **Step 4: Run documentation and release checks**

```bash
python3 scripts/check_agents.py
python3 scripts/public_release_check.py
rg -n 'VITE_ADMIN_API_TOKEN=<same-value|frontend.*management Token' README.md docs
```

Expected: governance and release checks pass; obsolete browser-token instructions
have no matches.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/AGENT_PROTOCOL.md docs/PROJECT_PACKAGE.md \
  docs/PUBLIC_RELEASE_READINESS.md docs/SECURITY_AUDIT_REMEDIATION_2026-07-10.md
git commit -m "docs: document hardened authentication rollout"
```

## Task 12: Full Verification And Workspace Integration

**Files:**
- Modify after evidence exists: `docs/SECURITY_AUDIT_REMEDIATION_2026-07-10.md`
- Preserve user changes: `/Users/aidi/情报官/osint-agent-network/PROJECT_CLOSURE_MAINTENANCE_LOG.md`
- Preserve user changes: `/Users/aidi/情报官/safe-agent-skills/.gitignore`

- [ ] **Step 1: Run full OSINT verification**

```bash
cd /Users/aidi/情报官/osint-agent-network/.worktrees/security-hardening
bash scripts/verify.sh
```

Expected: all backend, regression, frontend, and build checks pass.

- [ ] **Step 2: Run supply-chain audits**

```bash
cd frontend
npm audit --omit=dev --json --registry=https://registry.npmjs.org
npm audit --json --registry=https://registry.npmjs.org
```

Expected: zero high and zero critical advisories in both outputs.

- [ ] **Step 3: Run security reproductions**

Verify an unregistered agent, forged ID, reader fact write, and reporter without a
claim are rejected. Verify `127.1`, private IPv4, private IPv6, private DNS result,
and redirect-to-private cases invoke no connector. Build with a canary Vite token
and verify the token is absent from `dist`.

- [ ] **Step 4: Run Playwright verification**

Start API and frontend against a temporary database. Use Playwright CLI at
1440x1000 and 390x844. Assert login, empty-state create action, node detail open
and close, no horizontal document overflow, no console warnings, and screenshot
the selected graph state at both viewports.

- [ ] **Step 5: Verify the router repository**

```bash
cd /tmp/safe-agent-security-hardening
bash scripts/verify.sh
```

Expected: all tests, schema, registry, and router evaluations pass.

- [ ] **Step 6: Record final evidence**

Update every remediation ledger row to `verified` with exact commands, counts,
and screenshot paths. Run `git diff --check` and inspect both repository diffs.

- [ ] **Step 7: Integrate without overwriting user changes**

Merge the two feature branches into their original repositories only after clean
verification. In the original OSINT worktree, replace only personal-path values
inside the user's modified maintenance log with `<production-path>`; preserve all
other user edits. Confirm final status still shows the user's safe-agent
`.gitignore` additions and the maintained OSINT log changes.

- [ ] **Step 8: Run final verification in the original workspaces**

```bash
cd /Users/aidi/情报官/osint-agent-network && bash scripts/verify.sh
cd /Users/aidi/情报官/safe-agent-skills && bash scripts/verify.sh
```

Expected: both original workspaces pass after integration.

- [ ] **Step 9: Commit the final evidence update**

```bash
git add docs/SECURITY_AUDIT_REMEDIATION_2026-07-10.md
git commit -m "docs: close security audit remediation"
```
