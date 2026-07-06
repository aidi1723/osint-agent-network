# Report Export Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JSON, Markdown, and self-contained HTML report export endpoints using the existing structured investigation report data.

**Architecture:** Create a pure rendering service in `backend/app/services/report_export.py` that accepts an investigation detail dict, builds a deterministic section payload, redacts sensitive strings, and renders Markdown/HTML without new dependencies. Wire `ApiHandler.do_GET()` to expose `/report`, `/report.md`, and `/report.html` before the generic investigation detail route.

**Tech Stack:** Python standard library (`html`, `json`, `re`, `datetime`, `http.server`, `urllib.request`), existing `MemoryStore`, `build_quality_assessment()`, and `render_structured_report()`.

---

## File Structure

- Create: `backend/app/services/report_export.py`
  - Owns report payload construction, Markdown rendering, HTML rendering, and redaction.
- Create: `backend/tests/test_report_export.py`
  - Owns service-level export tests and API endpoint tests.
- Modify: `backend/app/main.py`
  - Adds report routes and a text response helper.
- Modify: `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`
  - Records P2 progress and verification results after implementation.
- Modify: `docs/DEVELOPMENT_MANUAL.md`
  - Aligns existing report endpoint notes with implemented behavior.
- Modify: `docs/superpowers/plans/2026-07-06-report-export-package.md`
  - Tracks execution status.

## Task 1: Add Failing Report Export Tests

**Files:**
- Create: `backend/tests/test_report_export.py`

- [x] **Step 1: Write the failing service and API tests**

Create `backend/tests/test_report_export.py`:

```python
import json
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from app.main import ApiHandler
from app.services.store import MemoryStore


REQUIRED_SECTION_IDS = {
    "bluf",
    "pir_answers",
    "eei_matrix",
    "quality_gate",
    "source_backed_facts",
    "evidence_appendix",
    "ach_iw",
    "intelligence_gaps",
    "next_collection_actions",
}


class ReportExportServiceTests(unittest.TestCase):
    def test_build_report_payload_includes_required_sections(self):
        from app.services.report_export import build_report_payload

        detail = _sample_detail()

        payload = build_report_payload(detail)

        self.assertEqual(payload["investigation_id"], detail["id"])
        self.assertEqual(payload["seed_type"], "company")
        self.assertTrue(payload["markdown"].startswith("# Example Manufacturing LLC"))
        self.assertTrue(REQUIRED_SECTION_IDS.issubset({section["id"] for section in payload["sections"]}))
        self.assertEqual(payload["quality"]["score"], detail["quality_assessment"]["score"])

    def test_render_report_markdown_redacts_sensitive_values(self):
        from app.services.report_export import render_report_markdown

        detail = _sample_detail()
        detail["report_markdown"] += "\nAuthorization: " + "Bearer " + ("A" * 24)
        detail["report_markdown"] += "\nPath: /Users/example/.config/tool/session.json"
        private_host_prefix = "192." + "168."
        detail["report_markdown"] += "\nHost: http://" + private_host_prefix + "1.20:8080/private"

        markdown = render_report_markdown(detail)

        self.assertIn("## BLUF", markdown)
        self.assertIn("## 证据附录", markdown)
        self.assertIn("<redacted-token>", markdown)
        self.assertIn("<redacted-path>", markdown)
        self.assertIn("<redacted-url>", markdown)
        self.assertNotIn("Authorization:", markdown)
        self.assertNotIn("/Users/example", markdown)
        self.assertNotIn(private_host_prefix, markdown)

    def test_render_report_html_returns_complete_escaped_document(self):
        from app.services.report_export import render_report_html

        detail = _sample_detail()
        detail["name"] = "Example <Manufacturing> LLC"

        html = render_report_html(detail)

        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("<html", html)
        self.assertIn("BLUF", html)
        self.assertIn("PIR Answers", html)
        self.assertIn("Evidence Appendix", html)
        self.assertIn("Example &lt;Manufacturing&gt; LLC", html)
        self.assertNotIn("Example <Manufacturing> LLC", html)
        self.assertIn("Generated from structured OSINT records", html)

    def test_redact_report_text_removes_runtime_secrets_and_paths(self):
        from app.services.report_export import redact_report_text

        raw = " ".join(
            [
                "Authorization:",
                "Bearer " + ("B" * 24),
                "api_key=" + ("C" * 32),
                "token=" + ("D" * 32),
                "path=/Users/example/project/.env",
                "url=http://" + "10." + "1.2.3:5000/status",
                "cookie=sessionid=" + ("E" * 24),
            ]
        )

        redacted = redact_report_text(raw)

        self.assertIn("<redacted-token>", redacted)
        self.assertIn("<redacted-path>", redacted)
        self.assertIn("<redacted-url>", redacted)
        self.assertNotIn("Bearer", redacted)
        self.assertNotIn("/Users/example", redacted)
        self.assertNotIn("10." + "1.2.3", redacted)
        self.assertNotIn("sessionid", redacted)


class ReportExportApiTests(unittest.TestCase):
    def test_report_json_endpoint_returns_structured_payload(self):
        api_store = _sample_store()
        investigation_id = next(iter(api_store.investigations))

        status, headers, body = _get_with_store(f"/api/investigations/{investigation_id}/report", api_store)
        payload = json.loads(body)

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(payload["investigation_id"], investigation_id)
        self.assertTrue(REQUIRED_SECTION_IDS.issubset({section["id"] for section in payload["sections"]}))

    def test_report_markdown_endpoint_returns_markdown_content_type(self):
        api_store = _sample_store()
        investigation_id = next(iter(api_store.investigations))

        status, headers, body = _get_with_store(f"/api/investigations/{investigation_id}/report.md", api_store)

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/markdown; charset=utf-8")
        self.assertIn("## BLUF", body)
        self.assertIn("## 证据附录", body)

    def test_report_html_endpoint_returns_html_content_type(self):
        api_store = _sample_store()
        investigation_id = next(iter(api_store.investigations))

        status, headers, body = _get_with_store(f"/api/investigations/{investigation_id}/report.html", api_store)

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("<!doctype html>", body)
        self.assertIn("Source-Backed Facts", body)

    def test_report_endpoint_returns_404_for_missing_investigation(self):
        status, headers, body = _get_with_store("/api/investigations/missing-id/report.html", MemoryStore())
        payload = json.loads(body)

        self.assertEqual(status, 404)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(payload["detail"], "investigation not found")


def _sample_store() -> MemoryStore:
    store = MemoryStore()
    investigation = store.create_investigation(
        name="Example Manufacturing LLC",
        seed_type="company",
        seed_value="Example Manufacturing LLC",
        strategy_name="standard",
    )
    evidence = store.add_evidence_record(
        investigation.id,
        "https://www.example.com/about",
        "official_website",
        "official_site_extractor",
        "Official site lists sales@example.com and uPVC windows.",
        0.86,
    )
    store.add_entity(investigation.id, "company", "Example Manufacturing LLC", "seed", 0.92)
    store.add_entity(investigation.id, "url", "https://www.example.com/about", "official_site_search", 0.78)
    store.add_entity(investigation.id, "email", "sales@example.com", "official_site_extractor", 0.86)
    store.add_entity(investigation.id, "business_scope", "uPVC windows", "official_site_extractor", 0.78)
    store.add_evidence(
        investigation.id,
        "sales@example.com",
        "official_site_contact",
        "official_site_extractor",
        "Official page lists sales@example.com.",
    )
    store.add_relationship(
        investigation.id,
        "https://www.example.com/about",
        "sales@example.com",
        "official_site_has_contact_email",
        0.82,
    )
    store.add_fact(
        investigation.id,
        "Example Manufacturing LLC uses sales@example.com as a public contact email.",
        "Example Manufacturing LLC",
        "uses_contact_email",
        "sales@example.com",
        "CONFIRMED",
        0.86,
        evidence["admiralty_code"],
        [evidence["id"]],
    )
    store.complete_task(
        investigation.id,
        agent_id="local-analysis-agent",
        status="COMPLETED",
        summary="Report ready.",
        report_markdown="",
        confidence=0.86,
    )
    return store


def _sample_detail() -> dict:
    store = _sample_store()
    investigation_id = next(iter(store.investigations))
    detail = store.get_investigation(investigation_id)
    assert detail is not None
    return detail


def _get_with_store(path: str, api_store: MemoryStore) -> tuple[int, dict, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    with patch("app.main.store", api_store):
        thread.start()
        try:
            try:
                with urlopen(f"{base_url}{path}", timeout=5) as response:
                    return response.status, dict(response.headers), response.read().decode("utf-8")
            except HTTPError as exc:
                try:
                    return exc.code, dict(exc.headers), exc.read().decode("utf-8")
                finally:
                    exc.close()
        finally:
            server.shutdown()
            server.server_close()
```

- [x] **Step 2: Run the new tests and verify they fail for missing module/routes**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v
```

Expected: ERROR with `ModuleNotFoundError: No module named 'app.services.report_export'` or route failures because the exporter does not exist yet.

## Task 2: Implement Report Export Service

**Files:**
- Create: `backend/app/services/report_export.py`
- Test: `backend/tests/test_report_export.py`

- [x] **Step 1: Add the report export service implementation**

Create `backend/app/services/report_export.py`:

```python
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
        (re.compile(r"\b(?:/Users|/home)/[^\s<>'\")]+"), "<redacted-path>"),
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
```

- [x] **Step 2: Run the report export tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v
```

Expected: service tests pass, API tests still fail because routes are not wired yet.

## Task 3: Wire Report Export API Routes

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_report_export.py`

- [x] **Step 1: Import report export functions**

In `backend/app/main.py`, add this import near the other service imports:

```python
from app.services.report_export import build_report_payload, render_report_html, render_report_markdown
```

- [x] **Step 2: Add report routes before the generic investigation detail route**

In `ApiHandler.do_GET()`, insert this block before:

```python
if parsed.path.startswith("/api/investigations/"):
```

Add:

```python
        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/report"):
            investigation_id = parsed.path.split("/")[3]
            item = store.get_investigation(investigation_id)
            if item is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._json(build_report_payload(item))
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/report.md"):
            investigation_id = parsed.path.split("/")[3]
            item = store.get_investigation(investigation_id)
            if item is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._text(render_report_markdown(item), "text/markdown; charset=utf-8")
            return

        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/report.html"):
            investigation_id = parsed.path.split("/")[3]
            item = store.get_investigation(investigation_id)
            if item is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            self._text(render_report_html(item), "text/html; charset=utf-8")
            return
```

- [x] **Step 3: Add a non-JSON response helper**

In `ApiHandler`, add this method directly after `_json()`:

```python
    def _text(self, body: str, content_type: str, status: int = 200):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        origin = self.headers.get("Origin", "")
        allowed_origins = _get_allowed_origins()
        if origin in allowed_origins or "*" in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin or allowed_origins[0])
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(encoded)
```

- [x] **Step 4: Run the report export tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v
```

Expected: all report export tests pass.

## Task 4: Run Backend Regression Surface

**Files:**
- Test: `backend/tests/test_report_export.py`
- Test: `backend/tests/test_mcp_descriptor.py`
- Test: `backend/tests/test_agent_protocol.py`

- [x] **Step 1: Run the new tests and adjacent API tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_mcp_descriptor.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_agent_protocol.py' -v
```

Expected: all targeted tests pass. The adjacent tests confirm the new `_text()` helper did not break existing JSON routes or agent protocol routes.

- [x] **Step 2: Run all backend tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_*.py' -v
```

Expected: all backend tests pass.

## Task 5: Update Documentation Records

**Files:**
- Modify: `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`
- Modify: `docs/DEVELOPMENT_MANUAL.md`

- [x] **Step 1: Update the development manual report endpoint section**

In `docs/DEVELOPMENT_MANUAL.md`, replace the report endpoint notes around the API list with:

```markdown
- `GET /api/investigations/{id}/report`: redacted structured report JSON.
- `GET /api/investigations/{id}/report.md`: redacted Markdown report.
- `GET /api/investigations/{id}/report.html`: redacted self-contained HTML report for external handoff.
```

- [x] **Step 2: Add a P2 progress note to the roadmap**

Append this section near the end of `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`:

```markdown
## P2 Progress - Report Export Package

Implemented first-stage report export for completed investigations:

- structured report JSON;
- Markdown report;
- self-contained HTML report.

Protected behavior:

- export reuses the existing structured report and quality assessment;
- HTML output includes BLUF, PIR answers, EEI coverage, quality gate,
  source-backed facts, evidence appendix, ACH/I&W, gaps, and next actions;
- export responses apply redaction before returning content;
- missing investigations return `404`.

Verification:

- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v`
- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_*.py' -v`
- `bash scripts/verify.sh`
- added-line privacy scan from `docs/PUBLIC_REPOSITORY_MAINTENANCE.md`

Deferred:

- PDF export remains a follow-up after the HTML contract is stable.
```

- [x] **Step 3: Review documentation diffs**

Run:

```bash
git diff -- docs/NEXT_PHASE_ROADMAP_2026-07-06.md docs/DEVELOPMENT_MANUAL.md
```

Expected: docs describe implemented endpoints without private targets, hostnames, local paths, tokens, or deployment details.

## Task 6: Full Verification, Privacy Scan, Commit, and Push

**Files:**
- All files changed in this plan.

- [x] **Step 1: Run full verification**

Run:

```bash
bash scripts/verify.sh
```

Expected: backend tests pass, frontend helper checks pass, Vitest passes, and frontend production build passes.

- [x] **Step 2: Run added-line privacy scan**

Run the added-line privacy scan documented in `docs/PUBLIC_REPOSITORY_MAINTENANCE.md`.

Expected: no matches. If `rg` exits with code `1`, that means no matches were found.

- [x] **Step 3: Review final status**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intended report export service, API route, tests, and documentation files are modified or untracked.

- [x] **Step 4: Commit implementation**

Run:

```bash
git add backend/app/services/report_export.py backend/app/main.py backend/tests/test_report_export.py docs/NEXT_PHASE_ROADMAP_2026-07-06.md docs/DEVELOPMENT_MANUAL.md docs/superpowers/plans/2026-07-06-report-export-package.md
git commit -m "feat: add report export endpoints"
```

Expected: commit succeeds.

- [ ] **Step 5: Push if verification and privacy scan passed**

Run:

```bash
git push
```

Expected: remote `main` receives the P2 implementation commit.

## Self-Review Checklist

- Spec coverage: JSON, Markdown, HTML, required sections, redaction, API routes, tests, docs, and PDF deferral are covered.
- No new dependencies: HTML rendering uses only Python standard library.
- Type consistency: test assertions use `sections[].id`, `quality.score`, and response content types matching the implementation.
- Public safety: sample data uses `example.com`, synthetic company names, and constructed sensitive strings rather than literal publishable secrets.
