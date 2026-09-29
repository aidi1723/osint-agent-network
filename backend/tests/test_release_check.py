import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app.core.release_check import release_findings


class ReleaseCheckTests(TestCase):
    def test_flags_public_ports_gpl_metadata_and_tracked_investigation_data(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_tree(
                root,
                compose='ports:\n      - "8088:8088"\n',
                license_name="GPL-3.0-only",
                dockerignore="node_modules/\n",
                gitignore=".env\n",
            )
            findings = release_findings(
                root,
                tracked=["data/osint.sqlite", "data/screenshots/lead.png", ".env"],
            )

        self.assertIn("docker compose publishes a port on all interfaces", findings)
        self.assertIn("frontend package license conflicts with the proprietary EULA", findings)
        self.assertIn("docker build context can include investigation data", findings)
        self.assertTrue(any(item.startswith("tracked sensitive path: data/osint.sqlite") for item in findings))
        self.assertTrue(any(item.startswith("tracked sensitive path: .env") for item in findings))

    def test_accepts_a_loopback_proprietary_tree_without_tracked_data(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_tree(
                root,
                compose='ports:\n      - "127.0.0.1:8088:8088"\n      - "127.0.0.1:3008:3008"\n',
                license_name="UNLICENSED",
                dockerignore="data/\n",
                gitignore=".env\ndata/*.sqlite\ndata/jobs/\ndata/screenshots/\ndata/snapshots/\ndata/samples/\n",
            )
            findings = release_findings(root, tracked=["README.md", "backend/app/main.py", ".env.example"])

        self.assertEqual(findings, [])

    def _write_tree(self, root: Path, compose: str, license_name: str, dockerignore: str, gitignore: str) -> None:
        (root / "docker-compose.yml").write_text(compose, encoding="utf-8")
        (root / ".dockerignore").write_text(dockerignore, encoding="utf-8")
        (root / ".gitignore").write_text(gitignore, encoding="utf-8")
        (root / "EULA.md").write_text(
            "The software is licensed, not sold. Users may not redistribute the software.\n",
            encoding="utf-8",
        )
        frontend = root / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(
            json.dumps({"name": "frontend", "license": license_name}),
            encoding="utf-8",
        )
