from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib import parse, request

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
    read_json_artifact,
)


class OfficialSiteSearchAdapter:
    name = "official_site_search"
    base_confidence = 0.58

    def __init__(self, base_url: str | None = None, command: str | None = None):
        self.base_url = base_url or os.getenv("OFFICIAL_SITE_SEARCH_BASE_URL", "")
        self.command = command or os.getenv("OFFICIAL_SITE_SEARCH_COMMAND", "python3")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type not in {"company", "sparse_lead"}:
            raise ValueError("official_site_search accepts company or sparse_lead targets")
        return normalize_target(target_type, target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 90,
    ) -> ToolCommand:
        target = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"official_site_search_{_safe_slug(target)}.json"
        return ToolCommand(
            args=[
                self.command,
                "-m",
                "app.tools.official_site_search",
                "--target-type",
                target_type,
                "--target",
                target,
                "--query",
                _official_query(target),
                "--base-url",
                self.base_url,
                "--output",
                str(artifact),
            ],
            cwd=workdir,
            expected_artifact=artifact,
            timeout_seconds=timeout_seconds,
        )

    def run(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int,
        fetch_fn=None,
    ) -> ToolRunResult:
        command = self.build_command(target_type, target_value, workdir, timeout_seconds)
        fetch = fetch_fn or fetch_search_payload
        try:
            payload = fetch(self.base_url, _official_query(self.validate_target(target_type, target_value)), timeout_seconds)
            payload["target_type"] = target_type
            payload["target_value"] = self.validate_target(target_type, target_value)
            command.expected_artifact.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return ToolRunResult(command, 0, "Official-site search artifact saved", "")
        except Exception as exc:
            fallback = {
                "target_type": target_type,
                "target_value": self.validate_target(target_type, target_value),
                "query": _official_query(self.validate_target(target_type, target_value)),
                "results": [],
                "error": str(exc),
            }
            command.expected_artifact.write_text(json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8")
            return ToolRunResult(command, 1, "", str(exc))

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        raw = read_json_artifact(artifact_path) if artifact_path.exists() else {"results": []}
        target_type = str(raw.get("target_type") or "company")
        return self.parse_json(raw, target_type=target_type, target_value=target_value)

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
            NormalizedEntity(target_type, normalized_target, self.name, 0.55),
        )

        for result in _result_records(raw):
            url = redacted_url(str(result.get("url") or result.get("link") or "").strip())
            title = str(result.get("title") or "").strip()
            snippet = str(result.get("content") or result.get("snippet") or "").strip()
            if not url or not _looks_like_official_result(normalized_target, url, title, snippet):
                continue
            confidence = _candidate_confidence(normalized_target, url, title, snippet)
            append_unique_entity(entities, seen_entities, NormalizedEntity("url", url, self.name, confidence))
            if title:
                append_unique_entity(
                    entities,
                    seen_entities,
                    NormalizedEntity("website_title", title, self.name, min(confidence, 0.62)),
                )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(url, "official_site_search_result", self.name, _snippet(title, snippet, url)),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(normalized_target, url, f"{target_type}_has_official_site_candidate", confidence),
            )

        return ParsedToolOutput(self.name, target_type, normalized_target, entities, evidence, relationships)


def fetch_search_payload(base_url: str, query: str, timeout_seconds: int) -> dict:
    if not base_url:
        raise ValueError("OFFICIAL_SITE_SEARCH_BASE_URL is not configured")
    separator = "&" if "?" in base_url else "?"
    url = f"{base_url}{separator}{parse.urlencode({'q': query, 'format': 'json'})}"
    req = request.Request(url, headers={"Accept": "application/json", "User-Agent": "osint-agent-network/official-site-search"})
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch official-site search candidates from a SearXNG-compatible endpoint")
    parser.add_argument("--target-type", required=True, choices=["company", "sparse_lead"])
    parser.add_argument("--target", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args(argv)
    payload = fetch_search_payload(args.base_url, args.query, args.timeout)
    payload["target_type"] = args.target_type
    payload["target_value"] = args.target
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _official_query(target: str) -> str:
    return f'"{target}" official website contact'


def _result_records(raw: dict) -> list[dict]:
    values = raw.get("results") or raw.get("items") or []
    return [item for item in values if isinstance(item, dict)]


def _looks_like_official_result(target: str, url: str, title: str, snippet: str) -> bool:
    parsed = parse.urlsplit(url)
    host = parsed.netloc.lower()
    if not host or any(token in host for token in _EXCLUDED_HOST_TOKENS):
        return False
    if _is_third_party_content_result(host, parsed.path, title, snippet):
        return False
    text = f"{title} {snippet} {host}".lower()
    target_tokens = _target_signal_tokens(target)
    host_token_matches = sum(1 for token in target_tokens if token in host)
    text_token_matches = sum(1 for token in target_tokens if token in text)
    if host_token_matches >= 1:
        return True
    return text_token_matches >= 1 and "official" in f"{title} {host}".lower()


def _is_third_party_content_result(host: str, path: str, title: str, snippet: str) -> bool:
    text = f"{host} {path} {title} {snippet}".lower()
    return any(token in text for token in _THIRD_PARTY_CONTENT_TOKENS)


def _candidate_confidence(target: str, url: str, title: str, snippet: str) -> float:
    host = parse.urlsplit(url).netloc.lower()
    text = f"{title} {snippet} {host}".lower()
    score = 0.50
    if any(token in host for token in _target_signal_tokens(target)):
        score += 0.08
    if "official" in text:
        score += 0.08
    if "contact" in text or "about" in text:
        score += 0.04
    if sum(1 for token in _target_signal_tokens(target) if token in text) >= 2:
        score += 0.05
    return min(score, 0.68)


def _tokenize(value: str) -> list[str]:
    return [token for token in "".join(ch.lower() if ch.isalnum() else " " for ch in value).split() if token]


def _target_signal_tokens(value: str) -> list[str]:
    return [token for token in _tokenize(value) if len(token) >= 4 and token not in _TARGET_TOKEN_STOPWORDS]


def _snippet(title: str, snippet: str, url: str) -> str:
    parts = [f"official-site search found {url}"]
    if title:
        parts.append(f"title={title}")
    if snippet:
        parts.append(f"snippet={snippet[:240]}")
    return "; ".join(parts)


def _safe_slug(value: str) -> str:
    return "_".join(_tokenize(value))[:80] or "target"


_EXCLUDED_HOST_TOKENS = (
    "directory",
    "linkedin",
    "facebook",
    "twitter",
    "instagram",
    "reddit",
    "stackexchange",
    "wikipedia",
    "medium",
    "blogspot",
    "wordpress",
    "youtube",
    "tiktok",
    "pinterest",
    "crunchbase",
    "foundationcenter",
    "alibaba",
    "yellowpages",
    "zoominfo",
    "dnb",
    "yelp",
    "google",
    "bing",
)

_THIRD_PARTY_CONTENT_TOKENS = (
    "/blog/",
    "/wiki/",
    "/questions/",
    "/r/",
    " blog article ",
    " discussion ",
    " forum ",
    " third-party ",
)

_TARGET_TOKEN_STOPWORDS = {
    "company",
    "corporation",
    "corp",
    "domain",
    "foundation",
    "global",
    "group",
    "inc",
    "international",
    "limited",
    "llc",
    "official",
    "trading",
    "website",
}


if __name__ == "__main__":
    raise SystemExit(main())
