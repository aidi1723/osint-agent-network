import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.core.planner import PlannedJob
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
    ToolCommand,
    ToolRunResult,
    write_json_artifact,
)
from app.services.store import MemoryStore, SQLiteStore
from app.services.worker import run_investigation_jobs
from app.tools.official_site_extractor import OfficialSiteExtractorAdapter


class FakeAdapter:
    name = "fake_social"

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int):
        artifact = workdir / "fake.json"
        write_json_artifact(artifact, {"target": target_value})
        return ToolRunResult(
            command=ToolCommand(
                args=["fake-social", target_value],
                cwd=workdir,
                expected_artifact=artifact,
                timeout_seconds=timeout_seconds,
            ),
            returncode=0,
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def parse_artifact(self, artifact_path: Path, target_value: str):
        return ParsedToolOutput(
            tool=self.name,
            target_type="username",
            target_value=target_value,
            entities=[
                NormalizedEntity("username", target_value, self.name, 0.72),
                NormalizedEntity("profile_url", f"https://github.com/{target_value}", self.name, 0.72),
                NormalizedEntity("bio_snippet", "crypto betting operator", self.name, 0.25),
            ],
            evidence=[
                NormalizedEvidence(
                    f"https://github.com/{target_value}",
                    "social_profile_exists",
                    self.name,
                    "Fake public profile exists",
                )
            ],
            relationships=[
                NormalizedRelationship(
                    target_value,
                    f"https://github.com/{target_value}",
                    "username_has_social_profile",
                    0.72,
                )
            ],
        )


class LowConfidenceAdapter(FakeAdapter):
    def parse_artifact(self, artifact_path: Path, target_value: str):
        return ParsedToolOutput(
            tool=self.name,
            target_type="username",
            target_value=target_value,
            entities=[
                NormalizedEntity("username", target_value, self.name, 0.4),
                NormalizedEntity("profile_url", f"https://github.com/{target_value}", self.name, 0.4),
            ],
            evidence=[
                NormalizedEvidence(
                    f"https://github.com/{target_value}",
                    "weak_social_profile_candidate",
                    self.name,
                    "Weak public profile candidate exists.",
                )
            ],
            relationships=[
                NormalizedRelationship(
                    target_value,
                    f"https://github.com/{target_value}",
                    "username_has_unverified_social_profile",
                    0.4,
                )
            ],
        )


class HeavyToolAdapter:
    name = "ghunt"

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int):
        artifact = workdir / "heavy.json"
        write_json_artifact(artifact, {"target": target_value})
        return ToolRunResult(
            command=ToolCommand(
                args=["fake-heavy", target_value],
                cwd=workdir,
                expected_artifact=artifact,
                timeout_seconds=timeout_seconds,
            ),
            returncode=0,
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def parse_artifact(self, artifact_path: Path, target_value: str):
        return ParsedToolOutput(
            tool=self.name,
            target_type="email",
            target_value=target_value,
            entities=[NormalizedEntity("profile_url", "https://profiles.google.com/buyer", self.name, 0.74)],
            evidence=[
                NormalizedEvidence(
                    "https://profiles.google.com/buyer",
                    "deep_profile_enrichment",
                    self.name,
                    "Heavy enrichment found a possible public profile.",
                )
            ],
            relationships=[
                NormalizedRelationship(
                    target_value,
                    "https://profiles.google.com/buyer",
                    "email_has_google_profile_candidate",
                    0.74,
                )
            ],
        )


class HttpxLiveUrlAdapter:
    name = "httpx"

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int):
        artifact = workdir / "httpx.jsonl"
        write_json_artifact(artifact, [{"url": "https://example-target.test", "input": target_value}])
        return ToolRunResult(
            command=ToolCommand(
                args=["fake-httpx", target_value],
                cwd=workdir,
                expected_artifact=artifact,
                timeout_seconds=timeout_seconds,
            ),
            returncode=0,
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def parse_artifact(self, artifact_path: Path, target_value: str):
        return ParsedToolOutput(
            tool=self.name,
            target_type="domain",
            target_value=target_value,
            entities=[
                NormalizedEntity("domain", target_value, self.name, 0.55),
                NormalizedEntity("url", "https://example-target.test", self.name, 0.62),
            ],
            evidence=[
                NormalizedEvidence(
                    "https://example-target.test",
                    "http_probe",
                    self.name,
                    "httpx confirmed live URL https://example-target.test",
                )
            ],
            relationships=[
                NormalizedRelationship(
                    target_value,
                    "https://example-target.test",
                    "host_serves_url",
                    0.62,
                )
            ],
        )


class OfficialSiteSearchUrlAdapter:
    name = "official_site_search"

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int):
        artifact = workdir / "official_site_search.json"
        write_json_artifact(artifact, {"target": target_value})
        return ToolRunResult(
            command=ToolCommand(
                args=["fake-official-site-search", target_value],
                cwd=workdir,
                expected_artifact=artifact,
                timeout_seconds=timeout_seconds,
            ),
            returncode=0,
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def parse_artifact(self, artifact_path: Path, target_value: str):
        return ParsedToolOutput(
            tool=self.name,
            target_type="company",
            target_value=target_value,
            entities=[
                NormalizedEntity("company", target_value, self.name, 0.55),
                NormalizedEntity("url", "https://www.example-target.test/about", self.name, 0.62),
            ],
            evidence=[
                NormalizedEvidence(
                    "https://www.example-target.test/about",
                    "official_site_search_result",
                    self.name,
                    "Search result suggests an official website candidate.",
                )
            ],
            relationships=[
                NormalizedRelationship(
                    target_value,
                    "https://www.example-target.test/about",
                    "company_has_official_site_candidate",
                    0.62,
                )
            ],
        )


class LargeOutputAdapter(FakeAdapter):
    name = "large_output"

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int):
        artifact = workdir / "large.json"
        write_json_artifact(artifact, {"target": target_value})
        return ToolRunResult(
            command=ToolCommand(
                args=["large-output", target_value],
                cwd=workdir,
                expected_artifact=artifact,
                timeout_seconds=timeout_seconds,
            ),
            returncode=0,
            stdout_excerpt="x" * 20000,
            stderr_excerpt="y" * 20000,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str):
        return ParsedToolOutput(
            tool=self.name,
            target_type="domain",
            target_value=target_value,
            entities=[NormalizedEntity("domain", target_value, self.name, 0.55)],
            evidence=[],
            relationships=[],
        )


class OfficialSiteOutputAdapter:
    name = "official_site_extractor"

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int):
        artifact = workdir / "official.html"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("<html></html>", encoding="utf-8")
        return ToolRunResult(
            command=ToolCommand(
                args=["official-site-extractor", target_value],
                cwd=workdir,
                expected_artifact=artifact,
                timeout_seconds=timeout_seconds,
            ),
            returncode=0,
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def parse_artifact(self, artifact_path: Path, target_value: str):
        return ParsedToolOutput(
            tool=self.name,
            target_type="url",
            target_value=target_value,
            entities=[
                NormalizedEntity("url", target_value, self.name, 0.72),
                NormalizedEntity("organization", "SAMPLE AUTO PARTS COMPANY LIMITED", self.name, 0.76),
                NormalizedEntity("phone", "+85282061801", self.name, 0.78),
                NormalizedEntity("business_scope", "auto parts", self.name, 0.74),
            ],
            evidence=[
                NormalizedEvidence(
                    "SAMPLE AUTO PARTS COMPANY LIMITED",
                    "official_site_identity",
                    self.name,
                    "Official site names organization.",
                ),
                NormalizedEvidence(
                    "+85282061801",
                    "official_site_contact",
                    self.name,
                    "Official site lists phone.",
                ),
                NormalizedEvidence(
                    "auto parts",
                    "official_site_business_scope",
                    self.name,
                    "Official site describes auto parts.",
                ),
            ],
            relationships=[
                NormalizedRelationship(target_value, "SAMPLE AUTO PARTS COMPANY LIMITED", "official_site_names_organization", 0.76),
                NormalizedRelationship(target_value, "auto parts", "official_site_describes_business_scope", 0.74),
            ],
        )


class MinimalCompleteAdapter:
    def __init__(self, name: str):
        self.name = name

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int):
        artifact = workdir / f"{self.name}.json"
        write_json_artifact(artifact, {"target": target_value})
        return ToolRunResult(
            command=ToolCommand(
                args=[f"fake-{self.name}", target_value],
                cwd=workdir,
                expected_artifact=artifact,
                timeout_seconds=timeout_seconds,
            ),
            returncode=0,
            stdout_excerpt="ok",
            stderr_excerpt="",
        )

    def parse_artifact(self, artifact_path: Path, target_value: str):
        target_type = "url" if target_value.startswith(("http://", "https://")) else "domain"
        return ParsedToolOutput(
            tool=self.name,
            target_type=target_type,
            target_value=target_value,
            entities=[NormalizedEntity(target_type, target_value, self.name, 0.52)],
            evidence=[],
            relationships=[],
        )


class MissingCommandAdapter:
    name = "missing_tool"

    def build_command(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int):
        return ToolCommand(
            args=["definitely-missing-osint-command", target_value],
            cwd=workdir,
            expected_artifact=workdir / "missing.json",
            timeout_seconds=timeout_seconds,
        )

    def parse_artifact(self, artifact_path: Path, target_value: str):
        raise AssertionError("blocked commands should not be parsed")


class WorkerTests(unittest.TestCase):
    def test_private_credentialed_official_site_failure_is_not_reflected_in_worker_events(self):
        target = "https://user:" + "supersecret@127.0.0.1/private-token"
        store = MemoryStore()
        investigation = store.create_investigation("unsafe url", "domain", "example.com", "quick")
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "official_site_extractor",
                    "target_type": "url",
                    "target_value": target,
                    "status": "QUEUED",
                }
            ],
        )

        with TemporaryDirectory() as tmpdir:
            run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: OfficialSiteExtractorAdapter(),
            )
            artifacts = [path.read_bytes() for path in Path(tmpdir).rglob("*") if path.is_file()]

        events = repr(store.get_investigation(investigation.id)["events"])
        for sensitive in ("user", "supersecret", "private-token"):
            self.assertNotIn(sensitive, events)
            self.assertTrue(all(sensitive.encode() not in artifact for artifact in artifacts))

    def test_worker_runs_agent_orchestration_jobs_locally(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="企业背调",
            seed_type="company",
            seed_value="Sample Hospitality LLC",
            strategy_name="deep",
        )

        summary = run_investigation_jobs(store, investigation.id, max_jobs=10)
        detail = store.get_investigation(investigation.id)

        self.assertEqual(summary["blocked"], 0)
        self.assertGreater(summary["role_completed"], 0)
        self.assertTrue(
            any(job["status"] == "COMPLETED" for job in detail["jobs"] if job["agent_role"] != "tool_agent")
        )
        completed_job = next(job for job in detail["jobs"] if job["agent_role"] != "tool_agent" and job["status"] == "COMPLETED")
        self.assertGreaterEqual(completed_job["attempt_count"], 1)
        self.assertEqual(completed_job["last_error"], "")

    def test_no_external_claim_needed_after_local_role_agent_execution(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="企业背调",
            seed_type="company",
            seed_value="Sample Hospitality LLC",
            strategy_name="deep",
        )
        run_investigation_jobs(store, investigation.id, max_jobs=10)
        agent = store.register_agent(
            agent_name="enterprise-agent",
            agent_type="enterprise_intel_agent",
            capabilities=["enterprise_intel_agent"],
            role_tier="reader",
        )

        claimed = store.claim_job(agent.id, ["enterprise_intel_agent"])
        detail = store.get_investigation(investigation.id)

        if claimed is not None:
            self.assertIn("gap:", claimed["depends_on"])
        self.assertTrue(any(job["status"] == "COMPLETED" for job in detail["jobs"] if job["agent_role"] == "enterprise_intel_agent"))

    def test_memory_worker_executes_job_writes_results_and_queues_followup(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="admin 风险复核",
            seed_type="username",
            seed_value="admin",
            strategy_name="standard",
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "fake_social",
                    "target_type": "username",
                    "target_value": "admin",
                    "depth": 0,
                    "status": "QUEUED",
                }
            ],
        )
        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: FakeAdapter(),
            )

        detail = store.get_investigation(investigation.id)
        job_statuses = {job["tool_name"]: job["status"] for job in detail["jobs"]}

        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["queued_followups"], 1)
        self.assertEqual(job_statuses["fake_social"], "COMPLETED")
        self.assertEqual(job_statuses["profile_parser"], "QUEUED")
        profile_job = next(job for job in detail["jobs"] if job["tool_name"] == "profile_parser")
        self.assertEqual(profile_job["depends_on"], "inferred_from:profile_url:https://github.com/admin")
        self.assertIn(("profile_url", "https://github.com/admin"), {(item["type"], item["value"]) for item in detail["entities"]})
        self.assertTrue(any("递进推演" in event["message"] for event in detail["events"]))
        self.assertTrue(detail["risk_report"]["review_required"])
        self.assertEqual(detail["status"], "NEEDS_REVIEW")

    def test_url_site_collection_jobs_run_before_domain_expansion_jobs(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Official site followup priority",
            seed_type="domain",
            seed_value="example-target.test",
            strategy_name="standard",
        )
        first_job = store.list_jobs(investigation.id)[0]
        def job(overrides: dict, index: int) -> dict:
            return {**first_job, "id": f"{first_job['id']}-{index}", **overrides}

        store.replace_jobs(
            investigation.id,
            [
                job({
                    "tool_name": "httpx",
                    "target_type": "domain",
                    "target_value": "example-target.test",
                    "depth": 0,
                    "status": "COMPLETED",
                }, 0),
                job({
                    "tool_name": "httpx",
                    "target_type": "url",
                    "target_value": "https://example-target.test/",
                    "agent_role": "tool_agent",
                    "depth": 1,
                    "status": "QUEUED",
                }, 1),
                job({
                    "tool_name": "katana",
                    "target_type": "url",
                    "target_value": "https://example-target.test/",
                    "agent_role": "tool_agent",
                    "depth": 1,
                    "status": "QUEUED",
                }, 2),
                job({
                    "tool_name": "official_site_extractor",
                    "target_type": "url",
                    "target_value": "https://example-target.test/",
                    "agent_role": "tool_agent",
                    "depth": 1,
                    "status": "QUEUED",
                }, 3),
                job({
                    "tool_name": "httpx",
                    "target_type": "url",
                    "target_value": "https://second-target.test/",
                    "agent_role": "tool_agent",
                    "depth": 1,
                    "status": "QUEUED",
                }, 4),
                job({
                    "tool_name": "katana",
                    "target_type": "url",
                    "target_value": "https://second-target.test/",
                    "agent_role": "tool_agent",
                    "depth": 1,
                    "status": "QUEUED",
                }, 5),
                job({
                    "tool_name": "official_site_extractor",
                    "target_type": "url",
                    "target_value": "https://second-target.test/",
                    "agent_role": "tool_agent",
                    "depth": 1,
                    "status": "QUEUED",
                }, 6),
                job({
                    "tool_name": "subfinder",
                    "target_type": "domain",
                    "target_value": "example-target.test",
                    "agent_role": "tool_agent",
                    "depth": 1,
                    "status": "QUEUED",
                }, 7),
                job({
                    "tool_name": "httpx",
                    "target_type": "domain",
                    "target_value": "example-target.test",
                    "agent_role": "tool_agent",
                    "depth": 1,
                    "status": "QUEUED",
                }, 8),
            ],
        )

        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=3,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: MinimalCompleteAdapter(name),
            )

        statuses = {
            (job["tool_name"], job["target_type"], job["target_value"]): job["status"]
            for job in store.list_jobs(investigation.id)
        }

        self.assertEqual(result["completed"], 3)
        self.assertEqual(statuses[("httpx", "url", "https://example-target.test/")], "COMPLETED")
        self.assertEqual(statuses[("katana", "url", "https://example-target.test/")], "COMPLETED")
        self.assertEqual(statuses[("official_site_extractor", "url", "https://example-target.test/")], "COMPLETED")
        self.assertEqual(statuses[("httpx", "url", "https://second-target.test/")], "QUEUED")
        self.assertEqual(statuses[("katana", "url", "https://second-target.test/")], "QUEUED")
        self.assertEqual(statuses[("official_site_extractor", "url", "https://second-target.test/")], "QUEUED")
        self.assertEqual(statuses[("httpx", "domain", "example-target.test")], "QUEUED")
        self.assertEqual(statuses[("subfinder", "domain", "example-target.test")], "QUEUED")

    def test_missing_external_tool_marks_investigation_blocked(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="domain environment blocker",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="quick",
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "missing_tool",
                    "target_type": "domain",
                    "target_value": "example.com",
                    "depth": 0,
                    "status": "QUEUED",
                }
            ],
        )
        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: MissingCommandAdapter(),
            )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(result["blocked"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(detail["jobs"][0]["status"], "BLOCKED")
        self.assertEqual(detail["status"], "BLOCKED")
        self.assertEqual(detail["summary"], "工具任务被环境依赖阻断")
        self.assertTrue(any("缺少工具命令" in event["message"] for event in detail["events"]))

    def test_planning_blocked_investigation_stays_blocked_when_run_jobs_is_invoked(self):
        store = MemoryStore()
        with (
            patch("app.core.tool_health.shutil.which", side_effect=lambda command: "/usr/bin/python3" if command == "python3" else None),
            patch("app.core.tool_health.Path.exists", return_value=False),
        ):
            investigation = store.create_investigation(
                name="planning blocked domain",
                seed_type="domain",
                seed_value="example.com",
                strategy_name="standard",
                respect_tool_health=True,
            )

        self.assertEqual(store.list_jobs(investigation.id), [])

        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
            )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(result["started"], 0)
        self.assertEqual(detail["status"], "BLOCKED")
        self.assertEqual(detail["summary"], "工具任务被环境依赖阻断")
        self.assertTrue(detail["metadata"]["initial_skipped_routes"])

    def test_tool_evidence_is_written_to_evidence_ledger(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="tool evidence ledger",
            seed_type="username",
            seed_value="admin",
            strategy_name="standard",
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "fake_social",
                    "target_type": "username",
                    "target_value": "admin",
                    "depth": 0,
                    "status": "QUEUED",
                }
            ],
        )

        with TemporaryDirectory() as tmpdir:
            run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: FakeAdapter(),
            )

        detail = store.get_investigation(investigation.id)
        ledger = detail["evidence_ledger"]

        self.assertTrue(ledger)
        self.assertTrue(any(record["source_tool"] == "fake_social" for record in ledger))
        self.assertTrue(any(record["source_type"] == "social_profile_exists" for record in ledger))
        self.assertTrue(all(record["admiralty_code"] for record in ledger))

    def test_low_confidence_tool_entities_do_not_queue_followups(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="weak profile candidate",
            seed_type="username",
            seed_value="admin",
            strategy_name="standard",
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "fake_social",
                    "target_type": "username",
                    "target_value": "admin",
                    "depth": 0,
                    "status": "QUEUED",
                }
            ],
        )

        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: LowConfidenceAdapter(),
            )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["queued_followups"], 0)
        self.assertNotIn("profile_parser", {job["tool_name"] for job in detail["jobs"]})

    def test_http_probe_url_queues_site_collection_followups_despite_medium_confidence(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="SampleCo domain quick probe",
            seed_type="domain",
            seed_value="example-target.test",
            strategy_name="quick",
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "httpx",
                    "target_type": "domain",
                    "target_value": "example-target.test",
                    "depth": 0,
                    "status": "QUEUED",
                }
            ],
        )

        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: HttpxLiveUrlAdapter(),
            )

        job_keys = {(job["tool_name"], job["target_type"], job["target_value"]) for job in store.list_jobs(investigation.id)}

        self.assertEqual(result["completed"], 1)
        self.assertGreaterEqual(result["queued_followups"], 2)
        self.assertIn(("katana", "url", "https://example-target.test/"), job_keys)
        self.assertIn(("official_site_extractor", "url", "https://example-target.test/"), job_keys)

    def test_official_site_search_url_queues_site_collection_followups(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Sample company official site search",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="standard",
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "official_site_search",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "agent_role": "tool_agent",
                    "depth": 0,
                    "status": "QUEUED",
                }
            ],
        )
        store.investigations[investigation.id].max_jobs = 20

        health_report = {
            "tools": [
                {"name": "httpx", "status": "ready", "reason": "command available"},
                {"name": "katana", "status": "ready", "reason": "command available"},
                {"name": "official_site_extractor", "status": "ready", "reason": "internal adapter"},
                {"name": "profile_parser", "status": "ready", "reason": "internal adapter"},
            ]
        }

        with TemporaryDirectory() as tmpdir, patch("app.core.intel_gateway.build_tool_health_report", return_value=health_report):
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: OfficialSiteSearchUrlAdapter(),
            )

        job_keys = {(job["tool_name"], job["target_type"], job["target_value"]) for job in store.list_jobs(investigation.id)}

        self.assertEqual(result["completed"], 1)
        self.assertGreaterEqual(result["queued_followups"], 2)
        self.assertIn(("katana", "url", "https://www.example-target.test/about"), job_keys)
        self.assertIn(("official_site_extractor", "url", "https://www.example-target.test/about"), job_keys)

    def test_progressive_followups_respect_tool_health(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="SampleCo domain quick probe with health",
            seed_type="domain",
            seed_value="example-target.test",
            strategy_name="quick",
            metadata={"respect_tool_health": True},
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "httpx",
                    "target_type": "domain",
                    "target_value": "example-target.test",
                    "depth": 0,
                    "status": "QUEUED",
                }
            ],
        )
        health_report = {
            "tools": [
                {"name": "httpx", "status": "ready", "reason": "command available"},
                {"name": "katana", "status": "ready", "reason": "command available"},
                {"name": "official_site_extractor", "status": "ready", "reason": "internal adapter"},
                {"name": "subfinder", "status": "ready", "reason": "command available"},
                {"name": "theharvester", "status": "missing_config", "reason": "THEHARVESTER_PATH does not exist"},
            ]
        }

        with TemporaryDirectory() as tmpdir, patch("app.core.intel_gateway.build_tool_health_report", return_value=health_report):
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: HttpxLiveUrlAdapter(),
            )

        detail = store.get_investigation(investigation.id)
        job_keys = {(job["tool_name"], job["target_type"], job["target_value"]) for job in detail["jobs"]}

        self.assertGreaterEqual(result["queued_followups"], 2)
        self.assertNotIn(("theharvester", "domain", "example-target.test"), job_keys)
        self.assertIn(("katana", "url", "https://example-target.test/"), job_keys)

    def test_worker_truncates_large_tool_output_before_writing_events(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="large output event",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="quick",
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "large_output",
                    "target_type": "domain",
                    "target_value": "example.com",
                    "depth": 0,
                    "status": "QUEUED",
                }
            ],
        )

        with TemporaryDirectory() as tmpdir:
            run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: LargeOutputAdapter(),
            )

        detail = store.get_investigation(investigation.id)
        event = next(item for item in detail["events"] if item["message"] == "完成工具任务：large_output")

        self.assertLessEqual(len(event["metadata"]["stdout_excerpt"]), 4096)
        self.assertLessEqual(len(event["metadata"]["stderr_excerpt"]), 4096)
        self.assertIn("truncated", event["metadata"]["stdout_excerpt"])

    def test_official_site_output_creates_source_backed_facts(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="official site fact promotion",
            seed_type="domain",
            seed_value="example-target.test",
            strategy_name="quick",
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.replace_jobs(
            investigation.id,
            [
                {
                    **first_job,
                    "tool_name": "official_site_extractor",
                    "target_type": "url",
                    "target_value": "https://example-target.test",
                    "depth": 0,
                    "status": "QUEUED",
                }
            ],
        )

        with TemporaryDirectory() as tmpdir:
            run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: OfficialSiteOutputAdapter(),
            )

        detail = store.get_investigation(investigation.id)
        fact_keys = {(fact["predicate"], fact["object"]) for fact in detail["facts"]}

        self.assertIn(("has_company_identity", "SAMPLE AUTO PARTS COMPANY LIMITED"), fact_keys)
        self.assertIn(("uses_contact_phone", "+85282061801"), fact_keys)
        self.assertIn(("has_business_scope", "auto parts"), fact_keys)
        self.assertTrue(all(fact["promotion_stage"] == "ACCEPTED_FACT" for fact in detail["facts"]))

    def test_worker_skips_when_investigation_already_has_running_job(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="busy workflow",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="quick",
        )
        first_job = store.list_jobs(investigation.id)[0]
        store.update_job_status(first_job["id"], "RUNNING")

        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: FakeAdapter(),
            )

        self.assertTrue(result["busy"])
        self.assertEqual(result["started"], 0)

    def test_heavy_tools_run_after_cross_verification_and_before_analysis(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="staged company workflow",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="deep",
        )
        store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "job-enterprise",
                    "investigation_id": investigation.id,
                    "tool_name": "company_osint",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 0,
                    "status": "QUEUED",
                    "agent_role": "enterprise_intel_agent",
                    "output_contract": "entities,evidence,relationships",
                    "depends_on": "",
                },
                {
                    "id": "job-cross",
                    "investigation_id": investigation.id,
                    "tool_name": "cross_verification",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 1,
                    "status": "QUEUED",
                    "agent_role": "cross_verification_agent",
                    "output_contract": "claims,evidence,relationships",
                    "depends_on": "company_osint",
                },
                {
                    "id": "job-heavy",
                    "investigation_id": investigation.id,
                    "tool_name": "ghunt",
                    "target_type": "email",
                    "target_value": "buyer@gmail.com",
                    "depth": 1,
                    "status": "QUEUED",
                    "agent_role": "tool_agent",
                    "output_contract": "entities,evidence,relationships",
                    "depends_on": "",
                },
                {
                    "id": "job-analysis",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 2,
                    "status": "QUEUED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "cross_verification",
                },
            ],
        )

        with TemporaryDirectory() as tmpdir:
            run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=6,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: HeavyToolAdapter() if name == "ghunt" else (_raise_missing(name)),
            )

        detail = store.get_investigation(investigation.id)
        event_order = [
            event["metadata"].get("tool_name")
            for event in detail["events"]
            if event["message"].startswith("本地职责 Agent 完成") or event["message"].startswith("完成工具任务")
        ]

        self.assertLess(event_order.index("company_osint"), event_order.index("cross_verification"))
        self.assertLess(event_order.index("cross_verification"), event_order.index("ghunt"))
        self.assertLess(event_order.index("ghunt"), event_order.index("analysis_judgement"))

    def test_sqlite_store_persists_job_counts_and_risk_report(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "osint.sqlite"
            store = SQLiteStore(str(db_path))
            investigation = store.create_investigation(
                name="admin 风险复核",
                seed_type="username",
                seed_value="admin",
                strategy_name="standard",
            )
            first_job = store.list_jobs(investigation.id)[0]
            store.replace_jobs(
                investigation.id,
                [
                    {
                        **first_job,
                        "tool_name": "fake_social",
                        "target_type": "username",
                        "target_value": "admin",
                        "depth": 0,
                        "status": "QUEUED",
                    }
                ],
            )

            run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir) / "jobs",
                adapter_factory=lambda name: FakeAdapter(),
            )

            second_store = SQLiteStore(str(db_path))
            detail = second_store.get_investigation(investigation.id)

        self.assertEqual(detail["job_counts"]["COMPLETED"], 1)
        self.assertEqual(detail["job_counts"]["QUEUED"], 1)
        self.assertIn("overall_risk_score", detail["risk_report"])

    def test_sqlite_add_jobs_preserves_planned_job_contract_fields(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "osint.sqlite"
            store = SQLiteStore(str(db_path))
            investigation = store.create_investigation(
                name="弱线索买家：Sample Lead",
                seed_type="company",
                seed_value="Sample Lead",
                strategy_name="deep",
            )

            created = store.add_jobs(
                investigation.id,
                [
                    PlannedJob(
                        tool_name="identity_match_review",
                        target_type="sparse_lead",
                        target_value="Sample Lead / member-redacted",
                        depth=1,
                        agent_role="cross_verification_agent",
                        output_contract="claims,evidence: identity_match_confidence",
                        depends_on="candidate_business_discovery",
                    )
                ],
            )

            detail = store.get_investigation(investigation.id)
            job = next(item for item in detail["jobs"] if item["id"] == created[0]["id"])

        self.assertEqual(job["agent_role"], "cross_verification_agent")
        self.assertEqual(job["output_contract"], "claims,evidence: identity_match_confidence")
        self.assertEqual(job["depends_on"], "candidate_business_discovery")

    def test_worker_extracts_sparse_lead_anchors_from_metadata(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Alibaba 买家弱线索：Sample Lead",
            seed_type="sparse_lead",
            seed_value="Sample Lead / member-redacted",
            strategy_name="quick",
            metadata={
                "platform": "Alibaba",
                "lead_display_name": "Sample Lead",
                "member_id": "member-redacted",
                "country_region": "IN",
                "registration_year": "2023",
                "company_name_raw": "Sample Lead",
                "privacy_state": "email_phone_hidden",
                "categories": ["Induction Cookers", "Gas Cooktops"],
                "recent_rfqs": ["2200W Best Quality And Low Price Durable Electric Cook Top"],
            },
        )

        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=1,
                artifact_root=Path(tmpdir),
            )

        detail = store.get_investigation(investigation.id)
        entity_pairs = {(item["type"], item["value"]) for item in detail["entities"]}
        evidence_kinds = {item["evidence_kind"] for item in detail["evidence"]}
        relationship_types = {item["relationship_type"] for item in detail["relationships"]}

        self.assertEqual(result["completed"], 1)
        self.assertIn(("platform_account", "Sample Lead"), entity_pairs)
        self.assertIn(("platform_member_id", "member-redacted"), entity_pairs)
        self.assertIn(("country_region", "IN"), entity_pairs)
        self.assertIn(("purchase_category", "Induction Cookers"), entity_pairs)
        self.assertIn(("rfq_text", "2200W Best Quality And Low Price Durable Electric Cook Top"), entity_pairs)
        self.assertIn("visible_buyer_anchor", evidence_kinds)
        self.assertIn("lead_has_platform_anchor", relationship_types)

    def test_worker_queues_gap_driven_followups_for_any_review_task(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="通用缺口补采",
            seed_type="company",
            seed_value="Example Trading LLC",
            strategy_name="deep",
        )
        store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "job-analysis",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Example Trading LLC",
                    "depth": 2,
                    "status": "QUEUED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "",
                }
            ],
        )
        store.add_entity(investigation.id, "company", "Example Trading LLC", "operator_seed", 0.9)

        result = run_investigation_jobs(store, investigation.id, max_jobs=10, artifact_root=Path("/tmp/unused"))

        detail = store.get_investigation(investigation.id)
        job_keys = {(job["tool_name"], job["agent_role"]) for job in detail["jobs"]}
        gap_jobs = [job for job in detail["jobs"] if "gap:" in str(job.get("depends_on") or "")]
        planner_events = [event for event in detail["events"] if "补采" in str(event.get("message") or "")]

        self.assertGreaterEqual(result["queued_followups"], 1)
        self.assertIn(("social_profile_search", "social_intel_agent"), job_keys)
        self.assertIn(("company_news_monitoring", "news_intel_agent"), job_keys)
        self.assertIn(("company_osint", "enterprise_intel_agent"), job_keys)
        self.assertIn(("cross_verification", "cross_verification_agent"), job_keys)
        self.assertIn(("analysis_judgement", "analysis_judgement_agent"), job_keys)
        self.assertTrue(gap_jobs)
        self.assertTrue(any(job["status"] == "QUEUED" for job in gap_jobs))
        self.assertTrue(planner_events)
        self.assertGreaterEqual(planner_events[-1]["metadata"]["gap_followup_summary"]["total_gaps"], 1)

    def test_worker_records_gap_tool_plan_when_tools_unavailable(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Example Manufacturing LLC",
            seed_type="company",
            seed_value="Example Manufacturing LLC",
            strategy_name="standard",
        )
        store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "job-analysis",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Example Manufacturing LLC",
                    "depth": 2,
                    "status": "COMPLETED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "",
                }
            ],
        )
        store.complete_task(
            investigation.id,
            agent_id="analysis",
            status="NEEDS_REVIEW",
            summary="Needs more evidence.",
            report_markdown="",
            confidence=0.4,
        )

        with patch(
            "app.services.worker.build_tool_health_report",
            return_value={
                "summary": {},
                "tools": [
                    {
                        "name": "official_site_search",
                        "status": "missing_config",
                        "reason": "OFFICIAL_SITE_SEARCH_BASE_URL is not configured",
                    },
                    {
                        "name": "company_osint",
                        "status": "missing_config",
                        "reason": "COMPANY_OSINT_BASE_URL is not configured",
                    },
                    {
                        "name": "contact_discovery",
                        "status": "missing_config",
                        "reason": "CONTACT_DISCOVERY_BASE_URL is not configured",
                    },
                ],
            },
        ):
            result = run_investigation_jobs(store, investigation.id, max_jobs=1, artifact_root=Path("/tmp/unused"))

        self.assertIn("gap_followup_summary", result)
        self.assertGreaterEqual(result["gap_followup_summary"]["blocked_by_config"], 1)
        detail = store.get_investigation(investigation.id)
        self.assertTrue(any("补采" in event["message"] for event in detail["events"]))

    def test_historical_review_task_queues_gap_followups_when_rerun(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="历史评审任务缺口补采",
            seed_type="company",
            seed_value="Example Trading LLC",
            strategy_name="deep",
        )
        store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "job-analysis",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Example Trading LLC",
                    "depth": 2,
                    "status": "COMPLETED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "",
                }
            ],
        )
        store.add_entity(investigation.id, "company", "Example Trading LLC", "operator_seed", 0.9)
        store.set_investigation_status(investigation.id, "NEEDS_REVIEW")

        result = run_investigation_jobs(store, investigation.id, max_jobs=10, artifact_root=Path("/tmp/unused"))

        detail = store.get_investigation(investigation.id)
        gap_jobs = [job for job in detail["jobs"] if "gap:" in str(job.get("depends_on") or "")]
        job_keys = {(job["tool_name"], job["agent_role"]) for job in gap_jobs}

        self.assertGreaterEqual(result["queued_gap_followups"], 1)
        self.assertGreaterEqual(result["completed"], 1)
        self.assertIn(("social_profile_search", "social_intel_agent"), job_keys)
        self.assertIn(("company_news_monitoring", "news_intel_agent"), job_keys)
        self.assertIn(("analysis_judgement", "analysis_judgement_agent"), job_keys)

    def test_existing_gap_jobs_with_legacy_analysis_dependency_can_run(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="旧格式缺口任务兼容",
            seed_type="company",
            seed_value="Example Trading LLC",
            strategy_name="deep",
        )
        store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "job-analysis-done",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Example Trading LLC",
                    "depth": 2,
                    "status": "COMPLETED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "",
                },
                {
                    "id": "job-social-gap",
                    "investigation_id": investigation.id,
                    "tool_name": "candidate_business_discovery",
                    "target_type": "company",
                    "target_value": "Example Trading LLC",
                    "depth": 3,
                    "status": "QUEUED",
                    "agent_role": "enterprise_intel_agent",
                    "output_contract": "entities,evidence,relationships",
                    "depends_on": "analysis_judgement;gap:business_scope",
                },
                {
                    "id": "job-reanalysis",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Example Trading LLC",
                    "depth": 5,
                    "status": "QUEUED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "cross_verification;identity_match_review;gap:reanalyze",
                },
            ],
        )
        store.add_entity(investigation.id, "identity", "Example Owner", "operator_seed", 0.9)
        store.add_entity(investigation.id, "news_article", "Example announcement", "operator_seed", 0.9)
        store.add_entity(investigation.id, "business_scope", "Trading", "operator_seed", 0.9)
        store.add_entity(investigation.id, "address", "Example City", "operator_seed", 0.9)
        store.add_entity(investigation.id, "risk_signal", "No public risk signal found", "operator_seed", 0.9)

        result = run_investigation_jobs(store, investigation.id, max_jobs=1, artifact_root=Path("/tmp/unused"))

        detail = store.get_investigation(investigation.id)
        gap_job = next(job for job in detail["jobs"] if job["id"] == "job-social-gap")

        self.assertEqual(result["role_completed"], 1)
        self.assertEqual(gap_job["status"], "COMPLETED")

    def test_worker_refreshes_report_after_second_round_collection(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="二轮补采刷新报告",
            seed_type="company",
            seed_value="Example Trading LLC",
            strategy_name="deep",
        )
        store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "job-analysis-done",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Example Trading LLC",
                    "depth": 2,
                    "status": "COMPLETED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "",
                },
                {
                    "id": "job-gap",
                    "investigation_id": investigation.id,
                    "tool_name": "candidate_business_discovery",
                    "target_type": "company",
                    "target_value": "Example Trading LLC",
                    "depth": 3,
                    "status": "QUEUED",
                    "agent_role": "enterprise_intel_agent",
                    "output_contract": "entities,evidence,relationships",
                    "depends_on": "analysis_judgement;gap:business_scope",
                },
            ],
        )
        store.complete_task(
            investigation.id,
            "local-analysis-agent",
            "NEEDS_REVIEW",
            "旧报告",
            "# 旧报告\n\n完整度评分：1.0 / 100",
            0.1,
        )
        store.add_entity(investigation.id, "identity", "Example Owner", "operator_seed", 0.9)
        store.add_entity(investigation.id, "news_article", "Example announcement", "operator_seed", 0.9)
        store.add_entity(investigation.id, "business_scope", "Trading", "operator_seed", 0.9)
        store.add_entity(investigation.id, "address", "Example City", "operator_seed", 0.9)
        store.add_entity(investigation.id, "risk_signal", "No public risk signal found", "operator_seed", 0.9)

        result = run_investigation_jobs(store, investigation.id, max_jobs=1, artifact_root=Path("/tmp/unused"))

        detail = store.get_investigation(investigation.id)

        self.assertEqual(result["role_completed"], 1)
        self.assertNotIn("完整度评分：1.0 / 100", detail["report_markdown"])
        self.assertIn(f"完整度评分：{result['quality_assessment']['score']} / 100", detail["report_markdown"])

    def test_worker_marks_limited_completion_completed_with_policy_summary(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="limited completion company",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="quick",
        )
        store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "job-analysis",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 0,
                    "status": "COMPLETED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "",
                },
                {
                    "id": "job-social",
                    "investigation_id": investigation.id,
                    "tool_name": "social_profile_search",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 1,
                    "status": "COMPLETED",
                    "agent_role": "social_intel_agent",
                    "output_contract": "entities,evidence,relationships",
                    "depends_on": "completed:analysis_judgement;gap:decision_maker",
                },
                {
                    "id": "job-news",
                    "investigation_id": investigation.id,
                    "tool_name": "company_news",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 1,
                    "status": "COMPLETED",
                    "agent_role": "tool_agent",
                    "output_contract": "entities,evidence,relationships",
                    "depends_on": "completed:analysis_judgement;gap:decision_maker",
                },
            ],
        )
        store.add_entity(investigation.id, "company", "Sample Auto Parts Co.", "company_osint", 0.9)
        store.add_entity(investigation.id, "email", "sales@example-target.test", "official_site_extractor", 0.8)
        store.add_entity(investigation.id, "phone", "+1-555-0100", "official_site_extractor", 0.76)
        store.add_entity(investigation.id, "address", "Chicago, IL", "company_osint", 0.72)
        store.add_entity(investigation.id, "business_scope", "auto parts distribution", "official_site_extractor", 0.8)
        identity_evidence = store.add_evidence_record(
            investigation.id,
            source_url="https://example-target.test/about",
            source_type="official_site_profile",
            source_tool="official_site_extractor",
            snippet="Official profile confirms Sample Auto Parts Co. identity and auto parts distribution.",
            credibility=0.86,
        )
        contact_evidence = store.add_evidence_record(
            investigation.id,
            source_url="https://example-target.test/contact",
            source_type="official_site_contact",
            source_tool="official_site_extractor",
            snippet="Official contact page lists sales@example-target.test.",
            credibility=0.82,
        )
        store.add_fact(
            investigation.id,
            statement="Sample Auto Parts Co. is the company identity on the official website.",
            subject="Sample Auto Parts Co.",
            predicate="company_identity",
            object_value="Sample Auto Parts Co.",
            status="CONFIRMED",
            confidence=0.86,
            admiralty_code="A-2",
            evidence_ids=[identity_evidence["id"]],
        )
        store.add_fact(
            investigation.id,
            statement="Sample Auto Parts Co. official website is https://example-target.test.",
            subject="Sample Auto Parts Co.",
            predicate="official_website",
            object_value="https://example-target.test",
            status="CONFIRMED",
            confidence=0.84,
            admiralty_code="A-2",
            evidence_ids=[identity_evidence["id"]],
        )
        store.add_fact(
            investigation.id,
            statement="Sample Auto Parts Co. business scope is auto parts distribution.",
            subject="Sample Auto Parts Co.",
            predicate="business_scope",
            object_value="auto parts distribution",
            status="CONFIRMED",
            confidence=0.82,
            admiralty_code="A-2",
            evidence_ids=[identity_evidence["id"]],
        )
        store.add_fact(
            investigation.id,
            statement="Sample Auto Parts Co. lists a source-backed contact channel.",
            subject="Sample Auto Parts Co.",
            predicate="has_contact_email",
            object_value="sales@example-target.test",
            status="CONFIRMED",
            confidence=0.82,
            admiralty_code="A-2",
            evidence_ids=[contact_evidence["id"]],
        )
        store.add_relationship(investigation.id, "Sample Auto Parts Co.", "sales@example-target.test", "has_contact", 0.82)
        store.add_hypothesis(investigation.id, "h1", "Sample Auto Parts Co. is the target company.")
        store.score_hypotheses(
            investigation.id,
            [
                {
                    "id": identity_evidence["id"],
                    "summary": "Official site evidence supports target identity and business scope.",
                    "kinds": ["official_site_profile"],
                    "supports": ["h1"],
                    "contradicts": [],
                    "source_reliability": "A",
                    "credibility": 0.86,
                    "keywords": ["sample", "auto parts"],
                }
            ],
        )
        store.complete_task(
            investigation.id,
            "local-analysis-agent",
            "NEEDS_REVIEW",
            "Initial BLUF",
            "## BLUF\nSample Auto Parts Co. has source-backed contact and scope evidence.",
            0.86,
        )

        limited_policy = {
            "recommended_status": "COMPLETED",
            "completion_mode": "limited",
            "strict_completion_ready": False,
            "limited_completion_ready": True,
            "auto_exhausted": True,
            "manual_decision_required": False,
            "environment_blocked": False,
            "reason": "Core evidence floor is satisfied; only acceptable limitations remain: decision_maker.",
            "remaining_blockers": ["decision_maker"],
            "acceptable_limitations": ["decision_maker"],
            "operator_next_actions": ["Manually verify decision-maker from an official team page, public profile, or trusted directory."],
            "evidence_floor": {
                "identity": True,
                "official_website": True,
                "business_scope": True,
                "contact_channel": True,
                "evidence_ledger": True,
                "fact_pool": True,
                "cross_verification": True,
                "bluf_report": True,
            },
        }

        with (
            patch("app.services.worker.build_completion_policy", return_value=limited_policy),
            patch("app.services.store.build_completion_policy", return_value=limited_policy),
            TemporaryDirectory() as tmpdir,
        ):
            summary = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=0,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: MinimalCompleteAdapter(name),
            )
            detail = store.get_investigation(investigation.id)

        self.assertEqual(summary["completion_mode"], "limited")
        self.assertEqual(summary["completion_policy"]["recommended_status"], "COMPLETED")
        self.assertFalse(summary["quality_assessment"]["completion_ready"])
        self.assertEqual(detail["status"], "COMPLETED")
        self.assertEqual(detail["completion_policy"]["completion_mode"], "limited")

    def test_worker_refreshes_stale_report_and_records_gap_followups(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="无新任务刷新陈旧报告",
            seed_type="company",
            seed_value="Example Trading LLC",
            strategy_name="deep",
        )
        store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "job-analysis-done",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Example Trading LLC",
                    "depth": 2,
                    "status": "COMPLETED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "",
                }
            ],
        )
        store.add_entity(investigation.id, "identity", "Example Owner", "operator_seed", 0.9)
        store.add_entity(investigation.id, "news_article", "Example announcement", "operator_seed", 0.9)
        store.add_entity(investigation.id, "business_scope", "Trading", "operator_seed", 0.9)
        store.add_entity(investigation.id, "address", "Example City", "operator_seed", 0.9)
        store.add_entity(investigation.id, "risk_signal", "No public risk signal found", "operator_seed", 0.9)
        store.complete_task(
            investigation.id,
            "local-analysis-agent",
            "NEEDS_REVIEW",
            "旧报告",
            "# 旧报告\n\n完整度评分：1.0 / 100",
            0.1,
        )

        result = run_investigation_jobs(store, investigation.id, max_jobs=1, artifact_root=Path("/tmp/unused"))

        detail = store.get_investigation(investigation.id)

        self.assertGreaterEqual(result["queued_gap_followups"], 1)
        self.assertGreaterEqual(result["gap_followup_summary"]["total_gaps"], 1)
        self.assertNotIn("完整度评分：1.0 / 100", detail["report_markdown"])
        self.assertIn(f"完整度评分：{result['quality_assessment']['score']} / 100", detail["report_markdown"])

    def test_worker_wires_one_health_snapshot_to_report_without_changing_final_status(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="环境覆盖报告刷新",
            seed_type="company",
            seed_value="Example Trading LLC",
            strategy_name="quick",
        )
        store.replace_jobs(investigation.id, [])
        store.set_investigation_status(investigation.id, "NEEDS_REVIEW")

        health_snapshot = {
            "summary": {"affected_capabilities": {"asset_discovery": ["amass"]}},
            "tools": [],
        }
        completion_policy = {
            "recommended_status": "COMPLETED",
            "completion_mode": "limited",
        }

        with (
            patch("app.services.worker.build_tool_health_report", return_value=health_snapshot) as health_report,
            patch("app.services.worker.render_structured_report", return_value="## BLUF\nRefreshed report.") as render_report,
            patch("app.services.worker.build_completion_policy", return_value=completion_policy),
            patch("app.services.store.build_completion_policy", return_value=completion_policy),
        ):
            result = run_investigation_jobs(store, investigation.id, max_jobs=1, artifact_root=Path("/tmp/unused"))
            detail = store.get_investigation(investigation.id)

        self.assertEqual(result["tool_health"], health_snapshot)
        health_report.assert_called_once_with()
        self.assertEqual(render_report.call_args.kwargs["tool_health"], health_snapshot)
        self.assertEqual(detail["status"], "COMPLETED")

    def test_worker_persists_environment_coverage_limit_for_memory_and_sqlite_stores(self):
        health_snapshot = {
            "summary": {"affected_capabilities": {"asset_discovery": ["amass"]}},
            "tools": [],
        }

        with TemporaryDirectory() as tmpdir:
            stores = [
                ("memory", MemoryStore()),
                ("sqlite", SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))),
            ]
            for store_name, store in stores:
                with self.subTest(store=store_name):
                    investigation = store.create_investigation(
                        name=f"{store_name} environment coverage refresh",
                        seed_type="company",
                        seed_value="Example Trading LLC",
                        strategy_name="quick",
                    )
                    store.replace_jobs(investigation.id, [])

                    with patch("app.services.worker.build_tool_health_report", return_value=health_snapshot):
                        result = run_investigation_jobs(
                            store,
                            investigation.id,
                            max_jobs=1,
                            artifact_root=Path(tmpdir),
                        )

                    detail = store.get_investigation(investigation.id)
                    self.assertEqual(result["tool_health"], health_snapshot)
                    self.assertIn("## 环境覆盖限制", detail["report_markdown"])
                    self.assertIn("asset_discovery", detail["report_markdown"])
                    self.assertIn("amass", detail["report_markdown"])
                    self.assertEqual(detail["status"], "NEEDS_REVIEW")
                    self.assertFalse(result["quality_assessment"]["completion_ready"])

    def test_sqlite_agent_completion_persists_supplied_environment_coverage_limit(self):
        health_snapshot = {
            "summary": {"affected_capabilities": {"asset_discovery": ["amass"]}},
            "tools": [],
        }

        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            reporter = store.register_agent(
                agent_name="environment-coverage-reporter",
                agent_type="reporter",
                capabilities=["domain"],
                role_tier="reporter",
            )
            investigation = store.create_investigation(
                name="SQLite agent environment coverage refresh",
                seed_type="domain",
                seed_value="example-target.test",
                strategy_name="quick",
            )
            claimed = store.claim_task(reporter["id"], ["domain"])
            self.assertEqual(claimed["id"], investigation.id)

            completed = store.agent_complete_task(
                agent_id=reporter["id"],
                required_tier="reporter",
                investigation_id=investigation.id,
                job_id=None,
                status="NEEDS_REVIEW",
                summary="Environment coverage refresh.",
                report_markdown="## BLUF\nEnvironment coverage refresh.",
                confidence=0.5,
                tool_health=health_snapshot,
            )

        self.assertIsNotNone(completed)
        self.assertIn("## 环境覆盖限制", completed["report_markdown"])
        self.assertIn("asset_discovery", completed["report_markdown"])
        self.assertIn("amass", completed["report_markdown"])
        self.assertEqual(completed["status"], "NEEDS_REVIEW")

    def test_completed_quality_gate_summary_is_stable_when_rerun_has_no_jobs(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="已完成官网侦察",
            seed_type="domain",
            seed_value="example-target.test",
            strategy_name="quick",
        )
        store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "job-official-site",
                    "investigation_id": investigation.id,
                    "tool_name": "official_site_extractor",
                    "target_type": "url",
                    "target_value": "https://example-target.test",
                    "depth": 1,
                    "status": "COMPLETED",
                    "agent_role": "tool_agent",
                    "output_contract": "entities,evidence,relationships",
                    "depends_on": "",
                }
            ],
        )
        store.add_entity(investigation.id, "organization", "SAMPLE AUTO PARTS COMPANY LIMITED", "official_site_extractor", 0.76)
        store.add_entity(investigation.id, "url", "https://example-target.test", "official_site_extractor", 0.72)
        store.add_entity(investigation.id, "phone", "+85282061801", "official_site_extractor", 0.78)
        store.add_entity(investigation.id, "business_scope", "auto parts", "official_site_extractor", 0.74)
        store.add_relationship(investigation.id, "https://example-target.test", "auto parts", "official_site_describes_business_scope", 0.74)
        evidence = store.add_evidence_record(
            investigation.id,
            "https://example-target.test",
            "official_site_identity",
            "official_site_extractor",
            "Official site names organization.",
            0.82,
        )
        store.add_fact(
            investigation.id,
            "Official site supports company identity.",
            "https://example-target.test",
            "has_company_identity",
            "SAMPLE AUTO PARTS COMPANY LIMITED",
            "CONFIRMED",
            0.76,
            evidence["admiralty_code"],
            [evidence["id"]],
        )
        store.add_fact(
            investigation.id,
            "Official site supports business scope.",
            "https://example-target.test",
            "has_business_scope",
            "auto parts",
            "CONFIRMED",
            0.74,
            evidence["admiralty_code"],
            [evidence["id"]],
        )
        store.complete_task(
            investigation.id,
            "local-worker",
            "COMPLETED",
            "旧摘要",
            "## BLUF\nOfficial site source-backed domain reconnaissance is complete.",
            0.8,
        )

        result = run_investigation_jobs(store, investigation.id, max_jobs=1, artifact_root=Path("/tmp/unused"))
        detail = store.get_investigation(investigation.id)

        self.assertEqual(result["started"], 0)
        self.assertEqual(detail["status"], "COMPLETED")
        self.assertIn("质量闸门已通过", detail["summary"])

    def test_sparse_lead_review_workflow_plans_second_round_collection(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="任意弱线索二轮补采",
            seed_type="sparse_lead",
            seed_value="Example Buyer / Example Trading",
            strategy_name="deep",
            metadata={
                "platform": "Alibaba",
                "lead_display_name": "Example Buyer",
                "country_region": "Malaysia",
                "company_name_raw": "Example Trading",
                "privacy_state": "email_phone_hidden",
            },
        )

        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=10,
                artifact_root=Path(tmpdir),
            )

        detail = store.get_investigation(investigation.id)
        gap_jobs = [job for job in detail["jobs"] if "gap:" in str(job.get("depends_on") or "")]
        job_keys = {(job["tool_name"], job["agent_role"]) for job in gap_jobs}

        self.assertGreaterEqual(result["queued_gap_followups"], 1)
        self.assertIn(("social_profile_search", "social_intel_agent"), job_keys)
        self.assertIn(("candidate_business_discovery", "enterprise_intel_agent"), job_keys)
        self.assertIn(("identity_match_review", "cross_verification_agent"), job_keys)
        self.assertIn(("analysis_judgement", "analysis_judgement_agent"), job_keys)
        self.assertTrue(all(job["target_value"] == "Example Buyer / Example Trading" for job in gap_jobs))


if __name__ == "__main__":
    unittest.main()
