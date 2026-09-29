from http.server import ThreadingHTTPServer
import json
from threading import Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.core.intelligence_summary import build_investigation_intelligence
from app.main import ApiHandler


class IntelligenceSummaryTests(TestCase):
    def test_groups_known_entities_without_inventing_trade_records(self):
        payload = build_investigation_intelligence(
            {
                "id": "task-1",
                "entities": [
                    {"type": "email", "value": "sales@example.com", "source_tool": "site", "confidence": 0.9},
                    {"type": "email", "value": "sales@example.com", "source_tool": "site", "confidence": 0.4},
                    {"type": "phone", "value": "+57 300", "source_tool": "site", "confidence": 0.6},
                    {"type": "domain", "value": "example.com", "source_tool": "site", "confidence": 0.8},
                    {"type": "whatsapp", "value": "+57 300", "source_tool": "site", "confidence": 0.5},
                    {"type": "profile_url", "value": "https://www.linkedin.com/in/ada", "source_tool": "search", "confidence": 0.7},
                    {"type": "product_scope", "value": "aluminum windows", "source_tool": "site", "confidence": 0.66},
                ],
                "evidence": [
                    {"entity_value": "sales@example.com", "snippet": "Contact sales@example.com"},
                ],
            }
        )

        self.assertEqual(payload["investigation_id"], "task-1")
        self.assertEqual(payload["contacts"]["summary"]["emails_count"], 1)
        self.assertTrue(payload["contacts"]["emails"][0]["verified"])
        self.assertEqual(payload["contacts"]["emails"][0]["context"], "Contact sales@example.com")
        self.assertEqual(payload["contacts"]["websites"], ["https://example.com"])
        self.assertEqual(payload["contacts"]["social"][0]["type"], "whatsapp")
        self.assertEqual(payload["social"]["summary"]["professional"], 1)
        self.assertEqual(payload["products"]["summary"]["total_products"], 1)
        self.assertEqual(payload["products"]["hs_codes"], [])

    def test_intelligence_route_reads_the_saved_investigation(self):
        detail = {"id": "task-9", "entities": [{"type": "phone", "value": "123", "source_tool": "note", "confidence": 0.4}]}
        with patch("app.main.store.get_investigation", return_value=detail):
            status, payload = _request("GET", "/api/investigations/task-9/intelligence")
        self.assertEqual(status, 200)
        self.assertEqual(payload["contacts"]["phones"][0]["value"], "123")

    def test_missing_investigation_intelligence_is_not_found(self):
        with patch("app.main.store.get_investigation", return_value=None):
            status, payload = _request("GET", "/api/investigations/missing/intelligence")
        self.assertEqual(status, 404)
        self.assertEqual(payload["detail"], "investigation not found")

    def test_customs_endpoint_explains_that_no_source_is_connected(self):
        status, payload = _request("POST", "/api/customs/supply-chain", {"company": "Example LLC"})
        self.assertEqual(status, 501)
        self.assertIn("海关", payload["detail"])


def _request(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with patch.dict(
            "os.environ",
            {"ADMIN_API_TOKEN": "", "AGENT_API_TOKEN": "", "READ_API_TOKEN": ""},
            clear=False,
        ):
            try:
                with urlopen(request, timeout=5) as response:
                    return response.status, json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                with exc:
                    return exc.code, json.loads(exc.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
