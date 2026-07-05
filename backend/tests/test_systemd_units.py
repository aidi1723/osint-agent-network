import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class SystemdUnitTests(unittest.TestCase):
    def test_web_unit_does_not_duplicate_preview_host_port_args(self):
        unit = (ROOT_DIR / "deploy" / "systemd" / "osint-agent-network-web.service").read_text(encoding="utf-8")

        self.assertIn("ExecStart=/usr/bin/npm run preview", unit)
        self.assertNotIn("npm run preview -- --host", unit)


if __name__ == "__main__":
    unittest.main()
