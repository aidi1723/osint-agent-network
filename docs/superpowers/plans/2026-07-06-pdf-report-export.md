# PDF Report Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a redacted PDF report export endpoint for completed investigations.

**Architecture:** Create a focused `report_pdf.py` renderer that depends on the existing redacted report payload builder, not on the database or HTML renderer. Wire `/api/investigations/{id}/report.pdf` into the existing API handler with binary response support and an explicit `503` path when `reportlab` is unavailable.

**Tech Stack:** Python 3.11, standard `unittest`, `reportlab` for PDF generation, `pypdf` for PDF text verification, Poppler `pdftoppm` for render verification when available.

---

## File Structure

- Create `backend/app/services/report_pdf.py`
  - Owns PDF generation only.
  - Exposes `render_report_pdf(detail: dict) -> bytes`.
  - Defines `ReportPdfDependencyError`.
  - Reuses `build_report_payload()` from `report_export.py`.
- Create `backend/tests/test_report_pdf_export.py`
  - Covers service behavior, API behavior, missing dependency behavior, and redaction.
  - Reuses the same public-safe sample investigation shape as `test_report_export.py`.
- Modify `backend/app/main.py`
  - Imports `render_report_pdf` and `ReportPdfDependencyError`.
  - Adds `/report.pdf` route before generic investigation detail route.
  - Adds `_binary()` response helper.
- Modify `backend/pyproject.toml`
  - Adds `reportlab` and `pypdf`.
- Modify `backend/uv.lock`
  - Updates lockfile after dependency resolution.
- Modify `docs/DEVELOPMENT_MANUAL.md`
  - Documents `/report.pdf` and `503` dependency behavior.
- Modify `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`
  - Marks P2b PDF export progress after verification.
- Modify this plan file as tasks are completed.

## Task 1: Add Failing PDF Export Tests

**Files:**
- Create: `backend/tests/test_report_pdf_export.py`
- Test: `backend/tests/test_report_pdf_export.py`

- [x] **Step 1: Create the failing test file**

Create `backend/tests/test_report_pdf_export.py` with this content:

```python
import importlib
import json
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from app.main import ApiHandler
from app.services.store import MemoryStore


REQUIRED_SECTION_TITLES = (
    "BLUF",
    "PIR Answers",
    "EEI Matrix",
    "Quality Gate",
    "Source-Backed Facts",
    "Evidence Appendix",
    "ACH / I&W",
    "Intelligence Gaps",
    "Next Collection Actions",
)


class ReportPdfServiceTests(unittest.TestCase):
    def test_render_report_pdf_returns_pdf_bytes_with_required_sections(self):
        from app.services.report_pdf import render_report_pdf

        pdf_bytes = render_report_pdf(_sample_detail())

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        text = _extract_pdf_text(pdf_bytes)
        for title in REQUIRED_SECTION_TITLES:
            self.assertIn(title, text)
        self.assertIn("Example Manufacturing LLC", text)
        self.assertIn("Generated from structured OSINT records", text)

    def test_render_report_pdf_redacts_sensitive_values(self):
        from app.services.report_pdf import render_report_pdf

        detail = _sample_detail()
        detail["report_markdown"] = "\n".join(
            [
                "# Example Manufacturing LLC",
                "Authorization: " + "Bearer " + ("A" * 24),
                "Path: /Users/example/.config/tool/session.json",
                "URL: http://" + "10." + "1.2.3:5000/status",
            ]
        )

        pdf_bytes = render_report_pdf(detail)
        text = _extract_pdf_text(pdf_bytes)

        self.assertIn("<redacted-token>", text)
        self.assertIn("<redacted-path>", text)
        self.assertIn("<redacted-url>", text)
        self.assertNotIn("Bearer", text)
        self.assertNotIn("/Users/example", text)
        self.assertNotIn("10." + "1.2.3", text)

    def test_missing_reportlab_raises_explicit_dependency_error(self):
        import app.services.report_pdf as report_pdf

        real_import_module = importlib.import_module

        def fake_import_module(name, package=None):
            if name.startswith("reportlab"):
                raise ModuleNotFoundError("No module named 'reportlab'")
            return real_import_module(name, package)

        with patch("importlib.import_module", side_effect=fake_import_module):
            with self.assertRaises(report_pdf.ReportPdfDependencyError):
                report_pdf.render_report_pdf(_sample_detail())


class ReportPdfApiTests(unittest.TestCase):
    def test_report_pdf_endpoint_returns_pdf_content_type(self):
        api_store = _sample_store()
        investigation_id = next(iter(api_store.investigations))

        status, headers, body = _get_bytes_with_store(f"/api/investigations/{investigation_id}/report.pdf", api_store)

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertTrue(body.startswith(b"%PDF"))

    def test_report_pdf_endpoint_returns_404_for_missing_investigation(self):
        status, headers, body = _get_bytes_with_store("/api/investigations/missing-id/report.pdf", MemoryStore())
        payload = json.loads(body.decode("utf-8"))

        self.assertEqual(status, 404)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(payload["detail"], "investigation not found")

    def test_report_pdf_endpoint_returns_503_when_dependency_is_missing(self):
        api_store = _sample_store()
        investigation_id = next(iter(api_store.investigations))

        with patch("app.main.render_report_pdf", side_effect=_dependency_error()):
            status, headers, body = _get_bytes_with_store(f"/api/investigations/{investigation_id}/report.pdf", api_store)

        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(status, 503)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(payload["detail"], "PDF export is unavailable because reportlab is not installed.")


def _dependency_error():
    from app.services.report_pdf import ReportPdfDependencyError

    return ReportPdfDependencyError("PDF export is unavailable because reportlab is not installed.")


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


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


def _get_bytes_with_store(path: str, api_store: MemoryStore) -> tuple[int, dict, bytes]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    with patch("app.main.store", api_store):
        thread.start()
        try:
            try:
                with urlopen(f"{base_url}{path}", timeout=5) as response:
                    return response.status, dict(response.headers), response.read()
            except HTTPError as exc:
                try:
                    return exc.code, dict(exc.headers), exc.read()
                finally:
                    exc.close()
        finally:
            server.shutdown()
            server.server_close()
```

- [x] **Step 2: Run the new test file and confirm it fails**

Run:

```bash
PYTHONPATH=backend uv run --project backend python3 -m unittest discover -s backend/tests -p 'test_report_pdf_export.py' -v
```

Expected:

```text
ModuleNotFoundError: No module named 'app.services.report_pdf'
```

- [x] **Step 3: Commit the failing tests**

Run:

```bash
git add backend/tests/test_report_pdf_export.py docs/superpowers/plans/2026-07-06-pdf-report-export.md
git commit -m "test: add pdf report export coverage"
```

## Task 2: Add PDF Dependencies

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Test: `backend/tests/test_report_pdf_export.py`

- [x] **Step 1: Add dependency declarations**

Modify `backend/pyproject.toml`:

```toml
[project]
name = "osint-agent-network-backend"
version = "0.1.0"
requires-python = ">=3.11"
license = "Proprietary"
dependencies = [
    "pypdf>=5.0.0",
    "reportlab>=4.2.0",
]

[tool.pytest.ini_options]
pythonpath = [".", ".."]
testpaths = ["tests"]
```

- [x] **Step 2: Update the backend lockfile**

Run from the backend directory:

```bash
uv lock
```

Expected:

```text
Resolved ... packages
```

If `uv` is unavailable, run:

```bash
python3 -m pip install reportlab pypdf
```

and record in the task notes that `backend/uv.lock` was not updated in this environment.

- [x] **Step 3: Confirm dependency imports work**

Run from the backend directory:

```bash
uv run python3 -c "import reportlab, pypdf; print('pdf deps ok')"
```

Expected:

```text
pdf deps ok
```

- [x] **Step 4: Commit dependency updates**

Run:

```bash
git add backend/pyproject.toml backend/uv.lock docs/superpowers/plans/2026-07-06-pdf-report-export.md
git commit -m "chore: add pdf report dependencies"
```

## Task 3: Implement PDF Renderer

**Files:**
- Create: `backend/app/services/report_pdf.py`
- Test: `backend/tests/test_report_pdf_export.py`

- [x] **Step 1: Create the PDF renderer**

Create `backend/app/services/report_pdf.py`:

```python
from __future__ import annotations

from io import BytesIO
import importlib
from typing import Any

from app.services.report_export import build_report_payload, redact_report_text


PDF_UNAVAILABLE_DETAIL = "PDF export is unavailable because reportlab is not installed."


class ReportPdfDependencyError(RuntimeError):
    pass


def render_report_pdf(detail: dict) -> bytes:
    reportlab = _load_reportlab()
    colors = reportlab["colors"]
    letter = reportlab["letter"]
    inch = reportlab["inch"]
    getSampleStyleSheet = reportlab["getSampleStyleSheet"]
    ParagraphStyle = reportlab["ParagraphStyle"]
    SimpleDocTemplate = reportlab["SimpleDocTemplate"]
    Paragraph = reportlab["Paragraph"]
    Spacer = reportlab["Spacer"]
    Table = reportlab["Table"]
    TableStyle = reportlab["TableStyle"]
    ListFlowable = reportlab["ListFlowable"]
    ListItem = reportlab["ListItem"]

    payload = build_report_payload(detail)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=str(payload.get("name") or "Investigation report"),
        author="osint-agent-network",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Meta", parent=styles["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor("#52616f")))
    styles.add(ParagraphStyle(name="SectionTitle", parent=styles["Heading2"], fontSize=13, leading=16, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#1f2933")))
    styles.add(ParagraphStyle(name="SmallBullet", parent=styles["BodyText"], fontSize=9, leading=12, leftIndent=4))

    quality = payload.get("quality") or {}
    completion = "Ready" if quality.get("completion_ready") else "Needs Review"
    story: list[Any] = [
        Paragraph(_xml(str(payload.get("name") or "Investigation report")), styles["Title"]),
        Paragraph(_xml(f"Generated at {payload.get('generated_at', '')}"), styles["Meta"]),
        Spacer(1, 8),
        _summary_table(payload, completion, Table, TableStyle, Paragraph, styles, colors),
        Spacer(1, 10),
    ]

    for section in payload.get("sections", []):
        story.append(Paragraph(_xml(str(section.get("title") or section.get("id") or "Section")), styles["SectionTitle"]))
        items = [
            ListItem(Paragraph(_xml(str(item)), styles["SmallBullet"]), leftIndent=10)
            for item in section.get("items", [])
        ]
        story.append(ListFlowable(items or [ListItem(Paragraph("No records available.", styles["SmallBullet"]))], bulletType="bullet", start="circle", leftIndent=16))

    story.append(Spacer(1, 14))
    story.append(Paragraph("Generated from structured OSINT records. Review source evidence before external distribution.", styles["Meta"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _load_reportlab() -> dict[str, Any]:
    try:
        return {
            "colors": importlib.import_module("reportlab.lib.colors"),
            "letter": importlib.import_module("reportlab.lib.pagesizes").letter,
            "inch": importlib.import_module("reportlab.lib.units").inch,
            "getSampleStyleSheet": importlib.import_module("reportlab.lib.styles").getSampleStyleSheet,
            "ParagraphStyle": importlib.import_module("reportlab.lib.styles").ParagraphStyle,
            "SimpleDocTemplate": importlib.import_module("reportlab.platypus").SimpleDocTemplate,
            "Paragraph": importlib.import_module("reportlab.platypus").Paragraph,
            "Spacer": importlib.import_module("reportlab.platypus").Spacer,
            "Table": importlib.import_module("reportlab.platypus").Table,
            "TableStyle": importlib.import_module("reportlab.platypus").TableStyle,
            "ListFlowable": importlib.import_module("reportlab.platypus").ListFlowable,
            "ListItem": importlib.import_module("reportlab.platypus").ListItem,
        }
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("reportlab"):
            raise ReportPdfDependencyError(PDF_UNAVAILABLE_DETAIL) from exc
        raise


def _summary_table(payload: dict, completion: str, Table: Any, TableStyle: Any, Paragraph: Any, styles: Any, colors: Any) -> Any:
    quality = payload.get("quality") or {}
    rows = [
        ["Status", str(payload.get("status") or "")],
        ["Seed", f"{payload.get('seed_type') or ''}: {payload.get('seed_value') or ''}"],
        ["Quality", f"{quality.get('score', 0)} / 100"],
        ["Completion", completion],
    ]
    table = Table(
        [[Paragraph(_xml(label), styles["Meta"]), Paragraph(_xml(value), styles["BodyText"])] for label, value in rows],
        colWidths=[90, 370],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfcfd")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8dee4")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8dee4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _footer(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColorRGB(0.42, 0.47, 0.53)
    canvas.drawString(doc.leftMargin, 0.38 * 72, "Generated from structured OSINT records")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.38 * 72, f"Page {doc.page}")
    canvas.restoreState()


def _xml(value: str) -> str:
    import html

    return html.escape(redact_report_text(value), quote=True)
```

- [x] **Step 2: Run the service tests and confirm only API wiring still fails**

Run:

```bash
PYTHONPATH=backend uv run --project backend python3 -m unittest backend.tests.test_report_pdf_export.ReportPdfServiceTests -v
```

Expected:

```text
OK
```

- [x] **Step 3: Commit the PDF renderer**

Run:

```bash
git add backend/app/services/report_pdf.py backend/tests/test_report_pdf_export.py docs/superpowers/plans/2026-07-06-pdf-report-export.md
git commit -m "feat: render pdf reports"
```

## Task 4: Wire PDF API Route

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_report_pdf_export.py`

- [x] **Step 1: Update imports**

Change the report imports near the top of `backend/app/main.py` to:

```python
from app.services.report_export import build_report_payload, render_report_html, render_report_markdown
from app.services.report_pdf import PDF_UNAVAILABLE_DETAIL, ReportPdfDependencyError, render_report_pdf
```

- [x] **Step 2: Add the PDF route before `/report`**

Insert this block before the existing `/api/investigations/{id}/report` route:

```python
        if parsed.path.startswith("/api/investigations/") and parsed.path.endswith("/report.pdf"):
            investigation_id = parsed.path.split("/")[3]
            item = store.get_investigation(investigation_id)
            if item is None:
                self._json({"detail": "investigation not found"}, status=404)
                return
            try:
                self._binary(render_report_pdf(item), "application/pdf")
            except ReportPdfDependencyError:
                self._json({"detail": PDF_UNAVAILABLE_DETAIL}, status=503)
            return
```

- [x] **Step 3: Add a binary response helper**

Add this method after `_text()` in `backend/app/main.py`:

```python
    def _binary(self, body: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        allowed_origins = configured_cors_origins()
        origin = self.headers.get("Origin")
        if allowed_origins and (origin in allowed_origins or "*" in allowed_origins):
            self.send_header("Access-Control-Allow-Origin", origin or allowed_origins[0])
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)
```

- [x] **Step 4: Run PDF API tests**

Run:

```bash
PYTHONPATH=backend uv run --project backend python3 -m unittest discover -s backend/tests -p 'test_report_pdf_export.py' -v
```

Expected:

```text
OK
```

- [x] **Step 5: Run existing report export tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v
```

Expected:

```text
OK
```

- [x] **Step 6: Commit API route wiring**

Run:

```bash
git add backend/app/main.py backend/tests/test_report_pdf_export.py docs/superpowers/plans/2026-07-06-pdf-report-export.md
git commit -m "feat: add pdf report endpoint"
```

## Task 5: Update Documentation

**Files:**
- Modify: `docs/DEVELOPMENT_MANUAL.md`
- Modify: `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`
- Modify: `docs/superpowers/plans/2026-07-06-pdf-report-export.md`

- [x] **Step 1: Update API manual report section**

Change section `11.5 Reports` in `docs/DEVELOPMENT_MANUAL.md` to:

```markdown
### 11.5 Reports

- `GET /api/investigations/{id}/report`: redacted structured report JSON.
- `GET /api/investigations/{id}/report.md`: redacted Markdown report.
- `GET /api/investigations/{id}/report.html`: redacted self-contained HTML report for external handoff.
- `GET /api/investigations/{id}/report.pdf`: redacted printable PDF report. Returns `503` with JSON detail when PDF support is unavailable because `reportlab` is not installed.
```

- [x] **Step 2: Update roadmap P2 progress**

Append this subsection after the existing `P2 Progress - Report Export Package` section in `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`:

```markdown
## P2b Progress - PDF Report Export

Implemented PDF report export for completed investigations:

- `GET /api/investigations/{id}/report.pdf`;
- PDF rendering from the same redacted structured report payload as JSON, Markdown, and HTML;
- explicit `503` response when the PDF dependency is unavailable;
- PDF text verification for required report sections.

Protected behavior:

- PDF export does not parse HTML or read the database directly;
- existing JSON, Markdown, and HTML report endpoints remain unchanged;
- generated report content keeps redaction safeguards for tokens, local paths, private hosts, and private service URLs.

Only the PDF/report unit tests are recorded as completed so far:

- `PYTHONPATH=backend uv run --project backend python3 -m unittest discover -s backend/tests -p 'test_report_pdf_export.py' -v`
- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v`

Pending Task 6 final checks:

- `bash scripts/verify.sh`
- PDF render check with `pdftoppm` when available
- added-line privacy scan from `docs/PUBLIC_REPOSITORY_MAINTENANCE.md`
```

- [x] **Step 3: Run documentation checks by inspection**

Run:

```bash
rg -n "report.pdf|PDF report|reportlab|P2b Progress" docs/DEVELOPMENT_MANUAL.md docs/NEXT_PHASE_ROADMAP_2026-07-06.md docs/superpowers/specs/2026-07-06-pdf-report-export-design.md docs/superpowers/plans/2026-07-06-pdf-report-export.md
```

Selected relevant output:

```text
docs/NEXT_PHASE_ROADMAP_2026-07-06.md:256:## P2b Progress - PDF Report Export
docs/NEXT_PHASE_ROADMAP_2026-07-06.md:258:Implemented PDF report export for completed investigations:
docs/NEXT_PHASE_ROADMAP_2026-07-06.md:260:- `GET /api/investigations/{id}/report.pdf`;
docs/NEXT_PHASE_ROADMAP_2026-07-06.md:273:- `PYTHONPATH=backend uv run --project backend python3 -m unittest discover -s backend/tests -p 'test_report_pdf_export.py' -v`
docs/DEVELOPMENT_MANUAL.md:902:- `GET /api/investigations/{id}/report.pdf`: redacted printable PDF report. Returns `503` with JSON detail when PDF support is unavailable because `reportlab` is not installed.
docs/superpowers/specs/2026-07-06-pdf-report-export-design.md:27:GET /api/investigations/{id}/report.pdf
docs/superpowers/specs/2026-07-06-pdf-report-export-design.md:33:reportlab
docs/superpowers/specs/2026-07-06-pdf-report-export-design.md:96:  "detail": "PDF export is unavailable because reportlab is not installed."
docs/superpowers/specs/2026-07-06-pdf-report-export-design.md:151:/api/investigations/{id}/report.pdf
docs/superpowers/specs/2026-07-06-pdf-report-export-design.md:255:  `/api/investigations/{id}/report.pdf`.
docs/superpowers/plans/2026-07-06-pdf-report-export.md:630:- `GET /api/investigations/{id}/report.pdf`: redacted printable PDF report. Returns `503` with JSON detail when PDF support is unavailable because `reportlab` is not installed.
docs/superpowers/plans/2026-07-06-pdf-report-export.md:638:## P2b Progress - PDF Report Export
docs/superpowers/plans/2026-07-06-pdf-report-export.md:640:Implemented PDF report export for completed investigations:
docs/superpowers/plans/2026-07-06-pdf-report-export.md:642:- `GET /api/investigations/{id}/report.pdf`;
docs/superpowers/plans/2026-07-06-pdf-report-export.md:655:- `PYTHONPATH=backend uv run --project backend python3 -m unittest discover -s backend/tests -p 'test_report_pdf_export.py' -v`
docs/superpowers/plans/2026-07-06-pdf-report-export.md:667:rg -n "report.pdf|PDF report|reportlab|P2b Progress" docs/DEVELOPMENT_MANUAL.md docs/NEXT_PHASE_ROADMAP_2026-07-06.md docs/superpowers/specs/2026-07-06-pdf-report-export-design.md docs/superpowers/plans/2026-07-06-pdf-report-export.md
```

- [x] **Step 4: Commit documentation updates**

Run:

```bash
git add docs/DEVELOPMENT_MANUAL.md docs/NEXT_PHASE_ROADMAP_2026-07-06.md docs/superpowers/plans/2026-07-06-pdf-report-export.md
git commit -m "docs: document pdf report export"
```

## Task 6: Full Verification And Privacy Scan

**Files:**
- Test: all changed backend and documentation files

- [x] **Step 1: Run PDF tests**

Run:

```bash
PYTHONPATH=backend uv run --project backend python3 -m unittest discover -s backend/tests -p 'test_report_pdf_export.py' -v
```

Expected:

```text
Ran 6 tests
OK
```

Evidence (2026-07-06):

```text
Actual command: cd backend && uv run python3 -m unittest discover -s tests -p 'test_report_pdf_export.py' -v
Initial sandboxed run could not access the uv cache; reran with approval for uv cache access.
Ran 6 tests in 1.591s
OK
```

- [x] **Step 2: Run existing report export tests**

Run:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v
```

Expected:

```text
Ran 8 tests
OK
```

Evidence (2026-07-06):

```text
Actual command: PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v
Ran 8 tests in 2.054s
OK
```

- [ ] **Step 3: Run full project verification**

Run:

```bash
bash scripts/verify.sh
```

Expected:

```text
backend tests pass
frontend checks pass
frontend build passes
```

Evidence (2026-07-06):

```text
Actual command: bash scripts/verify.sh
Result: FAILED during backend unittest discovery.
Summary: Ran 327 tests in 16.917s; FAILED (failures=1, errors=2).
Root cause observed: scripts/verify.sh uses system Python 3.14, where reportlab is not installed.
The same PDF tests pass in the backend uv environment.
No production code was changed.
```

- [x] **Step 4: Generate a sample PDF for rendering verification**

Run:

```bash
PYTHONPATH=backend uv run --project backend python3 - <<'PY'
from pathlib import Path
from backend.tests.test_report_pdf_export import _sample_detail
from app.services.report_pdf import render_report_pdf

output = Path("tmp/pdfs/sample-investigation-report.pdf")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(render_report_pdf(_sample_detail()))
print(output)
PY
```

Expected:

```text
tmp/pdfs/sample-investigation-report.pdf
```

Evidence (2026-07-06):

```text
Actual command: cd backend && uv run python3 -c '...'
Used imports: tests.test_report_pdf_export._sample_detail and app.services.report_pdf.render_report_pdf
Output: ../tmp/pdfs/sample-investigation-report.pdf
```

- [x] **Step 5: Render first PDF pages to PNG**

Run:

```bash
pdftoppm -png tmp/pdfs/sample-investigation-report.pdf tmp/pdfs/sample-investigation-report
```

Expected:

```text
tmp/pdfs/sample-investigation-report-1.png
```

Open or inspect the PNG locally and confirm:

```text
title visible, metadata aligned, headings readable, long text wraps, footer visible, no overlapping text
```

Evidence (2026-07-06):

```text
Actual command: pdftoppm -png tmp/pdfs/sample-investigation-report.pdf tmp/pdfs/sample-investigation-report
Generated:
- tmp/pdfs/sample-investigation-report-1.png
- tmp/pdfs/sample-investigation-report-2.png
Visual inspection: title visible, metadata aligned, headings readable, long text wraps, footers visible, no obvious overlapping text.
```

- [x] **Step 6: Run added-line privacy scan**

Run this diff-scoped added-line scan from the repository root. It extracts the
maintained privacy pattern from `docs/PUBLIC_REPOSITORY_MAINTENANCE.md`, scans
only lines added or changed relative to `HEAD`, and prints only findings:

```bash
set -euo pipefail
privacy_pattern="$(
  awk "/^rg -n --hidden -S / { line=\$0; sub(/^rg -n --hidden -S \047/, \"\", line); sub(/\047[[:space:]]*\\\\\$/, \"\", line); print line; exit }" docs/PUBLIC_REPOSITORY_MAINTENANCE.md
)"
findings="$(
  git diff --unified=0 HEAD -- . \
    | awk '/^\+/ && !/^\+\+\+/{sub(/^\+/, ""); print}' \
    | rg -n --pcre2 "$privacy_pattern" || true
)"
if [ -n "$findings" ]; then
  printf '%s\n' "$findings"
  exit 1
fi
```

Expected:

```text
no output and exit 0; any output is a finding to review before committing
```

Evidence (2026-07-06):

```text
Actual command: plan diff-scoped added-line privacy scan
Output: no output
Exit status: 0
```

- [x] **Step 7: Commit final plan status if the plan file was updated**

Run:

```bash
git add docs/superpowers/plans/2026-07-06-pdf-report-export.md
git commit -m "docs: record pdf report verification"
```

Skip this commit only if the plan file has no changes after Task 5.

Evidence (2026-07-06):

```text
Plan file updated with Task 6 evidence and prepared for the requested docs-only commit.
```

## Task 7: Push And Final Handoff

**Files:**
- Test: git state

- [ ] **Step 1: Confirm status**

Run:

```bash
git status --short --branch
```

Expected:

```text
## main...origin/main [ahead N]
```

- [ ] **Step 2: Push commits**

Run:

```bash
git push
```

Expected:

```text
main -> main
```

- [ ] **Step 3: Confirm clean synced state**

Run:

```bash
git status --short --branch
```

Expected:

```text
## main...origin/main
```

## Self-Review

Spec coverage:

- `/report.pdf` endpoint: Task 4.
- Reportlab dependency and missing dependency `503`: Tasks 2, 3, and 4.
- Redacted payload reuse: Task 3.
- Required sections: Tasks 1 and 3.
- Binary `application/pdf` response: Task 4.
- Text extraction verification: Tasks 1 and 6.
- Rendering verification with `pdftoppm`: Task 6.
- Documentation alignment: Task 5.
- Privacy scan before publication: Task 6.

Placeholder scan:

- The plan contains no unresolved placeholder markers or undefined task references.
- Each code-changing step names exact files and commands.

Type consistency:

- `render_report_pdf(detail: dict) -> bytes` is used consistently in tests, service, and API.
- `ReportPdfDependencyError` and `PDF_UNAVAILABLE_DETAIL` are defined in `report_pdf.py` and imported by `main.py`.
- API tests use byte response helper because PDF bodies are binary.
