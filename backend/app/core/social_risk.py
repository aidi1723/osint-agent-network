from __future__ import annotations

from dataclasses import asdict, dataclass


HIGH_RISK_KEYWORDS = ("crypto", "betting", "casino", "gambling", "forex", "loan", "pharma")


@dataclass(frozen=True)
class SocialRiskEvidence:
    kind: str
    severity: str
    summary: str
    evidence_values: list[str]


def build_social_risk_report(
    entities: list[dict],
    evidence: list[dict],
    relationships: list[dict],
    declared_region: str = "",
) -> dict:
    signals = extract_risk_signals(
        entities,
        evidence,
        relationships,
        declared_region=declared_region,
    )
    category_scores = score_categories(entities, evidence, relationships, signals)
    overall = round(
        category_scores["identity_consistency"] * 0.20
        + category_scores["contact_reputation"] * 0.20
        + category_scores["location_consistency"] * 0.20
        + category_scores["business_content_risk"] * 0.25
        + category_scores["evidence_uncertainty"] * 0.15
    )
    return {
        "overall_risk_score": overall,
        "overall_risk_level": _risk_level(overall),
        "category_scores": category_scores,
        "review_required": overall >= 25
        or any(signal.severity in {"high", "critical"} for signal in signals),
        "top_risk_signals": [asdict(signal) for signal in signals[:5]],
        "public_profile_summary": _profile_summary(entities),
        "supporting_evidence": evidence,
    }


def extract_risk_signals(
    entities: list[dict],
    evidence: list[dict],
    relationships: list[dict],
    declared_region: str = "",
) -> list[SocialRiskEvidence]:
    signals: list[SocialRiskEvidence] = []
    profiles = [item["value"] for item in entities if item.get("type") == "profile_url"]
    bio_values = [item["value"] for item in entities if item.get("type") == "bio_snippet"]
    locations = [item["value"] for item in entities if item.get("type") == "declared_location"]

    if len(profiles) == 0:
        signals.append(
            SocialRiskEvidence(
                "weak_public_footprint",
                "medium",
                "No public social profiles were found from the supplied identifiers.",
                [],
            )
        )
    elif len(profiles) == 1:
        signals.append(
            SocialRiskEvidence(
                "low_evidence_strength",
                "low",
                "Only one public profile source supports the social footprint.",
                profiles,
            )
        )

    for bio in bio_values:
        lowered = bio.lower()
        hits = [keyword for keyword in HIGH_RISK_KEYWORDS if keyword in lowered]
        if hits:
            signals.append(
                SocialRiskEvidence(
                    "business_risk_keyword",
                    "high",
                    f"Public profile text contains configured risk keywords: {', '.join(hits)}.",
                    [bio],
                )
            )
            break

    if declared_region:
        normalized_declared = declared_region.strip().lower()
        conflicting = [
            location
            for location in locations
            if normalized_declared and normalized_declared not in location.lower()
        ]
        if conflicting:
            signals.append(
                SocialRiskEvidence(
                    "location_conflict",
                    "medium",
                    "Public declared location differs from the customer-declared region.",
                    conflicting,
                )
            )

    linked_targets: dict[str, set[str]] = {}
    for relationship in relationships:
        if relationship.get("relationship_type") in {
            "username_has_social_profile",
            "email_linked_to_social_profile",
        }:
            linked_targets.setdefault(relationship.get("from_value", ""), set()).add(
                relationship.get("to_value", "")
            )
    if any(len(values) >= 5 for values in linked_targets.values()):
        signals.append(
            SocialRiskEvidence(
                "contact_identity_overlap",
                "medium",
                "One identifier links to many public profiles and needs review.",
                [],
            )
        )

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(signals, key=lambda signal: severity_order[signal.severity])


def score_categories(
    entities: list[dict],
    evidence: list[dict],
    relationships: list[dict],
    signals: list[SocialRiskEvidence],
) -> dict:
    signal_kinds = {signal.kind for signal in signals}
    source_tools = {item.get("source_tool") for item in evidence if item.get("source_tool")}
    profile_count = sum(1 for item in entities if item.get("type") == "profile_url")

    return {
        "identity_consistency": _score_from_signals(
            signal_kinds,
            {"contact_identity_overlap": 55},
            default=15,
        ),
        "contact_reputation": 65
        if "weak_public_footprint" in signal_kinds
        else 20
        if profile_count >= 2
        else 35,
        "location_consistency": 60 if "location_conflict" in signal_kinds else 10,
        "business_content_risk": 75 if "business_risk_keyword" in signal_kinds else 10,
        "evidence_uncertainty": 70 if profile_count == 0 else 45 if len(source_tools) <= 1 else 20,
    }


def _score_from_signals(signal_kinds: set[str], weights: dict[str, int], default: int) -> int:
    score = default
    for kind, value in weights.items():
        if kind in signal_kinds:
            score = max(score, value)
    return score


def _risk_level(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _profile_summary(entities: list[dict]) -> dict:
    def values(entity_type: str) -> list[str]:
        seen = []
        for item in entities:
            if item.get("type") == entity_type and item.get("value") not in seen:
                seen.append(item.get("value"))
        return seen

    return {
        "profiles": values("profile_url"),
        "declared_locations": values("declared_location"),
        "likely_activity_regions": values("likely_activity_region"),
        "profile_image_urls": values("profile_image_url"),
        "bio_snippets": values("bio_snippet"),
        "interest_tags": values("interest_tag"),
        "age_claims": values("age_claim"),
    }
