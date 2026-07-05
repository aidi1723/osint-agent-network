from __future__ import annotations

import os
from pathlib import Path

from app.core.normalization import normalize_target
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
    ToolCommand,
    append_unique_entity,
    append_unique_evidence,
    append_unique_relationship,
    read_json_artifact,
)


class MaigretAdapter:
    name = "maigret"
    target_type = "username"
    base_confidence = 0.40

    def __init__(self, command: str | None = None):
        self.command = command or os.getenv("MAIGRET_COMMAND", "maigret")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("Maigret only accepts username targets")
        return normalize_target("username", target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 300,
    ) -> ToolCommand:
        username = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"maigret_{username}.json"
        return ToolCommand(
            args=[
                self.command,
                username,
                "--json",
                str(artifact),
                "--timeout",
                str(timeout_seconds),
            ],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        return self.parse_json(read_json_artifact(artifact_path), username=target_value)

    def parse_json(self, raw: dict, username: str) -> ParsedToolOutput:
        normalized_username = normalize_target("username", username)
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(
            entities,
            seen_entities,
            NormalizedEntity("username", normalized_username, self.name, self.base_confidence),
        )

        records = raw.get("sites", raw) if isinstance(raw, dict) else {}
        for platform, item in records.items():
            if not isinstance(item, dict) or not _is_claimed(item):
                continue
            url = str(item.get("url_user") or item.get("url") or item.get("profile_url") or "").strip()
            if not url:
                continue
            try:
                profile_url = normalize_target("profile_url", url)
            except ValueError:
                continue
            platform_key = str(platform).strip().lower().replace(" ", "_")
            social_profile = f"{platform_key}:{normalized_username}"
            ids_data = item.get("ids_data") if isinstance(item.get("ids_data"), dict) else {}

            for entity in [
                NormalizedEntity("profile_url", profile_url, self.name, self.base_confidence),
                NormalizedEntity("social_profile", social_profile, self.name, self.base_confidence),
                NormalizedEntity("platform_account", social_profile, self.name, self.base_confidence),
            ]:
                append_unique_entity(entities, seen_entities, entity)

            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(
                    profile_url,
                    "social_profile_exists",
                    self.name,
                    f"Maigret found claimed profile on {platform}",
                ),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(
                    normalized_username,
                    profile_url,
                    "username_has_social_profile",
                    self.base_confidence,
                ),
            )
            _add_metadata_entities(
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
                profile_url,
                ids_data,
                self.name,
            )

        return ParsedToolOutput(
            self.name,
            self.target_type,
            normalized_username,
            entities,
            evidence,
            relationships,
        )


def _is_claimed(item: dict) -> bool:
    status = str(item.get("status") or item.get("status_code") or "").lower()
    return (
        status in {"claimed", "found", "exists"}
        or item.get("claimed") is True
        or item.get("exists") is True
    )


def _add_metadata_entities(
    entities,
    evidence,
    relationships,
    seen_entities,
    seen_evidence,
    seen_relationships,
    profile_url: str,
    ids_data: dict,
    source: str,
) -> None:
    mappings = [
        ("bio_snippet", ids_data.get("bio") or ids_data.get("description")),
        ("declared_location", ids_data.get("location")),
        ("profile_image_url", ids_data.get("avatar") or ids_data.get("image")),
        ("external_link", ids_data.get("website") or ids_data.get("url")),
    ]
    for entity_type, raw_value in mappings:
        value = str(raw_value or "").strip()
        if not value:
            continue
        if entity_type in {"profile_image_url", "external_link"}:
            try:
                value = normalize_target("url", value)
            except ValueError:
                continue
        append_unique_entity(
            entities,
            seen_entities,
            NormalizedEntity(entity_type, value, source, 0.30),
        )
        append_unique_evidence(
            evidence,
            seen_evidence,
            NormalizedEvidence(
                value,
                "public_profile_metadata",
                source,
                f"Public profile metadata from {profile_url}",
            ),
        )
        append_unique_relationship(
            relationships,
            seen_relationships,
            NormalizedRelationship(profile_url, value, f"profile_has_{entity_type}", 0.30),
        )
