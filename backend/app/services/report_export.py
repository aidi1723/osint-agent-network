from __future__ import annotations

from datetime import datetime, timezone
import html
import re
from typing import Any

from app.core.quality import build_quality_assessment, render_structured_report


REQUIRED_SECTION_IDS = (
    "bluf",
    "pir_answers",
    "eei_matrix",
    "quality_gate",
    "source_backed_facts",
    "evidence_appendix",
    "ach_iw",
    "intelligence_gaps",
    "next_collection_actions",
)


def build_report_payload(detail: dict) -> dict:
    quality = detail.get("quality_assessment") or build_quality_assessment(detail)
    markdown = render_report_markdown(detail)
    payload = {
        "investigation_id": str(detail.get("id") or ""),
        "name": _redact_value(detail.get("name") or detail.get("seed_value") or "Investigation report"),
        "seed_type": _redact_value(detail.get("seed_type") or ""),
        "seed_value": _redact_value(detail.get("seed_value") or ""),
        "status": _redact_value(detail.get("status") or ""),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "quality": _redact_value(
            {
                "score": quality.get("score", 0),
                "completion_ready": bool(quality.get("completion_ready")),
                "missing_keys": quality.get("missing_keys", []),
                "blocking_keys": quality.get("blocking_keys", []),
            }
        ),
        "sections": _sections(detail, quality),
        "markdown": markdown,
    }
    return _redact_value(payload)


def render_report_markdown(detail: dict) -> str:
    report = str(detail.get("report_markdown") or "")
    if not report.strip():
        report = render_structured_report(detail, detail.get("quality_assessment") or build_quality_assessment(detail))
    return redact_report_text(report)


def render_report_html(detail: dict) -> str:
    payload = build_report_payload(detail)
    title = _escape(str(payload.get("name") or "Investigation report"))
    status = _escape(str(payload.get("status") or ""))
    seed_type = _escape(str(payload.get("seed_type") or ""))
    seed_value = _escape(str(payload.get("seed_value") or ""))
    generated_at = _escape(str(payload.get("generated_at") or ""))
    quality = payload.get("quality") or {}
    quality_score = _escape(str(quality.get("score", 0)))
    completion = "Ready" if quality.get("completion_ready") else "Needs Review"

    section_html = "\n".join(_render_section(section) for section in payload.get("sections", []))
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1f2933; line-height: 1.55; margin: 0; background: #f7f8fa; }}
    main {{ max-width: 960px; margin: 0 auto; padding: 32px 24px 48px; background: #ffffff; min-height: 100vh; }}
    h1 {{ font-size: 28px; margin: 0 0 8px; }}
    h2 {{ font-size: 18px; margin: 28px 0 8px; border-bottom: 1px solid #d8dee4; padding-bottom: 6px; }}
    .meta {{ color: #52616f; font-size: 13px; margin-bottom: 20px; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; margin: 18px 0 24px; }}
    .summary div {{ border: 1px solid #d8dee4; padding: 10px; background: #fbfcfd; }}
    ul {{ padding-left: 22px; }}
    li {{ margin: 6px 0; }}
    footer {{ color: #697886; font-size: 12px; margin-top: 36px; border-top: 1px solid #d8dee4; padding-top: 12px; }}
  </style>
</head>
<body>
<main>
  <h1>{title}</h1>
  <div class="meta">Generated at {generated_at}</div>
  <section class="summary">
    <div><strong>Status</strong><br>{status}</div>
    <div><strong>Seed</strong><br>{seed_type}: {seed_value}</div>
    <div><strong>Quality</strong><br>{quality_score} / 100</div>
    <div><strong>Completion</strong><br>{completion}</div>
  </section>
  {section_html}
  <footer>Generated from structured OSINT records. Review source evidence before external distribution.</footer>
</main>
</body>
</html>
"""
    return redact_report_text(body)


def redact_report_text(value: str) -> str:
    text = str(value)
    replacements = (
        (re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9._~+\-/=]{8,}", re.IGNORECASE), "<redacted-token>"),
        (re.compile(r"\bBearer\s+[A-Za-z0-9._~+\-/=]{8,}", re.IGNORECASE), "<redacted-token>"),
        (re.compile(r"\b(?:api[_-]?key|token|secret|sessionid|cookie)\s*[:=]\s*[A-Za-z0-9._~+\-/=]{8,}", re.IGNORECASE), "<redacted-token>"),
        (re.compile(r"\b(?:sk|ghp|github_pat)-?[A-Za-z0-9_]{16,}", re.IGNORECASE), "<redacted-token>"),
        (re.compile(r"(?:/Users|/home)/[^\s<>'\")]+"), "<redacted-path>"),
        (re.compile(r"https?://(?:127\.0\.0\.1|localhost|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?::\d+)?[^\s<>'\")]*"), "<redacted-url>"),
        (re.compile(r"\b(?:127\.0\.0\.1|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"), "<redacted-host>"),
    )
    for pattern, replacement in replacements:
        text = pattern.sub(replacement, text)
    return text


def _sections(detail: dict, quality: dict) -> list[dict]:
    requirements = detail.get("intelligence_requirements") or {}
    memory = detail.get("intelligence_memory") or {}
    analysis = detail.get("hypothesis_analysis") or {}
    matrix = detail.get("cross_verification_matrix") or []
    facts = detail.get("facts") or []
    evidence = detail.get("evidence_ledger") or []

    sections = [
        {"id": "bluf", "title": "BLUF", "items": [_bluf_item(detail, quality)]},
        {"id": "pir_answers", "title": "PIR Answers", "items": [_pir_item(item) for item in requirements.get("pirs", [])[:8]] or ["No PIR records available."]},
        {"id": "eei_matrix", "title": "EEI Matrix", "items": [_eei_item(item) for item in requirements.get("eeis", [])[:12]] or ["No EEI records available."]},
        {"id": "quality_gate", "title": "Quality Gate", "items": _quality_items(quality)},
        {"id": "source_backed_facts", "title": "Source-Backed Facts", "items": [_fact_item(item) for item in facts[:12]] or ["No source-backed facts available."]},
        {"id": "evidence_appendix", "title": "Evidence Appendix", "items": [_evidence_item(item) for item in evidence[:12]] or ["No evidence ledger records available."]},
        {"id": "ach_iw", "title": "ACH / I&W", "items": _ach_items(analysis, detail, matrix)},
        {"id": "intelligence_gaps", "title": "Intelligence Gaps", "items": [_gap_item(item) for item in memory.get("collection_gaps", [])[:8]] or ["No major intelligence gaps recorded."]},
        {"id": "next_collection_actions", "title": "Next Collection Actions", "items": [_action_item(item) for item in memory.get("directed_collection", [])[:8]] or ["Continue source collection and cross-verification."]},
    ]
    return _redact_value(sections)


def _render_section(section: dict) -> str:
    title = _escape(section.get("title") or section.get("id") or "Section")
    items = section.get("items") or []
    list_items = "\n".join(f"    <li>{_escape(str(item))}</li>" for item in items)
    return f"<section id=\"{_escape(str(section.get('id') or 'section'))}\"><h2>{title}</h2><ul>\n{list_items}\n  </ul></section>"


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_report_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    return value


def _escape(value: str) -> str:
    return html.escape(redact_report_text(value), quote=True)


def _bluf_item(detail: dict, quality: dict) -> str:
    status = "ready" if quality.get("completion_ready") else "needs review"
    return f"{detail.get('name') or detail.get('seed_value') or 'Investigation'} is {status}; quality score {quality.get('score', 0)} / 100."


def _pir_item(item: dict) -> str:
    return f"[{item.get('status', 'OPEN')}] {item.get('question', '')}: {item.get('answer') or 'No complete answer yet.'}"


def _eei_item(item: dict) -> str:
    required = "required" if item.get("required") else "optional"
    return f"[{item.get('status', 'MISSING')} / {required}] {item.get('label') or item.get('field_key') or ''}"


def _quality_items(quality: dict) -> list[str]:
    items = [
        f"Score: {quality.get('score', 0)} / 100",
        f"Completion ready: {bool(quality.get('completion_ready'))}",
    ]
    missing = quality.get("missing_keys") or []
    blocking = quality.get("blocking_keys") or []
    if missing:
        items.append(f"Missing keys: {', '.join(str(item) for item in missing)}")
    if blocking:
        items.append(f"Blocking keys: {', '.join(str(item) for item in blocking)}")
    return items


def _fact_item(item: dict) -> str:
    return f"[{item.get('status', 'NEEDS_REVIEW')} / {item.get('admiralty_code') or 'unrated'}] {item.get('statement', '')}"


def _evidence_item(item: dict) -> str:
    source = item.get("source_url") or item.get("source_type") or "unknown source"
    return f"[{item.get('admiralty_code') or 'unrated'}] {item.get('snippet') or source} ({source})"


def _ach_items(analysis: dict, detail: dict, matrix: list[dict]) -> list[str]:
    items = []
    if analysis.get("most_likely_hypothesis"):
        items.append(f"Most likely hypothesis: {analysis.get('most_likely_hypothesis')}")
    if analysis.get("confidence_language"):
        items.append(f"Confidence language: {analysis.get('confidence_language')}")
    for row in matrix[:6]:
        if row.get("status") in {"CONFIRMED", "LIKELY", "SUPPORTED"}:
            items.append(f"Indicator: {row.get('label') or row.get('field_key')} is {row.get('status')}")
    if not items and detail.get("hypotheses"):
        items.append("Hypotheses exist but have not been scored.")
    return items or ["No ACH or I&W signals available."]


def _gap_item(item: dict) -> str:
    return f"{item.get('label', 'Gap')}: {item.get('reason', '')}"


def _action_item(item: dict) -> str:
    return f"{item.get('agent_focus', 'Continue collection')}: {item.get('prompt', '')}"
