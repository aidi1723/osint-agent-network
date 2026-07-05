import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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


class WorkerTests(unittest.TestCase):
    def test_worker_runs_agent_orchestration_jobs_locally(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="企业背调",
            seed_type="company",
            seed_value="Family Hospitality LLC",
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
            seed_value="Family Hospitality LLC",
            strategy_name="deep",
        )
        run_investigation_jobs(store, investigation.id, max_jobs=10)
        agent = store.register_agent(
            agent_name="enterprise-agent",
            agent_type="enterprise_intel_agent",
            capabilities=["enterprise_intel_agent"],
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
            seed_value="SRR Genuine Parts",
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
                    "target_value": "SRR Genuine Parts",
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
                    "target_value": "SRR Genuine Parts",
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
                    "target_value": "SRR Genuine Parts",
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
                name="弱线索买家：Long Way",
                seed_type="company",
                seed_value="Long Way",
                strategy_name="deep",
            )

            created = store.add_jobs(
                investigation.id,
                [
                    PlannedJob(
                        tool_name="identity_match_review",
                        target_type="sparse_lead",
                        target_value="Long Way / in19034126503jgqn",
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
            name="Alibaba 买家弱线索：Long Way",
            seed_type="sparse_lead",
            seed_value="Long Way / in19034126503jgqn",
            strategy_name="quick",
            metadata={
                "platform": "Alibaba",
                "lead_display_name": "Long Way",
                "member_id": "in19034126503jgqn",
                "country_region": "IN",
                "registration_year": "2023",
                "company_name_raw": "Long Way",
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
        self.assertIn(("platform_account", "Long Way"), entity_pairs)
        self.assertIn(("platform_member_id", "in19034126503jgqn"), entity_pairs)
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

        self.assertGreaterEqual(result["queued_followups"], 1)
        self.assertIn(("social_profile_search", "social_intel_agent"), job_keys)
        self.assertIn(("company_news_monitoring", "news_intel_agent"), job_keys)
        self.assertIn(("company_osint", "enterprise_intel_agent"), job_keys)
        self.assertIn(("cross_verification", "cross_verification_agent"), job_keys)
        self.assertIn(("analysis_judgement", "analysis_judgement_agent"), job_keys)
        self.assertTrue(gap_jobs)
        self.assertTrue(any(job["status"] == "QUEUED" for job in gap_jobs))

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

    def test_worker_refreshes_stale_report_when_no_jobs_run(self):
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

        self.assertEqual(result["started"], 0)
        self.assertNotIn("完整度评分：1.0 / 100", detail["report_markdown"])
        self.assertIn(f"完整度评分：{result['quality_assessment']['score']} / 100", detail["report_markdown"])

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
