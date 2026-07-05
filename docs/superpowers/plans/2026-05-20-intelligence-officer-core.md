# Intelligence Officer Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic intelligence-officer core assets for schema contracts, indicator scoring, and ACH contradiction analysis.

**Architecture:** The implementation adds two data assets and one pure-Python core module under `backend/app/core`. Tests drive the public API first, then implementation fills the smallest reusable surface needed by future `cross_verification_agent` and `analysis_judgement_agent` flows.

**Tech Stack:** Python standard library, `unittest`, JSON assets, YAML-like indicator asset parsed by a small built-in parser with optional PyYAML fallback.

---

## File Structure

- Create `backend/app/core/intel_schema.json`: machine-readable contract for intelligence records, unknown fields, confidence fields, Admiralty fields, and report sections.
- Create `backend/app/core/indicator_matrix.yaml`: deterministic indicator definitions for Alibaba/foreign-trade/building-material scenarios.
- Create `backend/app/core/ach_engine.py`: dataclasses, asset loaders, indicator scoring, ACH scoring, and default sparse-lead hypotheses.
- Create `backend/tests/test_intelligence_officer_core.py`: focused unit tests for loaders, indicators, ACH behavior, and Admiralty examples.
- Modify `backend/tests/test_core.py`: only if an Admiralty edge-case assertion is better placed with existing verification tests.

## Task 1: Test Intelligence Asset Loaders

**Files:**
- Create: `backend/tests/test_intelligence_officer_core.py`
- Create later: `backend/app/core/ach_engine.py`
- Create later: `backend/app/core/intel_schema.json`
- Create later: `backend/app/core/indicator_matrix.yaml`

- [ ] **Step 1: Write the failing loader tests**

Create `backend/tests/test_intelligence_officer_core.py` with:

```python
import unittest

from app.core.ach_engine import load_indicator_matrix, load_intel_schema


class IntelligenceAssetLoaderTests(unittest.TestCase):
    def test_loads_intel_schema_required_sections(self):
        schema = load_intel_schema()

        self.assertIn("entities", schema)
        self.assertIn("evidence", schema)
        self.assertIn("claims", schema)
        self.assertIn("admiralty_code", schema)
        self.assertIn("reports", schema)
        self.assertIn("unknown_markers", schema)
        self.assertIn("identity_confidence_fields", schema["entities"])
        self.assertIn("record_confidence", schema["entities"]["identity_confidence_fields"])
        self.assertIn("identity_match_confidence", schema["entities"]["identity_confidence_fields"])

    def test_loads_indicator_matrix_expected_ids(self):
        matrix = load_indicator_matrix()
        indicator_ids = {indicator["id"] for indicator in matrix["indicators"]}

        self.assertIn("IND_PROJECT_SPEC_PROVIDED", indicator_ids)
        self.assertIn("IND_GENERIC_PRICE_ONLY", indicator_ids)
        self.assertIn("IND_HARD_ASSET_IMPORT", indicator_ids)
        self.assertIn("IND_OFFICIAL_REGISTRY_MATCH", indicator_ids)
        self.assertIn("IND_SAME_NAME_NOISE", indicator_ids)
        self.assertIn("IND_SUPPLY_CHAIN_SHIFT", indicator_ids)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify import failure**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_officer_core
```

Expected: FAIL because `app.core.ach_engine` does not exist.

- [ ] **Step 3: Add minimal module and asset loaders**

Create `backend/app/core/ach_engine.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CORE_DIR = Path(__file__).resolve().parent


def load_intel_schema(path: str | Path | None = None) -> dict[str, Any]:
    schema_path = Path(path) if path is not None else CORE_DIR / "intel_schema.json"
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    _require_keys(schema, ("entities", "evidence", "claims", "admiralty_code", "reports"))
    return schema


def load_indicator_matrix(path: str | Path | None = None) -> dict[str, Any]:
    matrix_path = Path(path) if path is not None else CORE_DIR / "indicator_matrix.yaml"
    text = matrix_path.read_text(encoding="utf-8")
    return _parse_indicator_matrix(text)


def _require_keys(data: dict[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ValueError(f"Missing required intelligence schema keys: {', '.join(missing)}")


def _parse_indicator_matrix(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None
    if yaml is not None:
        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict):
            return parsed
    return _parse_simple_indicator_yaml(text)


def _parse_simple_indicator_yaml(text: str) -> dict[str, Any]:
    indicators: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_list_key = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "indicators:":
            continue
        if stripped.startswith("- id:"):
            if current:
                indicators.append(current)
            current = {"id": _yaml_scalar(stripped.split(":", 1)[1].strip())}
            current_list_key = ""
            continue
        if current is None:
            continue
        if stripped.startswith("- ") and current_list_key:
            current[current_list_key].append(_yaml_scalar(stripped[2:].strip()))
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                current[key] = []
                current_list_key = key
            else:
                current[key] = _yaml_scalar(value)
                current_list_key = ""
    if current:
        indicators.append(current)
    return {"indicators": indicators}


def _yaml_scalar(value: str) -> Any:
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value in {"true", "false"}:
        return value == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value
```

- [ ] **Step 4: Add the intelligence schema asset**

Create `backend/app/core/intel_schema.json`:

```json
{
  "version": "0.1",
  "unknown_markers": ["unknown", "unconfirmed", "待补充", "未在公开来源中确认"],
  "entities": {
    "required_fields": ["type", "value", "source_tool", "confidence"],
    "status_values": ["CONFIRMED", "CANDIDATE", "CONTRADICTED", "UNVERIFIED", "NEEDS_REVIEW"],
    "identity_confidence_fields": [
      "record_confidence",
      "identity_match_confidence",
      "field_interpretation_confidence"
    ],
    "candidate_rules": [
      "Keep CRM lead identity, public company record, and decision-maker profile separate until evidence closes the identity match.",
      "Do not promote broad same-name hits without country, platform, company, contact, product, or independent corroboration."
    ]
  },
  "evidence": {
    "required_fields": ["kind", "source_tool", "snippet"],
    "source_type_values": [
      "official_website",
      "government_registry",
      "regulatory_filing",
      "original_social_profile",
      "mainstream_media",
      "industry_association",
      "business_directory",
      "job_board",
      "map_listing",
      "search_result",
      "aggregator",
      "tool_output",
      "single_weak_signal",
      "anonymous_forum",
      "unknown"
    ]
  },
  "relationships": {
    "required_fields": ["from", "to", "type", "confidence"],
    "direction_required": true
  },
  "claims": {
    "required_fields": ["statement", "status", "supporting_evidence"],
    "status_values": ["CONFIRMED", "LIKELY", "PLAUSIBLE", "UNVERIFIED", "CONTRADICTED"]
  },
  "admiralty_code": {
    "source_reliability": ["A", "B", "C", "D", "E", "F"],
    "information_credibility": ["1", "2", "3", "4", "5", "6"],
    "required_fields": ["code", "source_reliability", "information_credibility", "probability_language"]
  },
  "hypotheses": {
    "default_sparse_lead": [
      "alpha_real_procurement",
      "beta_price_benchmarking",
      "gamma_noise_or_unmatched_identity"
    ],
    "status_values": ["MOST_LIKELY", "PLAUSIBLE", "DISFAVORED", "REJECTED", "UNVERIFIED"]
  },
  "indicators": {
    "required_fields": ["id", "scenario", "weight", "polarity", "evidence_kinds"]
  },
  "reports": {
    "required_sections": ["BLUF", "PIR", "confirmed_facts", "ACH", "I&W", "directed_collection", "recommendations"],
    "language_rule": "Use cautious evidence-bound language. Unknown fields must remain unknown or 待补充."
  }
}
```

- [ ] **Step 5: Add the indicator matrix asset**

Create `backend/app/core/indicator_matrix.yaml`:

```yaml
version: "0.1"
indicators:
  - id: IND_PROJECT_SPEC_PROVIDED
    scenario: real_procurement
    description: Buyer provides drawings, quantity, destination, standards, or timeline.
    weight: 0.28
    polarity: positive
    evidence_kinds:
      - project_specification
      - drawing_provided
      - quantity_destination_timeline
    keywords:
      - drawing
      - drawings
      - specification
      - quantity
      - destination
      - timeline
      - standard
      - project
  - id: IND_GENERIC_PRICE_ONLY
    scenario: price_benchmarking
    description: Buyer asks only for generic price, MOQ, or catalog without project constraints.
    weight: 0.22
    polarity: caution
    evidence_kinds:
      - generic_price_request
      - moq_only_request
      - catalog_only_request
    keywords:
      - price
      - moq
      - catalog
      - quotation
  - id: IND_HARD_ASSET_IMPORT
    scenario: hard_asset_confirmation
    description: Public or authorized import/customs data indicates relevant HS code, cargo, or container movement.
    weight: 0.34
    polarity: positive
    evidence_kinds:
      - customs_record
      - bill_of_lading
      - import_record
    keywords:
      - HS
      - 7604
      - 7007
      - import
      - customs
      - bill of lading
      - container
  - id: IND_OFFICIAL_REGISTRY_MATCH
    scenario: hard_asset_confirmation
    description: Official registry confirms company name, address, identifier, or active registration.
    weight: 0.3
    polarity: positive
    evidence_kinds:
      - government_registry
      - regulatory_filing
      - official_company_record
    keywords:
      - registry
      - registration
      - NIT
      - RUES
      - chamber
      - active
  - id: IND_SAME_NAME_NOISE
    scenario: identity_uncertainty
    description: Broad same-name result lacks country, platform, company, contact, or product constraints.
    weight: 0.26
    polarity: negative
    evidence_kinds:
      - same_name_noise
      - weak_search_hit
      - unrelated_public_figure
    keywords:
      - same name
      - unrelated
      - athlete
      - football
      - music
      - crime
      - prison
  - id: IND_SUPPLY_CHAIN_SHIFT
    scenario: supply_chain_movement
    description: Hiring, warehouse, project, supplier, logistics, or expansion signal suggests procurement change.
    weight: 0.24
    polarity: positive
    evidence_kinds:
      - job_board
      - warehouse_signal
      - supplier_change
      - logistics_signal
      - project_news
    keywords:
      - hiring
      - warehouse
      - supplier
      - logistics
      - expansion
      - project
```

- [ ] **Step 6: Run loader tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_officer_core
```

Expected: PASS for the two loader tests.

- [ ] **Step 7: Commit if repository metadata is available**

Run:

```bash
git status --short
```

Expected: If this directory is a git repository, review changed files, then commit:

```bash
git add backend/app/core/ach_engine.py backend/app/core/intel_schema.json backend/app/core/indicator_matrix.yaml backend/tests/test_intelligence_officer_core.py
git commit -m "feat: add intelligence officer assets"
```

If `git status` reports `fatal: not a git repository`, skip the commit and record that verification was run without committing.

## Task 2: Implement Indicator Scoring

**Files:**
- Modify: `backend/app/core/ach_engine.py`
- Modify: `backend/tests/test_intelligence_officer_core.py`

- [ ] **Step 1: Add failing indicator scoring tests**

Append to `backend/tests/test_intelligence_officer_core.py`:

```python
from app.core.ach_engine import EvidenceItem, score_triggered_indicators


class IndicatorScoringTests(unittest.TestCase):
    def test_scores_triggered_indicators_from_kinds_and_keywords(self):
        evidence = [
            EvidenceItem(
                id="E1",
                summary="Buyer provided drawings, destination, and project timeline.",
                kinds=("project_specification",),
                supports=("alpha_real_procurement",),
                source_reliability="B",
                credibility=0.8,
                keywords=("drawings", "destination", "timeline"),
            ),
            EvidenceItem(
                id="E2",
                summary="Authorized import record includes HS 7604.",
                kinds=("customs_record",),
                supports=("alpha_real_procurement",),
                source_reliability="B",
                credibility=0.75,
                keywords=("HS", "7604", "import"),
            ),
        ]

        result = score_triggered_indicators(evidence)

        self.assertIn("IND_PROJECT_SPEC_PROVIDED", result.triggered_ids)
        self.assertIn("IND_HARD_ASSET_IMPORT", result.triggered_ids)
        self.assertGreater(result.activation_rate, 0)
        self.assertLessEqual(result.activation_rate, 1)
        self.assertGreater(result.score, 0)

    def test_empty_evidence_has_zero_activation(self):
        result = score_triggered_indicators([])

        self.assertEqual(result.triggered_ids, [])
        self.assertEqual(result.activation_rate, 0.0)
        self.assertEqual(result.score, 0.0)
```

- [ ] **Step 2: Run tests to verify missing symbols**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_officer_core
```

Expected: FAIL because `EvidenceItem` and `score_triggered_indicators` are not implemented.

- [ ] **Step 3: Add dataclasses and indicator scoring**

Modify `backend/app/core/ach_engine.py` by adding these imports and classes after the existing imports:

```python
from dataclasses import dataclass
```

Add after `CORE_DIR`:

```python
@dataclass(frozen=True)
class EvidenceItem:
    id: str
    summary: str
    kinds: tuple[str, ...]
    supports: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()
    source_reliability: str = "unknown"
    credibility: float = 0.0
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class IndicatorScore:
    triggered_ids: list[str]
    activation_rate: float
    score: float
```

Add after `load_indicator_matrix`:

```python
def score_triggered_indicators(
    evidence_items: list[EvidenceItem],
    indicators: list[dict[str, Any]] | None = None,
) -> IndicatorScore:
    matrix_indicators = indicators if indicators is not None else load_indicator_matrix().get("indicators", [])
    if not evidence_items or not matrix_indicators:
        return IndicatorScore(triggered_ids=[], activation_rate=0.0, score=0.0)

    triggered: list[str] = []
    weighted_score = 0.0
    total_possible = sum(abs(float(indicator.get("weight", 0.0))) for indicator in matrix_indicators)
    for indicator in matrix_indicators:
        if _indicator_matches(indicator, evidence_items):
            indicator_id = str(indicator["id"])
            triggered.append(indicator_id)
            weighted_score += abs(float(indicator.get("weight", 0.0)))

    if total_possible <= 0:
        activation_rate = 0.0
    else:
        activation_rate = round(min(1.0, weighted_score / total_possible), 4)
    return IndicatorScore(
        triggered_ids=triggered,
        activation_rate=activation_rate,
        score=round(weighted_score, 4),
    )


def _indicator_matches(indicator: dict[str, Any], evidence_items: list[EvidenceItem]) -> bool:
    expected_kinds = {str(kind).lower() for kind in indicator.get("evidence_kinds", [])}
    expected_keywords = {str(keyword).lower() for keyword in indicator.get("keywords", [])}
    for evidence in evidence_items:
        evidence_kinds = {kind.lower() for kind in evidence.kinds}
        evidence_keywords = {keyword.lower() for keyword in evidence.keywords}
        summary = evidence.summary.lower()
        if expected_kinds and evidence_kinds.intersection(expected_kinds):
            return True
        if expected_keywords and evidence_keywords.intersection(expected_keywords):
            return True
        if expected_keywords and any(keyword in summary for keyword in expected_keywords):
            return True
    return False
```

- [ ] **Step 4: Run indicator tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_officer_core
```

Expected: PASS for loader and indicator tests.

- [ ] **Step 5: Commit if repository metadata is available**

Run:

```bash
git status --short
```

Expected: If this directory is a git repository, commit:

```bash
git add backend/app/core/ach_engine.py backend/tests/test_intelligence_officer_core.py
git commit -m "feat: score intelligence indicators"
```

If not a git repository, skip the commit.

## Task 3: Implement ACH Contradiction Analysis

**Files:**
- Modify: `backend/app/core/ach_engine.py`
- Modify: `backend/tests/test_intelligence_officer_core.py`

- [ ] **Step 1: Add failing ACH tests**

Append to `backend/tests/test_intelligence_officer_core.py`:

```python
from app.core.ach_engine import Hypothesis, run_ach_analysis


class AchEngineTests(unittest.TestCase):
    def test_ach_prefers_fewest_weighted_contradictions(self):
        hypotheses = [
            Hypothesis("alpha_real_procurement", "Real B2B buyer comparing suppliers for a live project"),
            Hypothesis("beta_price_benchmarking", "Buyer is benchmarking price to pressure an incumbent supplier"),
            Hypothesis("gamma_noise_or_unmatched_identity", "Same-name noise or insufficient identity match"),
        ]
        evidence = [
            EvidenceItem(
                id="E1",
                summary="Buyer supplied drawings, quantity, destination, and timeline.",
                kinds=("project_specification",),
                supports=("alpha_real_procurement",),
                contradicts=("gamma_noise_or_unmatched_identity",),
                source_reliability="B",
                credibility=0.8,
                keywords=("drawings", "quantity", "destination", "timeline"),
            ),
            EvidenceItem(
                id="E2",
                summary="Official registry confirms a matching active company.",
                kinds=("government_registry",),
                supports=("alpha_real_procurement",),
                contradicts=("gamma_noise_or_unmatched_identity",),
                source_reliability="A",
                credibility=0.92,
                keywords=("registry", "active"),
            ),
            EvidenceItem(
                id="E3",
                summary="Buyer also asked for generic MOQ.",
                kinds=("generic_price_request",),
                supports=("beta_price_benchmarking",),
                source_reliability="C",
                credibility=0.55,
                keywords=("moq", "price"),
            ),
        ]

        result = run_ach_analysis(hypotheses, evidence)

        self.assertEqual(result.most_likely_hypothesis, "alpha_real_procurement")
        statuses = {item["id"]: item["status"] for item in result.hypotheses}
        self.assertEqual(statuses["alpha_real_procurement"], "MOST_LIKELY")
        self.assertIn(statuses["gamma_noise_or_unmatched_identity"], {"DISFAVORED", "REJECTED"})
        self.assertIn("IND_PROJECT_SPEC_PROVIDED", result.triggered_indicators)
        self.assertGreater(result.indicator_activation_rate, 0)

    def test_ach_does_not_force_winner_without_evidence(self):
        hypotheses = [
            Hypothesis("alpha_real_procurement", "Real B2B buyer"),
            Hypothesis("beta_price_benchmarking", "Price benchmarking"),
        ]

        result = run_ach_analysis(hypotheses, [])

        self.assertEqual(result.most_likely_hypothesis, "")
        self.assertEqual(result.indicator_activation_rate, 0.0)
        self.assertTrue(all(item["status"] == "UNVERIFIED" for item in result.hypotheses))
        self.assertEqual(result.confidence_language, "很不可能")
```

- [ ] **Step 2: Run tests to verify missing ACH implementation**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_officer_core
```

Expected: FAIL because `Hypothesis` and `run_ach_analysis` are not implemented.

- [ ] **Step 3: Add ACH dataclasses and analysis**

Modify `backend/app/core/ach_engine.py` by importing probability language:

```python
from app.core.verification import estimate_probability_language
```

Add after `IndicatorScore`:

```python
@dataclass(frozen=True)
class Hypothesis:
    id: str
    statement: str
    mutually_exclusive_group: str = "default"


@dataclass(frozen=True)
class AchResult:
    most_likely_hypothesis: str
    hypotheses: list[dict[str, Any]]
    triggered_indicators: list[str]
    indicator_activation_rate: float
    confidence_language: str
```

Add after `score_triggered_indicators`:

```python
def run_ach_analysis(
    hypotheses: list[Hypothesis],
    evidence_items: list[EvidenceItem],
    indicators: list[dict[str, Any]] | None = None,
) -> AchResult:
    indicator_score = score_triggered_indicators(evidence_items, indicators)
    if not hypotheses:
        return AchResult(
            most_likely_hypothesis="",
            hypotheses=[],
            triggered_indicators=indicator_score.triggered_ids,
            indicator_activation_rate=indicator_score.activation_rate,
            confidence_language=estimate_probability_language(0.0),
        )

    if not evidence_items:
        return AchResult(
            most_likely_hypothesis="",
            hypotheses=[
                {
                    "id": hypothesis.id,
                    "statement": hypothesis.statement,
                    "supporting_evidence": [],
                    "contradictory_evidence": [],
                    "inconsistency_score": 0.0,
                    "support_score": 0.0,
                    "status": "UNVERIFIED",
                }
                for hypothesis in hypotheses
            ],
            triggered_indicators=indicator_score.triggered_ids,
            indicator_activation_rate=indicator_score.activation_rate,
            confidence_language=estimate_probability_language(0.0),
        )

    rows = [_score_hypothesis(hypothesis, evidence_items) for hypothesis in hypotheses]
    rows.sort(key=lambda row: (row["inconsistency_score"], -row["support_score"], row["id"]))
    winner_id = str(rows[0]["id"]) if rows else ""
    for row in rows:
        row["status"] = _hypothesis_status(row, winner_id)
    winner = next((row for row in rows if row["id"] == winner_id), None)
    confidence = _ach_confidence(winner, rows, indicator_score.activation_rate)
    return AchResult(
        most_likely_hypothesis=winner_id,
        hypotheses=rows,
        triggered_indicators=indicator_score.triggered_ids,
        indicator_activation_rate=indicator_score.activation_rate,
        confidence_language=estimate_probability_language(confidence),
    )


def _score_hypothesis(hypothesis: Hypothesis, evidence_items: list[EvidenceItem]) -> dict[str, Any]:
    supporting: list[str] = []
    contradictory: list[str] = []
    support_score = 0.0
    contradiction_score = 0.0
    for evidence in evidence_items:
        impact = _evidence_impact(evidence)
        if hypothesis.id in evidence.supports:
            supporting.append(evidence.id)
            support_score += impact
        if hypothesis.id in evidence.contradicts:
            contradictory.append(evidence.id)
            contradiction_score += impact * 1.45
    inconsistency_score = round(max(0.0, contradiction_score - support_score * 0.35), 4)
    return {
        "id": hypothesis.id,
        "statement": hypothesis.statement,
        "supporting_evidence": supporting,
        "contradictory_evidence": contradictory,
        "inconsistency_score": inconsistency_score,
        "support_score": round(support_score, 4),
        "status": "PLAUSIBLE",
    }


def _evidence_impact(evidence: EvidenceItem) -> float:
    reliability_weight = {
        "A": 1.0,
        "B": 0.82,
        "C": 0.62,
        "D": 0.42,
        "E": 0.2,
        "F": 0.1,
    }.get(str(evidence.source_reliability).upper(), 0.1)
    credibility = _bounded_probability(evidence.credibility)
    return round(max(0.05, reliability_weight * max(credibility, 0.1)), 4)


def _bounded_probability(value: float | int | str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number = number / 100
    return max(0.0, min(1.0, number))


def _hypothesis_status(row: dict[str, Any], winner_id: str) -> str:
    if row["id"] == winner_id and row["support_score"] > 0:
        return "MOST_LIKELY"
    if row["inconsistency_score"] >= 1.2:
        return "REJECTED"
    if row["inconsistency_score"] >= 0.5:
        return "DISFAVORED"
    if row["support_score"] == 0 and row["inconsistency_score"] == 0:
        return "UNVERIFIED"
    return "PLAUSIBLE"


def _ach_confidence(winner: dict[str, Any] | None, rows: list[dict[str, Any]], activation_rate: float) -> float:
    if winner is None or not rows or winner["support_score"] <= 0:
        return 0.0
    if len(rows) == 1:
        separation = 0.2
    else:
        next_best = rows[1]
        separation = max(0.0, float(next_best["inconsistency_score"]) - float(winner["inconsistency_score"]))
    raw = 0.25 + min(float(winner["support_score"]) * 0.25, 0.3) + min(separation * 0.2, 0.2) + activation_rate * 0.25
    return round(max(0.0, min(0.95, raw)), 4)
```

- [ ] **Step 4: Run ACH tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_officer_core
```

Expected: PASS for loader, indicator, and ACH tests.

- [ ] **Step 5: Commit if repository metadata is available**

Run:

```bash
git status --short
```

Expected: If this directory is a git repository, commit:

```bash
git add backend/app/core/ach_engine.py backend/tests/test_intelligence_officer_core.py
git commit -m "feat: add deterministic ach engine"
```

If not a git repository, skip the commit.

## Task 4: Add Default Sparse Lead Helpers And Admiralty Cases

**Files:**
- Modify: `backend/app/core/ach_engine.py`
- Modify: `backend/tests/test_intelligence_officer_core.py`
- Modify if preferred: `backend/tests/test_core.py`

- [ ] **Step 1: Add failing tests for default hypotheses and Admiralty examples**

Append to `backend/tests/test_intelligence_officer_core.py`:

```python
from app.core.ach_engine import default_sparse_lead_hypotheses
from app.core.verification import admiralty_code


class DefaultHypothesisAndAdmiraltyTests(unittest.TestCase):
    def test_default_sparse_lead_hypotheses_include_three_competing_scenarios(self):
        hypotheses = default_sparse_lead_hypotheses()
        ids = [hypothesis.id for hypothesis in hypotheses]

        self.assertEqual(
            ids,
            [
                "alpha_real_procurement",
                "beta_price_benchmarking",
                "gamma_noise_or_unmatched_identity",
            ],
        )

    def test_admiralty_examples_cover_strong_and_weak_sources(self):
        official = admiralty_code("government_registry", 0.96)
        weak = admiralty_code("single_weak_signal", 0.55)

        self.assertEqual(official["code"], "A-1")
        self.assertEqual(weak["code"], "D-3")
```

- [ ] **Step 2: Run tests to verify helper is missing**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_officer_core
```

Expected: FAIL because `default_sparse_lead_hypotheses` is not implemented.

- [ ] **Step 3: Add default hypotheses helper**

Add to `backend/app/core/ach_engine.py` after `run_ach_analysis`:

```python
def default_sparse_lead_hypotheses() -> list[Hypothesis]:
    return [
        Hypothesis(
            id="alpha_real_procurement",
            statement="Real B2B buyer comparing suppliers for a live project or supply-chain replacement.",
        ),
        Hypothesis(
            id="beta_price_benchmarking",
            statement="Buyer is collecting quotes to pressure an incumbent supplier or benchmark the market.",
        ),
        Hypothesis(
            id="gamma_noise_or_unmatched_identity",
            statement="Same-name noise, personal account, or insufficient company/procurement evidence.",
        ),
    ]
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_intelligence_officer_core
```

Expected: PASS.

- [ ] **Step 5: Run broader backend core tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_intel_gateway backend.tests.test_intelligence_officer_core
```

Expected: PASS.

- [ ] **Step 6: Commit if repository metadata is available**

Run:

```bash
git status --short
```

Expected: If this directory is a git repository, commit:

```bash
git add backend/app/core/ach_engine.py backend/tests/test_intelligence_officer_core.py
git commit -m "test: cover intelligence officer defaults"
```

If not a git repository, skip the commit.

## Task 5: Final Verification And Documentation Check

**Files:**
- Read: `docs/superpowers/specs/2026-05-20-intelligence-officer-core-design.md`
- Read: `docs/superpowers/plans/2026-05-20-intelligence-officer-core.md`
- Verify: all files changed in prior tasks

- [ ] **Step 1: Run the recommended verification command**

Run:

```bash
PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_intelligence_officer_core
```

Expected: PASS.

- [ ] **Step 2: Run the broader project verification if time allows**

Run:

```bash
bash scripts/verify.sh
```

Expected: PASS. If the script fails because frontend dependencies are missing, record the exact missing dependency output and keep the backend unit-test result as the primary verification for this backend-only change.

- [ ] **Step 3: Check for incomplete markers in new docs and assets**

Run:

```bash
rg -n "TB[D]|TOD[O]|待定|implement late[r]" docs/superpowers/specs/2026-05-20-intelligence-officer-core-design.md docs/superpowers/plans/2026-05-20-intelligence-officer-core.md backend/app/core/intel_schema.json backend/app/core/indicator_matrix.yaml backend/app/core/ach_engine.py backend/tests/test_intelligence_officer_core.py
```

Expected: no matches.

- [ ] **Step 4: Check repository status**

Run:

```bash
git status --short
```

Expected: If this directory is a git repository, only intended intelligence-officer files are modified. If not a git repository, record that git verification is unavailable in this workspace.

- [ ] **Step 5: Prepare handoff summary**

Summarize:

```text
Implemented:
- intelligence schema asset
- indicator matrix asset
- deterministic ACH and indicator scoring core
- backend unit tests

Verified:
- PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_intelligence_officer_core

Notes:
- No UI/API changes.
- Git commit skipped if workspace is not a git repository.
```
