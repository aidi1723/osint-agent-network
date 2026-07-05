import json
import tempfile
import unittest
from pathlib import Path

from scripts.public_release_check import evaluate_public_release


class PublicReleaseCheckTests(unittest.TestCase):
    def test_blocks_when_repository_still_uses_proprietary_license(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "LICENSE").write_text("Proprietary Commercial License\n", encoding="utf-8")
            package_dir = root / "frontend"
            package_dir.mkdir()
            (package_dir / "package.json").write_text(
                json.dumps({"license": "UNLICENSED"}),
                encoding="utf-8",
            )

            result = evaluate_public_release(root)

        self.assertFalse(result["ready"])
        self.assertIn("license_file", result["checks"])
        self.assertEqual(result["checks"]["license_file"], "fail")
        self.assertIn("package_license", result["checks"])
        self.assertEqual(result["checks"]["package_license"], "fail")

    def test_allows_gplv3_license_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "LICENSE").write_text(
                "\n".join(
                    [
                        "GNU GENERAL PUBLIC LICENSE",
                        "Version 3, 29 June 2007",
                        "Everyone is permitted to copy and distribute verbatim copies",
                        "END OF TERMS AND CONDITIONS",
                    ]
                ),
                encoding="utf-8",
            )
            package_dir = root / "frontend"
            package_dir.mkdir()
            (package_dir / "package.json").write_text(
                json.dumps({"license": "GPL-3.0-only"}),
                encoding="utf-8",
            )

            result = evaluate_public_release(root)

        self.assertTrue(result["ready"])
        self.assertEqual(result["checks"]["license_file"], "ok")
        self.assertEqual(result["checks"]["package_license"], "ok")

    def test_rejects_non_gpl_open_source_license_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "LICENSE").write_text("MIT License\n", encoding="utf-8")
            package_dir = root / "frontend"
            package_dir.mkdir()
            (package_dir / "package.json").write_text(
                json.dumps({"license": "MIT"}),
                encoding="utf-8",
            )

            result = evaluate_public_release(root)

        self.assertFalse(result["ready"])
        self.assertEqual(result["detected_license"], "")
        self.assertEqual(result["checks"]["license_file"], "fail")
        self.assertEqual(result["checks"]["package_license"], "fail")


if __name__ == "__main__":
    unittest.main()
