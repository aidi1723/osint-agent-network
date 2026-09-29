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


class GHuntAdapter:
    name = "ghunt"
    target_type = "email"
    base_confidence = 0.55

    def __init__(self, command: str | None = None):
        self.command = command or os.getenv("GHUNT_COMMAND", "ghunt")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("GHunt only accepts email targets")
        return normalize_target("email", target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 180,
    ) -> ToolCommand:
        email = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"ghunt_{email.replace('@', '_at_')}.json"
        return ToolCommand(
            args=[self.command, "email", email, "--json", str(artifact)],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        return self.parse_json(read_json_artifact(artifact_path), email=target_value)

    def parse_json(self, raw: dict, email: str) -> ParsedToolOutput:
        normalized_email = normalize_target("email", email)
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(
            entities,
            seen_entities,
            NormalizedEntity("email", normalized_email, self.name, self.base_confidence),
        )

        if raw.get("exists") is False or str(raw.get("status", "")).lower() in {"not_found", "missing"}:
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(
                    normalized_email,
                    "negative_result",
                    self.name,
                    str(raw.get("message") or "GHunt did not find a Google account signal"),
                ),
            )
            return ParsedToolOutput(self.name, self.target_type, normalized_email, entities, evidence, relationships)

        append_unique_evidence(
            evidence,
            seen_evidence,
            NormalizedEvidence(
                normalized_email,
                "google_account_exists",
                self.name,
                "GHunt returned public Google-account signal",
            ),
        )

        real_name = _first_string(
            raw,
            [
                ("profile", "name"),
                ("person", "name"),
                ("google_account", "name"),
                ("name",),
                ("full_name",),
            ],
        )
        if real_name:
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity("real_name", real_name, self.name, self.base_confidence),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(normalized_email, real_name, "email_has_real_name", self.base_confidence),
            )

        for url in _profile_urls(raw):
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity("profile_url", url, self.name, self.base_confidence),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(url, "google_public_profile", self.name, "GHunt returned public profile URL"),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(normalized_email, url, "email_has_profile", self.base_confidence),
            )

        return ParsedToolOutput(self.name, self.target_type, normalized_email, entities, evidence, relationships)


def _first_string(raw: dict, paths: list[tuple[str, ...]]) -> str:
    for path in paths:
        value = raw
        for part in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _profile_urls(raw: dict) -> list[str]:
    candidates = [
        _first_string(raw, [("profile", "profile_url"), ("profile", "url"), ("profile_url",)]),
        _first_string(raw, [("youtube", "channel_url"), ("youtube", "url")]),
        _first_string(raw, [("maps", "profile_url"), ("maps", "url")]),
    ]
    for key in ("profiles", "urls", "public_urls"):
        values = raw.get(key)
        if isinstance(values, list):
            for item in values:
                if isinstance(item, str):
                    candidates.append(item)
                elif isinstance(item, dict):
                    candidates.append(str(item.get("url") or item.get("profile_url") or ""))
    return [value.strip() for value in candidates if isinstance(value, str) and value.strip().startswith("http")]
