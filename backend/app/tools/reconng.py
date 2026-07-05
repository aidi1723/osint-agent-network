from __future__ import annotations

import os
import re
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


class ReconNgAdapter:
    name = "reconng"
    base_confidence = 0.35

    def __init__(self, command: str | None = None):
        self.command = command or os.getenv("RECONNG_COMMAND", "recon-ng")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type not in {"domain", "email", "company"}:
            raise ValueError("Recon-ng accepts domain, email, or company targets")
        if target_type == "company":
            value = target_value.strip()
            if not value or not re.match(r"^[A-Za-z0-9 .,&'-]{1,120}$", value):
                raise ValueError("invalid company target")
            return value
        return normalize_target(target_type, target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 900,
    ) -> ToolCommand:
        target = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / "reconng_report.json"
        script = workdir / "recon.rc"
        script.write_text(_resource_script(target_type, target, artifact), encoding="utf-8")
        return ToolCommand(
            args=[self.command, "-r", str(script)],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        if not artifact_path.exists():
            return self.parse_json({}, target_type=_infer_target_type(target_value), target_value=target_value)
        raw = read_json_artifact(artifact_path)
        return self.parse_json(raw, target_type=_infer_target_type(target_value), target_value=target_value)

    def parse_json(self, raw: dict, target_type: str, target_value: str) -> ParsedToolOutput:
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

        for host in _values(raw.get("hosts", []), "host"):
            try:
                normalized_host = normalize_target("domain", host)
            except ValueError:
                continue
            entity_type = "domain" if normalized_host == normalized_target else "subdomain"
            _add_finding(
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
                target=normalized_target,
                entity_type=entity_type,
                value=normalized_host,
                source=self.name,
                confidence=self.base_confidence,
            )

        for contact in raw.get("contacts", []) or []:
            if not isinstance(contact, dict):
                continue
            email = str(contact.get("email") or "").strip()
            if email:
                try:
                    normalized_email = normalize_target("email", email)
                except ValueError:
                    normalized_email = ""
                if normalized_email:
                    _add_finding(
                        entities,
                        evidence,
                        relationships,
                        seen_entities,
                        seen_evidence,
                        seen_relationships,
                        target=normalized_target,
                        entity_type="email",
                        value=normalized_email,
                        source=self.name,
                        confidence=self.base_confidence,
                    )
                    real_name = " ".join(
                        item
                        for item in [str(contact.get("first_name") or "").strip(), str(contact.get("last_name") or "").strip()]
                        if item
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

        for company in _values(raw.get("companies", []), "company"):
            _add_finding(
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
                target=normalized_target,
                entity_type="company",
                value=company,
                source=self.name,
                confidence=self.base_confidence,
            )

        return ParsedToolOutput(self.name, target_type, normalized_target, entities, evidence, relationships)


def _resource_script(target_type: str, target: str, artifact: Path) -> str:
    workspace = re.sub(r"[^A-Za-z0-9_]", "_", f"osint_{target}")[:80]
    inserts = {
        "domain": f"db insert domains {target}",
        "email": f"db insert contacts email={target}",
        "company": f"db insert companies {target}",
    }
    return "\n".join(
        [
            f"workspaces create {workspace}",
            inserts[target_type],
            "modules load reporting/json",
            f"options set FILENAME {artifact}",
            "run",
            "exit",
            "",
        ]
    )


def _infer_target_type(value: str) -> str:
    if "@" in value:
        return "email"
    try:
        normalize_target("domain", value)
        return "domain"
    except ValueError:
        return "company"


def _values(items, key: str) -> list[str]:
    values = []
    for item in items or []:
        if isinstance(item, str):
            value = item
        elif isinstance(item, dict):
            value = str(item.get(key) or item.get("value") or "")
        else:
            value = str(item)
        value = value.strip()
        if value:
            values.append(value)
    return values


def _add_finding(
    entities,
    evidence,
    relationships,
    seen_entities,
    seen_evidence,
    seen_relationships,
    target: str,
    entity_type: str,
    value: str,
    source: str,
    confidence: float,
) -> None:
    append_unique_entity(
        entities,
        seen_entities,
        NormalizedEntity(entity_type, value, source, confidence),
    )
    append_unique_evidence(
        evidence,
        seen_evidence,
        NormalizedEvidence(value, "reconng_report_record", source, f"Recon-ng report included {value}"),
    )
    append_unique_relationship(
        relationships,
        seen_relationships,
        NormalizedRelationship(target, value, "reconng_finding", confidence),
    )
