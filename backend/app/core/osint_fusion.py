from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
from urllib.parse import urlsplit

from app.tools.base import ParsedToolOutput


ORGANIZATION_AXIS = "organization_asset"
DECISION_AXIS = "decision_will"
BRIDGE_AXIS = "bridge"


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

    def to_dict(self) -> dict:
        return asdict(self)


def derive_osint_signals(parsed: ParsedToolOutput) -> list[OsintSignal]:
    signals: list[OsintSignal] = []
    evidence_by_value = {item.entity_value: item for item in parsed.evidence}
    relationship_by_to = {item.to_value: item for item in parsed.relationships}
    for entity in parsed.entities:
        classification = classify_osint_entity(
            tool=parsed.tool,
            target_type=parsed.target_type,
            target_value=parsed.target_value,
            entity_type=entity.type,
            entity_value=entity.value,
        )
        if classification is None:
            continue
        evidence = evidence_by_value.get(entity.value)
        relationship = relationship_by_to.get(entity.value)
        core_axis, slot_hint, review_status = classification
        signals.append(
            OsintSignal(
                signal_id=_signal_id(parsed.tool, entity.type, entity.value),
                tool=parsed.tool,
                target_type=parsed.target_type,
                target_value=parsed.target_value,
                entity_type=entity.type,
                entity_value=entity.value,
                evidence_kind=evidence.evidence_kind if evidence else "",
                relationship_type=relationship.relationship_type if relationship else "",
                confidence=entity.confidence,
                core_axis=core_axis,
                slot_hint=slot_hint,
                review_status=review_status,
                source_tier="passive_osint",
            )
        )
    return signals


def derive_osint_signals_from_detail(detail: dict) -> list[OsintSignal]:
    relationships_by_to = {
        str(item.get("to_value") or ""): str(item.get("relationship_type") or "")
        for item in detail.get("relationships", [])
    }
    evidence_by_value = {
        str(item.get("entity_value") or ""): str(item.get("evidence_kind") or "")
        for item in detail.get("evidence", [])
    }
    signals: list[OsintSignal] = []
    for entity in detail.get("entities", []):
        tool = str(entity.get("source_tool") or "")
        entity_type = str(entity.get("type") or "")
        entity_value = str(entity.get("value") or "")
        classification = classify_osint_entity(
            tool=tool,
            target_type=str(detail.get("seed_type") or ""),
            target_value=str(detail.get("seed_value") or ""),
            entity_type=entity_type,
            entity_value=entity_value,
        )
        if classification is None:
            continue
        core_axis, slot_hint, review_status = classification
        signals.append(
            OsintSignal(
                signal_id=_signal_id(tool, entity_type, entity_value),
                tool=tool,
                target_type=str(detail.get("seed_type") or ""),
                target_value=str(detail.get("seed_value") or ""),
                entity_type=entity_type,
                entity_value=entity_value,
                evidence_kind=evidence_by_value.get(entity_value, ""),
                relationship_type=relationships_by_to.get(entity_value, ""),
                confidence=float(entity.get("confidence") or 0.0),
                core_axis=core_axis,
                slot_hint=slot_hint,
                review_status=review_status,
                source_tier="passive_osint",
            )
        )
    return signals


def signal_metadata_by_value(detail: dict) -> dict[str, dict]:
    return {signal.entity_value: signal.to_dict() for signal in derive_osint_signals_from_detail(detail)}


def classify_osint_entity(
    tool: str,
    target_type: str,
    target_value: str,
    entity_type: str,
    entity_value: str,
) -> tuple[str, str, str] | None:
    tool = tool.lower()
    if tool not in {"amass", "spiderfoot", "sherlock"}:
        return None

    if tool == "amass":
        if entity_type in {"subdomain", "ip"}:
            return ORGANIZATION_AXIS, "digital-footprint", "candidate"
        if entity_type == "domain":
            return ORGANIZATION_AXIS, "company_website", "candidate"
        return None

    if tool == "spiderfoot":
        if entity_type == "email":
            slot = "company_contact" if _same_email_domain(entity_value, target_value) else "contact-channel"
            return BRIDGE_AXIS, slot, "candidate"
        if entity_type in {"url", "subdomain", "ip", "domain"}:
            return ORGANIZATION_AXIS, "digital-footprint", "candidate"
        if entity_type == "company":
            return ORGANIZATION_AXIS, "landed-entity", "candidate"
        if entity_type in {"real_name", "username"}:
            return DECISION_AXIS, "persona-role", "candidate"
        return None

    if tool == "sherlock":
        if entity_type in {"username", "profile_url", "social_profile", "platform_account"}:
            return DECISION_AXIS, "persona-role", "candidate"
        return None

    return None


def _same_email_domain(email: str, target_value: str) -> bool:
    if "@" not in email:
        return False
    email_domain = email.rsplit("@", 1)[1].lower()
    target_domain = _domain_like(target_value)
    return bool(target_domain and email_domain == target_domain)


def _domain_like(value: str) -> str:
    value = value.strip().lower()
    if "@" in value:
        return value.rsplit("@", 1)[1]
    if value.startswith(("http://", "https://")):
        return (urlsplit(value).hostname or "").removeprefix("www.")
    return value.removeprefix("www.")


def _signal_id(tool: str, entity_type: str, entity_value: str) -> str:
    digest = sha1(f"{tool}:{entity_type}:{entity_value}".encode("utf-8")).hexdigest()[:16]
    return f"osint:{digest}"
