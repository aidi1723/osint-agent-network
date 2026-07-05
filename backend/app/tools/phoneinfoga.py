from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import request
from urllib.parse import quote

from app.core.normalization import normalize_target
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
    ToolCommand,
    ToolRunResult,
    append_unique_entity,
    append_unique_evidence,
    append_unique_relationship,
    read_json_artifact,
    redacted_url,
    write_json_artifact,
)


class PhoneInfogaAdapter:
    name = "phoneinfoga"
    target_type = "phone"
    base_confidence = 0.45

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.getenv("PHONEINFOGA_BASE_URL", "http://localhost:5000")).rstrip("/")
        self.api_key = api_key or os.getenv("PHONEINFOGA_API_KEY", "")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("PhoneInfoga only accepts phone targets")
        return normalize_target("phone", target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 120,
    ) -> ToolCommand:
        phone = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        url = f"{self.base_url}/api/v2/numbers"
        return ToolCommand(
            args=["POST", redacted_url(url), phone],
            cwd=workdir,
            expected_artifact=workdir / f"phoneinfoga_{phone.replace('+', '')}.json",
            timeout_seconds=timeout_seconds,
        )

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int) -> ToolRunResult:
        command = self.build_command(target_type, target_value, workdir, timeout_seconds)
        phone = self.validate_target(target_type, target_value)
        url = f"{self.base_url}/api/v2/numbers"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers["Content-Type"] = "application/json"
        try:
            payload = json.dumps({"number": phone.lstrip("+")}).encode("utf-8")
            req = request.Request(url, data=payload, headers=headers, method="POST")
            with request.urlopen(req, timeout=timeout_seconds) as response:
                response_payload = response.read().decode("utf-8")
            command.expected_artifact.write_text(response_payload, encoding="utf-8")
            return ToolRunResult(command, 0, "PhoneInfoga response saved", "")
        except Exception as exc:
            legacy_url = f"{self.base_url}/api/v1/number/{quote(phone, safe='')}"
            try:
                req = request.Request(legacy_url, headers={key: value for key, value in headers.items() if key != "Content-Type"}, method="GET")
                with request.urlopen(req, timeout=timeout_seconds) as response:
                    response_payload = response.read().decode("utf-8")
                command.expected_artifact.write_text(response_payload, encoding="utf-8")
                return ToolRunResult(command, 0, "PhoneInfoga legacy response saved", "")
            except Exception as legacy_exc:
                write_json_artifact(command.expected_artifact, {"valid": False, "error": f"{exc}; legacy: {legacy_exc}"})
                return ToolRunResult(command, 1, "", str(exc))

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        return self.parse_json(read_json_artifact(artifact_path), phone=target_value)

    def parse_json(self, raw: dict, phone: str) -> ParsedToolOutput:
        normalized_phone = normalize_target("phone", raw.get("e164") or raw.get("number") or phone)
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(
            entities,
            seen_entities,
            NormalizedEntity("phone", normalized_phone, self.name, self.base_confidence),
        )

        if raw.get("valid") is False:
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(normalized_phone, "negative_result", self.name, str(raw.get("error") or "invalid phone")),
            )
            return ParsedToolOutput(self.name, self.target_type, normalized_phone, entities, evidence, relationships)

        metadata_parts = []
        for key in ("country", "carrier", "line_type", "lineType", "timezone", "local", "international", "countryCode"):
            if raw.get(key):
                metadata_parts.append(f"{key}={raw[key]}")
        if raw.get("timezones"):
            metadata_parts.append("timezones=" + ",".join(str(item) for item in raw["timezones"]))
        append_unique_evidence(
            evidence,
            seen_evidence,
            NormalizedEvidence(
                normalized_phone,
                "phone_metadata",
                self.name,
                "; ".join(metadata_parts) if metadata_parts else "PhoneInfoga returned phone metadata",
            ),
        )

        for url in _footprint_urls(raw):
            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity("url", url, self.name, 0.35),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(url, "phone_public_footprint", self.name, "PhoneInfoga returned public footprint URL"),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(normalized_phone, url, "phone_referenced_by_url", 0.35),
            )

        return ParsedToolOutput(self.name, self.target_type, normalized_phone, entities, evidence, relationships)


def _footprint_urls(raw: dict) -> list[str]:
    values = []
    for key in ("footprints", "results", "links", "urls"):
        items = raw.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    values.append(item)
                elif isinstance(item, dict):
                    values.append(str(item.get("url") or item.get("link") or ""))
    return [value.strip() for value in values if isinstance(value, str) and value.strip().startswith("http")]
