# PDF Report Export Design

## Context

P2 report export now exposes redacted structured JSON, Markdown, and
self-contained HTML report endpoints. The roadmap explicitly defers PDF until
the HTML contract is stable.

HTML export is stable enough to extend because the report module already has a
single normalized payload builder and redaction path:

- `build_report_payload(detail)`
- `render_report_markdown(detail)`
- `render_report_html(detail)`
- `redact_report_text(value)`

The PDF phase should reuse that payload. It should not parse HTML, read the
database directly, or bypass redaction.

## Decision

Add a PDF export endpoint backed by a small report PDF renderer.

Recommended endpoint:

```text
GET /api/investigations/{id}/report.pdf
```

Recommended rendering dependency:

```text
reportlab
```

`reportlab` is the right fit for this phase because it can create a printable
PDF directly from structured report sections without requiring a browser,
external renderer, or HTML-to-PDF service.

## Goals

- Add `GET /api/investigations/{id}/report.pdf`.
- Render PDF from the same redacted payload used by JSON, Markdown, and HTML.
- Include the required report sections:
  - BLUF;
  - PIR answers;
  - EEI matrix;
  - quality gate;
  - source-backed facts;
  - evidence appendix;
  - ACH / I&W;
  - intelligence gaps;
  - next collection actions.
- Return `application/pdf`.
- Keep the report printable and readable on A4 or letter-size pages.
- Add clear dependency handling when PDF support is unavailable.
- Add tests for success, missing dependency behavior, required sections, and
  privacy safeguards.
- Verify generated PDFs through both file signature checks and text/rendering
  checks when the local environment has PDF tooling.

## Non-Goals

- No frontend redesign.
- No report persistence table.
- No object storage or email delivery.
- No signed reports or watermarking.
- No HTML-to-PDF browser rendering.
- No external queue, worker, or deployment architecture change.
- No change to intelligence collection, fact promotion, quality scoring, or ACH
  analysis.

## Dependency Strategy

Add `reportlab` to `backend/pyproject.toml`.

The application should still fail gracefully if a deployment is missing the
dependency. The PDF renderer should use a guarded import and raise a local,
explicit exception such as:

```python
class ReportPdfDependencyError(RuntimeError):
    ...
```

API behavior when the dependency is missing:

```text
503 Service Unavailable
```

Response body:

```json
{
  "detail": "PDF export is unavailable because reportlab is not installed."
}
```

This keeps startup and existing report formats safe while making the operational
fix obvious.

## Report PDF Module

Preferred implementation location:

```text
backend/app/services/report_pdf.py
```

Public functions:

```python
def render_report_pdf(detail: dict) -> bytes:
    ...
```

Responsibilities:

- call `build_report_payload(detail)`;
- render title, metadata, quality summary, and required sections;
- wrap long text safely;
- preserve section order from the payload;
- include generated timestamp and investigation id;
- return PDF bytes only;
- never read or write files directly.

The module should depend on `report_export.py`, not the other way around. This
keeps JSON, Markdown, and HTML independent from the optional PDF path.

## PDF Layout

The PDF should be plain and operational:

- page title with investigation name;
- metadata block with status, seed type, quality score, completion state, and
  generated timestamp;
- section headings matching the existing report payload;
- bullet-style section items;
- footer with page number and a short review note;
- conservative margins and readable type size.

The layout does not need branding or complex charts. It should prioritize
legibility, predictable pagination, and no clipped text.

## API Routing

Extend `ApiHandler.do_GET()` before the generic investigation detail route:

```text
/api/investigations/{id}/report.pdf
```

Routing behavior:

- preserve existing read-token authorization behavior;
- return `404` when the investigation does not exist;
- return `200` with `application/pdf` when export succeeds;
- return `503` with JSON when `reportlab` is unavailable;
- avoid broad exception swallowing that hides rendering bugs in tests.

Add a binary response helper if needed:

```python
def _binary(self, body: bytes, content_type: str, status: int = 200) -> None:
    ...
```

## Testing

Add focused backend tests before implementation.

Recommended test additions:

```text
backend/tests/test_report_pdf_export.py
```

Service tests:

- `render_report_pdf()` returns bytes beginning with `%PDF` when `reportlab` is
  available.
- PDF output contains required section titles when extracted with `pypdf` or
  `pdfplumber`.
- generated PDF bytes do not contain known private sample strings.
- missing `reportlab` raises the explicit dependency error.

API tests:

- `/api/investigations/{id}/report.pdf` returns `application/pdf` when PDF
  support is available.
- `/api/investigations/{id}/report.pdf` returns `503` when `reportlab` is
  unavailable.
- missing investigation returns `404`.
- existing `/report`, `/report.md`, and `/report.html` behavior is unchanged.

Use public-safe sample data only. Do not add real target names, internal hosts,
tokens, local absolute paths, or raw production investigation identifiers.

## Rendering Verification

Use `pdftoppm` when available:

```text
pdftoppm -png <sample-report.pdf> <output-prefix>
```

Review the first rendered page for:

- title visible and not clipped;
- metadata aligned;
- headings readable;
- long section items wrapped;
- no overlapping text;
- no black boxes or missing glyphs;
- footer/page number visible.

If `pdftoppm` is not available in a future environment, record that rendering
verification could not be performed and keep text extraction checks in place.

## Documentation

After implementation, update:

- `docs/DEVELOPMENT_MANUAL.md`
  - add `/report.pdf` under Reports;
  - document the dependency and `503` behavior.
- `docs/NEXT_PHASE_ROADMAP_2026-07-06.md`
  - mark P2 PDF export as completed if verification passes.
- `docs/superpowers/plans/2026-07-06-pdf-report-export.md`
  - implementation plan and final verification notes.

## Verification

Required local verification:

```text
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_pdf_export.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v
bash scripts/verify.sh
```

Recommended PDF-specific verification after dependencies are installed:

```text
pdftoppm -png <sample-report.pdf> <output-prefix>
```

Before commit and push, run the repository's added-line privacy scan from
`docs/PUBLIC_REPOSITORY_MAINTENANCE.md`.

## Acceptance Criteria

- A completed investigation can be exported as PDF through
  `/api/investigations/{id}/report.pdf`.
- PDF generation reuses the redacted structured report payload.
- Required report sections are present in the PDF.
- The API returns a clear `503` if PDF support is not installed.
- PDF tests cover success and dependency-missing behavior.
- Rendered PDF sample is visually checked when `pdftoppm` is available.
- Existing JSON, Markdown, and HTML report endpoints still pass.
- `bash scripts/verify.sh` passes.
- Added-line privacy scan passes before publication.

## Safe-Agent Routing Notes

Safe-Agent router selected the `document-to-knowledge-base` scenario with
trusted PDF/document review guidance. The applicable method constraints for
this project are:

- identify source material and allowed workspace scope;
- preserve report structure and metadata;
- separate generated interpretation from source-backed report sections;
- verify PDF output through text extraction and rendering checks;
- record extraction or rendering gaps instead of treating unverified output as
  complete;
- keep privacy boundaries explicit before publication.

The router output is method-only guidance. It does not grant runtime,
deployment, network, or credential permissions.
