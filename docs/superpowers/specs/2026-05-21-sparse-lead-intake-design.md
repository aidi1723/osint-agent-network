# Sparse Lead Intake v1 Design

Date: 2026-05-21
Project: OSINT Agent Network / 情报官

## Purpose

Sparse Lead Intake v1 turns low-information Alibaba/CRM screenshots into structured intelligence work. The first target is the common case where the operator only has a buyer profile or CRM card: display name, country, platform member ID, registration year, categories, recent RFQs, privacy-hidden contact fields, and no direct email, phone, website, or company registration data.

The goal is not to identify a private person by bypassing platform privacy. The goal is to preserve visible anchors, generate constrained public-source searches, separate real public records from identity matches, and produce a cautious analyst-ready workflow: candidate entities, evidence chains, confidence fields, red-team scenarios, and directed collection.

## Scope

First version:

- Add a sparse lead investigation path for Alibaba/CRM-style weak buyer records.
- Capture screenshot-derived anchors as first-class structured data.
- Preserve platform facts separately from public candidate records.
- Add candidate confidence fields for sparse leads:
  - `record_confidence`
  - `identity_match_confidence`
  - `field_interpretation_confidence`
- Generate constrained search plans from anchors instead of broad-name searches.
- Add role-based jobs for anchor extraction, candidate discovery, identity matching, cross-verification, and analysis judgement.
- Surface the intake workflow in the UI as an analyst stage model.
- Keep all findings evidence-bound and privacy-safe.

Out of scope for v1:

- OCR or image recognition automation. Operators can manually enter screenshot facts in v1.
- Bypassing Alibaba privacy settings or finding hidden contact details.
- Paid customs database integration.
- Fully automated web search execution.
- Production multi-user permissions.
- PDF/HTML report export.

## Investigation Type

Add a new target type:

```text
sparse_lead
```

This type represents a platform or CRM lead where multiple weak anchors exist but no single stable company, domain, email, or phone is confirmed.

Example seed:

```json
{
  "seed_type": "sparse_lead",
  "seed_value": "Long Way / in19034126503jgqn",
  "strategy": "deep"
}
```

For compatibility, `company` tasks can still exist. Sparse lead intake is used when the input is a buyer card, screenshot, Alibaba profile, CRM lead, or other weak record where identity is not yet closed.

## Intake Data Model

Sparse lead intake should store a lead anchor bundle in investigation metadata or a dedicated normalized table later. In v1, the API can accept an optional `metadata` object on investigation creation.

Recommended anchor fields:

```json
{
  "platform": "Alibaba",
  "lead_display_name": "Long Way",
  "member_id": "in19034126503jgqn",
  "country_region": "IN",
  "registration_year": "2023",
  "company_name_raw": "Long Way",
  "privacy_state": "email_phone_hidden",
  "categories": [
    "Induction Cookers",
    "Toe Separator",
    "Commercial Cooking Equipment",
    "Safety Shoes",
    "Metal Crafts",
    "Other Animal Husbandry Equipment",
    "Others Windows",
    "Soles",
    "Home Energy Storage",
    "Gas Cooktops"
  ],
  "recent_rfqs": [
    "10T melting steel induction furnace melting iron copper aluminum steel industrial furnace",
    "Hongteng 5T 10T 15T 20T Steel shell induction melting furnace Good Price hydraulic tilting smelting furnace",
    "2200W Best Quality And Low Price Durable Electric Cook Top Induction Heating Plate Induction Cooker/",
    "10 Inch 1 Micron Carbon Sediment Melt Blown Pp Spun Udf Gac Cto Resin Replacement Whole House Ro Filter Cartridges"
  ],
  "screenshot_observed_at": "2026-05-21",
  "operator_notes": ""
}
```

Each anchor should be written as an entity and evidence row before any external lookup:

- `platform_account`: `Long Way`
- `platform_member_id`: `in19034126503jgqn`
- `country_region`: `IN`
- `company_name_raw`: `Long Way`
- `purchase_category`: each visible category
- `rfq_text`: each recent RFQ title
- `privacy_state`: `email_phone_hidden`

Screenshot evidence supports only the platform record and visible anchors. It does not prove the buyer belongs to any public company.

## Confidence Model

Sparse lead investigations must keep three confidence values separate:

```text
record_confidence
```

Whether a public record is real. Example: an official company registration or active website exists.

```text
identity_match_confidence
```

Whether the public record belongs to this exact platform lead.

```text
field_interpretation_confidence
```

Whether a source field is best interpreted as company name, display name, trade name, person name, or platform alias.

Example:

```json
{
  "candidate": "Longway India / Onetail Brands Technologies Limited",
  "record_confidence": 0.86,
  "identity_match_confidence": 0.62,
  "field_interpretation_confidence": 0.54,
  "candidate_status": "CANDIDATE"
}
```

The UI and final report must never collapse these into a single certainty statement.

## Route Matrix

For `sparse_lead`, the Intel Tool Gateway should generate role-based jobs:

| Job | Agent Role | Purpose |
| --- | --- | --- |
| `lead_anchor_extraction` | `lead_intake_agent` | Normalize visible screenshot/CRM fields into anchors, entities, and evidence. |
| `constrained_query_planning` | `search_planning_agent` | Build strong-to-weak query matrix from anchors. |
| `candidate_business_discovery` | `enterprise_intel_agent` | Find public company or trade-name candidates. |
| `rfq_category_analysis` | `purchase_intent_agent` | Classify visible categories and RFQs into intent signals and noise. |
| `identity_match_review` | `cross_verification_agent` | Score candidate identity match separately from record truth. |
| `analysis_judgement` | `analysis_judgement_agent` | Produce BLUF, ACH scenarios, risk level, and directed collection. |

`quick` strategy should include anchor extraction, query planning, and analysis judgement.

`standard` should add candidate discovery and identity match review.

`deep` and `maximum` should add RFQ/category analysis and broader candidate discovery.

## Workflow

```text
Operator enters visible screenshot facts
  -> lead_anchor_extraction writes platform anchors
  -> constrained_query_planning creates search matrix
  -> candidate_business_discovery finds public records
  -> rfq_category_analysis separates product intent from noisy categories
  -> identity_match_review scores candidate matches
  -> analysis_judgement runs ACH and writes BLUF report
  -> directed_collection lists missing facts for transparent follow-up
```

The workflow must preserve these boundaries:

- Platform anchor exists.
- Candidate public record exists.
- Candidate may or may not match the platform lead.
- Procurement intent may be visible, noisy, or mixed.
- Missing private fields stay missing unless the buyer supplies them transparently.

## Constrained Query Planning

The query planner should generate a matrix, not execute arbitrary broad searches.

For the Long Way example:

```text
"in19034126503jgqn"
"Long Way" "in19034126503jgqn"
"Long Way" Alibaba India buyer
"Long Way" India "Induction Cookers"
"Long Way" India "Gas Cooktops"
"Longway" India "induction cooktop"
"Longway" India official
"2200W Best Quality And Low Price Durable Electric Cook Top Induction Heating Plate"
"10T melting steel induction furnace" India buyer
```

The planner should also produce exclusion or caution notes:

- `Long Way` is a broad alias and cannot identify a subject alone.
- `Longway` may be a brand variant, but it is not automatically the same as `Long Way`.
- RFQ titles may be copied product titles and are weak identity evidence.
- Very broad category spread may indicate a trade/intermediary account or noisy buyer behavior.

## Candidate Discovery Rules

Candidates enter the system as candidate entities, not facts.

Allowed candidate statuses:

- `CANDIDATE`
- `LIKELY_MATCH`
- `CONFIRMED`
- `CONTRADICTED`
- `UNVERIFIED`
- `NEEDS_REVIEW`

Promotion rules:

- A candidate may become `LIKELY_MATCH` only when it matches at least two independent anchors, such as country + domain/brand + product category.
- A candidate may become `CONFIRMED` only when a platform-visible field, buyer-provided reply, official website, email domain, phone, registration record, or other strong evidence closes the identity.
- A real company record with no identity bridge remains `CANDIDATE`.
- A same-name public result with only broad name overlap remains `UNVERIFIED` or is discarded.

## ACH Scenarios

Sparse lead reports should include at least three competing hypotheses:

| Scenario | Meaning | Strengthening Evidence |
| --- | --- | --- |
| Alpha | Real B2B buyer or trade buyer with procurement intent. | Provides company identity, website, quantity, drawings/specs, destination, timeline. |
| Beta | Price benchmarking or quote collection. | Broad categories, generic RFQs, no project details, avoids identity disclosure. |
| Gamma | Same-name noise, personal account, or unmatched public candidate. | No company bridge, copied product titles, inconsistent category spread. |

The final report should state which scenario is least-disconfirmed, not claim absolute certainty.

## UI Design

The existing dashboard should stay dense and operational. Add a sparse lead intake panel to the create-task area:

- Target type select includes `弱线索买家`.
- When selected, the form expands into compact fields:
  - platform
  - display name
  - member ID
  - country/region
  - registration year
  - raw company field
  - categories
  - recent RFQs
  - notes
- Add a stage strip in the selected task view:
  - `锚点提取`
  - `约束检索`
  - `候选发现`
  - `身份匹配`
  - `ACH 判断`
  - `BLUF 报告`
  - `定向采集`

Graph placement:

- Platform anchors should appear near the seed.
- Candidate companies should be visually distinct from confirmed companies.
- Identity-match confidence should be visible in candidate detail.
- Unknown fields display `待补充`, never inferred filler.

## API Changes

Recommended create investigation payload:

```json
{
  "name": "Alibaba 买家弱线索：Long Way",
  "seed_type": "sparse_lead",
  "seed_value": "Long Way / in19034126503jgqn",
  "strategy": "deep",
  "metadata": {
    "platform": "Alibaba",
    "lead_display_name": "Long Way",
    "member_id": "in19034126503jgqn",
    "country_region": "IN"
  }
}
```

Recommended backend additions:

- Store `metadata_json` on investigations.
- Add `sparse_lead` to normalization and target labels.
- Add route templates in `intel_gateway.py`.
- Add entity labels for platform anchors and candidate fields.
- Add evidence kinds:
  - `platform_profile_screenshot`
  - `visible_buyer_anchor`
  - `candidate_public_record`
  - `identity_match_signal`
  - `identity_mismatch_signal`
  - `rfq_intent_signal`
  - `rfq_noise_signal`

## Data Integrity

Before implementation, fix the SQLite `add_jobs()` parity issue: follow-up jobs must preserve `planned.agent_role`, `planned.output_contract`, and `planned.depends_on`, matching MemoryStore behavior.

This prevents inferred sparse-lead jobs from losing why they were created or which agent role should execute them.

## Error Handling

- If no anchors are provided, reject `sparse_lead` creation with a clear validation message.
- If only a broad display name exists, create anchors but mark the task `NEEDS_REVIEW` after planning.
- If candidate discovery finds many same-name hits, keep them folded as review candidates.
- If no candidate is found, generate a BLUF explaining uncertainty and directed collection.
- If platform privacy hides contact information, report it as privacy state, not as missing system capability.

## Safety Rules

- Do not infer hidden email, phone, or private identity from platform-hidden fields.
- Do not use intrusive or credentialed enrichment unless explicitly configured and authorized.
- Do not merge candidate company and buyer identity without evidence.
- Do not present public CEO/director names as the account operator unless source evidence supports it.
- Business follow-up suggestions must be transparent: ask for company name, website, WhatsApp, drawings/specs, quantity, destination, standard, and timeline.

## Validation

Backend tests:

- `sparse_lead` normalizes and preserves human-readable seed values.
- Creating a sparse lead stores metadata anchors.
- Initial sparse-lead jobs include expected agent roles and output contracts.
- `quick`, `standard`, and `deep` strategies produce the right route subsets.
- SQLite and MemoryStore both preserve `agent_role`, `output_contract`, and `depends_on` in `add_jobs()`.
- Candidate confidence fields remain separate in generated schema or metadata.

Frontend checks:

- Target type dropdown includes `弱线索买家`.
- Sparse lead form fields appear only for that type.
- Created payload includes metadata.
- Stage strip renders from job statuses.
- Candidate confidence fields display without collapsing into one score.
- Existing company/domain/email/username/phone flows still work.

Recommended verification:

```bash
bash scripts/verify.sh
```

## First-Version Defaults

- Manual entry, no OCR.
- Deterministic route planning.
- Candidate-first reporting.
- Existing graph and report channels reused.
- No privacy bypass.
- Cautious language by default.
