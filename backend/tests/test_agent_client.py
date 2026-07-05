import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from app import agent_client


class AgentClientCliTests(unittest.TestCase):
    def test_register_posts_agent_payload_and_prints_json(self):
        calls = []

        def fake_post(base_url, path, payload, token):
            calls.append((base_url, path, payload, token))
            return {"id": "agent-1", "agent_name": payload["agent_name"]}

        output = _run_cli(
            [
                "--base-url",
                "http://hub.local",
                "--token",
                "secret",
                "register",
                "--agent-name",
                "codex-desktop",
                "--agent-type",
                "codex",
                "--capability",
                "domain",
                "--capability",
                "amass",
            ],
            fake_post,
        )

        self.assertEqual(calls[0][0], "http://hub.local")
        self.assertEqual(calls[0][1], "/api/agents/register")
        self.assertEqual(calls[0][2]["agent_name"], "codex-desktop")
        self.assertEqual(calls[0][2]["agent_type"], "codex")
        self.assertEqual(calls[0][2]["capabilities"], ["domain", "amass"])
        self.assertEqual(calls[0][3], "secret")
        self.assertEqual(output["id"], "agent-1")

    def test_claim_and_write_commands_use_protocol_paths(self):
        calls = []

        def fake_post(base_url, path, payload, token):
            calls.append((path, payload))
            return {"ok": True, "path": path}

        _run_cli(["claim", "--agent-id", "agent-1", "--capability", "domain"], fake_post)
        _run_cli(
            [
                "event",
                "--task-id",
                "task-1",
                "--agent-id",
                "agent-1",
                "--level",
                "info",
                "--message",
                "开始执行",
                "--metadata",
                '{"tool":"amass"}',
            ],
            fake_post,
        )
        _run_cli(
            [
                "entity",
                "--task-id",
                "task-1",
                "--type",
                "email",
                "--value",
                "admin@example.com",
                "--source-tool",
                "theharvester",
                "--confidence",
                "0.82",
            ],
            fake_post,
        )
        _run_cli(
            [
                "evidence",
                "--task-id",
                "task-1",
                "--entity-value",
                "admin@example.com",
                "--kind",
                "search_result",
                "--source-tool",
                "theharvester",
                "--snippet",
                "公开搜索结果命中",
            ],
            fake_post,
        )
        _run_cli(
            [
                "relationship",
                "--task-id",
                "task-1",
                "--from",
                "example.com",
                "--to",
                "admin@example.com",
                "--type",
                "domain_has_email",
                "--confidence",
                "0.74",
            ],
            fake_post,
        )

        self.assertEqual(calls[0][0], "/api/agent/tasks/claim")
        self.assertEqual(calls[0][1]["agent_id"], "agent-1")
        self.assertEqual(calls[0][1]["capabilities"], ["domain"])
        self.assertEqual(calls[1][0], "/api/agent/events")
        self.assertEqual(calls[1][1]["metadata"], {"tool": "amass"})
        self.assertEqual(calls[2][0], "/api/agent/entities")
        self.assertEqual(calls[2][1]["entities"][0]["value"], "admin@example.com")
        self.assertEqual(calls[3][0], "/api/agent/evidence")
        self.assertEqual(calls[4][0], "/api/agent/relationships")
        self.assertEqual(calls[4][1]["relationship_type"], "domain_has_email")

    def test_complete_reads_report_file_and_uses_env_token(self):
        calls = []

        def fake_post(base_url, path, payload, token):
            calls.append((path, payload, token))
            return {"status": payload["status"]}

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as report:
            report.write("# 报告\n\n完成。")
            report_path = report.name

        previous_token = os.environ.get("AGENT_API_TOKEN")
        os.environ["AGENT_API_TOKEN"] = "env-secret"
        try:
            output = _run_cli(
                [
                    "complete",
                    "--task-id",
                    "task-1",
                    "--agent-id",
                    "agent-1",
                    "--status",
                    "COMPLETED",
                    "--summary",
                    "发现 1 条线索",
                    "--report-file",
                    report_path,
                    "--confidence",
                    "0.91",
                ],
                fake_post,
            )
        finally:
            os.unlink(report_path)
            if previous_token is None:
                os.environ.pop("AGENT_API_TOKEN", None)
            else:
                os.environ["AGENT_API_TOKEN"] = previous_token

        self.assertEqual(calls[0][0], "/api/agent/tasks/task-1/complete")
        self.assertEqual(calls[0][1]["report_markdown"], "# 报告\n\n完成。")
        self.assertEqual(calls[0][1]["confidence"], 0.91)
        self.assertEqual(calls[0][2], "env-secret")
        self.assertEqual(output["status"], "COMPLETED")

    def test_core_v2_write_commands_use_protocol_paths(self):
        calls = []

        def fake_post(base_url, path, payload, token):
            calls.append((path, payload))
            return {"ok": True, "path": path}

        _run_cli(
            [
                "evidence-record",
                "--task-id",
                "task-1",
                "--source-url",
                "https://www.srrautopartsonline.com/en/",
                "--source-type",
                "official_website",
                "--source-tool",
                "official_web",
                "--snippet",
                "SRR contact page lists xs@csituo.com.",
                "--credibility",
                "0.82",
            ],
            fake_post,
        )
        _run_cli(
            [
                "fact",
                "--task-id",
                "task-1",
                "--statement",
                "SRR uses xs@csituo.com as a public contact email.",
                "--subject",
                "SRR Genuine Parts",
                "--predicate",
                "uses_contact_email",
                "--object",
                "xs@csituo.com",
                "--status",
                "CONFIRMED",
                "--confidence",
                "0.82",
                "--admiralty-code",
                "A-2",
                "--evidence-id",
                "ev-1",
            ],
            fake_post,
        )
        _run_cli(
            [
                "hypothesis",
                "--task-id",
                "task-1",
                "--id",
                "h1",
                "--statement",
                "SRR is an active export brand network.",
            ],
            fake_post,
        )
        _run_cli(
            [
                "score-hypotheses",
                "--task-id",
                "task-1",
                "--evidence-json",
                '[{"id":"ev-export","summary":"MIMS exhibitor page shows SRR export contact.","kinds":["company_news_report"],"supports":["h1"],"contradicts":["h2"],"source_reliability":"B","credibility":0.72,"keywords":["export"]}]',
            ],
            fake_post,
        )

        self.assertEqual(calls[0][0], "/api/agent/evidence-records")
        self.assertEqual(calls[0][1]["source_type"], "official_website")
        self.assertEqual(calls[1][0], "/api/agent/facts")
        self.assertEqual(calls[1][1]["evidence_ids"], ["ev-1"])
        self.assertEqual(calls[2][0], "/api/agent/hypotheses")
        self.assertEqual(calls[2][1]["hypothesis_id"], "h1")
        self.assertEqual(calls[3][0], "/api/agent/hypotheses/score")
        self.assertEqual(calls[3][1]["evidence_items"][0]["supports"], ["h1"])

    def test_run_tool_dry_run_outputs_normalized_artifact_without_posting(self):
        def fake_post(base_url, path, payload, token):
            raise AssertionError("dry-run must not post to the hub")

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as artifact:
            json.dump(
                {
                    "GitHub": {
                        "status": "CLAIMED",
                        "url_main": "https://github.com/admin",
                    }
                },
                artifact,
            )
            artifact_path = artifact.name

        try:
            output = _run_cli(
                [
                    "run-tool",
                    "--tool",
                    "sherlock",
                    "--target-type",
                    "username",
                    "--target",
                    "admin",
                    "--input-file",
                    artifact_path,
                    "--dry-run",
                ],
                fake_post,
            )
        finally:
            os.unlink(artifact_path)

        self.assertEqual(output["tool"], "sherlock")
        self.assertEqual(output["counts"]["entities"], 2)
        self.assertEqual(output["entities"][1]["value"], "https://github.com/admin")

    def test_run_tool_posts_entities_evidence_and_relationships_to_protocol(self):
        calls = []

        def fake_post(base_url, path, payload, token):
            calls.append((path, payload))
            return {"ok": True, "path": path}

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as artifact:
            json.dump(
                {
                    "emails": ["admin@example.com"],
                    "hosts": ["vpn.example.com"],
                    "urls": [],
                },
                artifact,
            )
            artifact_path = artifact.name

        try:
            output = _run_cli(
                [
                    "run-tool",
                    "--tool",
                    "theharvester",
                    "--target-type",
                    "domain",
                    "--target",
                    "example.com",
                    "--task-id",
                    "task-1",
                    "--agent-id",
                    "agent-1",
                    "--input-file",
                    artifact_path,
                ],
                fake_post,
            )
        finally:
            os.unlink(artifact_path)

        paths = [path for path, _payload in calls]
        self.assertEqual(paths[0], "/api/agent/events")
        self.assertIn("/api/agent/entities", paths)
        self.assertIn("/api/agent/evidence", paths)
        self.assertIn("/api/agent/relationships", paths)
        self.assertEqual(output["posted"]["entities"], 4)
        self.assertEqual(output["posted"]["evidence"], 2)
        self.assertEqual(output["posted"]["relationships"], 3)

    def test_run_tool_supports_amass_jsonl_dry_run(self):
        def fake_post(base_url, path, payload, token):
            raise AssertionError("dry-run must not post to the hub")

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False) as artifact:
            artifact.write('{"name":"vpn.example.com","addresses":[{"ip":"203.0.113.10"}]}\n')
            artifact_path = artifact.name

        try:
            output = _run_cli(
                [
                    "run-tool",
                    "--tool",
                    "amass",
                    "--target-type",
                    "domain",
                    "--target",
                    "example.com",
                    "--input-file",
                    artifact_path,
                    "--dry-run",
                ],
                fake_post,
            )
        finally:
            os.unlink(artifact_path)

        self.assertEqual(output["tool"], "amass")
        self.assertEqual(output["counts"]["entities"], 3)
        self.assertEqual(output["counts"]["relationships"], 2)

    def test_run_tool_supports_remaining_adapters_dry_run(self):
        def fake_post(base_url, path, payload, token):
            raise AssertionError("dry-run must not post to the hub")

        fixtures = {
            "ghunt": (
                "email",
                "target@gmail.com",
                {"exists": True, "profile": {"name": "Alice Example"}},
                ".json",
            ),
            "phoneinfoga": (
                "phone",
                "+639171234567",
                {"valid": True, "country": "Philippines"},
                ".json",
            ),
            "spiderfoot": (
                "domain",
                "example.com",
                [{"type": "EMAILADDR", "data": "admin@example.com"}],
                ".json",
            ),
            "reconng": (
                "domain",
                "example.com",
                {"hosts": [{"host": "vpn.example.com"}]},
                ".json",
            ),
            "company_news": (
                "company",
                "Example Inc",
                {"articles": [{"title": "Example Inc opens new project", "url": "https://news.example.com/a"}]},
                ".json",
            ),
        }

        for tool, (target_type, target, payload, suffix) in fixtures.items():
            with self.subTest(tool=tool):
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=suffix, delete=False) as artifact:
                    json.dump(payload, artifact)
                    artifact_path = artifact.name
                try:
                    output = _run_cli(
                        [
                            "run-tool",
                            "--tool",
                            tool,
                            "--target-type",
                            target_type,
                            "--target",
                            target,
                            "--input-file",
                            artifact_path,
                            "--dry-run",
                        ],
                        fake_post,
                    )
                finally:
                    os.unlink(artifact_path)

                self.assertEqual(output["tool"], tool)
                self.assertGreaterEqual(output["counts"]["entities"], 1)

    def test_risk_report_command_reads_investigation_artifact(self):
        def fake_post(base_url, path, payload, token):
            raise AssertionError("risk-report must not post to the hub")

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = Path(tmpdir) / "investigation.json"
            artifact.write_text(
                json.dumps(
                    {
                        "entities": [
                            {
                                "type": "profile_url",
                                "value": "https://github.com/admin",
                                "source_tool": "maigret",
                                "confidence": 0.4,
                            },
                            {
                                "type": "bio_snippet",
                                "value": "crypto betting operator",
                                "source_tool": "profile_parser",
                                "confidence": 0.25,
                            },
                        ],
                        "evidence": [
                            {
                                "entity_value": "https://github.com/admin",
                                "evidence_kind": "social_profile_exists",
                                "source_tool": "maigret",
                            }
                        ],
                        "relationships": [],
                    }
                ),
                encoding="utf-8",
            )

            output = _run_cli(
                [
                    "risk-report",
                    "--input-file",
                    str(artifact),
                    "--declared-region",
                    "Hong Kong",
                ],
                fake_post,
            )

        self.assertIn("overall_risk_score", output)
        self.assertIn("category_scores", output)
        self.assertTrue(output["review_required"])

    def test_plan_tools_command_outputs_gateway_routes(self):
        def fake_post(base_url, path, payload, token):
            raise AssertionError("plan-tools must not post to the hub")

        output = _run_cli(
            [
                "plan-tools",
                "--target-type",
                "email",
                "--target",
                "Buyer@Example.COM",
                "--strategy",
                "standard",
                "--env",
                "SPIDERFOOT_BASE_URL=http://127.0.0.1:5001",
                "--env",
                "RECONNG_COMMAND=/opt/recon-ng/recon-ng",
            ],
            fake_post,
        )

        self.assertEqual(output["target_type"], "email")
        self.assertEqual(output["target_value"], "buyer@example.com")
        self.assertEqual([route["tool_name"] for route in output["routes"]], ["socialscan", "spiderfoot", "reconng"])
        self.assertEqual(output["skipped_routes"][0]["tool_name"], "ghunt")

    def test_plan_tools_loads_project_dotenv_without_printing_secrets(self):
        def fake_post(base_url, path, payload, token):
            raise AssertionError("plan-tools must not post to the hub")

        previous_cwd = os.getcwd()
        saved_env = {key: os.environ.get(key) for key in ("SPIDERFOOT_BASE_URL", "RECONNG_COMMAND")}
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, ".env").write_text(
                "\n".join(
                    [
                        "SPIDERFOOT_BASE_URL=http://127.0.0.1:5001",
                        "RECONNG_COMMAND=/opt/recon-ng/recon-ng",
                    ]
                ),
                encoding="utf-8",
            )
            os.chdir(tmpdir)
            os.environ.pop("SPIDERFOOT_BASE_URL", None)
            os.environ.pop("RECONNG_COMMAND", None)
            try:
                output = _run_cli(
                    [
                        "plan-tools",
                        "--target-type",
                        "domain",
                        "--target",
                        "example.com",
                        "--strategy",
                        "deep",
                    ],
                    fake_post,
                )
            finally:
                os.chdir(previous_cwd)
                for key, value in saved_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertIn("spiderfoot", [route["tool_name"] for route in output["routes"]])
        self.assertIn("reconng", [route["tool_name"] for route in output["routes"]])
        self.assertNotIn("/opt/recon-ng/recon-ng", json.dumps(output))


def _run_cli(argv, fake_post):
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = agent_client.run(argv, post_json_fn=fake_post)
    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    return payload


if __name__ == "__main__":
    unittest.main()
