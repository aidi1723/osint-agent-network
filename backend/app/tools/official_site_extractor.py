from __future__ import annotations

import gzip
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re

from app.core.normalization import NormalizationError, normalize_target
from app.core.safe_http import (
    FakeIpApprovalRequired,
    SafeHttpError,
    fake_ip_allowance_from_env,
    safe_fetch,
)
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
from app.tools.official_site_semantics import (
    BUSINESS_SCOPE_PATTERNS,
    ContactCandidate,
    ScopeCandidate,
    extract_contact_candidates,
    extract_scope_candidates,
    is_role_linkable_contact,
)


ROLE_MARKERS = (
    "owner",
    "founder",
    "co-founder",
    "ceo",
    "president",
    "managing director",
    "director",
    "general manager",
    "sales manager",
    "export manager",
    "procurement manager",
    "purchasing manager",
    "contact person",
    "\u603b\u7ecf\u7406",
    "\u9500\u552e\u7ecf\u7406",
    "\u8d1f\u8d23\u4eba",
    "\u7ecf\u7406",
)
GENERIC_PERSON_LABELS = {
    "Contact Us",
    "Sales Team",
    "Customer Service",
    "About Us",
    "\u8054\u7cfb\u6211\u4eec",
    "\u5ba2\u670d",
    "\u9500\u552e\u56e2\u961f",
}
PERSON_HEADING_PREFIXES = {"leadership", "team", "management", "about", "contact"}
MAX_HTML_BYTES = 2 * 1024 * 1024
_PERSON_NAME_PATTERN = r"(?:[A-Z][A-Za-z'\u2019-]+(?:\s+[A-Z][A-Za-z'\u2019-]+){1,3}|[\u4e00-\u9fff]{2,4})"
_TITLE_SHAPE_PATTERN = r"(?:[A-Z][A-Za-z'\u2019-]+(?:\s+[A-Z][A-Za-z'\u2019-]+){0,3}|[\u4e00-\u9fff]{2,8})"
_NAME_TITLE_RECORD_RE = re.compile(
    rf"(?P<name>{_PERSON_NAME_PATTERN})\s*[,\uff0c|-]\s*(?P<title>{_TITLE_SHAPE_PATTERN})"
    rf"(?=$|[\s,\uff0c;\uff1b|:/()\-])"
)


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
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / "official_site_input.html"
        rejected_command = ToolCommand(
            args=["PARSE_ARTIFACT", "<rejected-target>"],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )
        command = rejected_command
        try:
            fake_ip_allowance = fake_ip_allowance_from_env()
            url = self.validate_target(target_type, target_value)
            command = self.build_command(target_type, url, workdir, timeout_seconds)
            response = safe_fetch(
                url,
                timeout_seconds=min(timeout_seconds, 15),
                max_bytes=MAX_HTML_BYTES,
                headers={
                    "User-Agent": "osint-agent-network/1.0 (+official-site-extractor)",
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                },
                fake_ip_allowance=fake_ip_allowance,
            )
            body = _decode_http_body(response.body, response)
            status = response.status
            truncated = len(body) > MAX_HTML_BYTES
            command.expected_artifact.write_bytes(body[:MAX_HTML_BYTES])
            return ToolRunResult(
                command=command,
                returncode=0 if 200 <= status < 400 else 1,
                stdout_excerpt=f"fetched official site html status={status} bytes={len(body[:MAX_HTML_BYTES])} truncated={truncated}",
                stderr_excerpt="",
            )
        except FakeIpApprovalRequired as exc:
            rejected_command.expected_artifact.write_text("", encoding="utf-8")
            return ToolRunResult(
                command=rejected_command,
                returncode=1,
                stdout_excerpt="",
                stderr_excerpt=f"fake_ip_review_required: {exc.hostname}",
            )
        except (NormalizationError, SafeHttpError):
            command.expected_artifact.write_text("", encoding="utf-8")
            return ToolRunResult(
                command=command,
                returncode=1,
                stdout_excerpt="",
                stderr_excerpt="official site fetch failed",
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
        text_blocks = parser.text_blocks or [parser.visible_text]
        scope_text_blocks = [parser.title, *text_blocks]
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

        for contact in extract_contact_candidates(text_blocks, structured):
            _add_contact_entity(
                contact,
                normalized_url,
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
            )

        for scope in extract_scope_candidates(
            structured,
            parser.meta_descriptions,
            parser.headings,
            scope_text_blocks,
            BUSINESS_SCOPE_PATTERNS,
        ):
            _add_scope_entity(
                scope,
                normalized_url,
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
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

        for candidate in _decision_maker_candidates(text_blocks, structured):
            _add_decision_maker_candidate(
                candidate,
                normalized_url,
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
            )

        return ParsedToolOutput(self.name, self.target_type, normalized_url, entities, evidence, relationships)


def _decode_http_body(body: bytes, response) -> bytes:
    headers = getattr(response, "headers", {}) or {}
    encoding = ""
    if hasattr(headers, "get"):
        encoding = str(headers.get("Content-Encoding", "") or "").lower()
    if "gzip" in encoding or body.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
                return stream.read(MAX_HTML_BYTES + 1)
        except (EOFError, OSError):
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


def _add_scope_entity(
    candidate: ScopeCandidate,
    url: str,
    entities: list[NormalizedEntity],
    evidence: list[NormalizedEvidence],
    relationships: list[NormalizedRelationship],
    seen_entities: set[tuple[str, str]],
    seen_evidence: set[tuple[str, str, str]],
    seen_relationships: set[tuple[str, str, str]],
) -> None:
    _add_sourced_entity(
        "business_scope",
        candidate.value,
        candidate.evidence_kind,
        candidate.snippet,
        "official_site_describes_business_scope",
        url,
        entities,
        evidence,
        relationships,
        seen_entities,
        seen_evidence,
        seen_relationships,
        candidate.confidence,
    )


def _add_contact_entity(
    candidate: ContactCandidate,
    url: str,
    entities: list[NormalizedEntity],
    evidence: list[NormalizedEvidence],
    relationships: list[NormalizedRelationship],
    seen_entities: set[tuple[str, str]],
    seen_evidence: set[tuple[str, str, str]],
    seen_relationships: set[tuple[str, str, str]],
) -> None:
    confidence = {"email": 0.82, "phone": 0.78, "fax": 0.78}[candidate.entity_type]
    _add_sourced_entity(
        candidate.entity_type,
        candidate.value,
        f"official_site_contact_{candidate.classification}",
        candidate.snippet,
        f"official_site_has_contact_{candidate.entity_type}",
        url,
        entities,
        evidence,
        relationships,
        seen_entities,
        seen_evidence,
        seen_relationships,
        confidence,
    )


def _add_sourced_entity(
    entity_type: str,
    value: str,
    evidence_kind: str,
    snippet: str,
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
    append_unique_entity(
        entities,
        seen_entities,
        NormalizedEntity(entity_type, normalized_value, "official_site_extractor", confidence),
    )
    append_unique_evidence(
        evidence,
        seen_evidence,
        NormalizedEvidence(normalized_value, evidence_kind, "official_site_extractor", snippet),
    )
    append_unique_relationship(
        relationships,
        seen_relationships,
        NormalizedRelationship(url, normalized_value, relationship_type, confidence),
    )


def _add_decision_maker_candidate(
    candidate: dict,
    url: str,
    entities: list[NormalizedEntity],
    evidence: list[NormalizedEvidence],
    relationships: list[NormalizedRelationship],
    seen_entities: set[tuple[str, str]],
    seen_evidence: set[tuple[str, str, str]],
    seen_relationships: set[tuple[str, str, str]],
) -> None:
    name = str(candidate.get("name") or "")
    title = str(candidate.get("title") or "")
    confidence = float(candidate.get("confidence") or 0.66)
    if not name or not title:
        return
    decision_value = f"{name} - {title}"
    snippet = f"Official site {url} lists {decision_value}"
    append_unique_entity(entities, seen_entities, NormalizedEntity("person", name, "official_site_extractor", confidence))
    append_unique_entity(entities, seen_entities, NormalizedEntity("job_title", title, "official_site_extractor", confidence))
    append_unique_entity(entities, seen_entities, NormalizedEntity("decision_maker", decision_value, "official_site_extractor", confidence))
    append_unique_evidence(
        evidence,
        seen_evidence,
        NormalizedEvidence(name, "official_site_decision_maker_candidate", "official_site_extractor", snippet),
    )
    append_unique_relationship(
        relationships,
        seen_relationships,
        NormalizedRelationship(url, name, "official_site_mentions_decision_maker", confidence),
    )
    append_unique_relationship(
        relationships,
        seen_relationships,
        NormalizedRelationship(name, title, "person_has_public_role", confidence),
    )
    for contact in extract_contact_candidates([str(candidate.get("context") or "")], []):
        if not is_role_linkable_contact(contact):
            continue
        normalized_contact = _normalize_entity_value(contact.entity_type, contact.value)
        if not normalized_contact:
            continue
        append_unique_evidence(
            evidence,
            seen_evidence,
            NormalizedEvidence(
                normalized_contact,
                "official_site_role_linked_contact",
                "official_site_extractor",
                contact.snippet,
            ),
        )
        append_unique_relationship(
            relationships,
            seen_relationships,
            NormalizedRelationship(name, normalized_contact, "person_has_role_linked_contact", min(confidence, 0.64)),
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
    if entity_type in {"phone", "fax"}:
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
        except (json.JSONDecodeError, RecursionError):
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


def _decision_maker_candidates(text_blocks: list[str], items: list[dict]) -> list[dict]:
    candidates = []
    candidates.extend(_json_ld_people(items))
    candidates.extend(_visible_text_people(text_blocks))
    seen: set[tuple[str, str]] = set()
    result = []
    for candidate in candidates:
        key = (candidate["name"].lower(), candidate["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result[:5]


def _json_ld_people(items: list[dict]) -> list[dict]:
    candidates = []
    for item in items:
        item_type = item.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        if not any(str(t).lower() == "person" for t in types):
            continue
        name = _normalize_person_name(str(item.get("name") or ""))
        title = _normalize_job_title(str(item.get("jobTitle") or item.get("title") or ""))
        if not name or not title:
            continue
        context = " ".join(
            str(item.get(key) or "")
            for key in ("name", "jobTitle", "title", "email", "telephone", "phone")
            if str(item.get(key) or "")
        )
        candidates.append({"name": name, "title": title, "confidence": 0.70, "context": context})
    return candidates


def _visible_text_people(text_blocks: list[str]) -> list[dict]:
    candidates = []
    for part in text_blocks:
        window = _normalize_space(part)
        if not window:
            continue
        boundary_starts = sorted({match.start() for match in _NAME_TITLE_RECORD_RE.finditer(window)})
        matches: list[tuple[int, int, str, str]] = []
        for marker in ROLE_MARKERS:
            marker_flags = re.IGNORECASE if marker.isascii() else 0
            for match in re.finditer(
                rf"(?P<name>{_PERSON_NAME_PATTERN})\s*[,\uff0c|-]\s*(?P<title>{re.escape(marker)})(?=$|[\s,\uff0c;\uff1b|:/()\-])",
                window,
                flags=marker_flags,
            ):
                name = _normalize_person_name(match.group("name"))
                title = _normalize_job_title(match.group("title"))
                if name and title:
                    matches.append((match.start(), match.end(), name, title))
        matches.sort(key=lambda item: (item[0], item[1], item[2].casefold(), item[3].casefold()))
        seen_starts: set[int] = set()
        for start, _end, name, title in matches:
            if start in seen_starts:
                continue
            seen_starts.add(start)
            next_start = next((item for item in boundary_starts if item > start), len(window))
            context = window[start : min(next_start, start + 240)]
            candidates.append({"name": name, "title": title, "confidence": 0.66, "context": context})
    return candidates


def _normalize_person_name(value: str) -> str:
    name = _normalize_space(value).strip(" .,:;-")
    if name in GENERIC_PERSON_LABELS:
        return ""
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", name):
        return name
    tokens = name.split()
    if len(tokens) > 2 and tokens[0].lower() in PERSON_HEADING_PREFIXES:
        tokens = tokens[1:]
        name = " ".join(tokens)
    if len(tokens) < 2 or len(tokens) > 4:
        return ""
    if any(token.lower() in {"contact", "sales", "team", "service", "about"} for token in tokens):
        return ""
    return name


def _normalize_job_title(value: str) -> str:
    title = _normalize_space(value).strip(" .,:;-")
    for marker in ROLE_MARKERS:
        if title.lower() == marker:
            if not marker.isascii():
                return marker
            return " ".join(part.capitalize() if part.lower() != "ceo" else "CEO" for part in marker.split())
    return ""


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class _OfficialSiteHTMLParser(HTMLParser):
    _BLOCK_TAGS = {"address", "article", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "p", "section", "td", "th"}
    _HEADING_TAGS = {"h1", "h2", "h3"}

    def __init__(self):
        super().__init__()
        self.title = ""
        self.visible_text = ""
        self.json_ld: list[str] = []
        self.meta_descriptions: list[str] = []
        self.headings: list[str] = []
        self._in_title = False
        self._in_script_json_ld = False
        self._script_chunks: list[str] = []
        self._skip_depth = 0
        self._active_heading = ""
        self._heading_chunks: list[str] = []

    @property
    def text_blocks(self) -> list[str]:
        return [
            _normalize_space(block)
            for block in re.split(r"\n\s*\n", self.visible_text)
            if _normalize_space(block)
        ]

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        attrs_dict = {key.lower(): value for key, value in attrs}
        if tag == "meta":
            descriptor = str(
                attrs_dict.get("name") or attrs_dict.get("property") or attrs_dict.get("itemprop") or ""
            ).lower()
            content = str(attrs_dict.get("content") or "")
            if descriptor in {"description", "og:description", "twitter:description"} and content.strip():
                self.meta_descriptions.append(content)
        if tag in self._BLOCK_TAGS:
            self.visible_text += "\n\n"
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in self._HEADING_TAGS and not self._skip_depth:
            self._active_heading = tag
            self._heading_chunks = []
        if tag == "script" and str(attrs_dict.get("type") or "").lower() == "application/ld+json":
            self._in_script_json_ld = True
            self._script_chunks = []

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag == self._active_heading:
            heading = _normalize_space(" ".join(self._heading_chunks))
            if heading:
                self.headings.append(heading)
            self._active_heading = ""
            self._heading_chunks = []
        if tag == "script" and self._in_script_json_ld:
            self.json_ld.append("".join(self._script_chunks))
            self._script_chunks = []
            self._in_script_json_ld = False
        if tag in self._BLOCK_TAGS:
            self.visible_text += "\n\n"

    def handle_data(self, data: str):
        if self._in_script_json_ld:
            self._script_chunks.append(data)
            return
        if self._in_title:
            self.title += " " + data
            return
        if self._active_heading and not self._skip_depth:
            self._heading_chunks.append(data)
        if not self._skip_depth:
            self.visible_text += " " + data
