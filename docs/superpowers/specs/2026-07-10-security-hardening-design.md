# Security Hardening Design

## Purpose

Resolve the eight findings from the 2026-07-10 workspace audit across
`osint-agent-network` and `safe-agent-skills` without changing investigation
workflows, report semantics, or the existing single-operator deployment model.

The target deployment is one trusted administrator operating the web console on
an internal network. External agents remain supported, but each agent must have
its own scoped credential. Production browser traffic must terminate TLS before
reaching the application.

## Audit Record

| ID | Severity | Finding | Required outcome |
| --- | --- | --- | --- |
| SEC-01 | High | `VITE_ADMIN_API_TOKEN` exposes the management token in browser assets | Browser assets contain no long-lived API credential |
| SEC-02 | High | External agents share one bearer token and can forge `agent_id` or role | Every agent request is identity-bound, role-checked, and ownership-checked |
| SEC-03 | High | URL validation permits private-network SSRF variants and unsafe redirects | User-derived HTTP requests use a pinned, redirect-aware safe fetcher |
| REL-01 | Medium | Public release checks miss personal paths and other policy blockers | Release verification deterministically rejects current policy blockers |
| REL-02 | Medium | Backend package metadata says `Proprietary` while the repository is GPLv3 | All package and repository license declarations use `GPL-3.0-only` |
| DEP-01 | Medium | Vite and transitive build dependencies have fixable advisories | Full npm audit has no high or critical advisories |
| RTR-01 | Medium | Chinese project-audit requests route to the website launch scenario | Representative Chinese audit requests route to code review |
| UI-01 | Medium | Graph details obscure the graph, labels overflow, and the empty state is passive | Desktop and mobile graph states remain readable and the empty state is actionable |

## Scope Boundaries

### In scope

- Browser login, session, logout, CSRF protection, and frontend auth state.
- Per-agent credentials, route permissions, and task/job ownership checks.
- Safe outbound fetching for user-derived official-site URLs.
- Public release policy enforcement and license metadata.
- Direct and transitive frontend dependency updates needed to clear high-risk advisories.
- Chinese router signals and regression evaluation.
- Graph detail behavior, compact labels, responsive layout, and empty state.
- Audit, migration, deployment, and verification documentation.

### Out of scope

- Multi-user accounts, password recovery, organization tenancy, and fine-grained
  human RBAC.
- OAuth, OIDC, SAML, or a bundled TLS certificate authority.
- Replacing the Python HTTP server or SQLite store.
- General redesign of the dashboard, graph information architecture, or report
  structure.
- Security guarantees for third-party OSINT executables outside the existing
  subprocess boundary.

## 1. Browser Authentication

### Server contract

Add a focused authentication module that owns administrator sessions. The
administrator submits the server-side `ADMIN_API_TOKEN` to
`POST /api/auth/login`. The value is compared with `hmac.compare_digest` and is
never logged, returned, persisted, or embedded in frontend assets.

Successful login creates a random, server-side session with:

- a random session ID stored only in an HttpOnly cookie;
- a random CSRF token returned in the JSON response and held only in frontend
  memory;
- creation, last-seen, and expiry timestamps;
- an administrator role;
- an eight-hour absolute lifetime.

The default production cookie is `HttpOnly; SameSite=Strict; Secure; Path=/`.
Development may set `OSINT_COOKIE_SECURE=false`; production readiness must fail
when authentication is required and secure cookies are disabled. Sessions are
in-memory by design: an API restart logs the administrator out, which is an
acceptable trade-off for a single-process, single-administrator deployment.

`GET /api/auth/session` returns the authenticated state and a fresh CSRF token.
`POST /api/auth/logout` revokes the session and expires the cookie. State-changing
browser requests require both the session cookie and `X-CSRF-Token`. The server
also rejects browser mutation requests whose `Origin` is not in
`CORS_ALLOWED_ORIGINS`.

### Compatibility

Bearer authentication remains supported for non-browser administration and
read-only automation. `ADMIN_API_TOKEN` and `READ_API_TOKEN` continue to work in
the `Authorization` header. Browser code uses cookies only and must not read any
`VITE_*_TOKEN` value.

### Frontend behavior

The app starts by calling `/api/auth/session`. An unauthenticated production
response shows a compact administrator login screen. Successful login stores the
CSRF token in React state, reloads application data, and sends credentials with
same-origin requests. A 401 clears local auth state and returns to login.

## 2. External Agent Identity And Authorization

### Credential lifecycle

`POST /api/agents/register` remains an administrator operation. Registration
creates a cryptographically random agent credential, returns it exactly once,
and stores only its SHA-256 hash. Registration requires an explicit `role_tier`
of `reader`, `verifier`, `reporter`, or `tool_agent`; it does not infer authority
from a free-form `agent_type`. Existing agent rows receive nullable credential
and role fields through an idempotent SQLite migration.

The registration response adds `agent_token`; subsequent reads never expose it.
The CLI prints an explicit instruction to store the token in the agent runtime.
Re-registering or rotating an agent invalidates the previous token.

### Request identity

For `/api/agent/*`, bearer authentication resolves directly to one registered
agent. The authenticated identity is the only accepted identity:

- a missing, unknown, disabled, or expired credential returns 401;
- a body `agent_id` that differs from the authenticated agent returns 403;
- handlers pass the authenticated ID to the store instead of trusting payload
  identity;
- the global `AGENT_API_TOKEN` is accepted only when
  `OSINT_ALLOW_LEGACY_AGENT_TOKEN=true`, which defaults to false in production;
- production readiness reports legacy shared-token mode as a blocker.

### Role policy

Reuse the existing reader/verifier/reporter method sets as the source of truth.
Map API routes to store actions and enforce the corresponding tier before the
handler runs:

- reader: entities, evidence, evidence records, relationships, and scoped task
  reads;
- verifier: facts, hypotheses, and hypothesis scoring;
- reporter: task completion;
- tool agents: claimed job events and tool-output contracts only.

Task and job mutations additionally require that the authenticated agent owns
the active claim or is completing the exact job assigned to it. Administrator
Bearer/session access does not impersonate an agent and cannot use agent routes.

### Migration behavior

Existing external agents must be re-registered or rotated to receive individual
credentials. Documentation and the CLI state this explicitly. There is no silent
fallback to the shared token in production.

## 3. SSRF-Safe HTTP Fetching

Create a standard-library safe fetch module for untrusted HTTP(S) targets. It
must:

1. parse and normalize the URL;
2. reject credentials in URLs, non-HTTP(S) schemes, and ports other than 80 or
   443;
3. resolve all A and AAAA records;
4. reject loopback, private, link-local, multicast, reserved, unspecified, and
   non-global addresses using `ipaddress`;
5. connect to one validated IP through injectable resolver and connector
   boundaries while preserving the original `Host` header and HTTPS
   SNI/certificate validation;
6. disable automatic redirects, resolve each `Location`, and repeat the full
   validation for at most five hops;
7. enforce response byte and timeout limits;
8. return a stable error type that does not expose sensitive connection detail.

`OfficialSiteExtractorAdapter` uses this module for user-derived URLs. Configured
internal services such as SearXNG, SpiderFoot, or PhoneInfoga remain explicit
trusted-service configuration and are not routed through the untrusted-target
policy.

`normalize_target` also rejects private IP literals and obvious local hostnames
early, but DNS and redirect enforcement remains in the fetch layer.

## 4. Public Release And Dependency Gates

### Repository policy scan

Extend `public_release_check.py` to verify:

- `LICENSE`, frontend package metadata, and backend package metadata all declare
  `GPL-3.0-only`;
- tracked text files do not contain personal `/Users/<name>` or `/home/<name>`
  paths, private/LAN IPs, non-placeholder credential values, or forbidden runtime
  artifacts;
- documentation ranges, generic paths, and documented placeholders remain
  allowed;
- the check explains every blocker with a relative path and rule ID.

The checker uses `git ls-files` in a repository and a deterministic filesystem
fallback in unit-test fixtures. Binary files are skipped. The current maintenance
log replaces personal deployment paths with `<production-path>` while preserving
the user's other uncommitted documentation changes when the final changes are
integrated.

### Dependencies

Update Vite, its React plugin, and lockfile-resolved transitive dependencies to
versions that clear the recorded advisories. Do not use `npm audit fix --force`.
Acceptance requires both production-only and full npm audits to contain no high
or critical findings.

## 5. Router Classification

Add specific Chinese compound signals such as `代码审核`, `项目审核`, `安全审计`,
`代码质量`, and `可维护性` to the code-review profile. Avoid the bare term
`审核`, because it also describes UI, content, compliance, and business review.

Add the original audit request and shorter Chinese variants to router unit tests
and `evals/router-quality.json`. The expected task type is `code_review` and the
expected scenario is `code-review-hardening`. Existing website, UI, content, and
skill-router cases must remain unchanged.

## 6. UI Behavior

### Graph details

The template graph starts with no selected node. Clicking or keyboard-activating
a node opens details; activating the selected node again or using an icon-only
close button closes it. The close button has an accessible label and focus style.

Above 620px, details may remain an anchored overlay but must reserve a bounded
area that does not cover primary nodes. At 620px and below, details move into
normal document flow below the graph viewport. The SVG remains horizontally
scrollable where necessary.

### Labels

Central node labels use a deterministic compact-label helper with an ellipsis and
an SVG `<title>` containing the full value. Fixed-format node labels must not
cross node bounds or obscure relationship text.

### Empty state

When no investigation exists, the task/operations panel is open by default and
the dashboard presents a concise empty state with a direct create-task action.
It must not leave a viewport-sized decorative grid as the primary experience.

The implementation follows `DESIGN.md`: dense operational hierarchy, shared
tokens, restrained motion, keyboard access, and no product-level navigation
redesign.

## 7. Error Handling And Observability

- Authentication failures use 401; authenticated but unauthorized actions use
  403; claim conflicts use 409; malformed payloads use 400.
- Logs record route, result, and authenticated identity ID, but never bearer
  values, cookies, CSRF values, or login input.
- Safe-fetch failures distinguish invalid target, blocked network target,
  redirect limit, timeout, and response size without returning resolved private
  addresses to clients.
- Release checks return a non-zero status when any blocker exists.

## 8. Test Strategy

Every behavior change follows red-green-refactor.

### Backend tests

- login success/failure, cookie flags, session expiry, logout, CSRF, Origin, and
  Bearer compatibility;
- per-agent token hashing, one-time response, role route matrix, forged identity,
  unregistered identity, claim ownership, rotation, and legacy-mode production
  rejection;
- IPv4/IPv6 private ranges, alternative loopback spellings, DNS results, mixed
  safe/unsafe DNS answers, redirects, size limits, and a successful public-safe
  fetch using injected resolver and connector fakes that make no network call;
- release-policy path, IP, secret, runtime artifact, license, and allowed
  placeholder fixtures.

### Frontend tests

- no environment-token reference or Authorization header construction;
- login/session transitions and CSRF headers;
- compact graph labels, closed initial details, toggle/close behavior, responsive
  CSS contract, and actionable empty state.

### Router tests

- original Chinese audit request selects code review;
- ambiguous non-code review requests retain their existing classifications;
- full router evaluation remains green.

### Final verification

- `bash scripts/verify.sh` in both repositories;
- targeted authentication, authorization, SSRF, release, router, and UI tests;
- `npm audit --omit=dev` and full `npm audit` against the official registry;
- production build canary proving no administrator token appears in assets;
- Playwright desktop and mobile screenshots, DOM assertions, console check, and
  horizontal-overflow check;
- final diff review confirming pre-existing user changes were preserved.

## 9. Rollout And Rollback

1. Back up the SQLite database and current environment files.
2. Deploy the API changes with TLS termination and secure cookies configured.
3. Register or rotate each external agent and distribute its one-time token
   through the existing private operations channel.
4. Build the frontend without `VITE_ADMIN_API_TOKEN` and verify the asset scan.
5. Run readiness, health, browser, and agent claim/write smoke tests.

Rollback restores the prior application version and database backup together.
Because the agent credential migration is additive, an application rollback can
ignore the new nullable columns. Do not re-enable legacy shared-token mode as a
long-term rollback strategy.

## Acceptance Criteria

- All eight audit findings have a failing regression test on the old behavior and
  a passing test after implementation.
- Browser assets contain no administrator, read, or agent bearer credential.
- An unregistered or wrong-role agent cannot write or complete a task.
- Alternative loopback and private-network URLs cannot trigger a connection.
- Public release verification catches the current personal-path example and the
  backend license mismatch.
- The original Chinese audit request routes to code review.
- Desktop and mobile graph screenshots show readable nodes and non-obscuring
  details; the empty state exposes task creation.
- Both complete repository verification scripts pass.
- Full npm audit contains zero high or critical vulnerabilities.
