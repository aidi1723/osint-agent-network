import unittest

from app.main import (
    agent_request_authorized,
    missing_required_auth_tokens,
    read_request_authorized,
    request_authorized,
    requires_write_authorization,
)


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


if __name__ == "__main__":
    unittest.main()
