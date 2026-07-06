import importlib
import json
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from app.main import ApiHandler
from app.services.report_pdf import ReportPdfDependencyError, render_report_pdf
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

PDF_UNAVAILABLE_DETAIL = "PDF export is unavailable because reportlab is not installed."


class ReportPdfServiceTests(unittest.TestCase):
    def test_render_report_pdf_returns_pdf_bytes_with_required_sections(self):
        pdf_bytes = render_report_pdf(_sample_detail())

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        text = _extract_pdf_text(pdf_bytes)
        for title in REQUIRED_SECTION_TITLES:
            self.assertIn(title, text)
        self.assertIn("Example Manufacturing LLC", text)
        self.assertIn("Generated from structured OSINT records", text)

    def test_render_report_pdf_redacts_sensitive_values(self):
        detail = _sample_detail()
        detail["facts"][0]["statement"] += " Authorization: " + "Bearer " + ("A" * 24)
        detail["evidence_ledger"][0]["snippet"] += " Path: /Users/example/.config/tool/session.json"
        detail["evidence_ledger"][0]["source_url"] = "http://" + "10." + "1.2.3:5000/status"

        pdf_bytes = render_report_pdf(detail)
        text = _extract_pdf_text(pdf_bytes)

        self.assertIn("<redacted-token>", text)
        self.assertIn("<redacted-path>", text)
        self.assertIn("<redacted-url>", text)
        self.assertNotIn("Bearer", text)
        self.assertNotIn("/Users/example", text)
        self.assertNotIn("10." + "1.2.3", text)

    def test_missing_reportlab_raises_explicit_dependency_error(self):
        real_import_module = importlib.import_module

        def fake_import_module(name, package=None):
            if name.startswith("reportlab"):
                raise ModuleNotFoundError("No module named 'reportlab'")
            return real_import_module(name, package)

        with patch("importlib.import_module", side_effect=fake_import_module):
            with self.assertRaises(ReportPdfDependencyError):
                render_report_pdf(_sample_detail())


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

        with patch("app.main.render_report_pdf", side_effect=ReportPdfDependencyError(PDF_UNAVAILABLE_DETAIL)):
            status, headers, body = _get_bytes_with_store(f"/api/investigations/{investigation_id}/report.pdf", api_store)

        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(status, 503)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(payload["detail"], PDF_UNAVAILABLE_DETAIL)


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
