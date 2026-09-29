from __future__ import annotations

import argparse
from email.utils import parsedate_to_datetime
from html import unescape
import json
import os
from pathlib import Path
import re
from urllib import request
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

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
)


class CompanyNewsAdapter:
    name = "company_news"
    target_type = "company"
    base_confidence = 0.42

    def __init__(self, command: str | None = None, source: str | None = None):
        self.command = command or os.getenv("COMPANY_NEWS_COMMAND", "python3")
        self.source = source or os.getenv("COMPANY_NEWS_SOURCE", "gnews")

    def validate_target(self, target_type: str, target_value: str) -> str:
        if target_type != self.target_type:
            raise ValueError("Company News only accepts company targets")
        return normalize_target("company", target_value)

    def build_command(
        self,
        target_type: str,
        target_value: str,
        workdir: Path,
        timeout_seconds: int = 120,
    ) -> ToolCommand:
        company = self.validate_target(target_type, target_value)
        workdir.mkdir(parents=True, exist_ok=True)
        artifact = workdir / f"company_news_{_safe_slug(company)}.json"
        return ToolCommand(
            args=[
                self.command,
                "-m",
                "app.tools.company_news",
                "--company",
                company,
                "--source",
                self.source,
                "--limit",
                os.getenv("COMPANY_NEWS_LIMIT", "10"),
                "--days",
                os.getenv("COMPANY_NEWS_DAYS", "365"),
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
        company = self.validate_target(target_type, target_value)
        fetch = fetch_fn or self.fetch_news_payload
        try:
            payload = fetch(
                company=company,
                source=self.source,
                limit=int(os.getenv("COMPANY_NEWS_LIMIT", "10")),
                days=int(os.getenv("COMPANY_NEWS_DAYS", "365")),
                timeout_seconds=timeout_seconds,
            )
            command.expected_artifact.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return ToolRunResult(command, 0, "Company news artifact saved", "")
        except Exception as exc:
            command.expected_artifact.write_text(
                json.dumps({"source": self.source, "query": f'"{company}" company news', "articles": [], "error": str(exc)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return ToolRunResult(command, 1, "", str(exc))

    def parse_artifact(self, artifact_path: Path, target_value: str) -> ParsedToolOutput:
        return self.parse_json(read_json_artifact(artifact_path), company=target_value)

    def parse_json(self, raw: dict, company: str) -> ParsedToolOutput:
        normalized_company = self.validate_target("company", company)
        records = _article_records(raw)
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []
        seen_entities: set[tuple[str, str]] = set()
        seen_evidence: set[tuple[str, str, str]] = set()
        seen_relationships: set[tuple[str, str, str]] = set()

        append_unique_entity(
            entities,
            seen_entities,
            NormalizedEntity("company", normalized_company, self.name, self.base_confidence),
        )

        for record in records:
            title = _first_text(record, "title", "headline", "name")
            url = _first_text(record, "url", "link", "href")
            source = _first_text(record, "source", "source_media", "publisher", "site")
            published_at = _first_text(record, "published_at", "date", "published", "time")
            summary = _first_text(record, "snippet", "summary", "description", "content")
            if not title and not summary:
                continue
            article_label = title or summary[:120]
            article_confidence = _article_confidence(source, url)

            append_unique_entity(
                entities,
                seen_entities,
                NormalizedEntity("news_article", article_label, self.name, article_confidence),
            )
            append_unique_evidence(
                evidence,
                seen_evidence,
                NormalizedEvidence(article_label, "company_news_report", self.name, _news_snippet(source, published_at, summary or title)),
            )
            append_unique_relationship(
                relationships,
                seen_relationships,
                NormalizedRelationship(normalized_company, article_label, "company_has_news_article", article_confidence),
            )

            if url.startswith("http"):
                append_unique_entity(
                    entities,
                    seen_entities,
                    NormalizedEntity("external_link", url, self.name, article_confidence),
                )
                append_unique_relationship(
                    relationships,
                    seen_relationships,
                    NormalizedRelationship(article_label, url, "news_has_url", article_confidence),
                )
            if published_at:
                append_unique_entity(
                    entities,
                    seen_entities,
                    NormalizedEntity("published_at", published_at, self.name, article_confidence),
                )
                append_unique_relationship(
                    relationships,
                    seen_relationships,
                    NormalizedRelationship(article_label, published_at, "news_published_at", article_confidence),
                )
            if summary:
                append_unique_entity(
                    entities,
                    seen_entities,
                    NormalizedEntity("news_summary", summary, self.name, article_confidence),
                )
                _add_news_signal(
                    evidence,
                    relationships,
                    seen_evidence,
                    seen_relationships,
                    normalized_company,
                    summary,
                    self.name,
                    article_confidence,
                )

        return ParsedToolOutput(self.name, self.target_type, normalized_company, entities, evidence, relationships)

    @staticmethod
    def fetch_news_payload(
        company: str,
        source: str,
        limit: int,
        days: int,
        timeout_seconds: int,
        discover_fn=None,
        parse_article_fn=None,
    ) -> dict:
        discover = discover_fn or discover_company_news
        parse_article = parse_article_fn or parse_article_url
        try:
            discovered = discover(company, source, limit, days)
        except Exception:
            discovered = []
        articles = []
        for item in discovered[:limit]:
            url = _first_text(item, "url", "link", "href")
            enriched = {}
            if url.startswith("http"):
                enriched = parse_article(url, timeout_seconds)
            article = _merge_article(item, enriched)
            if _article_matches_company(article, company):
                articles.append(article)
        return {
            "source": source,
            "query": f'"{company}" company news',
            "articles": articles,
        }


def _article_records(raw) -> list[dict]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if not isinstance(raw, dict):
        return []
    for key in ("articles", "news", "items", "results"):
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _first_text(record: dict, *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def _article_confidence(source: str, url: str) -> float:
    if source and url.startswith("http"):
        return 0.62
    if source or url.startswith("http"):
        return 0.52
    return 0.42


def _news_snippet(source: str, published_at: str, summary: str) -> str:
    parts = []
    if source:
        parts.append(f"source={source}")
    if published_at:
        parts.append(f"published_at={published_at}")
    if summary:
        parts.append(summary)
    return "; ".join(parts) if parts else "Company news article found"


def _add_news_signal(
    evidence: list[NormalizedEvidence],
    relationships: list[NormalizedRelationship],
    seen_evidence: set[tuple[str, str, str]],
    seen_relationships: set[tuple[str, str, str]],
    company: str,
    summary: str,
    source: str,
    confidence: float,
) -> None:
    lowered = summary.lower()
    if _contains_any(lowered, ("buy", "purchase", "procurement", "supplier", "project", "opens", "expansion", "construction", "renovation", "采购", "项目", "扩张", "开店", "供应商")):
        append_unique_evidence(evidence, seen_evidence, NormalizedEvidence(summary, "news_buying_signal", source, summary))
        append_unique_relationship(relationships, seen_relationships, NormalizedRelationship(company, summary, "news_supports_buying_signal", confidence))
    if _contains_any(lowered, ("partner", "partnership", "supplier", "distributor", "customer", "合作", "供应商", "经销商", "客户")):
        append_unique_evidence(evidence, seen_evidence, NormalizedEvidence(summary, "news_business_event", source, summary))
        append_unique_relationship(relationships, seen_relationships, NormalizedRelationship(company, summary, "news_supports_business_event", confidence))
    if _contains_any(lowered, ("lawsuit", "fine", "penalty", "bankrupt", "recall", "fraud", "unpaid", "complaint", "诉讼", "处罚", "破产", "拖欠", "投诉")):
        append_unique_evidence(evidence, seen_evidence, NormalizedEvidence(summary, "news_risk_signal", source, summary))
        append_unique_relationship(relationships, seen_relationships, NormalizedRelationship(company, summary, "news_supports_risk_signal", confidence))


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower())[:80]


def discover_company_news(company: str, source: str, limit: int, days: int) -> list[dict]:
    source_name = source.lower()
    if source_name in {"gnews", "gnews_package"}:
        package_results = _discover_with_gnews_package(company, limit, days)
        if package_results:
            return package_results
    if source_name in {"gnews", "google_news_rss", "rss", "gnews_package"}:
        return _discover_with_google_news_rss(company, limit)
    return []


def parse_article_url(url: str, timeout_seconds: int) -> dict:
    try:
        from newspaper import Article
    except Exception:
        return {"url": url}
    try:
        article = Article(url)
        article.download()
        article.parse()
        try:
            article.nlp()
        except Exception:
            pass
        return {
            "title": article.title or "",
            "url": url,
            "published_at": article.publish_date.isoformat() if article.publish_date else "",
            "summary": article.summary or _clean_text(article.text)[:500],
            "authors": ", ".join(article.authors or []),
            "top_image": article.top_image or "",
        }
    except Exception as exc:
        return {"url": url, "parse_error": str(exc)[:200]}


def _discover_with_gnews_package(company: str, limit: int, days: int) -> list[dict]:
    try:
        from gnews import GNews
    except Exception:
        return []
    try:
        client = GNews(max_results=limit, period=f"{max(1, days)}d")
        records = client.get_news(f'"{company}" company news')
    except Exception:
        return []
    results = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        publisher = record.get("publisher")
        source = ""
        if isinstance(publisher, dict):
            source = str(publisher.get("title") or publisher.get("href") or "")
        results.append(
            {
                "title": str(record.get("title") or ""),
                "url": str(record.get("url") or ""),
                "source": source,
                "published_at": str(record.get("published date") or record.get("publishedAt") or ""),
                "snippet": str(record.get("description") or ""),
            }
        )
    return results


def _discover_with_google_news_rss(company: str, limit: int) -> list[dict]:
    query = quote_plus(f'"{company}" company news')
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    try:
        with request.urlopen(url, timeout=20) as response:
            payload = response.read()
    except Exception:
        return []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    results = []
    for item in root.findall(".//item")[:limit]:
        title = _node_text(item, "title")
        link = _node_text(item, "link")
        source = _node_text(item, "source")
        description = _clean_html(_node_text(item, "description"))
        published = _node_text(item, "pubDate")
        results.append(
            {
                "title": title,
                "url": link,
                "source": source or "Google News",
                "published_at": _parse_rss_date(published),
                "snippet": description,
            }
        )
    return results


def _merge_article(discovered: dict, enriched: dict) -> dict:
    merged = dict(discovered)
    for key, value in enriched.items():
        if value:
            merged[key] = value
    return merged


def _article_matches_company(article: dict, company: str) -> bool:
    tokens = _company_tokens(company)
    if not tokens:
        return True
    haystack = " ".join(
        _first_text(article, key)
        for key in ("title", "headline", "summary", "snippet", "description", "content", "source", "source_media")
    ).lower()
    return all(token in haystack for token in tokens[:2])


def _company_tokens(company: str) -> list[str]:
    stopwords = {"inc", "llc", "ltd", "corp", "corporation", "company", "co", "the", "group", "limited"}
    return [
        token
        for token in re.findall(r"[a-z0-9]+", company.lower())
        if token not in stopwords and len(token) >= 3
    ]


def _node_text(node, child_name: str) -> str:
    child = node.find(child_name)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _parse_rss_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except Exception:
        return value


def _clean_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return _clean_text(unescape(without_tags))


def _clean_text(value: str) -> str:
    return " ".join((value or "").split())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Create a placeholder company-news artifact")
    parser.add_argument("--company", required=True)
    parser.add_argument("--source", default="gnews")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = CompanyNewsAdapter.fetch_news_payload(
        company=args.company,
        source=args.source,
        limit=args.limit,
        days=args.days,
        timeout_seconds=60,
    )
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
