import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class StartScriptTests(unittest.TestCase):
    def test_start_script_waits_for_api_and_web_health(self):
        script = (ROOT_DIR / "scripts" / "start.sh").read_text(encoding="utf-8")

        self.assertIn("wait_for_http", script)
        self.assertIn("/api/health", script)
        self.assertIn("API_LOG", script)
        self.assertIn("WEB_LOG", script)

    def test_start_script_uses_stable_python3_by_default(self):
        script = (ROOT_DIR / "scripts" / "start.sh").read_text(encoding="utf-8")

        self.assertIn("find_python_bin", script)
        self.assertIn("python3.14 python3.13 python3.12 python3.11 python3", script)
        self.assertIn("Python 3.11 or newer is required", script)
        self.assertIn("sys.version_info >= (3, 11)", script)


if __name__ == "__main__":
    unittest.main()
