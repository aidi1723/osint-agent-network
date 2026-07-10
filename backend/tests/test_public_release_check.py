import json
import subprocess
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from scripts.public_release_check import (
    ReleaseFinding,
    evaluate_public_release,
    scan_public_text,
    tracked_files,
)


GPL_TEXT = "\n".join(
    [
        "GNU GENERAL PUBLIC LICENSE",
        "Version 3, 29 June 2007",
        "Everyone is permitted to copy and distribute verbatim copies",
        "END OF TERMS AND CONDITIONS",
    ]
)


def write_release_fixture(root: Path, *, backend_license: str = "GPL-3.0-only") -> None:
    (root / "LICENSE").write_text(GPL_TEXT, encoding="utf-8")
    (root / "frontend").mkdir()
    (root / "frontend" / "package.json").write_text(
        json.dumps({"license": "GPL-3.0-only"}), encoding="utf-8"
    )
    (root / "backend").mkdir()
    (root / "backend" / "pyproject.toml").write_text(
        f'[project]\nname = "fixture"\nlicense = "{backend_license}"\n',
        encoding="utf-8",
    )


class PublicReleaseCheckTests(unittest.TestCase):
    def test_release_finding_is_immutable(self):
        finding = ReleaseFinding("PUBLIC_PATH", "notes.txt", 3, "Personal home path")

        with self.assertRaises(FrozenInstanceError):
            finding.line = 4

    def test_blocks_backend_license_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root, backend_license="MIT")

            result = evaluate_public_release(root)

        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"]["backend_license"], "fail")
        self.assertEqual(result["backend_license"], "MIT")
        self.assertTrue(
            any(
                finding["rule_id"] == "LICENSE_BACKEND"
                and finding["path"] == "backend/pyproject.toml"
                for finding in result["findings"]
            )
        )

    def test_blocks_personal_home_paths_with_stable_locations(self):
        text = "first\ncheckout=/home/alice/project\ncache=/Users/alice/project\n"

        findings = scan_public_text(Path("notes/setup.txt"), text)

        self.assertEqual(
            [(item.rule_id, item.path, item.line) for item in findings],
            [
                ("PUBLIC_PERSONAL_PATH", "notes/setup.txt", 2),
                ("PUBLIC_PERSONAL_PATH", "notes/setup.txt", 3),
            ],
        )

    def test_blocks_all_private_lan_ranges_but_allows_documentation_network(self):
        text = "\n".join(
            [
                "docs=192.0.2.10",
                "first=10.23.4.5",
                "second=172.16.4.5",
                "third=172.31.255.254",
                "fourth=192.168.1.20",
            ]
        )

        findings = scan_public_text("deployment.txt", text)

        self.assertEqual(
            [(item.rule_id, item.line) for item in findings],
            [
                ("PUBLIC_PRIVATE_NETWORK", 2),
                ("PUBLIC_PRIVATE_NETWORK", 3),
                ("PUBLIC_PRIVATE_NETWORK", 4),
                ("PUBLIC_PRIVATE_NETWORK", 5),
            ],
        )

    def test_blocks_real_credential_assignments_without_reflecting_values(self):
        secret = "sk-live-" + "do-not-reflect-987654"
        text = "\n".join(["ADMIN_API_TOKEN", f"ADMIN_API_TOKEN={secret}"])

        findings = scan_public_text("config.env.example", text)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "PUBLIC_CREDENTIAL_VALUE")
        self.assertEqual(findings[0].line, 2)
        self.assertNotIn(secret, findings[0].summary)
        self.assertNotIn(secret, json.dumps(findings[0].to_dict()))

    def test_allows_generic_paths_variable_names_and_placeholder_credentials(self):
        text = "\n".join(
            [
                "/opt/osint-agent-network",
                "/var/backups/osint-agent-network",
                "/path/to/osint-agent-network",
                "/home/aidi/...",
                "ADMIN_API_TOKEN",
                "ADMIN_API_TOKEN=<your-token>",
                "READ_API_TOKEN=${READ_API_TOKEN}",
                "PASSWORD=placeholder",
            ]
        )

        self.assertEqual(scan_public_text("docs/example.md", text), [])

    def test_ellipsized_home_placeholder_cannot_hide_a_continued_concrete_path(self):
        findings = scan_public_text("notes.txt", "/home/alice/.../private/config\n")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "PUBLIC_PERSONAL_PATH")

    def test_self_scan_allowlist_uses_exact_content_and_still_scans_adjacent_lines(self):
        marker = "checkout=/home/" + "alice/project"
        allowed_line = next(
            line for line in Path(__file__).read_text(encoding="utf-8").splitlines() if marker in line
        )
        adjacent = "checkout=/home/" + "mallory/private"

        findings = scan_public_text(
            "backend/tests/test_public_release_check.py",
            f"moved\n{allowed_line}\n{adjacent}\n",
        )

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_PERSONAL_PATH", 3)],
        )

    def test_allows_code_constants_boolean_flags_and_generated_or_documented_values(self):
        text = "\n".join(
            [
                "KNOWN_OUTPUT_TOKENS = {'entities'}",
                "OSINT_ALLOW_LEGACY_AGENT_TOKEN=false",
                "ADMIN_API_TOKEN=$(openssl rand -hex 32)",
                "UPKUAJING_AUTHORIZATION=Bearer <your-token>",
                "UPKUAJING_AUTHORIZATION=Bearer your_token_here",
            ]
        )

        self.assertEqual(scan_public_text("docs/configuration.md", text), [])

    def test_runtime_artifact_policy_uses_tracked_path_not_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            (root / "data").mkdir()
            (root / "data" / "state.sqlite").write_bytes(b"\xff\xfeSQLite binary")
            (root / "notes.txt").write_text("state.sqlite is ignored at runtime\n", encoding="utf-8")

            result = evaluate_public_release(root)

        runtime = [item for item in result["findings"] if item["rule_id"] == "PUBLIC_RUNTIME_ARTIFACT"]
        self.assertEqual(runtime, [{
            "rule_id": "PUBLIC_RUNTIME_ARTIFACT",
            "path": "data/state.sqlite",
            "line": 0,
            "summary": "Tracked runtime artifact is not allowed in a public release.",
        }])

    def test_runtime_directory_marker_is_not_treated_as_an_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            (root / "reports").mkdir()
            (root / "reports" / ".gitkeep").write_text("", encoding="utf-8")

            result = evaluate_public_release(root)

        self.assertTrue(result["ready"])

    def test_binary_files_are_skipped_for_text_scanning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            binary = root / "opaque.bin"
            binary.write_bytes(b"\xff\xfe/home/alice/project")

            result = evaluate_public_release(root)

        self.assertTrue(result["ready"])

    def test_tracked_files_fallback_is_sorted_and_excludes_generated_dirs_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "z.txt").write_text("z", encoding="utf-8")
            (root / "a.txt").write_text("a", encoding="utf-8")
            (root / "frontend" / "node_modules").mkdir(parents=True)
            (root / "frontend" / "node_modules" / "ignored.js").write_text("x", encoding="utf-8")
            outside = root.parent / f"{root.name}-outside.txt"
            outside.write_text("outside", encoding="utf-8")
            try:
                (root / "escape.txt").symlink_to(outside)

                paths = tracked_files(root)
            finally:
                outside.unlink(missing_ok=True)

        self.assertEqual(paths, [Path("a.txt"), Path("z.txt")])

    def test_tracked_files_uses_git_index_and_handles_non_utf8_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "tracked.txt").write_text("tracked", encoding="utf-8")
            (root / "binary.dat").write_bytes(b"\xff\xfe")
            (root / "untracked.txt").write_text("untracked", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "tracked.txt", "binary.dat"],
                check=True,
            )

            paths = tracked_files(root)

        self.assertEqual(paths, [Path("binary.dat"), Path("tracked.txt")])

    def test_tracked_files_falls_back_when_git_command_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            (root / "visible.txt").write_text("visible", encoding="utf-8")

            paths = tracked_files(root)

        self.assertEqual(paths, [Path("visible.txt")])

    def test_allows_consistent_gplv3_license_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)

            result = evaluate_public_release(root)

        self.assertTrue(result["ready"])
        self.assertEqual(result["checks"]["license_file"], "ok")
        self.assertEqual(result["checks"]["package_license"], "ok")
        self.assertEqual(result["checks"]["backend_license"], "ok")
        self.assertEqual(result["findings"], [])

    def test_rejects_invalid_backend_toml_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            (root / "backend" / "pyproject.toml").write_text("[project\n", encoding="utf-8")

            result = evaluate_public_release(root)

        self.assertFalse(result["ready"])
        self.assertEqual(result["backend_license"], "")
        self.assertEqual(result["checks"]["backend_license"], "fail")


if __name__ == "__main__":
    unittest.main()
