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


class SocialScanAdapter:
    name = "socialscan"
    base_confidence = 0.35

    def __init__(self, command: str | None = None):
        self.command = command or os.getenv("SOCIALSCAN_COMMAND", "socialscan")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type not in {"email", "username"}:
            raise ValueError("socialscan accepts email or username targets")
        return normalize_target(target_type, target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 120,
    ) -> ToolCommand:
        target = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"socialscan_{target_type}_{target.replace('@', '_at_')}.json"
        return ToolCommand(
            args=[self.command, "--json", target],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        target_type = "email" if "@" in target_value else "username"
        return self.parse_json(
            read_json_artifact(artifact_path),
            target_type=target_type,
            target_value=target_value,
        )

    def parse_json(self, raw, target_type: str, target_value: str) -> ParsedToolOutput:
        normalized_target = self.validate_target(target_type, target_value)
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(
            entities,
            seen_entities,
            NormalizedEntity(target_type, normalized_target, self.name, self.base_confidence),
        )

        records = raw.get("results", raw) if isinstance(raw, dict) else raw
        if not isinstance(records, list):
            records = []

        for record in records:
            if not isinstance(record, dict):
                continue
            platform = str(record.get("platform") or record.get("site") or "").strip().lower()
            if not platform:
                continue
            account_key = f"{platform}:{normalized_target}"
            exists = record.get("exists")
            status = str(record.get("status") or "").lower()
            if exists is False or status in {"not_found", "available", "missing"}:
                append_unique_evidence(
                    evidence,
                    seen_evidence,
                    NormalizedEvidence(
                        account_key,
                        "negative_result",
                        self.name,
                        str(record.get("message") or f"{platform} account not found"),
                    ),
                )
                continue

            url = str(record.get("url") or record.get("profile_url") or "").strip()
            if not url:
                append_unique_entity(
                    entities,
                    seen_entities,
                    NormalizedEntity("platform_account", account_key, self.name, self.base_confidence),
                )
                append_unique_evidence(
                    evidence,
                    seen_evidence,
                    NormalizedEvidence(
                        account_key,
                        "account_exists",
                        self.name,
                        f"socialscan found {platform} account signal",
                    ),
                )
                continue
            try:
                profile_url = normalize_target("profile_url", url)
            except ValueError:
                continue
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity("profile_url", profile_url, self.name, self.base_confidence),
            )
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity("platform_account", account_key, self.name, self.base_confidence),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(
                    profile_url,
                    "account_exists",
                    self.name,
                    f"socialscan found {platform} account signal",
                ),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(
                    normalized_target,
                    profile_url,
                    f"{target_type}_linked_to_social_profile",
                    self.base_confidence,
                ),
            )

        return ParsedToolOutput(
            self.name,
            target_type,
            normalized_target,
            entities,
            evidence,
            relationships,
        )
