import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def _env_example_keys() -> set[str]:
    keys = set()
    for line in (ROOT_DIR / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _value = line.split("=", 1)
        keys.add(key)
    return keys


class EnvironmentTemplateTests(unittest.TestCase):
    def test_env_example_lists_frontend_and_readiness_variables_without_browser_secret(self):
        keys = _env_example_keys()

        self.assertIn("VITE_API_BASE_URL", keys)
        self.assertNotIn("VITE_ADMIN_API_TOKEN", keys)
        self.assertIn("VITE_DEV_API_PROXY_TARGET", keys)
        self.assertIn("API_URL", keys)
        self.assertIn("WEB_URL", keys)
        self.assertIn("READ_API_TOKEN", keys)
        self.assertIn("CORS_ALLOWED_ORIGINS", keys)
        self.assertIn("MAX_REQUEST_BODY_BYTES", keys)

    def test_env_example_lists_backend_tool_and_operations_variables(self):
        keys = _env_example_keys()

        expected_keys = {
            "OSINT_STORE_BACKEND",
            "OSINT_AGENT_HUB_URL",
            "WORKER_MAX_WALL_SECONDS",
            "BACKUP_ROOT",
            "BACKUP_KEEP_LAST",
            "UPKUAJING_BASE_URL",
            "UPKUAJING_AUTHORIZATION",
            "UPKUAJING_TIMEOUT_SECONDS",
            "MAIGRET_COMMAND",
            "SOCIALSCAN_COMMAND",
            "PROFILE_PARSER_COMMAND",
            "OPENAI_BASE_URL",
            "OPENAI_API_KEY",
            "OPENAI_MODEL",
            "OSINT_SAFE_HTTP_FAKE_IP_APPROVALS_FILE",
        }
        self.assertTrue(expected_keys.issubset(keys), expected_keys - keys)

if __name__ == "__main__":
    unittest.main()
