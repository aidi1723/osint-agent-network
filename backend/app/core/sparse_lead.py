from __future__ import annotations

from dataclasses import dataclass

from app.tools.base import NormalizedEntity, NormalizedEvidence, NormalizedRelationship


@dataclass(frozen=True)
class SparseLeadAnchorBundle:
    entities: list[NormalizedEntity]
    evidence: list[NormalizedEvidence]
    relationships: list[NormalizedRelationship]


def anchors_from_metadata(seed_value: str, metadata: dict) -> SparseLeadAnchorBundle:
    source_tool = "lead_anchor_extraction"
    entities: list[NormalizedEntity] = []
    evidence: list[NormalizedEvidence] = []
    relationships: list[NormalizedRelationship] = []

    def add_anchor(entity_type: str, value: str, confidence: float = 1.0) -> None:
        cleaned = str(value or "").strip()
        if not cleaned:
            return
        entities.append(NormalizedEntity(entity_type, cleaned, source_tool, confidence))
        evidence.append(
            NormalizedEvidence(
                cleaned,
                "visible_buyer_anchor",
                source_tool,
                f"Visible sparse lead anchor from operator-entered platform/CRM record: {entity_type}={cleaned}",
            )
        )
        relationships.append(
            NormalizedRelationship(
                seed_value,
                cleaned,
                "lead_has_platform_anchor",
                confidence,
            )
        )

    add_anchor("platform", metadata.get("platform", ""), 1.0)
    add_anchor("platform_account", metadata.get("lead_display_name", ""), 1.0)
    add_anchor("platform_member_id", metadata.get("member_id", ""), 1.0)
    add_anchor("country_region", metadata.get("country_region", ""), 1.0)
    add_anchor("registration_year", metadata.get("registration_year", ""), 0.95)
    add_anchor("company_name_raw", metadata.get("company_name_raw", ""), 0.9)
    add_anchor("privacy_state", metadata.get("privacy_state", ""), 0.9)

    for category in metadata.get("categories", []) or []:
        add_anchor("purchase_category", category, 0.72)

    for rfq in metadata.get("recent_rfqs", []) or []:
        add_anchor("rfq_text", rfq, 0.62)

    return SparseLeadAnchorBundle(entities=entities, evidence=evidence, relationships=relationships)
