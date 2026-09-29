from dataclasses import dataclass


SOURCE_RELIABILITY_MAP = {
    "official_website": "A",
    "government_registry": "A",
    "regulatory_filing": "A",
    "original_social_profile": "A",
    "mainstream_media": "B",
    "industry_association": "B",
    "business_directory": "B",
    "job_board": "B",
    "map_listing": "B",
    "search_result": "C",
    "aggregator": "C",
    "tool_output": "C",
    "single_weak_signal": "D",
    "anonymous_forum": "E",
    "unknown": "F",
}


@dataclass(frozen=True)
class EvidenceSignal:
    tool: str
    kind: str
    weight: float
    negative: bool = False


@dataclass(frozen=True)
class ScoreResult:
    score: float
    status: str
    positive_evidence_count: int
    negative_evidence_count: int


def score_entity(base_prior: float, signals: list[EvidenceSignal]) -> ScoreResult:
    positive_tools = {signal.tool for signal in signals if signal.weight > 0}
    negative_count = sum(1 for signal in signals if signal.negative or signal.weight < 0)
    positive_count = sum(1 for signal in signals if signal.weight > 0)

    agreement_bonus = max(0, min(len(positive_tools) - 1, 2)) * 0.15
    raw_score = base_prior + sum(signal.weight for signal in signals) + agreement_bonus
    score = max(0.0, min(1.0, round(raw_score, 4)))

    if negative_count and positive_count:
        status = "CONTRADICTED"
    elif negative_count and score < 0.2:
        status = "NEGATIVE"
    elif score >= 0.8:
        status = "VERIFIED"
    elif score >= 0.6:
        status = "LIKELY"
    elif score >= 0.35:
        status = "WEAK"
    else:
        status = "UNVERIFIED"

    return ScoreResult(
        score=score,
        status=status,
        positive_evidence_count=positive_count,
        negative_evidence_count=negative_count,
    )


def admiralty_code(source_reliability: str, credibility: float | int | str) -> dict[str, str]:
    reliability = _source_reliability_code(source_reliability)
    information = _information_credibility_code(_as_probability(credibility))
    probability = _credibility_probability(information)
    return {
        "code": f"{reliability}-{information}",
        "source_reliability": reliability,
        "information_credibility": information,
        "probability_language": estimate_probability_language(probability),
    }


def estimate_probability_language(probability: float | int | str) -> str:
    value = _as_probability(probability)
    if value >= 0.90:
        return "几乎可以肯定"
    if value >= 0.70:
        return "很有可能"
    if value >= 0.50:
        return "有可能"
    if value >= 0.25:
        return "可能性较低"
    return "很不可能"


def _source_reliability_code(source_reliability: str) -> str:
    value = str(source_reliability or "").strip()
    upper = value.upper()
    if upper in {"A", "B", "C", "D", "E", "F"}:
        return upper
    normalized = value.lower().replace("-", "_").replace(" ", "_")
    return SOURCE_RELIABILITY_MAP.get(normalized, "F")


def _information_credibility_code(probability: float) -> str:
    if probability >= 0.90:
        return "1"
    if probability >= 0.70:
        return "2"
    if probability >= 0.50:
        return "3"
    if probability >= 0.25:
        return "4"
    if probability > 0:
        return "5"
    return "6"


def _credibility_probability(code: str) -> float:
    return {
        "1": 0.95,
        "2": 0.80,
        "3": 0.60,
        "4": 0.35,
        "5": 0.10,
        "6": 0.0,
    }[code]


def _as_probability(value: float | int | str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number = number / 100
    return max(0.0, min(1.0, number))
