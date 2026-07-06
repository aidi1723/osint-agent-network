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
