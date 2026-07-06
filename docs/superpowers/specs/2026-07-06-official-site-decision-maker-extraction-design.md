# Official Site Decision-Maker Extraction Design

## Objective

Close the next company/sparse-lead quality-gate gap by extracting conservative, source-backed public decision-maker candidates from official website pages already collected by `official_site_extractor`.

This phase improves the existing official-site chain. It does not add a new crawler, social-search integration, credentialed account lookup, or private-person inference.

## Current Gap

The platform can now discover official website candidates and queue URL collection followups. Company and sparse-lead tasks still remain incomplete when they lack public decision-maker evidence. Current local role agents may add weak platform identity candidates, but the quality gate intentionally keeps those from closing the decision-maker gap.

The lowest-risk next source is the target's own official website, especially about, team, leadership, contact, and sales pages.

## Approved Approach

Enhance `official_site_extractor` so its HTML parser can identify public staff or leadership candidates when the page itself provides enough context.

Accepted source context:

- HTML visible text from an official URL.
- JSON-LD data embedded in the official page.
- Contact/about/team/leadership/sales page text reached through the existing URL collection path.

Rejected source context:

- Third-party directory pages.
- Generic search result snippets.
- Names inferred from emails alone.
- Personal social-profile matches without an explicit company bridge.
- Private attributes, family details, demographic guesses, or account-session data.

## Extraction Rules

The parser should emit a decision-maker candidate only when a person-like name appears near a role marker.

Role markers include:

- owner
- founder
- co-founder
- CEO
- president
- managing director
- director
- general manager
- sales manager
- export manager
- procurement manager
- purchasing manager
- contact person

Candidate safeguards:

- Require a capitalized multi-token name or a JSON-LD `Person.name`.
- Reject generic labels such as `Contact Us`, `Sales Team`, `Customer Service`, and `About Us`.
- Keep confidence conservative:
  - `0.66` for a visible-text name with a nearby role marker.
  - `0.70` for JSON-LD `Person` or staff data with a role/title.
  - Add no higher-confidence promotion in this phase.
- Do not mark candidates as accepted facts directly. Cross-verification remains responsible for fact promotion.

## Output Contract

For each accepted candidate, `official_site_extractor` should emit:

- `person` entity for the public name.
- `job_title` entity for the role text when available.
- `decision_maker` entity as a conservative business-role candidate.
- Evidence kind `official_site_decision_maker_candidate`.
- Relationship from official URL to person:
  - `official_site_mentions_decision_maker`
- Relationship from person to title:
  - `person_has_public_role`
- Relationship from person to nearby email or phone only when the contact appears in the same short text window:
  - `person_has_contact`

The snippet must identify the page-derived context without including excessive page text.

## Data Flow

1. `official_site_search` finds a likely official URL.
2. URL followups queue `httpx`, `katana`, `official_site_extractor`, and related parsers.
3. `official_site_extractor` parses the fetched HTML.
4. Existing official-site extraction continues to emit organization, email, phone, address, and business-scope fields.
5. New decision-maker extraction adds conservative person/title/contact candidates from official page text.
6. Existing cross-verification and quality assessment consume the new entities without changing completion rules.

## Safety And Compliance

- Use only publicly visible official-site content.
- Keep company contact and personal/decision-maker contact separated.
- Treat every extracted person as a candidate until cross-verification evaluates it.
- Do not infer sensitive or private personal attributes.
- Avoid broad scraping. This feature only parses artifacts already fetched by the existing official-site route.

## Test Plan

Unit tests should cover:

- HTML visible text with `Jane Smith, Export Manager` produces `person`, `job_title`, `decision_maker`, evidence, and relationships.
- JSON-LD `Person` with `jobTitle` produces the same candidate family.
- Generic page labels such as `Contact Us` and `Sales Team` do not become person entities.
- Nearby email links can create `person_has_contact`; distant unrelated emails do not.
- Existing organization, email, phone, address, and business-scope extraction still passes.

Integration checks should confirm:

- The quality gate can see the candidate as a decision-maker signal while still requiring evidence ledger, facts, BLUF, and cross-verification for completion.
- The full local verification suite passes.
- <production-host> health/readiness remains `ready=true`.

## Success Criteria

- `official_site_extractor` can extract public decision-maker candidates from official website artifacts.
- No new external service or credential is required.
- Existing official-site outputs are unchanged except for additional candidate entities/evidence/relationships.
- Company/sparse-lead tasks have a source-backed path to reduce the `decision_maker` gap after official-site discovery is configured.
