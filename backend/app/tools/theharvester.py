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


class TheHarvesterAdapter:
    name = "theharvester"
    target_type = "domain"
    base_confidence = 0.35

    def __init__(
        self,
        command: str | None = None,
        script_path: str | None = None,
        sources: str | None = None,
        limit: int | None = None,
    ):
        self.command = command or os.getenv("THEHARVESTER_COMMAND", "python3")
        self.script_path = script_path or os.getenv(
            "THEHARVESTER_PATH",
            "/opt/osint/theHarvester/theHarvester.py",
        )
        self.sources = sources or os.getenv("THEHARVESTER_SOURCES", "all")
        self.limit = limit or int(os.getenv("THEHARVESTER_LIMIT", "500"))

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("theHarvester only accepts domain targets")
        return normalize_target("domain", target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 600,
    ) -> ToolCommand:
        domain = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        report_base = workdir / "theharvester_report"
        return ToolCommand(
            args=[
                self.command,
                self.script_path,
                "-d",
                domain,
                "-l",
                str(self.limit),
                "-b",
                self.sources,
                "-f",
                str(report_base),
            ],
            cwd=workdir,
            expected_artifact=report_base.with_suffix(".json"),
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        return self.parse_json(read_json_artifact(artifact_path), domain=target_value)

    def parse_json(self, raw: dict, domain: str) -> ParsedToolOutput:
        normalized_domain = normalize_target("domain", domain)
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
                type="domain",
                value=normalized_domain,
                source_tool=self.name,
                confidence=self.base_confidence,
            ),
        )

        for email in _strings(raw.get("emails", [])):
            try:
                normalized_email = normalize_target("email", email)
            except ValueError:
                continue
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity(
                    type="email",
                    value=normalized_email,
                    source_tool=self.name,
                    confidence=self.base_confidence,
                ),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(
                    entity_value=normalized_email,
                    evidence_kind="search_result",
                    source_tool=self.name,
                    snippet=f"theHarvester exposed email for {normalized_domain}",
                ),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(
                    from_value=normalized_domain,
                    to_value=normalized_email,
                    relationship_type="domain_exposes_email",
                    confidence=self.base_confidence,
                ),
            )
            username = normalized_email.split("@", 1)[0]
            try:
                normalized_username = normalize_target("username", username)
            except ValueError:
                continue
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity(
                    type="username",
                    value=normalized_username,
                    source_tool=self.name,
                    confidence=0.25,
                ),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(
                    from_value=normalized_email,
                    to_value=normalized_username,
                    relationship_type="email_has_username",
                    confidence=0.45,
                ),
            )

        for host in _strings(raw.get("hosts", [])):
            host_value = host.lower().rstrip(".")
            try:
                normalized_host = normalize_target("domain", host_value)
            except ValueError:
                continue
            entity_type = "domain" if normalized_host == normalized_domain else "subdomain"
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity(
                    type=entity_type,
                    value=normalized_host,
                    source_tool=self.name,
                    confidence=self.base_confidence,
                ),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(
                    entity_value=normalized_host,
                    evidence_kind="host_discovery",
                    source_tool=self.name,
                    snippet=f"theHarvester discovered host {normalized_host}",
                ),
            )
            if normalized_host != normalized_domain:
                append_unique_relationship(
                    relationships,
                    seen_relationships,
                    NormalizedRelationship(
                        from_value=normalized_domain,
                        to_value=normalized_host,
                        relationship_type="domain_has_subdomain",
                        confidence=self.base_confidence,
                    ),
                )

        for url in _strings(raw.get("urls", [])):
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity(
                    type="url",
                    value=url,
                    source_tool=self.name,
                    confidence=0.30,
                ),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(
                    entity_value=url,
                    evidence_kind="search_result",
                    source_tool=self.name,
                    snippet=f"theHarvester returned public URL for {normalized_domain}",
                ),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(
                    from_value=normalized_domain,
                    to_value=url,
                    relationship_type="domain_referenced_by_url",
                    confidence=0.30,
                ),
            )

        return ParsedToolOutput(
            tool=self.name,
            target_type=self.target_type,
            target_value=normalized_domain,
            entities=entities,
            evidence=evidence,
            relationships=relationships,
        )


def _strings(values) -> list[str]:
    if isinstance(values, str):
        return [values]
    result = []
    for item in values or []:
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, dict):
            value = str(item.get("host") or item.get("email") or item.get("url") or "").strip()
        else:
            value = str(item).strip()
        if value:
            result.append(value)
    return result
