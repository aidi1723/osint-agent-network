# Intelligence Core v3 Design

Version: 1.0
Updated: 2026-05-22
Status: Ready for implementation planning

## 1. Purpose

Intelligence Core v3 upgrades the project from an OSINT execution workbench into a stricter intelligence analysis workbench. The goal is to make every important conclusion answer three questions:

- Why is this conclusion credible?
- What remains uncertain?
- What should be collected next?

This phase focuses on the highest-leverage improvements for accuracy, stability, and operator trust:

1. PIR / EEI intelligence requirements.
2. Fact pool promotion stages.
3. Cross-verification matrix.
4. Fixed ACH and I&W report sections.
5. Whitepaper report structure aligned to professional intelligence reporting.

This design does not add intrusive collection, credential capture, bypass behavior, or non-public data access. It remains limited to authorized public-source research and transparent follow-up recommendations.

## 2. Current Baseline

The project already has:

- React/Vite dense operations UI.
- Python `http.server` API.
- SQLite persistence.
- Role-based investigation jobs.
- Evidence ledger.
- Fact records.
- ACH hypotheses.
- Quality gate.
- Whitepaper report area.
- Intelligence memory and directed collection hints.
- <production-host> systemd deployment.

The current gap is not basic execution. The gap is stricter analytical discipline: tasks need explicit intelligence requirements, facts need visible maturity stages, and key fields need a source-by-source verification view before entering the main conclusion.

## 3. Product Scope

### In Scope

- Add structured PIR and EEI fields to investigations.
- Generate default PIR / EEI from target type and sparse-lead metadata.
- Add fact promotion stages separate from existing analytical status.
- Add deterministic promotion rules based on evidence quality and source diversity.
- Add a cross-verification matrix derived from entities, evidence, evidence ledger, facts, and relationships.
- Show the matrix in the investigation detail UI.
- Include PIR answers, matrix summary, ACH, I&W, gaps, and directed collection in the whitepaper report.
- Add quality gate checks for PIR / EEI coverage and cross-verification coverage.

### Out of Scope For This Phase

- Full multi-user permissions.
- Audit log productization.
- PDF export.
- Large external source-reputation database.
- Machine-learning feedback model.
- Replacing SQLite with a graph database.
- Rebuilding the UI framework.

## 4. Core Concepts

### 4.1 PIR

PIR means Priority Intelligence Requirement. It is the question the investigation must answer.

Default PIR examples:

- Is the target organization real and operational?
- Does the target show credible purchase capacity or intent?
- Are the contact channels tied to the target by public evidence?
- Is the decision-maker candidate supported by public evidence?
- Are there risk, contradiction, fraud, sanctions, litigation, or reputation signals?

Each PIR should contain:

```json
{
  "id": "pir_identity",
  "question": "Is the target organization real and operational?",
  "priority": "high",
  "status": "OPEN",
  "answer": "",
  "confidence": 0.0,
  "linked_fact_ids": [],
  "remaining_gaps": []
}
```

Allowed PIR statuses:

- `OPEN`
- `PARTIAL`
- `ANSWERED`
- `BLOCKED`
- `NEEDS_REVIEW`

### 4.2 EEI

EEI means Essential Element of Information. It is the concrete field needed to answer one or more PIRs.

Default EEI examples:

- Legal or operating company name.
- Official website or domain.
- Public contact email.
- Public phone or WhatsApp.
- Address or operating region.
- Registration identifier.
- Business scope and product fit.
- Decision-maker candidate.
- Import, project, RFQ, or purchase-intent signal.
- Risk or contradiction signal.

Each EEI should contain:

```json
{
  "id": "eei_official_website",
  "label": "Official website or domain",
  "field_key": "official_website",
  "required": true,
  "status": "MISSING",
  "linked_entity_values": [],
  "linked_fact_ids": []
}
```

Allowed EEI statuses:

- `MISSING`
- `CANDIDATE`
- `SUPPORTED`
- `CONFIRMED`
- `CONFLICTED`

### 4.3 Fact Promotion Stage

Existing fact status currently represents analytical judgement such as `CONFIRMED`, `LIKELY`, or `NEEDS_REVIEW`. Core v3 adds a separate promotion stage that describes where the fact sits in the intelligence production pipeline.

Allowed promotion stages:

- `RAW_OBSERVATION`: observed from a source or tool output, not yet interpreted.
- `CANDIDATE_FACT`: plausible field or claim, not enough evidence for main conclusion.
- `ASSESSED_FACT`: evaluated with source quality and context.
- `ACCEPTED_FACT`: strong enough for whitepaper conclusion and primary graph display.
- `REJECTED_FACT`: known noise, contradiction, or disproven candidate.

Promotion rules:

- A single tool-only hit can reach at most `CANDIDATE_FACT`.
- A primary source such as official website or government registry can reach `ASSESSED_FACT`.
- Two independent supporting sources with no direct contradiction can reach `ACCEPTED_FACT`.
- A primary source plus one independent contextual source can reach `ACCEPTED_FACT`.
- Any direct contradiction blocks automatic acceptance and sets `NEEDS_REVIEW` or `REJECTED_FACT`.
- Identity matching for sparse leads must separate `record_confidence` from `identity_match_confidence`.

### 4.4 Cross-Verification Matrix

The cross-verification matrix is a derived analytical view. It summarizes how key fields are supported or contradicted across source families.

Default matrix fields:

- Company identity.
- Official website.
- Contact email.
- Contact phone / WhatsApp.
- Address / operating region.
- Registration information.
- Business scope / product fit.
- Decision-maker candidate.
- Purchase intent.
- Risk signal.

Source families:

- `official`
- `registry`
- `news`
- `directory`
- `social`
- `tool`
- `operator`
- `unknown`

Each matrix row should contain:

```json
{
  "field_key": "contact_email",
  "label": "Contact email",
  "candidate_value": "sales@example.com",
  "supporting_sources": ["official", "tool"],
  "contradicting_sources": [],
  "source_count": 2,
  "independent_source_count": 2,
  "best_admiralty_code": "A-2",
  "status": "LIKELY",
  "confidence": 0.78,
  "linked_evidence_ids": ["ev-1"],
  "linked_fact_ids": ["fact-1"],
  "rationale": "Official contact page and tool extraction agree on the same email."
}
```

Allowed matrix statuses:

- `MISSING`
- `CANDIDATE`
- `SUPPORTED`
- `LIKELY`
- `CONFIRMED`
- `CONFLICTED`
- `NEEDS_REVIEW`

The matrix must be deterministic and derived from stored records. Operators should be able to refresh an investigation and receive the same matrix for the same data.

## 5. Data Model

### 5.1 Investigation Metadata

To avoid heavy migration risk, PIR and EEI can first be stored in `investigations.metadata_json` under:

```json
{
  "intelligence_requirements": {
    "decision_context": "",
    "confidence_requirement": "standard",
    "pirs": [],
    "eeis": []
  }
}
```

This keeps Core v3 compatible with existing SQLite deployments and existing API responses.

### 5.2 Facts Table

Add `promotion_stage` to `facts`:

```sql
ALTER TABLE facts ADD COLUMN promotion_stage TEXT NOT NULL DEFAULT 'CANDIDATE_FACT';
```

Existing records should map as:

- `CONFIRMED` -> `ACCEPTED_FACT`
- `LIKELY` -> `ASSESSED_FACT`
- `CONTRADICTED` -> `REJECTED_FACT`
- `NEEDS_REVIEW` -> `CANDIDATE_FACT`
- `RETIRED` -> `REJECTED_FACT`

The app should tolerate legacy rows without this column during migration.

### 5.3 Derived Matrix

The matrix does not need a table in this phase. It should be derived in backend core logic and included in investigation detail responses:

```json
{
  "cross_verification_matrix": []
}
```

The UI consumes this array directly.

## 6. Backend Components

### 6.1 Requirements Builder

Create a core module responsible for defaults and normalization:

```text
backend/app/core/intelligence_requirements.py
```

Responsibilities:

- Build default PIR / EEI sets from `seed_type`, `seed_value`, `strategy`, and metadata.
- Normalize user-provided PIR / EEI payloads.
- Ensure stable IDs.
- Provide coverage scoring helpers.

### 6.2 Fact Promotion

Extend:

```text
backend/app/core/fact_pool.py
```

Responsibilities:

- Define `FACT_PROMOTION_STAGES`.
- Validate `promotion_stage`.
- Provide `promotion_stage_for_fact(fact, evidence_ledger, relationships)`.
- Keep status and promotion stage separate.

### 6.3 Cross-Verification Matrix

Create:

```text
backend/app/core/cross_verification.py
```

Responsibilities:

- Classify evidence source family.
- Map entities and facts to matrix fields.
- Count source diversity.
- Detect contradictions from facts with `CONTRADICTED`, negative evidence kinds, or conflicting values for the same field.
- Generate deterministic field rows.
- Provide rationale strings short enough for UI display.

### 6.4 Quality Gate

Extend:

```text
backend/app/core/quality.py
```

New checks:

- PIR exists.
- Required EEI coverage.
- Cross-verification has at least one `CONFIRMED` or `LIKELY` identity row.
- Accepted facts exist before completion.

Completion should remain conservative. Missing Core v3 fields should not crash old tasks, but should lower quality readiness.

### 6.5 Report Rendering

Extend `render_structured_report()` to include:

- PIR answers.
- EEI coverage summary.
- Cross-verification matrix summary.
- ACH section.
- I&W section.
- Intelligence gaps.
- Directed collection.
- Evidence appendix.

The BLUF must stay first.

## 7. API Behavior

### 7.1 Create Investigation

`POST /api/investigations` should accept optional:

```json
{
  "intelligence_requirements": {
    "decision_context": "qualify buyer lead",
    "confidence_requirement": "standard",
    "pirs": [],
    "eeis": []
  }
}
```

If omitted, the backend generates defaults.

### 7.2 Get Investigation Detail

`GET /api/investigations/{id}` should include:

```json
{
  "intelligence_requirements": {},
  "cross_verification_matrix": []
}
```

The response should remain backward compatible for the current frontend.

### 7.3 Agent Writeback

No new mandatory Agent API route is required in this phase. Agents can continue writing entities, evidence, evidence ledger, facts, and hypotheses. Core v3 derives requirements coverage and matrix status from those records.

Later phases can add explicit Agent updates for PIR answers if needed.

## 8. Frontend UX

Follow `DESIGN.md`: dense technical operations console, compact panels, no landing-page treatment, no decorative cards.

### 8.1 Task Creation

Add a compact "情报需求" section:

- Decision context select or text input.
- Confidence requirement segmented control: `quick`, `standard`, `strict`.
- Default PIR preview.
- Required EEI preview.

The first implementation can keep PIR / EEI editable through compact text fields or generated defaults. It does not need a large wizard.

### 8.2 Detail Page

Add three panels near the current report and quality areas:

1. `情报需求`
   - PIR status list.
   - EEI coverage chips.
   - Missing required fields.

2. `交叉验证矩阵`
   - Table with field, candidate value, source families, status, confidence, rationale.
   - Highlight `CONFLICTED` and `NEEDS_REVIEW`.
   - Keep rows compact and scannable.

3. `事实晋级`
   - Show counts by promotion stage.
   - Show accepted facts and candidates needing review.

The whitepaper remains a primary panel. The quality gate remains visible but secondary.

## 9. UI Placement

Recommended order in investigation detail:

1. Executive cockpit metrics.
2. Graph.
3. Intelligence requirements and queue.
4. Whitepaper report.
5. Cross-verification matrix.
6. Fact promotion and evidence ledger.
7. Quality gate and audit panels.

The exact layout may adapt to available space, but whitepaper and matrix should have enough width to be useful.

## 10. Report Structure

Core v3 whitepaper format:

```text
BLUF
PIR Answers
Key Judgements
Cross-Verification Summary
Accepted Facts
ACH / Competing Hypotheses
I&W Indicators
Uncertainty And Intelligence Gaps
Directed Collection Plan
Business Follow-Up Recommendation
Evidence Appendix
```

Report rules:

- The report must distinguish known facts, assessed judgements, and open gaps.
- The report must avoid absolute certainty except when quoting official records.
- Sparse-lead reports must keep record confidence separate from identity-match confidence.
- Business recommendations must be transparent requests for missing information, not deceptive probes.

## 11. Testing Strategy

Backend tests:

- Default PIR / EEI generation for `company`, `sparse_lead`, `domain`, and `email`.
- Legacy metadata without requirements still loads.
- Fact promotion migration preserves existing facts.
- Cross-verification matrix confirms official + tool support.
- Cross-verification matrix flags conflicting values.
- Quality gate lowers readiness when PIR / EEI coverage is missing.
- Structured report includes BLUF, PIR answers, matrix summary, ACH, I&W, gaps, and evidence appendix.

Frontend tests:

- UI state helpers label Core v3 statuses.
- Cross-verification matrix helper sorts rows by priority and severity.
- Report sanitization still applies.
- Build passes.

End-to-end smoke:

- Create a sparse-lead task.
- Run quick jobs.
- Verify PIR / EEI exist.
- Verify matrix rows render.
- Verify whitepaper contains PIR answers and directed collection.

## 12. Migration And Rollback

Migration must be safe for <production-host>:

- Backup `data/osint.sqlite` before deployment.
- Additive schema change only.
- Derived matrix requires no persisted table.
- If deployment fails, restore previous app directory and database backup.

Rollback compatibility:

- Old rows without `promotion_stage` should continue loading after migration.
- Existing report rendering should continue even if requirements metadata is absent.

## 13. Acceptance Criteria

Core v3 is accepted when:

- `bash scripts/verify.sh` passes locally.
- `bash scripts/verify.sh` passes on <production-host> after deployment.
- New investigations include default PIR / EEI.
- Existing investigations load without manual migration.
- Facts include promotion stages.
- Investigation detail includes `cross_verification_matrix`.
- UI shows intelligence requirements and matrix without layout crowding.
- Whitepaper starts with BLUF and includes PIR answers, matrix summary, ACH, I&W, gaps, and next collection actions.
- Quality gate reflects Core v3 readiness without blocking old tasks from opening.

## 14. Risks And Controls

Risk: More fields could make task creation slower.
Control: Generate defaults and keep editing compact.

Risk: Matrix may overstate confidence from duplicated sources.
Control: Count source families and source independence, not raw evidence count alone.

Risk: Existing tasks may lack requirement metadata.
Control: Generate derived defaults at read time when metadata is absent.

Risk: UI becomes crowded.
Control: Use compact tables, chips, and collapsible secondary sections under the existing dense console style.

Risk: Promotion logic could hide useful weak leads.
Control: Weak leads remain visible as candidates; they simply do not enter accepted conclusions without support.

