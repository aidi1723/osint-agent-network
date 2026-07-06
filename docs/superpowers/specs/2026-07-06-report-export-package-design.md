# Report Export Package Design

## Context

The platform already produces structured investigation detail and a Markdown
report through `render_structured_report()`. The current API returns the whole
investigation detail, but it does not expose delivery-oriented report endpoints
or a standalone HTML package that can be handed to an analyst, salesperson, or
reviewer outside the web UI.

P2 should make completed investigation output easier to export without changing
the investigation pipeline or adding another runtime dependency.

## Decision

Add a small report export layer that renders existing investigation detail into:

- structured report JSON;
- Markdown report;
- self-contained HTML report.

The first implementation should focus on HTML export. PDF export is explicitly
deferred until the HTML contract is stable.

## Goals

- Add API endpoints for report export:
  - `GET /api/investigations/{id}/report`
  - `GET /api/investigations/{id}/report.md`
  - `GET /api/investigations/{id}/report.html`
- Reuse existing detail fields, quality assessment, and
  `render_structured_report()` output.
- Include the required report sections:
  - BLUF;
  - PIR answers;
  - EEI coverage matrix;
  - quality gate;
  - source-backed facts;
  - evidence appendix;
  - ACH / I&W;
  - intelligence gaps;
  - next collection actions.
- Apply redaction before report content is returned.
- Add tests for section presence, response content types, missing investigation
  behavior, and redaction.
- Avoid new dependencies for the HTML phase.

## Non-Goals

- No PDF generation in this task.
- No frontend redesign.
- No report persistence table.
- No external storage or object upload.
- No new authentication model.
- No live collection or background job changes.
- No change to fact promotion, quality scoring, or ACH logic.

## Report Export Module

Create `backend/app/services/report_export.py`.

Responsibilities:

- build a normalized report payload from an investigation detail dict;
- render Markdown using existing structured report behavior;
- render HTML from the normalized payload;
- redact sensitive strings from all returned report formats.

Suggested public functions:

```python
def build_report_payload(detail: dict) -> dict:
    ...

def render_report_markdown(detail: dict) -> str:
    ...

def render_report_html(detail: dict) -> str:
    ...

def redact_report_text(value: str) -> str:
    ...
```

The module should not read the database directly. It should accept the detail
dict returned by the existing store, which keeps API routing, store behavior,
and rendering concerns separate.

## JSON Contract

`GET /api/investigations/{id}/report` returns:

```json
{
  "investigation_id": "<id>",
  "name": "Example Manufacturing LLC",
  "seed_type": "company",
  "seed_value": "Example Manufacturing LLC",
  "status": "COMPLETED",
  "quality": {
    "score": 82.0,
    "completion_ready": true,
    "missing_keys": []
  },
  "sections": [
    {
      "id": "bluf",
      "title": "BLUF",
      "items": ["..."]
    }
  ],
  "markdown": "# Example Manufacturing LLC\n..."
}
```

`sections` should be deterministic and should include the required section ids:

- `bluf`
- `pir_answers`
- `eei_matrix`
- `quality_gate`
- `source_backed_facts`
- `evidence_appendix`
- `ach_iw`
- `intelligence_gaps`
- `next_collection_actions`

The JSON endpoint should be suitable for later frontend controls and export
scripts. It should not include raw environment variables, API keys, cookies,
local absolute paths, or deployment host details.

## Markdown Endpoint

`GET /api/investigations/{id}/report.md` returns the redacted Markdown report.

Content type:

```text
text/markdown; charset=utf-8
```

If an investigation has no stored `report_markdown`, the exporter should render
one from the current detail and quality assessment instead of returning an empty
body.

## HTML Endpoint

`GET /api/investigations/{id}/report.html` returns a complete HTML document.

Content type:

```text
text/html; charset=utf-8
```

HTML rendering should use only the Python standard library. Use `html.escape()`
for all dynamic text. Do not render raw Markdown as HTML.

The report should be self-contained:

- document title;
- lightweight inline CSS;
- summary metadata;
- required sections;
- evidence and fact lists;
- generated timestamp in UTC;
- footer stating the report was generated from structured OSINT records.

The layout should be simple and printable. It does not need frontend app styling
or JavaScript.

## Redaction Contract

Redaction applies to JSON string fields, Markdown, and HTML dynamic text before
responses are returned.

Minimum redactions:

- bearer tokens and authorization headers;
- common API key patterns;
- GitHub token patterns;
- local absolute paths;
- private deployment host aliases;
- RFC1918 addresses;
- loopback service URLs when they expose local tool ports;
- cookie/session-like fields.

Replacement strings should be stable and explicit:

- `<redacted-token>`
- `<redacted-path>`
- `<redacted-host>`
- `<redacted-url>`

Redaction should be conservative. If a pattern is ambiguous but could reveal
runtime infrastructure or credentials, redact it.

## API Routing

Extend `ApiHandler.do_GET()` before the generic investigation detail handler:

- `/api/investigations/{id}/report`
- `/api/investigations/{id}/report.md`
- `/api/investigations/{id}/report.html`

Routing behavior:

- preserve the current read-token authorization behavior;
- return `404` when the investigation does not exist;
- return `200` with the appropriate content type when export succeeds;
- avoid broad exception swallowing that would hide rendering bugs in tests.

Add a small response helper for non-JSON text responses if needed:

```python
def _text(self, body: str, content_type: str, status: int = 200) -> None:
    ...
```

## Testing

Add focused backend tests before implementation.

Recommended test file:

```text
backend/tests/test_report_export.py
```

Test coverage:

- `build_report_payload()` includes all required section ids.
- `render_report_markdown()` returns a redacted Markdown report with BLUF and
  evidence appendix sections.
- `render_report_html()` returns a complete HTML document with escaped dynamic
  content and required section titles.
- redaction removes tokens, local paths, private hosts, and private IPs from
  sample report content.
- API endpoint tests verify:
  - `/report` returns JSON;
  - `/report.md` returns Markdown content type;
  - `/report.html` returns HTML content type;
  - missing investigation returns `404`.

Use public-safe sample data only. Prefer `MemoryStore` and local HTTP handler
test patterns already present in the backend test suite.

## Documentation

After implementation, update:

- `docs/NEXT_PHASE_ROADMAP_2026-07-06.md` with P2 progress;
- `docs/DEVELOPMENT_MANUAL.md` API notes if the existing report endpoint notes
  are incomplete or inaccurate.

## Verification

Required verification:

```text
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_report_export.py' -v
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_*.py' -v
bash scripts/verify.sh
```

Before commit and push, run the repository's added-line privacy scan from
`docs/PUBLIC_REPOSITORY_MAINTENANCE.md`.

## Acceptance Criteria

- A completed investigation can be exported through JSON, Markdown, and HTML
  report endpoints.
- HTML output includes all required report sections.
- Export output is redacted before being returned.
- Tests verify report sections, content types, missing investigation handling,
  and redaction.
- `bash scripts/verify.sh` passes.
- Added-line privacy scan passes before publication.
