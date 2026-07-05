import tempfile
import unittest
from pathlib import Path

from scripts.runtime_inventory import build_runtime_inventory


class RuntimeInventoryTests(unittest.TestCase):
    def test_build_runtime_inventory_counts_artifacts_without_reading_payloads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data" / "jobs" / "task-1" / "job-1").mkdir(parents=True)
            (root / "data" / "jobs" / "task-1" / "job-1" / "result.json").write_text("{}", encoding="utf-8")
            (root / "data" / "snapshots").mkdir(parents=True)
            (root / "data" / "snapshots" / "case.json").write_text("{}", encoding="utf-8")
            (root / "reports").mkdir()
            (root / "reports" / "report.md").write_text("# Report", encoding="utf-8")

            inventory = build_runtime_inventory(root)

        self.assertEqual(inventory["data/jobs"]["files"], 1)
        self.assertEqual(inventory["data/jobs"]["directories"], 3)
        self.assertEqual(inventory["data/snapshots"]["files"], 1)
        self.assertEqual(inventory["reports"]["files"], 1)


if __name__ == "__main__":
    unittest.main()
