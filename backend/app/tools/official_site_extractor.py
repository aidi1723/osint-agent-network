from __future__ import annotations

import gzip
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
from urllib import error, request

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
    redacted_url,
)


BUSINESS_SCOPE_PATTERNS = (
    "auto parts",
    "automotive spare parts",
    "spare parts",
    "brake components",
    "suspension parts",
    "engine parts",
    "uPVC windows",
    "aluminum curtain wall systems",
    "curtain wall",
    "sliding doors",
    "doors",
    "windows",
)
MAX_HTML_BYTES = 2 * 1024 * 1024


class OfficialSiteExtractorAdapter:
    name = "official_site_extractor"
    target_type = "url"
    base_confidence = 0.72

    def __init__(self, command: str | None = None):
        self.command = command or os.getenv("OFFICIAL_SITE_EXTRACTOR_COMMAND", "official-site-extractor")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != "url":
            raise ValueError("official_site_extractor only accepts url targets")
        return normalize_target("url", redacted_url(target_value))

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 60,
    ) -> ToolCommand:
        url = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / "official_site_input.html"
        return ToolCommand(
            args=["PARSE_ARTIFACT", url],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int) -> ToolRunResult:
        url = self.validate_target(target_type, target_value)
        command = self.build_command(target_type, url, workdir, timeout_seconds)
        command.expected_artifact.parent.mkdir(parents=True, exist_ok=True)
        try:
            req = request.Request(
                url,
                headers={
                    "User-Agent": "osint-agent-network/1.0 (+official-site-extractor)",
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                },
            )
            with request.urlopen(req, timeout=min(timeout_seconds, 15)) as response:
                body = response.read(MAX_HTML_BYTES + 1)
                status = int(getattr(response, "status", 200) or 200)
                body = _decode_http_body(body, response)
            truncated = len(body) > MAX_HTML_BYTES
            command.expected_artifact.write_bytes(body[:MAX_HTML_BYTES])
            return ToolRunResult(
                command=command,
                returncode=0 if 200 <= status < 400 else 1,
                stdout_excerpt=f"fetched official site html status={status} bytes={len(body[:MAX_HTML_BYTES])} truncated={truncated}",
                stderr_excerpt="",
            )
        except (OSError, error.URLError, TimeoutError) as exc:
            command.expected_artifact.write_text("", encoding="utf-8")
            return ToolRunResult(
                command=command,
                returncode=1,
                stdout_excerpt="",
                stderr_excerpt=str(exc),
            )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        if not artifact_path.exists():
            return self.parse_html("", url=target_value)
        return self.parse_html(artifact_path.read_bytes().decode("utf-8", errors="replace"), url=target_value)

    def parse_html(self, html: str, url: str) -> ParsedToolOutput:
        normalized_url = self.validate_target("url", url)
        parser = _OfficialSiteHTMLParser()
        parser.feed(html)
        text = _normalize_space(" ".join([parser.title, parser.visible_text]))
        structured = _structured_items(parser.json_ld)

        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(entities, seen_entities, NormalizedEntity("url", normalized_url, self.name, self.base_confidence))

        for organization in _organizations(structured, text):
            _add_entity(
                "organization",
                organization,
                "official_site_identity",
                "official_site_names_organization",
                normalized_url,
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
                confidence=0.76,
            )

        for email in _emails(text, structured):
            _add_entity(
                "email",
                email,
                "official_site_contact",
                "official_site_has_contact_email",
                normalized_url,
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
                confidence=0.82,
            )

        for phone in _phones(text, structured):
            _add_entity(
                "phone",
                phone,
                "official_site_contact",
                "official_site_has_contact_phone",
                normalized_url,
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
                confidence=0.78,
            )

        for scope in _business_scopes(text):
            _add_entity(
                "business_scope",
                scope,
                "official_site_business_scope",
                "official_site_describes_business_scope",
                normalized_url,
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
                confidence=0.74,
            )

        for address in _addresses(text, structured):
            _add_entity(
                "address",
                address,
                "official_site_address",
                "official_site_lists_address",
                normalized_url,
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
                confidence=0.70,
            )

        return ParsedToolOutput(self.name, self.target_type, normalized_url, entities, evidence, relationships)


def _decode_http_body(body: bytes, response) -> bytes:
    headers = getattr(response, "headers", {}) or {}
    encoding = ""
    if hasattr(headers, "get"):
        encoding = str(headers.get("Content-Encoding", "") or "").lower()
    if "gzip" in encoding or body.startswith(b"\x1f\x8b"):
        try:
            return gzip.decompress(body)
        except OSError:
            return body
    return body


def _add_entity(
    entity_type: str,
    value: str,
    evidence_kind: str,
    relationship_type: str,
    url: str,
    entities: list[NormalizedEntity],
    evidence: list[NormalizedEvidence],
    relationships: list[NormalizedRelationship],
    seen_entities: set[tuple[str, str]],
    seen_evidence: set[tuple[str, str, str]],
    seen_relationships: set[tuple[str, str, str]],
    confidence: float,
) -> None:
    normalized_value = _normalize_entity_value(entity_type, value)
    if not normalized_value:
        return
    append_unique_entity(entities, seen_entities, NormalizedEntity(entity_type, normalized_value, "official_site_extractor", confidence))
    append_unique_evidence(
        evidence,
        seen_evidence,
        NormalizedEvidence(normalized_value, evidence_kind, "official_site_extractor", f"Official site {url} contains {entity_type}: {normalized_value}"),
    )
    append_unique_relationship(
        relationships,
        seen_relationships,
        NormalizedRelationship(url, normalized_value, relationship_type, confidence),
    )


def _normalize_entity_value(entity_type: str, value: str) -> str:
    value = _normalize_space(value).strip(" .,:;")
    if not value:
        return ""
    if entity_type == "email":
        try:
            return normalize_target("email", value)
        except ValueError:
            return ""
    if entity_type == "phone":
        digits = re.sub(r"\D+", "", value)
        if not 7 <= len(digits) <= 15:
            return ""
        return "+" + digits if value.strip().startswith("+") else digits
    return value


def _structured_items(values: list[str]) -> list[dict]:
    items: list[dict] = []
    for raw in values:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            items.extend(item for item in parsed if isinstance(item, dict))
        elif isinstance(parsed, dict):
            graph = parsed.get("@graph")
            if isinstance(graph, list):
                items.extend(item for item in graph if isinstance(item, dict))
            items.append(parsed)
    return items


def _organizations(items: list[dict], text: str) -> list[str]:
    values = []
    for item in items:
        item_type = item.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        if any(str(t).lower() in {"organization", "localbusiness", "corporation"} for t in types):
            name = str(item.get("name") or "").strip()
            if name:
                values.append(name)
    heading_match = re.search(
        r"\b([A-Z][A-Za-z0-9&.,' -]{2,100}?\s(?:LLC|INC|LTD|LIMITED|COMPANY(?:\s+LIMITED)?|CORPORATION|CORP|CO\.?\s*LTD\.?))\b",
        text,
        flags=re.IGNORECASE,
    )
    if heading_match:
        values.append(heading_match.group(1))
    return values[:3]


def _emails(text: str, items: list[dict]) -> list[str]:
    values = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    for item in items:
        email = str(item.get("email") or "").strip()
        if email:
            values.append(email)
    return values[:5]


def _phones(text: str, items: list[dict]) -> list[str]:
    values = re.findall(
        r"(?:\+\d[\d .()/-]{7,}\d|\b0?\d{2,3}[\s.-]\d{3,4}[\s.-]\d{4}\b|\b\d{3}[\s.-]\d{3}[\s.-]\d{4}\b)",
        text,
    )
    for item in items:
        phone = str(item.get("telephone") or item.get("phone") or "").strip()
        if phone:
            values.append(phone)
    return values[:5]


def _business_scopes(text: str) -> list[str]:
    lowered = text.lower()
    values = []
    for pattern in BUSINESS_SCOPE_PATTERNS:
        if pattern.lower() in lowered:
            values.append(pattern)
    return values[:5]


def _addresses(text: str, items: list[dict]) -> list[str]:
    values = []
    for item in items:
        address = item.get("address")
        if isinstance(address, str):
            values.append(address)
        elif isinstance(address, dict):
            parts = [
                str(address.get(key) or "").strip()
                for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")
                if str(address.get(key) or "").strip()
            ]
            if parts:
                values.append(", ".join(parts))
    match = re.search(r"Address:\s*([^.\n<]+)", text, flags=re.IGNORECASE)
    if match:
        values.append(match.group(1))
    return values[:3]


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class _OfficialSiteHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.visible_text = ""
        self.json_ld: list[str] = []
        self._in_title = False
        self._in_script_json_ld = False
        self._script_chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        attrs_dict = {key.lower(): value for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "script" and str(attrs_dict.get("type") or "").lower() == "application/ld+json":
            self._in_script_json_ld = True
            self._script_chunks = []

    def handle_endtag(self, tag: str):
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._in_script_json_ld:
            self.json_ld.append("".join(self._script_chunks))
            self._script_chunks = []
            self._in_script_json_ld = False

    def handle_data(self, data: str):
        if self._in_script_json_ld:
            self._script_chunks.append(data)
            return
        if self._in_title:
            self.title += " " + data
            return
        if not self._skip_depth:
            self.visible_text += " " + data
