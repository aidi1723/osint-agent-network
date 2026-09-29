# OSINT Fusion Dual-Core Upgrade Design

## Context

The current OSINT Agent Network already has a working task center, Intel Gateway, Worker, SQLite store, HCS dual-core dashboard, and tool adapters for Amass, SpiderFoot, and Sherlock. The next upgrade should not bolt raw tool output directly onto the graph. It should turn tool findings into a traceable "mosaic evidence chain" that can support the left organization asset core and the right decision will core without overstating weak public-source matches.

The user selected a two-phase delivery:

1. Phase 1 strengthens the internal contracts, normalization, graph mapping, and dashboard display using fixtures and existing adapters.
2. Phase 2 mounts real tool execution through optional Docker/profile configuration and deployment docs.

This design keeps the existing product shape: a dense, light, technical analyst workstation defined by `DESIGN.md`, with the selected investigation detail area presented as the HCS dual-core cockpit.

## Upstream Tool Assumptions

- SpiderFoot is treated as a passive enrichment and all-source OSINT automation layer. Its open-source project supports Web UI or CLI, over 200 modules, JSON/CSV/GEXF export, and Docker-based deployments.
- Sherlock is treated as a username-to-public-profile discovery runner. Its current project describes username searches across 400+ social networks and supports Docker and JSON output.
- OWASP Amass is treated as the organization-side external asset discovery tool. Its current project focuses on attack surface mapping and external asset discovery from open-source information and reconnaissance techniques.

All three tools must remain bounded to authorized public-source collection. Tool hits are not mature conclusions by themselves.

## Goals

- Convert Amass, SpiderFoot, and Sherlock findings into traceable evidence chains.
- Map technical findings into the HCS dual-core model:
  - Left rail: organization asset core.
  - Right rail: decision will core.
  - Center bridge: mosaic evidence chain.
- Preserve existing APIs, job queue shape, store model, graph panel structure, and task-center workflow during Phase 1.
- Keep weak or ambiguous OSINT hits in candidate/review states until cross-verification supports them.
- Make missing tools, missing config, no findings, partial failures, and candidate findings visible to operators.
- Prepare Phase 2 Docker/container mounting without forcing live tools into Phase 1 tests.

## Non-Goals

- No intrusive scanning, bypassing, credential acquisition, account login, hidden access, or non-public data collection.
- No automatic claim that a Sherlock username hit is the target decision-maker.
- No automatic claim that an Amass or SpiderFoot technical asset is a confirmed operating asset of the company.
- No product-wide redesign, new component library, or routing change.
- No requirement that local or N100 machines have all OSINT tools installed for Phase 1 to pass.

## Recommended Approach

Use the conservative two-phase path.

Phase 1 introduces an internal OSINT Fusion layer. Existing adapters still parse artifacts into `Entity`, `Evidence`, and `Relationship`, then fusion logic classifies those findings for graph slots, candidate status, review status, and evidence-chain presentation.

Phase 2 adds optional real execution mounts: Docker profile/services, environment variables, health checks, runner commands, real artifact validation, and N100 deployment notes.

This avoids the risky state where real tools produce many raw findings before the product knows how to grade, display, and verify them.

## Architecture

```text
seed lead
  -> Intel Gateway route planning
  -> tool adapter artifact parsing
  -> OSINT Fusion classification
  -> left/right/bridge core mapping
  -> Evidence Ledger + Fact Pool + ACH inputs
  -> HCS dual-core graph and mosaic evidence chain
```

Phase 2 extends the beginning of the flow:

```text
optional docker compose profile
  -> SpiderFoot REST service
  -> Sherlock runner
  -> Amass runner / CLI image
  -> Worker artifact contract
  -> same OSINT Fusion classification
```

## OSINT Fusion Contract

Add a lightweight core module, preferably `backend/app/core/osint_fusion.py`, with a dataclass like:

```python
@dataclass(frozen=True)
class OsintSignal:
    signal_id: str
    tool: str
    target_type: str
    target_value: str
    entity_type: str
    entity_value: str
    evidence_kind: str
    relationship_type: str
    confidence: float
    core_axis: str
    slot_hint: str
    review_status: str
    source_tier: str
```

Allowed values:

- `core_axis`: `organization_asset`, `decision_will`, `bridge`.
- `review_status`: `candidate`, `confirmed`, `conflict`, `noise`.
- `source_tier`: `tool_raw`, `passive_osint`, `cross_verified`.

Phase 1 should avoid a new database table unless implementation proves the existing `facts`, `evidence_ledger`, graph metadata, and generated frontend props cannot carry this. Prefer derived signals from existing investigation detail data.

## Tool Mapping Rules

### Amass

- `subdomain` maps to `organization_asset` with slot hint `digital-footprint`.
- `ip` maps to `organization_asset` with slot hint `digital-footprint`.
- `domain_has_subdomain` supports the left rail network extension chain.
- `subdomain_resolves_to_ip` supports the left rail infrastructure evidence chain.
- Default review status is `candidate` unless the same domain/subdomain is supported by stronger sources or known seed constraints.

### SpiderFoot

- `email` maps to `bridge`.
  - Same-domain company email can hint `company_contact`.
  - Personal-looking email stays as a right-core candidate.
- `url`, `subdomain`, and `ip` map to the organization asset core.
- `real_name` and `username` map to the decision will core as candidates.
- `company` maps to a candidate organization identity, not a confirmed landed entity.
- SpiderFoot source events should preserve module/source snippets where possible.

### Sherlock

- `username` maps to `decision_will`.
- `profile_url` maps to the right-core social/public profile candidate slot.
- `username_has_profile` supports "public profile candidate".
- Sherlock hits stay `candidate` until constrained by company, email, geography, name, platform context, or another independent source.

## Review And Confidence Rules

- Raw Amass, SpiderFoot, and Sherlock findings begin as `candidate`.
- Findings can become `confirmed` when supported by official website, same-domain email, registry/government source, original profile source, or two independent B/C-tier public sources.
- Findings become `conflict` when they contradict seed company, geography, domain ownership, contact boundaries, or a stronger source.
- Generic username/name-only matches remain candidates or become `noise`; they must not light up the main decision-maker slot.
- Mature facts should still flow through the existing cross-verification and ACH model.

## Backend Changes

Phase 1:

- Add `backend/app/core/osint_fusion.py`.
- Add unit tests for signal classification, status assignment, and slot hints.
- Extend adapter tests for representative Amass JSONL, SpiderFoot JSON, and Sherlock JSON artifacts.
- Keep Worker writes in the existing entity/evidence/relationship path.
- Derive fusion signals after parsed tool output, then expose them through graph metadata or investigation detail helpers.
- Ensure `missing_config:SPIDERFOOT_BASE_URL`, missing executables, no findings, and partial failures remain explicit events/jobs rather than silent failures.

Phase 2:

- Extend `docker-compose.yml` with optional OSINT profile services or runner containers.
- Document `SPIDERFOOT_BASE_URL`, `SPIDERFOOT_API_KEY`, `SHERLOCK_COMMAND`, `SHERLOCK_PATH`, `AMASS_COMMAND`, and timeout settings.
- Add health/status checks where practical.
- Validate that real artifacts parse into the same Phase 1 contract.
- Update README and N100 deployment notes.

## Frontend Changes

Phase 1 should keep the existing HCS cockpit and add visible evidence semantics:

- Left core, `digital-footprint`: prioritize Amass subdomains/IPs and SpiderFoot URLs/emails.
- Left core, `manufacturing-base`: show evidence summaries for claimed factory/manufacturing assets versus digital/website evidence.
- Left core, `landed-entity`: show candidate company names, Whois/domain-related entities, and verified organization identities only when supported.
- Right core, `persona-role`: show Sherlock/Profile Parser public-profile candidates.
- Right core, `contact-channel`: separate company contacts from personal contact candidates.
- Right core, `activity-habit`: show public activity clues, timezone/location clues, and collection gaps.
- Center bridge: add or adapt a compact `Mosaic Evidence Chain` panel.

Example chain display:

```text
domain -> amass subdomain/ip
domain -> spiderfoot email/company/person
email/username -> sherlock profile
profile -> profile_parser bio/location/link
cross_verification -> fact / ACH
```

Each chain row should show tool, finding, evidence snippet, confidence, review status, and trigger source.

The visual style stays aligned with `DESIGN.md`: light background, dense technical surfaces, compact panels, subtle status color, no marketing hero, no decorative large cards.

Phase 2 can add:

- Tool health strip for SpiderFoot REST, Amass runner, and Sherlock runner.
- Container log excerpts.
- Scan progress, timeout, and cancel/read-only artifact states.
- Artifact view/download link if it fits the existing operations workflow.

## Data Flow

- Existing investigation detail remains the source of truth.
- Tool adapters parse artifacts into normalized entities, evidence, and relationships.
- OSINT Fusion derives signals from parsed output and existing detail data.
- Graph metadata and cockpit helpers use `core_axis`, `slot_hint`, and `review_status` to decide whether findings appear as main, candidate, conflict, or review-only items.
- Cross-verification and analysis jobs remain responsible for mature facts, ACH, BLUF, and final report language.

## States

The upgrade must preserve and clarify:

- Tool missing executable.
- Tool missing required config.
- Tool running.
- No findings.
- Partial failure.
- Candidate finding.
- Confirmed finding.
- Conflict finding.
- Needs cross-verification.
- Graph empty.
- Report missing.

## Testing

Backend:

- Add `backend/tests/test_osint_fusion.py`.
- Extend `backend/tests/test_tool_adapters.py` for the three tool artifact shapes.
- Extend `backend/tests/test_worker.py` for traceable evidence chain writeback or derived signals.
- Extend `backend/tests/test_graph.py` for graph metadata needed by dual-core display.

Frontend:

- Add or extend graph helper tests to verify dual-core slot mapping.
- Run `npm run check:ui-copy`.
- Run `npm run build`.
- Inspect the selected dashboard at desktop and mobile widths after implementation.

Full verification:

```bash
bash scripts/verify.sh
```

## Phase 1 Acceptance Criteria

- Given an Amass fixture, subdomains and IPs appear as organization asset candidates with evidence-chain relationships.
- Given a SpiderFoot fixture, emails, company names, URLs, usernames, and names map to left/right/bridge candidates without becoming confirmed facts automatically.
- Given a Sherlock fixture, public profile URLs appear as decision will candidates and do not confirm identity by themselves.
- The HCS cockpit can show left core, right core, bridge evidence chain, and review/conflict states.
- Missing tool/config cases are visible in queue/events and do not crash the Worker or UI.
- `bash scripts/verify.sh` passes.

## Phase 2 Acceptance Criteria

- Optional Docker/profile setup can be enabled or skipped without breaking normal app startup.
- SpiderFoot REST configuration can produce a real artifact that parses through the Phase 1 contract.
- Amass and Sherlock runner commands can produce artifacts that parse through the Phase 1 contract.
- Worker can parse real artifacts into entities, evidence, relationships, and derived OSINT signals.
- README and deployment docs explain local and N100 configuration.

## Safety And Compliance

The system only supports authorized public-source intelligence collection, evidence preservation, and human review. It must not include credential theft, login bypass, evasion, account takeover, coercive outreach, or hidden access. Reports should use estimative language and preserve uncertainty. High-risk conflict labels require evidence-chain support and should not be phrased as certainty unless sourced from an authoritative public record.

