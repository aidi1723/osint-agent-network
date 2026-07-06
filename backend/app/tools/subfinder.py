from __future__ import annotations

import json
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
)


class SubfinderAdapter:
    name = "subfinder"
    target_type = "domain"
    base_confidence = 0.48

    def __init__(
        self,
        command: str | None = None,
        max_time_minutes: int | None = None,
        request_timeout_seconds: int | None = None,
        result_limit: int | None = None,
    ):
        self.command = command or os.getenv("SUBFINDER_COMMAND", "subfinder")
        self.max_time_minutes = max_time_minutes or int(os.getenv("SUBFINDER_MAX_TIME_MINUTES", "1"))
        self.request_timeout_seconds = request_timeout_seconds or int(os.getenv("SUBFINDER_TIMEOUT_SECONDS", "8"))
        self.result_limit = max(1, result_limit or int(os.getenv("SUBFINDER_RESULT_LIMIT", "300")))

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("subfinder only accepts domain targets")
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
        artifact = workdir / f"subfinder_{domain}.jsonl"
        return ToolCommand(
            args=[
                self.command,
                "-d",
                domain,
                "-json",
                "-max-time",
                str(self.max_time_minutes),
                "-timeout",
                str(self.request_timeout_seconds),
                "-o",
                artifact.name,
            ],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        if not artifact_path.exists():
            return self.parse_jsonl([], domain=target_value)
        records = []
        for line in artifact_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                item = {"host": line}
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
            NormalizedEntity("domain", normalized_domain, self.name, self.base_confidence),
        )

        emitted_subdomains = 0
        for record in records:
            if emitted_subdomains >= self.result_limit:
                break
            raw_host = str(record.get("host") or record.get("input") or record.get("fqdn") or "").strip()
            if not raw_host:
                continue
            try:
                host = normalize_target("domain", raw_host.lower().rstrip("."))
            except ValueError:
                continue
            if host == normalized_domain:
                continue
            if ("subdomain", host) not in seen_entities:
                emitted_subdomains += 1
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity("subdomain", host, self.name, self.base_confidence),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(host, "subfinder_passive_discovery", self.name, _snippet(record, host)),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(normalized_domain, host, "domain_has_subdomain", self.base_confidence),
            )

        return ParsedToolOutput(self.name, self.target_type, normalized_domain, entities, evidence, relationships)


def _snippet(record: dict, host: str) -> str:
    sources = record.get("sources") or record.get("source") or []
    if isinstance(sources, str):
        sources = [sources]
    if sources:
        return f"Subfinder discovered {host} via {', '.join(str(item) for item in sources[:3])}"
    return f"Subfinder discovered {host}"
