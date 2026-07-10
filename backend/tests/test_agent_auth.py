import http.client
import json
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from app.main import (
    ApiHandler,
    agent_request_authorized,
    missing_required_auth_tokens,
    read_request_authorized,
    request_authorized,
    requires_write_authorization,
)


PRODUCTION_ENV = {
    "APP_ENV": "production",
    "ADMIN_API_TOKEN": "admin-secret",
    "AGENT_API_TOKEN": "agent-secret",
    "READ_API_TOKEN": "read-secret",
    "CORS_ALLOWED_ORIGINS": "https://hcs.test",
}


class ApiTestServer:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict | None = None,
        headers: list[tuple[str, str]] | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, bytes, list[tuple[str, str]]]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        with patch.dict("os.environ", env or PRODUCTION_ENV, clear=True):
            connection.putrequest(method, path)
            if payload is not None:
                connection.putheader("Content-Type", "application/json")
                connection.putheader("Content-Length", str(len(body)))
            for name, value in headers or []:
                connection.putheader(name, value)
            connection.endheaders(body)
            response = connection.getresponse()
            response_body = response.read()
            response_headers = response.getheaders()
        connection.close()
        return response.status, response_body, response_headers


def header_value(headers: list[tuple[str, str]], name: str) -> str | None:
    values = [value for key, value in headers if key.casefold() == name.casefold()]
    return values[0] if len(values) == 1 else None


def json_payload(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


def cookie_from_set_cookie(value: str) -> str:
    return value.split(";", 1)[0]


def assert_security_headers(test_case: unittest.TestCase, headers: list[tuple[str, str]]) -> None:
    test_case.assertEqual(header_value(headers, "Cache-Control"), "no-store")
    test_case.assertEqual(header_value(headers, "X-Content-Type-Options"), "nosniff")
    test_case.assertEqual(header_value(headers, "Referrer-Policy"), "no-referrer")


class AgentAuthTests(unittest.TestCase):
    def test_allows_agent_request_when_token_is_not_configured(self):
        self.assertTrue(agent_request_authorized({}, expected_token=""))

    def test_fail_closed_mode_rejects_missing_token(self):
        self.assertFalse(request_authorized({}, expected_token="", require_token=True))
        self.assertFalse(
            read_request_authorized("/api/investigations", {}, expected_token="", require_token=True)
        )
        self.assertTrue(
            request_authorized({"Authorization": "Bearer secret"}, expected_token="secret", require_token=True)
        )

    def test_production_reports_missing_required_tokens(self):
        missing = missing_required_auth_tokens(
            {
                "APP_ENV": "production",
                "ADMIN_API_TOKEN": "admin",
                "AGENT_API_TOKEN": "",
                "READ_API_TOKEN": "",
            }
        )

        self.assertEqual(missing, ["AGENT_API_TOKEN", "READ_API_TOKEN"])

    def test_development_does_not_require_tokens_by_default(self):
        self.assertEqual(missing_required_auth_tokens({"APP_ENV": "development"}), [])

    def test_requires_bearer_token_when_configured(self):
        self.assertFalse(agent_request_authorized({}, expected_token="secret"))
        self.assertFalse(
            agent_request_authorized({"Authorization": "Bearer wrong"}, expected_token="secret")
        )
        self.assertTrue(
            agent_request_authorized({"Authorization": "Bearer secret"}, expected_token="secret")
        )

    def test_cors_allows_authorization_header_for_browser_agents(self):
        self.assertIn("Authorization", "Content-Type, Authorization")

    def test_write_routes_require_authorization_when_admin_token_is_configured(self):
        self.assertTrue(requires_write_authorization("/api/investigations"))
        self.assertTrue(requires_write_authorization("/api/agents/heartbeat"))
        self.assertTrue(requires_write_authorization("/api/investigations/task-1/run-jobs"))
        self.assertTrue(requires_write_authorization("/api/investigations/task-1/delete"))
        self.assertTrue(requires_write_authorization("/api/investigations/release-stale"))
        self.assertFalse(requires_write_authorization("/api/health"))

    def test_admin_token_authorizes_management_write_routes(self):
        self.assertFalse(request_authorized({}, expected_token="admin-secret"))
        self.assertFalse(request_authorized({"Authorization": "Bearer wrong"}, expected_token="admin-secret"))
        self.assertTrue(request_authorized({"Authorization": "Bearer admin-secret"}, expected_token="admin-secret"))

    def test_read_token_authorizes_sensitive_read_routes(self):
        self.assertTrue(read_request_authorized("/api/health", {}, expected_token="read-secret"))
        self.assertFalse(read_request_authorized("/api/investigations", {}, expected_token="read-secret"))
        self.assertFalse(
            read_request_authorized(
                "/api/investigations/task-1",
                {"Authorization": "Bearer wrong"},
                expected_token="read-secret",
            )
        )
        self.assertTrue(
            read_request_authorized(
                "/api/investigations/task-1",
                {"Authorization": "Bearer read-secret"},
                expected_token="read-secret",
            )
        )


class BrowserAuthHttpTests(unittest.TestCase):
    def setUp(self):
        self.server_context = ApiTestServer()
        self.server = self.server_context.__enter__()

    def tearDown(self):
        self.server_context.__exit__(None, None, None)

    def login(self, env: dict[str, str] | None = None) -> tuple[str, str, list[tuple[str, str]]]:
        status, body, headers = self.server.request(
            "POST",
            "/api/auth/login",
            payload={"admin_token": "admin-secret"},
            env=env,
        )
        self.assertEqual(status, 200)
        payload = json_payload(body)
        self.assertNotIn("admin-secret", json.dumps(payload))
        cookie = header_value(headers, "Set-Cookie")
        self.assertIsNotNone(cookie)
        return cookie_from_set_cookie(cookie), payload["csrf_token"], headers

    def test_login_creates_secure_strict_http_only_session_without_echoing_secret(self):
        cookie, csrf_token, headers = self.login()

        set_cookie = header_value(headers, "Set-Cookie")
        self.assertTrue(cookie.startswith("osint_admin_session="))
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertIn("Secure", set_cookie)
        self.assertIn("Path=/", set_cookie)
        self.assertNotEqual(csrf_token, "admin-secret")
        self.assertNotIn("admin-secret", json.dumps(json_payload(self.server.request(
            "GET", "/api/auth/session", headers=[("Cookie", cookie)]
        )[1])))
        assert_security_headers(self, headers)

    def test_wrong_and_empty_login_fail_without_echoing_credentials(self):
        for supplied in ("wrong-secret", ""):
            with self.subTest(supplied=supplied):
                status, body, headers = self.server.request(
                    "POST", "/api/auth/login", payload={"admin_token": supplied}
                )
                self.assertEqual(status, 401)
                response_text = body.decode("utf-8")
                self.assertNotIn("admin-secret", response_text)
                if supplied:
                    self.assertNotIn(supplied, response_text)
                self.assertIsNone(header_value(headers, "Set-Cookie"))
                assert_security_headers(self, headers)

    def test_session_reports_required_state_and_rotates_csrf_when_authenticated(self):
        status, body, _headers = self.server.request("GET", "/api/auth/session")
        self.assertEqual(status, 200)
        self.assertEqual(json_payload(body), {"authenticated": False, "required": True})

        cookie, login_csrf, _headers = self.login()
        status, body, _headers = self.server.request(
            "GET", "/api/auth/session", headers=[("Cookie", cookie)]
        )
        payload = json_payload(body)
        self.assertEqual(status, 200)
        self.assertTrue(payload["authenticated"])
        self.assertTrue(payload["required"])
        self.assertEqual(payload["role"], "administrator")
        self.assertNotEqual(payload["csrf_token"], login_csrf)

        development = {"APP_ENV": "development"}
        status, body, _headers = self.server.request(
            "GET", "/api/auth/session", env=development
        )
        self.assertEqual(status, 200)
        self.assertEqual(json_payload(body), {"authenticated": False, "required": False})

    def test_cookie_mutation_requires_exact_origin_and_csrf(self):
        cookie, csrf_token, _headers = self.login()
        cases = (
            [("Cookie", cookie)],
            [("Cookie", cookie), ("Origin", "https://hcs.test")],
            [("Cookie", cookie), ("Origin", "https://wrong.test"), ("X-CSRF-Token", csrf_token)],
            [("Cookie", cookie), ("Origin", "https://hcs.test"), ("X-CSRF-Token", "wrong")],
        )
        for headers in cases:
            with self.subTest(headers=headers):
                status, _body, _response_headers = self.server.request(
                    "POST",
                    "/api/investigations/release-stale",
                    payload={"stale_after_seconds": 1800},
                    headers=headers,
                )
                self.assertEqual(status, 403)

        with patch("app.main.store.release_stale_claims", return_value=[]):
            status, body, _headers = self.server.request(
                "POST",
                "/api/investigations/release-stale",
                payload={"stale_after_seconds": 1800},
                headers=[
                    ("Cookie", cookie),
                    ("Origin", "https://hcs.test"),
                    ("X-CSRF-Token", csrf_token),
                ],
            )
        self.assertEqual(status, 200)
        self.assertEqual(json_payload(body), {"released": []})

    def test_duplicate_cookie_origin_and_csrf_headers_fail_closed(self):
        cookie, csrf_token, _headers = self.login()
        duplicate_cases = (
            [("Cookie", cookie), ("Cookie", cookie), ("Origin", "https://hcs.test"), ("X-CSRF-Token", csrf_token)],
            [("Cookie", cookie), ("Origin", "https://hcs.test"), ("Origin", "https://hcs.test"), ("X-CSRF-Token", csrf_token)],
            [("Cookie", cookie), ("Origin", "https://hcs.test"), ("X-CSRF-Token", csrf_token), ("X-CSRF-Token", csrf_token)],
        )
        for headers in duplicate_cases:
            with self.subTest(headers=headers):
                status, _body, _response_headers = self.server.request(
                    "POST", "/api/investigations/release-stale", payload={}, headers=headers
                )
                self.assertIn(status, (401, 403))

    def test_cookie_authenticates_reads_and_logout_revokes_session(self):
        cookie, csrf_token, _headers = self.login()
        with patch("app.main.store.list_agents", return_value=[]):
            status, body, _headers = self.server.request(
                "GET", "/api/agents", headers=[("Cookie", cookie)]
            )
        self.assertEqual(status, 200)
        self.assertEqual(json_payload(body), {"agents": []})

        status, _body, headers = self.server.request(
            "POST",
            "/api/auth/logout",
            payload={},
            headers=[
                ("Cookie", cookie),
                ("Origin", "https://hcs.test"),
                ("X-CSRF-Token", csrf_token),
            ],
        )
        self.assertEqual(status, 200)
        expired_cookie = header_value(headers, "Set-Cookie")
        self.assertIn("Max-Age=0", expired_cookie)
        self.assertIn("expires=thu, 01 jan 1970 00:00:00 gmt", expired_cookie.lower())

        status, body, _headers = self.server.request(
            "GET", "/api/auth/session", headers=[("Cookie", cookie)]
        )
        self.assertEqual(status, 200)
        self.assertEqual(json_payload(body), {"authenticated": False, "required": True})

    def test_logout_rejects_missing_browser_mutation_protection(self):
        cookie, _csrf_token, _headers = self.login()
        status, _body, headers = self.server.request(
            "POST", "/api/auth/logout", payload={}, headers=[("Cookie", cookie)]
        )
        self.assertEqual(status, 403)
        self.assertIsNone(header_value(headers, "Set-Cookie"))

    def test_bearer_read_and_management_compatibility(self):
        with patch("app.main.store.list_agents", return_value=[]):
            status, _body, _headers = self.server.request(
                "GET",
                "/api/agents",
                headers=[("Authorization", "Bearer read-secret")],
            )
        self.assertEqual(status, 200)

        with patch("app.main.store.release_stale_claims", return_value=[]):
            status, _body, _headers = self.server.request(
                "POST",
                "/api/investigations/release-stale",
                payload={},
                headers=[("Authorization", "Bearer admin-secret")],
            )
        self.assertEqual(status, 200)

    def test_development_management_requests_remain_usable_without_auth(self):
        with patch("app.main.store.release_stale_claims", return_value=[]):
            status, body, _headers = self.server.request(
                "POST",
                "/api/investigations/release-stale",
                payload={},
                env={"APP_ENV": "development"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(json_payload(body), {"released": []})

    def test_missing_production_management_auth_returns_401(self):
        status, _body, _headers = self.server.request(
            "POST", "/api/investigations/release-stale", payload={}
        )
        self.assertEqual(status, 401)

    def test_cookie_defaults_and_invalid_ttl_are_environment_safe(self):
        development_env = {
            "APP_ENV": "development",
            "ADMIN_API_TOKEN": "admin-secret",
            "OSINT_SESSION_TTL_SECONDS": "not-an-integer",
            "OSINT_COOKIE_SECURE": "not-a-boolean",
        }
        _cookie, _csrf, headers = self.login(development_env)
        set_cookie = header_value(headers, "Set-Cookie")
        self.assertNotIn("Secure", set_cookie)
        self.assertIn("Max-Age=28800", set_cookie)

        production_insecure = {**PRODUCTION_ENV, "OSINT_COOKIE_SECURE": "false", "OSINT_SESSION_TTL_SECONDS": "120"}
        _cookie, _csrf, headers = self.login(production_insecure)
        set_cookie = header_value(headers, "Set-Cookie")
        self.assertNotIn("Secure", set_cookie)
        self.assertIn("Max-Age=120", set_cookie)

    def test_security_headers_cover_json_text_binary_error_and_cors(self):
        bearer = [("Authorization", "Bearer read-secret")]
        status, _body, headers = self.server.request("GET", "/missing", headers=bearer)
        self.assertEqual(status, 404)
        assert_security_headers(self, headers)

        report = {"id": "task-1", "name": "Report"}
        with (
            patch("app.main.store.get_investigation", return_value=report),
            patch("app.main.render_report_markdown", return_value="# report"),
        ):
            status, body, headers = self.server.request(
                "GET", "/api/investigations/task-1/report.md", headers=bearer
            )
        self.assertEqual((status, body), (200, b"# report"))
        assert_security_headers(self, headers)

        with (
            patch("app.main.store.get_investigation", return_value=report),
            patch("app.main.render_report_pdf", return_value=b"%PDF-test"),
        ):
            status, body, headers = self.server.request(
                "GET", "/api/investigations/task-1/report.pdf", headers=bearer
            )
        self.assertEqual((status, body), (200, b"%PDF-test"))
        assert_security_headers(self, headers)

        status, _body, headers = self.server.request(
            "OPTIONS", "/api/investigations", headers=[("Origin", "https://hcs.test")]
        )
        self.assertEqual(status, 200)
        self.assertEqual(header_value(headers, "Access-Control-Allow-Origin"), "https://hcs.test")
        self.assertEqual(header_value(headers, "Access-Control-Allow-Credentials"), "true")
        self.assertIn("X-CSRF-Token", header_value(headers, "Access-Control-Allow-Headers"))
        assert_security_headers(self, headers)


if __name__ == "__main__":
    unittest.main()
