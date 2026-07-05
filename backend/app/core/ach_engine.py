from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import json
from pathlib import Path
from typing import Any

from app.core.verification import estimate_probability_language


CORE_DIR = Path(__file__).resolve().parent


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


def _require_keys(data: dict[str, Any], keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ValueError(f"Missing required intelligence schema keys: {', '.join(missing)}")


def _parse_indicator_matrix(text: str) -> dict[str, Any]:
    try:
        yaml_module = import_module("yaml")
    except ImportError:
        yaml_module = None
    if yaml_module is not None:
        safe_load = getattr(yaml_module, "safe_load", None)
        parsed = safe_load(text) if callable(safe_load) else None
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
