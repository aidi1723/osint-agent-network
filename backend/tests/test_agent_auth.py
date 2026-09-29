from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from unittest.mock import patch

from app.main import (
    agent_request_authorized,
    bind_authorization_error,
    login_with_admin_token,
    read_request_authorized,
    request_authorized,
    requires_write_authorization,
    reset_browser_sessions,
    session_status_payload,
)


class AgentAuthTests(unittest.TestCase):
    def test_allows_agent_request_when_token_is_not_configured(self):
        self.assertTrue(agent_request_authorized({}, expected_token=""))

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

    def test_tool_health_requires_token_when_configured(self):
        self.assertFalse(read_request_authorized("/api/tools/health", {}, expected_token="read-secret"))
        self.assertTrue(
            read_request_authorized(
                "/api/tools/health",
                {"Authorization": "Bearer read-secret"},
                expected_token="read-secret",
            )
        )

    def test_session_is_open_when_no_token_is_configured(self):
        with patch.dict("os.environ", {}, clear=True):
            payload = session_status_payload({})
        self.assertFalse(payload["required"])
        self.assertFalse(payload["authenticated"])

    def test_login_creates_a_session_for_the_admin_token(self):
        with TemporaryDirectory() as tmpdir:
            with patch.dict(
                "os.environ",
                {
                    "ADMIN_API_TOKEN": "admin-secret",
                    "OSINT_SESSION_DB_PATH": str(Path(tmpdir) / "sessions.sqlite"),
                },
                clear=True,
            ):
                reset_browser_sessions()
                self.assertEqual(session_status_payload({})["required"], True)
                self.assertIsNone(login_with_admin_token("wrong"))
                body, cookie = login_with_admin_token("admin-secret")
                self.assertTrue(body["authenticated"])
                self.assertTrue(body["csrf_token"])
                self.assertIn("osint_session=", cookie)
                session = session_status_payload({"Cookie": cookie.split(";", 1)[0]})
            self.assertTrue(session["authenticated"])
            self.assertEqual(session["csrf_token"], body["csrf_token"])

    def test_non_loopback_bind_requires_a_token(self):
        self.assertEqual(bind_authorization_error("127.0.0.1", "", ""), "")
        self.assertEqual(bind_authorization_error("0.0.0.0", "agent-secret", ""), "")
        self.assertIn("AGENT_API_TOKEN", bind_authorization_error("0.0.0.0", "", ""))


if __name__ == "__main__":
    unittest.main()
