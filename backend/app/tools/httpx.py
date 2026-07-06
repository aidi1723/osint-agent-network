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
    redacted_url,
)


class HttpxAdapter:
    name = "httpx"
    base_confidence = 0.62

    def __init__(
        self,
        command: str | None = None,
        request_timeout_seconds: int | None = None,
        retries: int | None = None,
        rate_limit: int | None = None,
        threads: int | None = None,
    ):
        self.command = command or os.getenv("HTTPX_COMMAND", "httpx")
        self.request_timeout_seconds = request_timeout_seconds or int(os.getenv("HTTPX_TIMEOUT_SECONDS", "8"))
        self.retries = retries if retries is not None else int(os.getenv("HTTPX_RETRIES", "0"))
        self.rate_limit = rate_limit or int(os.getenv("HTTPX_RATE_LIMIT", "20"))
        self.threads = threads or int(os.getenv("HTTPX_THREADS", "10"))

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type == "url":
            return redacted_url(target_value)
        if target_type in {"domain", "subdomain"}:
            return normalize_target("domain", target_value)
        raise ValueError("httpx accepts domain, subdomain, or url targets")

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 300,
    ) -> ToolCommand:
        target = self.validate_target(target_type, target_value)
        url = target if target.startswith(("http://", "https://")) else f"https://{target}"
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"httpx_{_safe_name(target)}.jsonl"
        return ToolCommand(
            args=[
                self.command,
                "-json",
                "-title",
                "-tech-detect",
                "-status-code",
                "-timeout",
                str(self.request_timeout_seconds),
                "-retries",
                str(self.retries),
                "-rl",
                str(self.rate_limit),
                "-t",
                str(self.threads),
                "-u",
                url,
                "-o",
                artifact.name,
            ],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        if not artifact_path.exists():
            return self.parse_jsonl([], target_type="url" if target_value.startswith(("http://", "https://")) else "domain", target_value=target_value)
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
        return self.parse_jsonl(records, target_type="url" if target_value.startswith(("http://", "https://")) else "domain", target_value=target_value)

    def parse_jsonl(self, records: list[dict], target_type: str, target_value: str) -> ParsedToolOutput:
        normalized_target = self.validate_target(target_type, target_value)
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        if target_type in {"domain", "subdomain"}:
            append_unique_entity(entities, seen_entities, NormalizedEntity(target_type, normalized_target, self.name, 0.55))

        for record in records:
            url = redacted_url(str(record.get("url") or "").strip())
            if not url:
                continue
            append_unique_entity(entities, seen_entities, NormalizedEntity("url", url, self.name, self.base_confidence))
            title = str(record.get("title") or "").strip()
            if title:
                append_unique_entity(entities, seen_entities, NormalizedEntity("website_title", title, self.name, 0.58))
                append_unique_relationship(
                    relationships,
                    seen_relationships,
                    NormalizedRelationship(url, title, "url_has_title", 0.58),
                )
            for tech in record.get("tech") or record.get("technologies") or []:
                tech_value = str(tech or "").strip()
                if not tech_value:
                    continue
                append_unique_entity(entities, seen_entities, NormalizedEntity("technology", tech_value, self.name, 0.42))
                append_unique_relationship(
                    relationships,
                    seen_relationships,
                    NormalizedRelationship(url, tech_value, "url_uses_technology", 0.42),
                )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(url, "http_probe", self.name, _snippet(record, url)),
            )
            source_host = str(record.get("input") or normalized_target).strip()
            if source_host and not source_host.startswith(("http://", "https://")):
                try:
                    source_host = normalize_target("domain", source_host)
                except ValueError:
                    source_host = normalized_target
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(source_host, url, "host_serves_url", self.base_confidence),
            )

        return ParsedToolOutput(self.name, target_type, normalized_target, entities, evidence, relationships)


def _snippet(record: dict, url: str) -> str:
    status = record.get("status_code") or record.get("status-code") or ""
    title = str(record.get("title") or "").strip()
    parts = [f"httpx confirmed live URL {url}"]
    if status:
        parts.append(f"status={status}")
    if title:
        parts.append(f"title={title}")
    return "; ".join(parts)


def _safe_name(value: str) -> str:
    return value.replace("https://", "").replace("http://", "").replace("/", "_").replace(":", "_")
