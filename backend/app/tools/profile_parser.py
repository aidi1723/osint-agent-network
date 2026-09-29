from __future__ import annotations

from html.parser import HTMLParser
import os
from pathlib import Path
import re

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


INTEREST_KEYWORDS = ("fintech", "crypto", "runner", "builder", "trader", "import", "export")


class ProfileParserAdapter:
    name = "profile_parser"
    target_type = "profile_url"
    base_confidence = 0.25

    def __init__(self, command: str | None = None):
        self.command = command or os.getenv("PROFILE_PARSER_COMMAND", "profile-parser")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("profile_parser only accepts profile_url targets")
        return normalize_target("profile_url", target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 60,
    ) -> ToolCommand:
        profile_url = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / "profile_parser_input.html"
        return ToolCommand(
            args=["PARSE_ARTIFACT", profile_url],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        return self.parse_html(artifact_path.read_text(encoding="utf-8"), profile_url=target_value)

    def parse_html(self, html: str, profile_url: str) -> ParsedToolOutput:
        normalized_url = normalize_target("profile_url", profile_url)
        parser = _ProfileHTMLParser()
        parser.feed(html)

        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(
            entities,
            seen_entities,
            NormalizedEntity("profile_url", normalized_url, self.name, self.base_confidence),
        )

        bio = parser.meta.get("og:description") or parser.meta.get("description") or ""
        image = parser.meta.get("og:image") or parser.meta.get("twitter:image") or ""
        location = parser.location_text

        _add_value(
            "bio_snippet",
            bio,
            normalized_url,
            entities,
            evidence,
            relationships,
            seen_entities,
            seen_evidence,
            seen_relationships,
        )
        _add_url_value(
            "profile_image_url",
            image,
            normalized_url,
            entities,
            evidence,
            relationships,
            seen_entities,
            seen_evidence,
            seen_relationships,
        )
        _add_value(
            "declared_location",
            location,
            normalized_url,
            entities,
            evidence,
            relationships,
            seen_entities,
            seen_evidence,
            seen_relationships,
            relationship_type="profile_declares_location",
        )

        for link in parser.links:
            _add_url_value(
                "external_link",
                link,
                normalized_url,
                entities,
                evidence,
                relationships,
                seen_entities,
                seen_evidence,
                seen_relationships,
            )

        combined_text = " ".join([bio, parser.title, location]).lower()
        for keyword in INTEREST_KEYWORDS:
            if re.search(rf"\b{re.escape(keyword)}\b", combined_text):
                _add_value(
                    "interest_tag",
                    keyword,
                    normalized_url,
                    entities,
                    evidence,
                    relationships,
                    seen_entities,
                    seen_evidence,
                    seen_relationships,
                    relationship_type="profile_mentions_interest",
                )

        return ParsedToolOutput(
            self.name,
            self.target_type,
            normalized_url,
            entities,
            evidence,
            relationships,
        )


class _ProfileHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta: dict[str, str] = {}
        self.links: list[str] = []
        self.title = ""
        self.location_text = ""
        self._in_title = False
        self._capture_location = False

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "meta":
            key = attr.get("property") or attr.get("name")
            content = attr.get("content")
            if key and content:
                self.meta[key] = content.strip()
        if tag == "a" and attr.get("href"):
            self.links.append(attr["href"].strip())
        if tag == "title":
            self._in_title = True
        if "location" in (attr.get("class") or "").lower():
            self._capture_location = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if self._capture_location and tag in {"span", "div", "p"}:
            self._capture_location = False

    def handle_data(self, data):
        value = data.strip()
        if not value:
            return
        if self._in_title:
            self.title = value
        if self._capture_location:
            self.location_text = value


def _add_value(
    entity_type,
    value,
    profile_url,
    entities,
    evidence,
    relationships,
    seen_entities,
    seen_evidence,
    seen_relationships,
    relationship_type=None,
):
    value = str(value or "").strip()
    if not value:
        return
    append_unique_entity(
        entities,
        seen_entities,
        NormalizedEntity(entity_type, value, "profile_parser", 0.25),
    )
    append_unique_evidence(
        evidence,
        seen_evidence,
        NormalizedEvidence(
            value,
            "public_profile_metadata",
            "profile_parser",
            f"Public profile metadata from {profile_url}",
        ),
    )
    append_unique_relationship(
        relationships,
        seen_relationships,
        NormalizedRelationship(
            profile_url,
            value,
            relationship_type or f"profile_has_{entity_type}",
            0.25,
        ),
    )


def _add_url_value(
    entity_type,
    value,
    profile_url,
    entities,
    evidence,
    relationships,
    seen_entities,
    seen_evidence,
    seen_relationships,
):
    value = str(value or "").strip()
    if not value:
        return
    try:
        normalized = normalize_target("url", value)
    except ValueError:
        return
    _add_value(
        entity_type,
        normalized,
        profile_url,
        entities,
        evidence,
        relationships,
        seen_entities,
        seen_evidence,
        seen_relationships,
    )
