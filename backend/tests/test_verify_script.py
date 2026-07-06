import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class VerifyScriptTests(unittest.TestCase):
    def test_backend_unittest_discovery_prefers_uv_project_with_system_python_fallback(self):
        script = (ROOT_DIR / "scripts" / "verify.sh").read_text(encoding="utf-8")

        self.assertIn("command -v uv", script)
        self.assertIn("uv run --project backend python3 -m unittest discover -s backend/tests", script)
        self.assertIn('echo "backend/.venv/bin/python"', script)
        self.assertIn('PYTHONPATH=backend "$PYTHON_BIN" -m unittest discover -s backend/tests', script)
        self.assertIn("python3.14 python3.13 python3.12 python3.11 python3", script)
        self.assertIn("sys.version_info >= (3, 11)", script)
        self.assertIn("Python 3.11 or newer is required", script)
        self.assertIn('"$PYTHON_BIN" scripts/check_agents.py', script)
        self.assertIn('"$PYTHON_BIN" scripts/regression_smoke.py', script)
        self.assertIn('"$PYTHON_BIN" scripts/runtime_inventory.py', script)
        self.assertIn('"$PYTHON_BIN" scripts/public_release_check.py', script)
        self.assertNotIn("python3 scripts/check_agents.py", script)


if __name__ == "__main__":
    unittest.main()
