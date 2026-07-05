import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class StopScriptTests(unittest.TestCase):
    def test_stop_script_removes_stale_pid_files(self):
        script = (ROOT_DIR / "scripts" / "stop.sh").read_text(encoding="utf-8")

        self.assertIn('rm -f "$pid_file"', script)


if __name__ == "__main__":
    unittest.main()
