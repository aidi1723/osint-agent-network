# OSINT Community Tool Gap Fill Design

## Objective

Raise actual investigation completion quality by adding source-backed collection for the fields currently blocking <production-host> tasks: official website, contact channel, business scope, decision-maker candidates, and relationships.

## Current Gaps

- Domain tasks are blocked because `theHarvester`, `amass`, and `spiderfoot` are not ready on <production-host>.
- Company tasks complete local role-agent passes but mostly produce low-confidence anchor entities instead of verified public fields.
- Sparse-lead enrichment can improve identity confidence, but still lacks public website/contact/business-scope evidence.

## Approved Tool Direction

Use a layered tool chain instead of relying on a single broad OSINT platform:

- `subfinder`: passive subdomain discovery as a lighter ProjectDiscovery alternative/complement to `amass`.
- `httpx`: HTTP probing and title/technology extraction to identify live official-site candidates.
- `katana`: scoped crawler for contact, about, team, product, and catalog pages.
- `trafilatura` and `extruct`: local HTML parsing for page text and structured metadata.
- `SearXNG`: optional self-hosted metasearch service for company and sparse-lead candidate website search.

## Implementation Shape

Phase 1 adds first-class CLI tool support for `subfinder`, `httpx`, and `katana`:

- registry entries;
- health checks;
- CLI adapters;
- planning routes for domain/subdomain URL discovery;
- agent client support;
- parser tests.

Phase 2 adds an internal `official_site_extractor` parser:

- parse HTML/text artifacts;
- extract emails, phones, page URLs, organization names, business-scope snippets, addresses, and JSON-LD organization/contact data;
- emit normalized entities, evidence, and relationships with snippets.

Phase 3 wires source-backed extraction into company and sparse-lead flows:

- candidate website search/probing;
- crawl selected pages;
- extract quality-gate fields;
- preserve source URLs/snippets for cross-verification and reports.

## Safety And Compliance

- Default to passive/public-source tools.
- Keep credentialed or probing-heavy tools disabled unless explicitly configured.
- Record source URL and snippet for every quality-gate field.
- Do not treat guessed websites or same-name matches as confirmed facts without corroborating evidence.

## Success Criteria

- `/api/tools/health` reports `subfinder`, `httpx`, and `katana` separately.
- Domain plans can use `subfinder` as an additional route and can use `httpx/katana` when input type matches.
- Parser tests prove normalized outputs for subdomains, live URLs, titles, technologies, and discovered contact/product URLs.
- Later <production-host> actual tests should show fewer domain `BLOCKED` cases after tool installation and higher company/sparse-lead quality scores after source-backed extraction.

## Execution Result - 2026-07-06

Phase 1 was implemented and deployed.

<production-host> installed tools:

- `subfinder` v2.14.0
- `httpx` v1.9.0
- `katana` v1.6.1

Final actual verification task:

- Early proof task: `<phase-domain-task-id>`
- Final completion task: `<final-domain-task-id>`
- Target: `example-target.test`
- Strategy: `quick`

Result:

- Completed available chain:
  - `subfinder`
  - `httpx`
  - `katana`
  - `official_site_extractor`
- Failed jobs: `0`
- Blocked jobs: `0`
- Quality score: `78.1`
- Status: `COMPLETED`

Confirmed improvements:

- Domain execution no longer stops at missing-tool blockers when health-aware planning is used.
- URL follow-ups now run after `httpx` confirms a live site.
- Official-site extraction can fetch and parse gzip-compressed HTML.
- Event logs no longer persist oversized crawler stdout excerpts.
- Official-site outputs now create source-backed accepted facts for quality-gate closure.
- Domain/URL reconnaissance does not require decision-maker evidence to complete.

Confirmed remaining gaps:

- Company/sparse-lead tasks still need an official-website search layer before domain probing. SearXNG remains the preferred next community component for this role.
- Decision-maker discovery remains required for company/sparse-lead quality-gate closure.
- Remaining disabled/missing tools can improve coverage but no longer block the proven domain quick chain.
