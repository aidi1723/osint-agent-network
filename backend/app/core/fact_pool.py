from __future__ import annotations

from dataclasses import dataclass, replace


FACT_STATUSES = {"CONFIRMED", "LIKELY", "CONTRADICTED", "RETIRED", "NEEDS_REVIEW"}
FACT_PROMOTION_STAGES = {
    "RAW_OBSERVATION",
    "CANDIDATE_FACT",
    "ASSESSED_FACT",
    "ACCEPTED_FACT",
    "REJECTED_FACT",
}


@dataclass(frozen=True)
class FactRecord:
    id: str
    investigation_id: str
    statement: str
    subject: str
    predicate: str
    object: str
    status: str
    confidence: float
    admiralty_code: str
    evidence_ids: list[str]
    observed_at: str
    valid_from: str
    promotion_stage: str = "CANDIDATE_FACT"
    valid_to: str | None = None
    supersedes_fact_id: str | None = None


def validate_fact_record(fact: FactRecord) -> None:
    if fact.status not in FACT_STATUSES:
        raise ValueError(f"invalid fact status: {fact.status}")
    if fact.promotion_stage not in FACT_PROMOTION_STAGES:
        raise ValueError(f"invalid fact promotion_stage: {fact.promotion_stage}")
    if fact.promotion_stage == "ACCEPTED_FACT" and fact.status not in {"CONFIRMED", "LIKELY"}:
        raise ValueError("accepted facts must be confirmed or likely")
    if not fact.statement.strip():
        raise ValueError("fact statement is required")
    if not fact.subject.strip() or not fact.predicate.strip() or not fact.object.strip():
        raise ValueError("fact subject, predicate, and object are required")
    if fact.status in {"CONFIRMED", "LIKELY"} and not fact.evidence_ids:
        raise ValueError("confirmed or likely facts require evidence")
    if fact.status in {"CONFIRMED", "LIKELY"} and not fact.admiralty_code:
        raise ValueError("confirmed or likely facts require admiralty_code")
    if not 0 <= float(fact.confidence) <= 1:
        raise ValueError("fact confidence must be between 0 and 1")


def default_promotion_stage_for_status(status: str) -> str:
    if status == "CONFIRMED":
        return "ACCEPTED_FACT"
    if status == "LIKELY":
        return "ASSESSED_FACT"
    if status in {"CONTRADICTED", "RETIRED"}:
        return "REJECTED_FACT"
    return "CANDIDATE_FACT"


def supersede_fact(
    old_fact: FactRecord,
    new_id: str,
    new_object: str,
    observed_at: str,
    evidence_ids: list[str],
) -> tuple[FactRecord, FactRecord]:
    retired = replace(old_fact, status="RETIRED", valid_to=observed_at)
    replacement = replace(
        old_fact,
        id=new_id,
        object=new_object,
        statement=f"{old_fact.subject} {old_fact.predicate} {new_object}.",
        evidence_ids=evidence_ids,
        observed_at=observed_at,
        valid_from=observed_at,
        valid_to=None,
        supersedes_fact_id=old_fact.id,
    )
    validate_fact_record(replacement)
    return retired, replacement
