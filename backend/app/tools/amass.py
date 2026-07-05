from __future__ import annotations

import json
import os
from ipaddress import ip_address
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
)


class AmassAdapter:
    name = "amass"
    target_type = "domain"
    base_confidence = 0.50

    def __init__(self, command: str | None = None, passive: bool | None = None):
        self.command = command or os.getenv("AMASS_COMMAND", "amass")
        if passive is None:
            passive = os.getenv("AMASS_PASSIVE", "true").lower() in {"1", "true", "yes"}
        self.passive = passive

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("Amass only accepts domain targets")
        return normalize_target("domain", target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 1200,
    ) -> ToolCommand:
        domain = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"amass_{domain}.jsonl"
        args = [self.command, "enum"]
        if self.passive:
            args.append("-passive")
        args.extend(["-d", domain, "-json", str(artifact)])
        return ToolCommand(
            args=args,
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        records = []
        for line in artifact_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
        return self.parse_jsonl(records, domain=target_value)

    def parse_jsonl(self, records: list[dict], domain: str) -> ParsedToolOutput:
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

        for record in records:
            name = str(record.get("name") or record.get("fqdn") or "").strip().lower().rstrip(".")
            if not name:
                continue
            try:
                normalized_name = normalize_target("domain", name)
            except ValueError:
                continue
            entity_type = "domain" if normalized_name == normalized_domain else "subdomain"
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity(
                    type=entity_type,
                    value=normalized_name,
                    source_tool=self.name,
                    confidence=self.base_confidence,
                ),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(
                    entity_value=normalized_name,
                    evidence_kind="amass_name_discovery",
                    source_tool=self.name,
                    snippet=_snippet(record, normalized_name),
                ),
            )
            if normalized_name != normalized_domain:
                append_unique_relationship(
                    relationships,
                    seen_relationships,
                    NormalizedRelationship(
                        from_value=normalized_domain,
                        to_value=normalized_name,
                        relationship_type="domain_has_subdomain",
                        confidence=self.base_confidence,
                    ),
                )

            for ip_value in _addresses(record):
                append_unique_entity(
                    entities,
                    seen_entities,
                    NormalizedEntity(
                        type="ip",
                        value=ip_value,
                        source_tool=self.name,
                        confidence=0.45,
                    ),
                )
                append_unique_evidence(
                    evidence,
                    seen_evidence,
                    NormalizedEvidence(
                        entity_value=ip_value,
                        evidence_kind="dns_resolution",
                        source_tool=self.name,
                        snippet=f"Amass linked {normalized_name} to {ip_value}",
                    ),
                )
                append_unique_relationship(
                    relationships,
                    seen_relationships,
                    NormalizedRelationship(
                        from_value=normalized_name,
                        to_value=ip_value,
                        relationship_type="subdomain_resolves_to_ip",
                        confidence=0.45,
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


def _addresses(record: dict) -> list[str]:
    addresses = []
    for item in record.get("addresses", []) or []:
        raw_ip = item.get("ip") if isinstance(item, dict) else item
        value = str(raw_ip or "").strip()
        if not value:
            continue
        try:
            addresses.append(str(ip_address(value)))
        except ValueError:
            continue
    return addresses


def _snippet(record: dict, name: str) -> str:
    sources = record.get("sources") or []
    if isinstance(sources, list) and sources:
        return f"Amass discovered {name} via {', '.join(str(item) for item in sources[:3])}"
    tag = record.get("tag")
    if tag:
        return f"Amass discovered {name} with tag {tag}"
    return f"Amass discovered {name}"
