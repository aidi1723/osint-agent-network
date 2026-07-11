import http.client
import json
import socket
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from app.main import (
    ApiHandler,
    agent_request_authorized,
    missing_required_auth_tokens,
    production_security_configuration_errors,
    read_request_authorized,
    request_authorized,
    requires_write_authorization,
    run,
)


PRODUCTION_ENV = {
    "APP_ENV": "production",
    "ADMIN_API_TOKEN": "admin-secret",
    "AGENT_API_TOKEN": "agent-secret",
    "READ_API_TOKEN": "read-secret",
    "CORS_ALLOWED_ORIGINS": "https://hcs.test",
}

_NO_PAYLOAD = object()


class ApiTestServer:
    def __init__(self, handler_class=ApiHandler):
        self.handler_class = handler_class

    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler_class)
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
        payload: object = _NO_PAYLOAD,
        headers: list[tuple[str, str]] | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, bytes, list[tuple[str, str]]]:
        with patch.dict("os.environ", env or PRODUCTION_ENV, clear=True):
            return self.request_in_current_environment(
                method,
                path,
                payload=payload,
                headers=headers,
            )

    def request_in_current_environment(
        self,
        method: str,
        path: str,
        *,
        payload: object = _NO_PAYLOAD,
        headers: list[tuple[str, str]] | None = None,
    ) -> tuple[int, bytes, list[tuple[str, str]]]:
        body = json.dumps(payload).encode("utf-8") if payload is not _NO_PAYLOAD else b""
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.putrequest(method, path)
            if payload is not _NO_PAYLOAD:
                connection.putheader("Content-Type", "application/json")
                connection.putheader("Content-Length", str(len(body)))
            for name, value in headers or []:
                connection.putheader(name, value)
            connection.endheaders(body)
            response = connection.getresponse()
            response_body = response.read()
            response_headers = response.getheaders()
            return response.status, response_body, response_headers
        finally:
            connection.close()

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        headers: list[tuple[str, str]] | None = None,
        env: dict[str, str] | None = None,
        shutdown_write: bool = False,
    ) -> tuple[int, bytes, list[tuple[str, str]]]:
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            with patch.dict("os.environ", env or PRODUCTION_ENV, clear=True):
                connection.putrequest(method, path)
                for name, value in headers or []:
                    connection.putheader(name, value)
                connection.endheaders(body)
                if shutdown_write and connection.sock is not None:
                    connection.sock.shutdown(socket.SHUT_WR)
                response = connection.getresponse()
                response_body = response.read()
                response_headers = response.getheaders()
            return response.status, response_body, response_headers
        finally:
            connection.close()


class ObservedTimeoutApiHandler(ApiHandler):
    INITIAL_TIMEOUT_SECONDS = 0.2

    def setup(self):
        super().setup()
        self.connection.settimeout(self.INITIAL_TIMEOUT_SECONDS)

    def do_POST(self):
        try:
            super().do_POST()
        finally:
            self.server.observed_connection_timeout = self.connection.gettimeout()


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

        self.assertEqual(missing, ["READ_API_TOKEN"])

    def test_production_does_not_require_global_agent_token(self):
        env = {
            "APP_ENV": "  PrOd  ",
            "ADMIN_API_TOKEN": "admin",
            "READ_API_TOKEN": "read",
            "OSINT_COOKIE_SECURE": " YES ",
        }

        self.assertEqual(missing_required_auth_tokens(env), [])
        self.assertEqual(production_security_configuration_errors(env), [])

    def test_nonproduction_explicit_auth_requires_admin_and_read_only(self):
        env = {
            "APP_ENV": "development",
            "OSINT_REQUIRE_AUTH": " On ",
            "ADMIN_API_TOKEN": "admin",
        }

        self.assertEqual(missing_required_auth_tokens(env), ["READ_API_TOKEN"])

    def test_production_security_configuration_errors_match_boolean_policy(self):
        base = {
            "APP_ENV": " Production ",
            "ADMIN_API_TOKEN": "admin",
            "READ_API_TOKEN": "read",
        }
        self.assertIn(
            "OSINT_COOKIE_SECURE must be true in production",
            production_security_configuration_errors(base),
        )
        for true_value in ("1", "true", "YES", " on "):
            with self.subTest(true_value=true_value):
                self.assertEqual(
                    production_security_configuration_errors(
                        {**base, "OSINT_COOKIE_SECURE": true_value}
                    ),
                    [],
                )
                self.assertIn(
                    "OSINT_ALLOW_LEGACY_AGENT_TOKEN must be false in production",
                    production_security_configuration_errors(
                        {
                            **base,
                            "OSINT_COOKIE_SECURE": "true",
                            "OSINT_ALLOW_LEGACY_AGENT_TOKEN": true_value,
                        }
                    ),
                )
        for false_value in ("0", "false", "NO", " off "):
            with self.subTest(false_value=false_value):
                errors = production_security_configuration_errors(
                    {
                        **base,
                        "OSINT_REQUIRE_AUTH": false_value,
                        "OSINT_COOKIE_SECURE": false_value,
                        "OSINT_ALLOW_LEGACY_AGENT_TOKEN": false_value,
                    }
                )
                self.assertIn("OSINT_REQUIRE_AUTH must not be false in production", errors)
                self.assertIn("OSINT_COOKIE_SECURE must be true in production", errors)
                self.assertNotIn(
                    "OSINT_ALLOW_LEGACY_AGENT_TOKEN must be false in production", errors
                )

    def test_production_security_diagnostics_never_include_token_values(self):
        admin_secret = "admin-secret-that-must-not-leak"
        read_secret = "read-secret-that-must-not-leak"
        errors = production_security_configuration_errors(
            {
                "APP_ENV": "production",
                "ADMIN_API_TOKEN": admin_secret,
                "READ_API_TOKEN": read_secret,
                "OSINT_REQUIRE_AUTH": "false",
                "OSINT_COOKIE_SECURE": "false",
                "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "true",
            }
        )

        diagnostic = " ".join(errors)
        self.assertNotIn(admin_secret, diagnostic)
        self.assertNotIn(read_secret, diagnostic)

    def test_run_refuses_invalid_production_security_before_starting_services(self):
        env = {
            "APP_ENV": "production",
            "ADMIN_API_TOKEN": "admin",
            "READ_API_TOKEN": "read",
            "OSINT_REQUIRE_AUTH": "false",
            "OSINT_COOKIE_SECURE": "false",
            "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "true",
        }
        with (
            patch.dict("os.environ", env, clear=True),
            patch("app.main.job_queue.ensure_running") as ensure_running,
            patch("app.main.ThreadingHTTPServer") as server_class,
            self.assertRaises(SystemExit) as raised,
        ):
            run()

        ensure_running.assert_not_called()
        server_class.assert_not_called()
        message = str(raised.exception)
        self.assertIn("OSINT_REQUIRE_AUTH", message)
        self.assertIn("OSINT_COOKIE_SECURE", message)
        self.assertIn("OSINT_ALLOW_LEGACY_AGENT_TOKEN", message)
        self.assertNotIn("admin", message)
        self.assertNotIn("read", message)

    def test_run_refuses_each_missing_management_token_before_starting_services(self):
        base = {
            "APP_ENV": "production",
            "ADMIN_API_TOKEN": "admin",
            "READ_API_TOKEN": "read",
            "OSINT_COOKIE_SECURE": "true",
        }
        for missing_token in ("ADMIN_API_TOKEN", "READ_API_TOKEN"):
            with (
                self.subTest(missing_token=missing_token),
                patch.dict("os.environ", {**base, missing_token: ""}, clear=True),
                patch("app.main.job_queue.ensure_running") as ensure_running,
                patch("app.main.ThreadingHTTPServer") as server_class,
                self.assertRaises(SystemExit) as raised,
            ):
                run()

            ensure_running.assert_not_called()
            server_class.assert_not_called()
            self.assertIn(missing_token, str(raised.exception))

    def test_run_starts_secure_production_without_global_agent_token(self):
        env = {
            "APP_ENV": " PrOd ",
            "ADMIN_API_TOKEN": "admin",
            "READ_API_TOKEN": "read",
            "OSINT_COOKIE_SECURE": " On ",
            "OSINT_ALLOW_LEGACY_AGENT_TOKEN": " off ",
        }
        with (
            patch.dict("os.environ", env, clear=True),
            patch("app.main.job_queue.ensure_running") as ensure_running,
            patch("app.main.ThreadingHTTPServer") as server_class,
        ):
            run()

        ensure_running.assert_called_once()
        server_class.assert_called_once()
        server_class.return_value.serve_forever.assert_called_once_with()

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
                status, body, _response_headers = self.server.request(
                    "POST",
                    "/api/investigations/release-stale",
                    payload={"stale_after_seconds": 1800},
                    headers=headers,
                )
                self.assertEqual(status, 403)
                self.assertEqual(
                    json_payload(body),
                    {"detail": "browser mutation protection failed"},
                )

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
            for token in ("read-secret", "admin-secret"):
                with self.subTest(token=token):
                    status, _body, _headers = self.server.request(
                        "GET",
                        "/api/agents",
                        headers=[("Authorization", f"Bearer {token}")],
                    )
                    self.assertEqual(status, 200)

            status, _body, _headers = self.server.request(
                "GET", "/api/agents", headers=[("Authorization", "Bearer wrong")]
            )
            self.assertEqual(status, 401)

        with patch("app.main.store.release_stale_claims", return_value=[]):
            status, _body, _headers = self.server.request(
                "POST",
                "/api/investigations/release-stale",
                payload={},
                headers=[("Authorization", "Bearer admin-secret")],
            )
        self.assertEqual(status, 200)

        for token in ("read-secret", "agent-secret"):
            with self.subTest(management_token=token):
                status, body, _headers = self.server.request(
                    "POST",
                    "/api/investigations/release-stale",
                    payload={},
                    headers=[("Authorization", f"Bearer {token}")],
                )
                self.assertEqual(status, 403)
                self.assertEqual(
                    json_payload(body),
                    {"detail": "forbidden management request"},
                )

        for token in (None, "wrong"):
            with self.subTest(invalid_management_token=token):
                headers = [] if token is None else [("Authorization", f"Bearer {token}")]
                status, body, _headers = self.server.request(
                    "POST",
                    "/api/investigations/release-stale",
                    payload={},
                    headers=headers,
                )
                self.assertEqual(status, 401)
                self.assertEqual(
                    json_payload(body),
                    {"detail": "unauthorized management request"},
                )

        agent_fallback_env = {
            **PRODUCTION_ENV,
            "ADMIN_API_TOKEN": "",
            "READ_API_TOKEN": "",
        }
        with patch("app.main.store.list_agents", return_value=[]):
            status, _body, _headers = self.server.request(
                "GET",
                "/api/agents",
                headers=[("Authorization", "Bearer agent-secret")],
                env=agent_fallback_env,
            )
        self.assertEqual(status, 200)

    def test_duplicate_authorization_headers_fail_closed_for_every_auth_scope(self):
        cases = (
            ("GET", "/api/agents", _NO_PAYLOAD, "read-secret"),
            ("POST", "/api/investigations/release-stale", {}, "admin-secret"),
            ("POST", "/api/agent/facts", {}, "agent-secret"),
        )
        with (
            patch("app.main.store.list_agents", return_value=[]),
            patch("app.main.store.release_stale_claims", return_value=[]),
        ):
            for method, path, payload, valid_token in cases:
                for values in (
                    (f"Bearer {valid_token}", "Bearer wrong"),
                    ("Bearer wrong", f"Bearer {valid_token}"),
                ):
                    with self.subTest(path=path, values=values):
                        status, body, _headers = self.server.request(
                            method,
                            path,
                            payload=payload,
                            headers=[("Authorization", value) for value in values],
                        )
                        self.assertEqual(status, 401)
                        if path == "/api/investigations/release-stale":
                            self.assertEqual(
                                json_payload(body),
                                {"detail": "unauthorized management request"},
                            )

    def test_known_management_bearers_are_forbidden_and_legacy_agent_token_defaults_off(self):
        with patch("app.main.store.list_agents", return_value=[]):
            status, _body, _headers = self.server.request(
                "GET",
                "/api/agents",
                headers=[("Authorization", "Bearer agent-secret")],
            )
        self.assertEqual(status, 403)

        for token in ("admin-secret", "read-secret"):
            with self.subTest(agent_route_token=token):
                status, _body, _headers = self.server.request(
                    "POST",
                    "/api/agent/facts",
                    payload={},
                    headers=[("Authorization", f"Bearer {token}")],
                )
                self.assertEqual(status, 403)

        for token in (None, "wrong"):
            with self.subTest(invalid_agent_route_token=token):
                headers = [] if token is None else [("Authorization", f"Bearer {token}")]
                status, _body, _headers = self.server.request(
                    "POST", "/api/agent/facts", payload={}, headers=headers
                )
                self.assertEqual(status, 401)

        status, body, _headers = self.server.request(
            "POST",
            "/api/agent/facts",
            payload={},
            headers=[("Authorization", "Bearer agent-secret")],
        )
        self.assertEqual(status, 401)
        self.assertEqual(json_payload(body), {"detail": "unauthorized agent request"})

    def test_login_rejects_non_object_json_with_safe_json_error(self):
        for supplied in ([], "scalar-value", None):
            with self.subTest(supplied=supplied):
                status, body, headers = self.server.request(
                    "POST", "/api/auth/login", payload=supplied
                )
                self.assertEqual(status, 400)
                payload = json_payload(body)
                self.assertEqual(payload, {"detail": "json body must be an object"})
                self.assertNotIn("admin-secret", json.dumps(payload))
                self.assertNotIn("scalar-value", json.dumps(payload))
                assert_security_headers(self, headers)

    def test_request_body_framing_errors_are_structured_and_non_reflective(self):
        malformed_cases = (
            ([('Content-Length', '-1')], b"", True, 400, "invalid content length"),
            ([('Content-Length', 'abc')], b"", False, 400, "invalid content length"),
            (
                [('Content-Length', '2'), ('Content-Length', '2')],
                b"{}",
                False,
                400,
                "invalid content length",
            ),
            (
                [('Content-Length', '1')],
                b"\xff",
                False,
                400,
                "request body is not valid utf-8",
            ),
            (
                [('Content-Length', '20')],
                b"private-body-value",
                True,
                400,
                "incomplete request body",
            ),
        )
        for headers, body, shutdown_write, expected_status, expected_detail in malformed_cases:
            with self.subTest(headers=headers):
                status, response_body, response_headers = self.server.request_bytes(
                    "POST",
                    "/api/auth/login",
                    body=body,
                    headers=headers,
                    shutdown_write=shutdown_write,
                )
                self.assertEqual(status, expected_status)
                self.assertEqual(json_payload(response_body), {"detail": expected_detail})
                self.assertNotIn("private-body-value", response_body.decode("utf-8"))
                assert_security_headers(self, response_headers)

        oversized_env = {**PRODUCTION_ENV, "MAX_REQUEST_BODY_BYTES": "4"}
        status, response_body, response_headers = self.server.request_bytes(
            "POST",
            "/api/auth/login",
            headers=[("Content-Length", "5")],
            env=oversized_env,
        )
        self.assertEqual(status, 413)
        self.assertEqual(json_payload(response_body), {"detail": "request body too large"})
        assert_security_headers(self, response_headers)

    def test_request_body_timeout_returns_408_and_restores_socket_timeout(self):
        with ApiTestServer(ObservedTimeoutApiHandler) as timeout_server:
            with patch(
                "app.main.REQUEST_BODY_READ_TIMEOUT_SECONDS",
                0.05,
                create=True,
            ):
                status, body, headers = timeout_server.request_bytes(
                    "POST",
                    "/api/auth/login",
                    headers=[("Content-Length", "2")],
                )

            self.assertEqual(status, 408)
            self.assertEqual(json_payload(body), {"detail": "request body read timed out"})
            assert_security_headers(self, headers)
            self.assertEqual(
                timeout_server.server.observed_connection_timeout,
                ObservedTimeoutApiHandler.INITIAL_TIMEOUT_SECONDS,
            )

    def test_extreme_decimal_content_length_fails_closed_before_body_read(self):
        status, body, headers = self.server.request_bytes(
            "POST",
            "/api/auth/login",
            headers=[("Content-Length", "9" * 5000)],
        )
        self.assertEqual(status, 400)
        self.assertEqual(json_payload(body), {"detail": "invalid content length"})
        assert_security_headers(self, headers)

    def test_missing_content_length_remains_an_empty_body_for_compatibility(self):
        status, body, headers = self.server.request_bytes(
            "POST", "/api/auth/login"
        )
        self.assertEqual(status, 401)
        self.assertEqual(json_payload(body), {"detail": "invalid credentials"})
        assert_security_headers(self, headers)

    def test_transfer_encoded_request_body_is_rejected_as_invalid_framing(self):
        status, body, headers = self.server.request_bytes(
            "POST",
            "/api/auth/login",
            headers=[("Transfer-Encoding", "chunked")],
        )
        self.assertEqual(status, 400)
        self.assertEqual(json_payload(body), {"detail": "invalid request framing"})
        assert_security_headers(self, headers)

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

    def test_credentialed_cors_requires_one_exact_configured_origin(self):
        exact_origin = [("Origin", "https://hcs.test")]
        status, _body, headers = self.server.request(
            "GET", "/api/auth/session", headers=exact_origin
        )
        self.assertEqual(status, 200)
        self.assertEqual(header_value(headers, "Access-Control-Allow-Origin"), "https://hcs.test")
        self.assertEqual(header_value(headers, "Access-Control-Allow-Credentials"), "true")

        for request_headers in (
            [("Origin", "https://wrong.test")],
            [("Origin", "https://hcs.test"), ("Origin", "https://hcs.test")],
        ):
            with self.subTest(request_headers=request_headers):
                status, _body, headers = self.server.request(
                    "GET", "/api/auth/session", headers=request_headers
                )
                self.assertEqual(status, 200)
                self.assertIsNone(header_value(headers, "Access-Control-Allow-Origin"))
                self.assertIsNone(header_value(headers, "Access-Control-Allow-Credentials"))

    def test_cors_wildcard_never_enables_credentials_or_cookie_mutation(self):
        wildcard_env = {**PRODUCTION_ENV, "CORS_ALLOWED_ORIGINS": "*"}
        origin = [("Origin", "https://arbitrary.test")]
        status, _body, headers = self.server.request(
            "OPTIONS", "/api/investigations", headers=origin, env=wildcard_env
        )
        self.assertEqual(status, 200)
        self.assertIsNone(header_value(headers, "Access-Control-Allow-Origin"))
        self.assertIsNone(header_value(headers, "Access-Control-Allow-Credentials"))

        cookie, csrf_token, _headers = self.login(wildcard_env)
        status, _body, headers = self.server.request(
            "POST",
            "/api/investigations/release-stale",
            payload={},
            headers=[
                ("Cookie", cookie),
                ("Origin", "https://arbitrary.test"),
                ("X-CSRF-Token", csrf_token),
            ],
            env=wildcard_env,
        )
        self.assertEqual(status, 403)
        self.assertIsNone(header_value(headers, "Access-Control-Allow-Origin"))
        self.assertIsNone(header_value(headers, "Access-Control-Allow-Credentials"))


if __name__ == "__main__":
    unittest.main()
