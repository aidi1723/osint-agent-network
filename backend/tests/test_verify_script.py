import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class VerifyScriptTests(unittest.TestCase):
    def test_backend_unittest_discovery_prefers_uv_project_with_system_python_fallback(self):
        script = (ROOT_DIR / "scripts" / "verify.sh").read_text(encoding="utf-8")

        self.assertIn("command -v uv", script)
        self.assertIn("uv run --project backend python3 -m unittest discover -s backend/tests", script)
        self.assertIn("backend/.venv/bin/python -m unittest discover -s backend/tests", script)
        self.assertIn("python3.14 python3.13 python3.12 python3.11 python3", script)
        self.assertIn("sys.version_info >= (3, 11)", script)
        self.assertIn("Python 3.11 or newer is required", script)


if __name__ == "__main__":
    unittest.main()
