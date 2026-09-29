# Intelligence Officer Core Design

Date: 2026-05-20
Project: OSINT Agent Network

## Purpose

Turn the current OSINT workflow from a search-and-summary assistant into a stricter intelligence-officer core. The first implementation should make analytic discipline reusable in backend code: facts remain traceable, weak or single-source findings stay tentative, competing hypotheses are tested with contradiction-first logic, and reports can use BLUF, Admiralty Code, ACH, and I&W indicators without relying on ad hoc prompting.

This phase intentionally avoids UI changes. It creates tested backend assets that later agents, workers, reports, or API routes can call.

## Scope

First version:

- Add a machine-readable intelligence schema contract.
- Add an industry indicator matrix for Alibaba, foreign trade, building materials, doors/windows, and supply-chain signals.
- Add a lightweight ACH engine with contradiction scoring and indicator activation scoring.
- Expose pure Python helpers that can be reused by `cross_verification_agent` and `analysis_judgement_agent`.
- Add unit tests for schema loading, Admiralty-related examples, ACH falsification behavior, and indicator activation rate.
- Preserve the existing tool gateway, worker, store, and frontend behavior.

Out of scope for this version:

- Frontend graph/report display changes.
- New third-party APIs such as Brave Search, Serper, Panjiva, or ImportGenius.
- Automatic deception, counter-information, or competitor-interference execution.
- Replacing existing `verification.py`; the new engine should extend it, not fork the scoring model.
- LLM calls inside the ACH engine. The first version must be deterministic and testable.

## Intelligence Assets

### `intel_schema.json`

Location:

```text
backend/app/core/intel_schema.json
```

Responsibilities:

- Define normalized contracts for entities, evidence, relationships, claims, hypotheses, indicators, reports, and directed collection actions.
- Encode the rule that unknown fields are written as `unknown`, `unconfirmed`, or `待补充`, never invented.
- Separate `record_confidence`, `identity_match_confidence`, and `field_interpretation_confidence` for sparse Alibaba/CRM leads.
- Define Admiralty Code fields: `source_reliability`, `information_credibility`, `code`, and `probability_language`.
- Define candidate status values such as `CONFIRMED`, `CANDIDATE`, `CONTRADICTED`, `UNVERIFIED`, and `NEEDS_REVIEW`.

The schema is a contract and documentation asset first. The first implementation should include a loader and basic shape validation, but it does not need a full JSON Schema validator dependency.

### `indicator_matrix.yaml`

Location:

```text
backend/app/core/indicator_matrix.yaml
```

Responsibilities:

- Convert recurring business-intelligence signs into stable indicators.
- Group indicators by scenario: real procurement, price-shopping, same-name noise, hard-asset confirmation, supply-chain movement, news/business change, and evidence uncertainty.
- Assign each indicator a weight, polarity, evidence kinds, and optional keywords.
- Support triggered-indicator scoring for I&W output.

Example indicator families:

- `IND_PROJECT_SPEC_PROVIDED`: buyer provides drawings, quantity, destination, standards, or timeline.
- `IND_GENERIC_PRICE_ONLY`: buyer asks only generic price or MOQ and avoids project details.
- `IND_HARD_ASSET_IMPORT`: public or authorized import/customs data indicates relevant HS code or cargo movement.
- `IND_OFFICIAL_REGISTRY_MATCH`: official registry confirms company name, address, or NIT/RUES-style identifier.
- `IND_SAME_NAME_NOISE`: broad same-name result lacks country, company, contact, or product constraints.
- `IND_SUPPLY_CHAIN_SHIFT`: hiring, warehouse, project, supplier, or logistics signal suggests procurement change.

### `ach_engine.py`

Location:

```text
backend/app/core/ach_engine.py
```

Responsibilities:

- Provide deterministic ACH and I&W helpers.
- Accept explicit hypotheses and evidence items.
- Score each evidence item against each hypothesis as supporting, contradictory, or neutral.
- Prefer contradiction-first elimination: hypotheses with the largest contradiction burden become less likely even if they have some supporting evidence.
- Return the least-disconfirmed hypothesis, not a single overconfident prediction.
- Return triggered indicators and indicator activation rate.

Recommended API:

```python
load_intel_schema() -> dict
load_indicator_matrix() -> dict
score_triggered_indicators(evidence_items, indicators=None) -> IndicatorScore
run_ach_analysis(hypotheses, evidence_items, indicators=None) -> AchResult
```

Recommended dataclasses:

```python
EvidenceItem(
    id: str,
    summary: str,
    kinds: tuple[str, ...],
    supports: tuple[str, ...] = (),
    contradicts: tuple[str, ...] = (),
    source_reliability: str = "unknown",
    credibility: float = 0.0,
    keywords: tuple[str, ...] = (),
)

Hypothesis(
    id: str,
    statement: str,
    mutually_exclusive_group: str = "default",
)
```

Output shape:

```json
{
  "most_likely_hypothesis": "alpha",
  "hypotheses": [
    {
      "id": "alpha",
      "statement": "Real B2B buyer comparing suppliers for a live project",
      "supporting_evidence": ["E1"],
      "contradictory_evidence": ["E3"],
      "inconsistency_score": 0.24,
      "status": "MOST_LIKELY"
    }
  ],
  "triggered_indicators": ["IND_PROJECT_SPEC_PROVIDED"],
  "indicator_activation_rate": 0.5,
  "confidence_language": "有可能"
}
```

## ACH Behavior

The default Alibaba sparse-lead hypothesis set should include at least:

- `alpha_real_procurement`: real B2B buyer comparing suppliers for a live project or supply-chain replacement.
- `beta_price_benchmarking`: buyer is collecting quotes to pressure an incumbent supplier or benchmark the market.
- `gamma_noise_or_unmatched_identity`: same-name noise, personal account, or insufficient company/procurement evidence.

The engine should not invent evidence. If all evidence is weak or neutral, the result should say that the most likely hypothesis is still low confidence and recommend directed collection.

Contradiction logic:

- Supporting evidence reduces a hypothesis score modestly.
- Contradictory evidence increases inconsistency strongly.
- Stronger source reliability and credibility increase evidence impact.
- A hypothesis with many contradictions should be marked `DISFAVORED` or `REJECTED` even if it also has support.
- If two hypotheses remain close, status should stay cautious: `PLAUSIBLE`, not forced certainty.

## Data Flow

The first version adds reusable core functions without changing runtime orchestration:

```text
entities/evidence/relationships
  -> cross_verification_agent can assign Admiralty and conflict notes
  -> ach_engine scores hypotheses and indicators
  -> analysis_judgement_agent can compose BLUF, ACH, I&W, directed collection
  -> existing report_markdown remains the delivery channel
```

The implementation should keep functions independent from `MemoryStore`, `SQLiteStore`, and HTTP handlers so they are easy to test and reuse.

## Error Handling

- Missing schema or matrix files should raise a clear `FileNotFoundError` or `ValueError` during explicit load.
- Malformed indicator entries should be skipped only if non-critical; required fields should fail tests.
- Empty hypothesis input should return no winner and a low-confidence result rather than throwing in normal report generation.
- Empty evidence input should keep all hypotheses as `PLAUSIBLE` or `UNVERIFIED` and set activation rate to `0.0`.

## Safety Rules

- The system may recommend transparent business follow-up questions.
- The system must not generate executable deception, counter-information, or competitor-interference actions.
- Paid or operator-provided customs data must be labeled by source type and must not be described as official unless it is official.
- Single-source data remains tentative unless it is an authoritative A-grade source or cross-confirmed.
- Candidate company, candidate decision maker, and CRM/Alibaba lead identity remain separate until evidence closes the identity match.

## Validation

Backend tests should cover:

- Schema loader returns required top-level sections.
- Indicator matrix loader returns expected indicator IDs.
- `score_triggered_indicators` activates indicators from evidence kinds and keywords.
- Indicator activation rate is deterministic and bounded between `0.0` and `1.0`.
- ACH picks the hypothesis with the fewest weighted contradictions.
- ACH marks contradiction-heavy hypotheses as `DISFAVORED` or `REJECTED`.
- Sparse or empty evidence does not force an overconfident conclusion.
- Existing `admiralty_code` helper still maps official/high-credibility examples to `A-1` or `A-2`, and weak/single-source examples to lower reliability.

Recommended command:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_intelligence_officer_core
```

## First-Version Defaults

- Deterministic, no LLM calls.
- Pure functions and dataclasses before service integration.
- YAML parser should use the standard library if possible, or a small fallback parser for the limited matrix shape. Avoid adding a dependency unless the project already has one available.
- Existing reports can manually call the helpers later; this phase only makes the core available and tested.
- Keep all language cautious and evidence-bound.
