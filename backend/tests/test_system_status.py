import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.main import system_status_payload
from app.services.store import SQLiteStore


class SystemStatusTests(unittest.TestCase):
    def test_sqlite_store_records_schema_versions(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            versions = store.schema_versions()

        version_ids = {item["version"] for item in versions}

        self.assertIn("20260522_core_v3", version_ids)
        self.assertIn("20260522_stability_pack", version_ids)

    def test_system_status_payload_reports_database_tasks_and_scripts(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scripts = root / "scripts"
            scripts.mkdir()
            for name in ("backup.sh", "healthcheck.sh"):
                path = scripts / name
                path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
                path.chmod(0o755)
            store = SQLiteStore(str(root / "data" / "osint.sqlite"))
            store.create_investigation("Stable", "company", "Stable LLC", "quick")

            payload = system_status_payload(store_obj=store, root_dir=str(root))

        self.assertEqual(payload["service"], "osint-agent-network")
        self.assertEqual(payload["database"]["status"], "ok")
        self.assertGreaterEqual(payload["database"]["schema_version_count"], 2)
        self.assertEqual(payload["investigations"]["total"], 1)
        self.assertTrue(payload["scripts"]["backup"]["present"])
        self.assertTrue(payload["scripts"]["healthcheck"]["present"])
        self.assertGreaterEqual(payload["tools"]["registered"], 1)
        self.assertIn("health", payload["tools"])
        self.assertGreaterEqual(payload["tools"]["health"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
