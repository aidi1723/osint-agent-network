from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

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


class KatanaAdapter:
    name = "katana"
    target_type = "url"
    base_confidence = 0.50

    def __init__(
        self,
        command: str | None = None,
        depth: int | None = None,
        crawl_duration: str | None = None,
        request_timeout_seconds: int | None = None,
        retry_count: int | None = None,
        concurrency: int | None = None,
        rate_limit: int | None = None,
    ):
        self.command = command or os.getenv("KATANA_COMMAND", "katana")
        self.depth = depth or int(os.getenv("KATANA_DEPTH", "2"))
        self.crawl_duration = crawl_duration or os.getenv("KATANA_CRAWL_DURATION", "30s")
        self.request_timeout_seconds = request_timeout_seconds or int(os.getenv("KATANA_TIMEOUT_SECONDS", "8"))
        self.retry_count = retry_count if retry_count is not None else int(os.getenv("KATANA_RETRY", "0"))
        self.concurrency = concurrency or int(os.getenv("KATANA_CONCURRENCY", "5"))
        self.rate_limit = rate_limit or int(os.getenv("KATANA_RATE_LIMIT", "20"))

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != "url":
            raise ValueError("katana only accepts url targets")
        return redacted_url(target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 600,
    ) -> ToolCommand:
        url = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"katana_{_safe_name(url)}.jsonl"
        return ToolCommand(
            args=[
                self.command,
                "-u",
                url,
                "-jsonl",
                "-d",
                str(self.depth),
                "-ct",
                self.crawl_duration,
                "-timeout",
                str(self.request_timeout_seconds),
                "-retry",
                str(self.retry_count),
                "-c",
                str(self.concurrency),
                "-rl",
                str(self.rate_limit),
                "-o",
                artifact.name,
            ],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        if not artifact_path.exists():
            return self.parse_jsonl([], url=target_value)
        records = []
        for line in artifact_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                item = {"url": line}
            if isinstance(item, dict):
                records.append(item)
        return self.parse_jsonl(records, url=target_value)

    def parse_jsonl(self, records: list[dict], url: str) -> ParsedToolOutput:
        root_url = redacted_url(url)
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(entities, seen_entities, NormalizedEntity("url", root_url, self.name, self.base_confidence))
        for record in records:
            try:
                discovered = redacted_url(str(record.get("url") or record.get("request", {}).get("endpoint") or "").strip())
            except ValueError:
                continue
            if not discovered:
                continue
            page_type = _page_type(discovered)
            if not page_type:
                continue
            append_unique_entity(entities, seen_entities, NormalizedEntity("url", discovered, self.name, self.base_confidence))
            append_unique_entity(entities, seen_entities, NormalizedEntity(page_type, discovered, self.name, 0.56))
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(discovered, "katana_business_page", self.name, f"Katana found relevant page: {discovered}"),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(root_url, discovered, "site_has_relevant_page", 0.56),
            )

        return ParsedToolOutput(self.name, self.target_type, root_url, entities, evidence, relationships)


def _page_type(url: str) -> str:
    lowered = url.lower()
    if _looks_like_static_asset(lowered):
        return ""
    if any(token in lowered for token in ("contact", "about", "team", "staff")):
        return "contact_page"
    if any(token in lowered for token in ("product", "catalog", "service", "solution", "category")):
        return "business_scope_page"
    return ""


def _looks_like_static_asset(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.endswith(
        (
            ".css",
            ".js",
            ".mjs",
            ".map",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".webp",
            ".ico",
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            ".pdf",
            ".zip",
        )
    )


def _safe_name(value: str) -> str:
    return value.replace("https://", "").replace("http://", "").replace("/", "_").replace(":", "_")
