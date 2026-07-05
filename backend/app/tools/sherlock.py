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


class SherlockAdapter:
    name = "sherlock"
    target_type = "username"
    base_confidence = 0.35

    def __init__(
        self,
        command: str | None = None,
        module: str | None = None,
        script_path: str | None = None,
    ):
        self.command = command or os.getenv("SHERLOCK_COMMAND", "python3")
        self.module = module or os.getenv("SHERLOCK_MODULE", "sherlock_project")
        self.script_path = script_path or os.getenv("SHERLOCK_PATH", "")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("Sherlock only accepts username targets")
        return normalize_target("username", target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 120,
    ) -> ToolCommand:
        username = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"sherlock_{username}.json"
        if self.script_path:
            args = [
                self.command,
                self.script_path,
                username,
                "--json",
                str(artifact),
                "--timeout",
                str(timeout_seconds),
            ]
        else:
            args = [
                self.command,
                "-m",
                self.module,
                username,
                "--json",
                str(artifact),
                "--timeout",
                str(timeout_seconds),
            ]
        return ToolCommand(
            args=args,
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
            NormalizedEntity(
                type="username",
                value=normalized_username,
                source_tool=self.name,
                confidence=self.base_confidence,
            ),
        )

        for platform, item in raw.items():
            if not isinstance(item, dict):
                continue
            if not _is_claimed(item):
                continue
            url = str(item.get("url_main") or item.get("url") or "").strip()
            if not url:
                continue
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity(
                    type="profile_url",
                    value=url,
                    source_tool=self.name,
                    confidence=self.base_confidence,
                ),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(
                    entity_value=url,
                    evidence_kind="profile_exists",
                    source_tool=self.name,
                    snippet=f"Sherlock claimed profile on {platform}",
                ),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(
                    from_value=normalized_username,
                    to_value=url,
                    relationship_type="username_has_profile",
                    confidence=self.base_confidence,
                ),
            )

        return ParsedToolOutput(
            tool=self.name,
            target_type=self.target_type,
            target_value=normalized_username,
            entities=entities,
            evidence=evidence,
            relationships=relationships,
        )


def _is_claimed(item: dict) -> bool:
    status = str(item.get("status") or "").upper()
    if status in {"CLAIMED", "FOUND", "EXISTS"}:
        return True
    if item.get("status") is True:
        return True
    return bool(item.get("claimed") or item.get("exists"))
