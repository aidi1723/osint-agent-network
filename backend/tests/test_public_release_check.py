import json
import os
import subprocess
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.public_release_check import (
    ReleaseFinding,
    evaluate_public_release,
    scan_public_text,
    tracked_files,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GPL_TEXT = (REPOSITORY_ROOT / "LICENSE").read_text(encoding="utf-8")


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
        text = (
            "first\ncheckout=/home/" + "alice/project\ncache=/Users/" + "alice/project\n"
        )

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
                "first=10." + "23.4.5",
                "second=172." + "16.4.5",
                "third=172." + "31.255.254",
                "fourth=192." + "168.1.20",
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

    def test_blocks_case_insensitive_shell_dotenv_and_toml_credentials(self):
        secret = "actual-" + "credential-123"
        text = "\n".join(
            [
                "export " + "password" + " = " + secret,
                "Db_PassWord" + "='" + secret + "'",
                "client_secret" + ' = "' + secret + '"',
                "user=public " + "api_token" + "=" + secret + " mode=test",
            ]
        )

        findings = scan_public_text("config/settings.toml", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(1, 5)],
        )
        self.assertNotIn(secret, json.dumps([finding.to_dict() for finding in findings]))

    def test_blocks_yaml_and_json_credential_values_with_quoted_keys(self):
        secret = "yaml-" + "credential-456"
        text = "\n".join(
            [
                "password" + ": " + secret,
                '"api_token"' + ': "' + secret + '",',
                "'Client_Secret'" + ": '" + secret + "'",
            ]
        )

        findings = scan_public_text("deploy/config.yaml", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", 1), ("PUBLIC_CREDENTIAL_VALUE", 2), ("PUBLIC_CREDENTIAL_VALUE", 3)],
        )

    def test_blocks_url_userinfo_private_keys_and_bearer_tokens(self):
        secret = "network-" + "credential-789"
        private_key = "-----BEGIN " + "PRIVATE KEY-----"
        text = "\n".join(
            [
                "endpoint=https://alice:" + secret + "@example.com/api",
                private_key,
                "Bearer " + secret,
                "Authorization: Bearer " + secret,
            ]
        )

        findings = scan_public_text("deploy/secrets.txt", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [
                ("PUBLIC_URL_CREDENTIAL", 1),
                ("PUBLIC_PRIVATE_KEY", 2),
                ("PUBLIC_CREDENTIAL_VALUE", 3),
                ("PUBLIC_CREDENTIAL_VALUE", 4),
            ],
        )
        self.assertNotIn(secret, json.dumps([finding.to_dict() for finding in findings]))

    def test_allows_username_only_url_authority_without_password(self):
        findings = scan_public_text(
            "fixtures/page.html",
            '<a href="https://support@example.com/help">Support</a>',
        )

        self.assertEqual(findings, [])

    def test_blocks_multiline_yaml_credential_scalars(self):
        secret = "multiline-" + "credential-321"
        text = "\n".join(
            [
                "password: |",
                "  " + secret,
                "description: public",
                "api_token: >-",
                "  " + secret,
            ]
        )

        findings = scan_public_text("deploy/secrets.yaml", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", 1), ("PUBLIC_CREDENTIAL_VALUE", 4)],
        )

    def test_placeholder_and_dynamic_values_must_match_the_entire_value(self):
        lines = [
            "api_token=<token>",
            "api_token=<your-token>",
            "api_token=$TOKEN",
            "api_token=${TOKEN}",
            "api_token=placeholder",
            "api_token=$(openssl rand -hex 32)",
            "api_token=$(uuidgen)",
            "api_token=<token> actual",
            "api_token=placeholder actual",
            "api_token=audit-canary-live",
            "api_token=$(echo secret)",
        ]

        findings = scan_public_text("deploy/placeholders.env", "\n".join(lines))

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", line) for line in range(8, 12)],
        )

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
        findings = scan_public_text(
            "notes.txt", "/home/" + "alice/.../private/config\n"
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "PUBLIC_PERSONAL_PATH")

    def test_personal_paths_are_case_insensitive_unicode_and_match_at_path_end(self):
        text = "\n".join(
            [
                "first=/HOME/" + "Alice",
                "second=/users/" + "张伟/项目",
                "third=/Users/" + "Élodie",
                "service=/home/osint/project",
                "placeholder=/home/aidi/...",
            ]
        )

        findings = scan_public_text("notes/paths.txt", text)

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_PERSONAL_PATH", 1), ("PUBLIC_PERSONAL_PATH", 2), ("PUBLIC_PERSONAL_PATH", 3)],
        )

    def test_self_scan_allowlist_uses_exact_content_and_still_scans_adjacent_lines(self):
        marker = "Path: /Users/" + "example/.config"
        source = Path(__file__).with_name("test_report_export.py")
        allowed_line = next(
            line for line in source.read_text(encoding="utf-8").splitlines() if marker in line
        )
        adjacent = "checkout=/home/" + "mallory/private"

        findings = scan_public_text(
            "backend/tests/test_report_export.py",
            f"moved\n{allowed_line}\n{adjacent}\n",
        )

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_PERSONAL_PATH", 3)],
        )

    def test_credential_allowlist_does_not_hide_adjacent_unmarked_assignments(self):
        marker = "VITE_ADMIN_API_" + "TOKEN=<same-value"
        source = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "superpowers"
            / "plans"
            / "2026-07-10-security-hardening.md"
        )
        allowed_line = next(
            line for line in source.read_text(encoding="utf-8").splitlines() if marker in line
        )
        adjacent = "password" + '="new-real-value"'

        findings = scan_public_text(
            "docs/superpowers/plans/2026-07-10-security-hardening.md",
            f"{allowed_line}\n{adjacent}\n",
        )

        self.assertEqual(
            [(finding.rule_id, finding.line) for finding in findings],
            [("PUBLIC_CREDENTIAL_VALUE", 2)],
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

    def test_blocks_database_auxiliaries_logs_backups_and_runtime_archives_by_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            artifact_paths = [
                "data/state.DB-wal",
                "data/state.sqlite3-SHM",
                "data/state.sqlite-journal",
                "logs/service.LOG",
                "config/settings.bak",
                "backups/runtime.tar.gz",
            ]
            for path in artifact_paths:
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("runtime", encoding="utf-8")
            source_archive = root / "fixtures" / "source.zip"
            source_archive.parent.mkdir()
            source_archive.write_text("legitimate source fixture", encoding="utf-8")

            result = evaluate_public_release(root)

        runtime_paths = [
            finding["path"]
            for finding in result["findings"]
            if finding["rule_id"] == "PUBLIC_RUNTIME_ARTIFACT"
        ]
        self.assertEqual(runtime_paths, sorted(artifact_paths))
        self.assertNotIn("fixtures/source.zip", runtime_paths)

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
            (root / "z space.txt").write_text("space", encoding="utf-8")
            (root / "a\nline.txt").write_text("newline", encoding="utf-8")
            (root / "untracked.txt").write_text("untracked", encoding="utf-8")
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "add",
                    "tracked.txt",
                    "binary.dat",
                    "z space.txt",
                    "a\nline.txt",
                ],
                check=True,
            )

            paths = tracked_files(root)

        self.assertEqual(
            paths,
            [Path("a\nline.txt"), Path("binary.dat"), Path("tracked.txt"), Path("z space.txt")],
        )

    def test_nested_directory_without_own_git_metadata_uses_filesystem_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            subprocess.run(["git", "init", "-q", str(parent)], check=True)
            root = parent / "fixture"
            root.mkdir()
            (root / "visible.txt").write_text("visible", encoding="utf-8")
            subprocess.run(["git", "-C", str(parent), "add", "fixture/visible.txt"], check=True)

            with patch(
                "scripts.public_release_check.subprocess.run",
                side_effect=AssertionError("nested root must not query parent Git repository"),
            ):
                try:
                    paths = tracked_files(root)
                except AssertionError as exc:
                    self.fail(str(exc))

        self.assertEqual(paths, [Path("visible.txt")])

    @unittest.skipUnless(os.name == "posix", "invalid filename bytes require POSIX paths")
    def test_invalid_utf8_git_filename_is_policy_checked_and_safely_displayed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            (root / ".git").mkdir()
            raw_name = b"runtime-\xff\n.sqlite"
            completed = SimpleNamespace(returncode=0, stdout=raw_name + b"\0")

            with (
                patch("scripts.public_release_check.subprocess.run", return_value=completed),
                patch("scripts.public_release_check._safe_regular_file", return_value=True),
            ):
                result = evaluate_public_release(root)

        runtime = [
            finding
            for finding in result["findings"]
            if finding["rule_id"] == "PUBLIC_RUNTIME_ARTIFACT"
        ]
        self.assertEqual(
            [finding["path"] for finding in runtime], ["runtime-\\xff\\n.sqlite"]
        )
        self.assertNotIn("\udcff", json.dumps(result))

    def test_tracked_symlinks_are_scanned_without_following_outside_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "personal-link").symlink_to("/home/" + "alice/private")
            (root / "runtime.sqlite").symlink_to("/outside/runtime.db")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)

            result = evaluate_public_release(root)

        findings = {(finding["rule_id"], finding["path"]) for finding in result["findings"]}
        self.assertIn(("PUBLIC_PERSONAL_PATH", "personal-link"), findings)
        self.assertIn(("PUBLIC_RUNTIME_ARTIFACT", "runtime.sqlite"), findings)

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

    def test_rejects_four_marker_license_spoof(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
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

            result = evaluate_public_release(root)

        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"]["license_file"], "fail")
        self.assertTrue(any(item["rule_id"] == "LICENSE_FILE" for item in result["findings"]))

    def test_accepts_canonical_gplv3_with_crlf_and_trailing_newline_normalization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_release_fixture(root)
            normalized = GPL_TEXT.rstrip("\r\n").replace("\n", "\r\n") + "\r\n\r\n"
            (root / "LICENSE").write_bytes(normalized.encode("utf-8"))

            result = evaluate_public_release(root)

        self.assertTrue(result["ready"])

    def test_malformed_license_metadata_roots_return_stable_findings(self):
        cases = [
            ("[]", '[project]\nlicense = "GPL-3.0-only"\n', "LICENSE_FRONTEND"),
            ('"GPL-3.0-only"', '[project]\nlicense = "GPL-3.0-only"\n', "LICENSE_FRONTEND"),
            ('{"license":"GPL-3.0-only"}', 'project = "bad"\n', "LICENSE_BACKEND"),
            ('{"license":"GPL-3.0-only"}', 'name = "missing-project"\n', "LICENSE_BACKEND"),
        ]
        for package_json, backend_toml, expected_rule in cases:
            with self.subTest(expected_rule=expected_rule, backend_toml=backend_toml):
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    write_release_fixture(root)
                    (root / "frontend" / "package.json").write_text(package_json, encoding="utf-8")
                    (root / "backend" / "pyproject.toml").write_text(backend_toml, encoding="utf-8")

                    try:
                        result = evaluate_public_release(root)
                    except (AttributeError, TypeError) as exc:
                        self.fail(f"malformed metadata raised {type(exc).__name__}")

                self.assertFalse(result["ready"])
                self.assertTrue(
                    any(item["rule_id"] == expected_rule for item in result["findings"])
                )

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
