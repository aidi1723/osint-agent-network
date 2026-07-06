# Real Sample Regression Pack Design

## Context

The current platform baseline has a recoverable SQLite-backed background queue,
working official-site discovery, and passing full verification. The next risk is
not orchestration reliability; it is parser drift.

Most current adapter tests use small inline records. They prove individual
parsing branches, but they do not exercise the file-level artifact path that
production uses after external tools run. A future parser change could silently
drop official-site URL evidence, business pages, contact records, or passive
subdomain findings while the narrow inline tests still pass.

The next phase should add a public-safe fixture regression pack that protects
the realistic parser contract without publishing private investigation data.

## Decision

Add a small fixture library under `backend/tests/fixtures/tool_outputs/` and a
dedicated regression test module for file-level parser behavior.

Fixtures must be synthetic-realistic and public-safe. They may resemble real
tool output shapes, but they must not include private target names, tokens,
internal hostnames, local absolute paths, raw private task identifiers, or
deployment host aliases.

The first regression pack covers:

- `official_site_search`
- `httpx`
- `katana`
- `official_site_extractor`
- `subfinder`
- selected company or sparse-lead role-agent output summaries

## Goals

- Exercise `parse_artifact()` with real files for the core public OSINT tool
  adapters.
- Keep fixtures minimal, readable, and safe for a public repository.
- Assert the important behavior contract: official-site evidence becomes
  entities, evidence records, relationships, and source-backed facts where that
  pipeline already exists.
- Make future parser regressions fail at test time when important official-site
  or collection evidence is dropped.
- Keep this phase focused on test coverage and parser confidence, not new
  runtime collection behavior.

## Non-Goals

- No live network collection.
- No production host deployment.
- No new third-party dependency.
- No broad snapshot tests.
- No real private customer, lead, target, task, or deployment records.
- No report export, permission tier, or evidence review schema changes.

## Fixture Layout

Use a dedicated fixture directory:

```text
backend/tests/fixtures/tool_outputs/
  official_site_search/
  httpx/
  katana/
  official_site_extractor/
  subfinder/
  role_agent_outputs/
```

Recommended first fixture names:

```text
official_site_search/example_company_results.json
httpx/example_company_live.jsonl
katana/example_company_pages.jsonl
official_site_extractor/example_company_official.html
subfinder/example_company_subdomains.jsonl
role_agent_outputs/example_sparse_lead_summary.json
```

All target values should use generic domains such as `example.com`,
`www.example.com`, `support.example.com`, or reserved placeholder domains such
as `example-target.test`. Company names should be generic names like
`Example Manufacturing LLC`.

## Parser Regression Tests

Add a dedicated test file:

```text
backend/tests/test_tool_fixture_regressions.py
```

The tests should assert selected entities, evidence, and relationships rather
than full exact output snapshots.

Required cases:

- `official_site_search` reads a JSON artifact and emits an official-site URL
  candidate while filtering third-party directory noise.
- `httpx` reads JSONL and emits a live URL, title, technology, `http_probe`
  evidence, and `host_serves_url` relationship.
- `katana` reads JSONL and emits relevant contact or business-scope pages while
  ignoring static assets and low-value policy pages.
- `official_site_extractor` reads HTML and emits organization, email, phone,
  business scope, address, evidence records, and official-site relationships.
- `subfinder` reads JSONL and emits passive subdomain entities, evidence, and
  `domain_has_subdomain` relationships.
- role-agent summary fixture can be parsed as JSON and validated for expected
  public-safe fields, so future agent-output fixtures have a documented shape.

## Source-Backed Official-Site Smoke Case

Add one small smoke test that composes parsed output from the official-site
fixture chain and verifies that a source-backed official-site fact can be
constructed from the parsed records.

The smoke test does not need to run the full job orchestrator. It should stay
bounded to parser outputs and existing helper APIs where available. It should
prove the end-to-end data expectation:

```text
official-site URL -> parsed official-site entities -> evidence -> relationship
or source-backed fact
```

If the current helper layer does not expose a narrow source-backed fact builder,
the test should assert the underlying entities, evidence, and relationships and
record the missing helper as a follow-up rather than expanding this phase.

## Data Safety Contract

Before committing, run an added-line privacy scan for:

- private target names;
- tokens and bearer strings;
- GitHub tokens;
- internal or RFC1918 IP addresses;
- local absolute paths;
- production host aliases;
- raw private task identifiers.

Fixtures must not contain:

- real customer or lead names;
- real task ids;
- real private websites discovered in previous runs;
- deployment usernames, hostnames, or paths;
- API keys, cookies, authorization headers, or session identifiers.

## Testing

Implementation should follow test-first order:

1. Add fixture regression tests that fail if fixtures or parser outputs are
   missing.
2. Add the minimal public-safe fixtures.
3. Adjust parser behavior only if a fixture exposes an actual parser gap.
4. Run the targeted backend regression tests.
5. Run full verification:

```text
bash scripts/verify.sh
```

## Documentation

After implementation, update the next-phase records with:

- fixture files added;
- parser behavior protected;
- verification commands and results;
- privacy scan result;
- unresolved follow-up items.

## Acceptance Criteria

- Public-safe fixtures exist under `backend/tests/fixtures/tool_outputs/`.
- File-level parser regression tests cover all first-pack adapters.
- Regression tests fail if important official-site evidence is dropped.
- Role-agent sample output has a documented public-safe shape.
- `bash scripts/verify.sh` passes.
- Added-line privacy scan passes before commit and push.
