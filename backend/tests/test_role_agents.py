import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.core.agent_permissions import PermissionedRoleStore, tier_for_role
from app.core.planner import PlannedJob
from app.services.role_agents import run_role_agent
from app.services.store import MemoryStore
from app.services.worker import run_investigation_jobs
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
    ToolCommand,
    ToolRunResult,
    write_json_artifact,
)


class DomainFollowupAdapter:
    name = "theharvester"

    def run(self, target_type: str, target_value: str, workdir: Path, timeout_seconds: int):
        artifact = workdir / "domain_followup.json"
        write_json_artifact(artifact, {"target": target_value})
        return ToolRunResult(
            command=ToolCommand(
                args=["fake-theharvester", target_value],
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
            entities=[NormalizedEntity("email", f"sales@{target_value}", self.name, 0.72)],
            evidence=[
                NormalizedEvidence(
                    f"sales@{target_value}",
                    "business_email",
                    self.name,
                    "Domain enrichment found a business email.",
                )
            ],
            relationships=[
                NormalizedRelationship(
                    target_value,
                    f"sales@{target_value}",
                    "domain_exposes_email",
                    0.72,
                )
            ],
        )


class LocalRoleAgentTests(unittest.TestCase):
    def test_role_tier_mapping_separates_reader_verifier_and_reporter(self):
        self.assertEqual(tier_for_role("enterprise_intel_agent"), "reader")
        self.assertEqual(tier_for_role("cross_verification_agent"), "verifier")
        self.assertEqual(tier_for_role("analysis_judgement_agent"), "reporter")

    def test_reader_store_cannot_write_facts(self):
        store = MemoryStore()
        permissioned = PermissionedRoleStore(store, "reader")

        with self.assertRaises(PermissionError):
            permissioned.add_fact(
                investigation_id="task-1",
                statement="Example fact.",
                subject="Example",
                predicate="has_domain",
                object_value="example.com",
                status="CONFIRMED",
                confidence=0.9,
                admiralty_code="A-2",
                evidence_ids=["ev-1"],
            )

    def test_verifier_store_cannot_complete_task(self):
        store = MemoryStore()
        permissioned = PermissionedRoleStore(store, "verifier")

        with self.assertRaises(PermissionError):
            permissioned.complete_task(
                investigation_id="task-1",
                agent_id="agent",
                status="COMPLETED",
                summary="summary",
                report_markdown="# Report",
                confidence=0.8,
            )

    def test_reporter_store_cannot_collect_entities(self):
        store = MemoryStore()
        permissioned = PermissionedRoleStore(store, "reporter")

        with self.assertRaises(PermissionError):
            permissioned.add_entity("task-1", "domain", "example.com", "reporter", 0.8)

    def test_run_role_agent_uses_permissioned_store_for_collection(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Permissioned collection",
            seed_type="company",
            seed_value="Example LLC",
            strategy_name="quick",
        )
        result = run_role_agent(
            store,
            investigation.id,
            {
                "id": "job-enterprise",
                "tool_name": "company_osint",
                "agent_role": "enterprise_intel_agent",
            },
        )

        detail = store.get_investigation(investigation.id)
        self.assertTrue(result.completed)
        self.assertIn(("company", "Example LLC"), {(item["type"], item["value"]) for item in detail["entities"]})

    def test_analysis_judgement_uses_store_health_default_in_persisted_report(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Analysis health default",
            seed_type="company",
            seed_value="Example LLC",
            strategy_name="quick",
        )
        health_snapshot = {
            "summary": {"affected_capabilities": {"asset_discovery": ["amass"]}},
            "tools": [],
        }

        with patch(
            "app.services.store.build_tool_health_report",
            return_value=health_snapshot,
            create=True,
        ) as health_report:
            result = run_role_agent(
                store,
                investigation.id,
                {
                    "id": "job-analysis",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "agent_role": "analysis_judgement_agent",
                },
            )

        detail = store.get_investigation(investigation.id)
        self.assertTrue(result.completed)
        self.assertEqual(detail["status"], "NEEDS_REVIEW")
        self.assertIn("## 环境覆盖限制", detail["report_markdown"])
        self.assertIn("asset_discovery", detail["report_markdown"])
        self.assertIn("amass", detail["report_markdown"])
        health_report.assert_called_once_with()

    def test_sparse_lead_identity_match_respects_declared_dependencies(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Sparse lead dependency order",
            seed_type="sparse_lead",
            seed_value="Alibaba:member-redacted",
            strategy_name="deep",
            metadata={
                "platform": "Alibaba",
                "lead_display_name": "Sample Lead",
                "member_id": "member-redacted",
                "country_region": "IN",
                "categories": ["Induction Cookers"],
                "recent_rfqs": ["2200W Electric Cook Top"],
            },
        )

        with TemporaryDirectory() as tmpdir:
            run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=8,
                artifact_root=Path(tmpdir),
            )

        detail = store.get_investigation(investigation.id)
        event_order = [
            event["metadata"].get("tool_name")
            for event in detail["events"]
            if event["message"].startswith("本地职责 Agent 完成") or event["message"].startswith("完成工具任务")
        ]

        self.assertLess(event_order.index("lead_anchor_extraction"), event_order.index("constrained_query_planning"))
        self.assertLess(event_order.index("constrained_query_planning"), event_order.index("candidate_business_discovery"))
        self.assertLess(event_order.index("lead_anchor_extraction"), event_order.index("rfq_category_analysis"))
        self.assertLess(event_order.index("candidate_business_discovery"), event_order.index("identity_match_review"))
        self.assertLess(event_order.index("rfq_category_analysis"), event_order.index("identity_match_review"))
        self.assertLess(event_order.index("identity_match_review"), event_order.index("analysis_judgement"))

    def test_analysis_waits_until_followup_tools_finish(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Stable scheduling",
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
        store.add_entity(investigation.id, "domain", "example-target.test", "operator_seed", 0.85)
        store.add_evidence(investigation.id, "example-target.test", "official_website", "operator_seed", "Operator-confirmed official site.")

        with TemporaryDirectory() as tmpdir:
            run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=4,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: DomainFollowupAdapter() if name == "theharvester" else (_raise_missing(name)),
            )

        detail = store.get_investigation(investigation.id)
        event_order = [
            event["metadata"].get("tool_name") or event["metadata"].get("source_tool")
            for event in detail["events"]
            if event["message"].startswith("本地职责 Agent 完成") or event["message"].startswith("完成工具任务")
        ]

        self.assertLess(event_order.index("company_osint"), event_order.index("cross_verification"))
        self.assertLess(event_order.index("cross_verification"), event_order.index("theharvester"))
        self.assertLess(event_order.index("cross_verification"), event_order.index("analysis_judgement"))
        self.assertLess(event_order.index("theharvester"), event_order.index("analysis_judgement"))

    def test_cross_verification_and_analysis_jobs_run_locally(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="SampleCo local role agents",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="deep",
        )
        store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "job-cross",
                    "investigation_id": investigation.id,
                    "tool_name": "cross_verification",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 0,
                    "status": "QUEUED",
                    "agent_role": "cross_verification_agent",
                    "output_contract": "claims,evidence,relationships",
                    "depends_on": "",
                },
                {
                    "id": "job-analysis",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 1,
                    "status": "QUEUED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "cross_verification",
                },
            ],
        )
        evidence_record = store.add_evidence_record(
            investigation.id,
            "https://www.example-target.test/en/contact",
            "official_website",
            "seed",
            "SampleCo contact page lists xs@csituo.com.",
            0.82,
        )
        store.add_entity(investigation.id, "company", "Sample Auto Parts Co.", "seed", 0.9)
        store.add_entity(investigation.id, "domain", "example-target.test", "seed", 0.82)
        store.add_entity(investigation.id, "email", "xs@csituo.com", "seed", 0.82)
        store.add_evidence(investigation.id, "xs@csituo.com", "official_contact", "seed", "Official contact page lists xs@csituo.com.")
        store.add_relationship(investigation.id, "Sample Auto Parts Co.", "xs@csituo.com", "uses_business_email", 0.82)

        result = run_investigation_jobs(store, investigation.id, max_jobs=5, artifact_root=Path("/tmp/unused"))
        detail = store.get_investigation(investigation.id)

        self.assertGreaterEqual(result["role_completed"], 2)
        self.assertEqual({job["id"]: job["status"] for job in detail["jobs"]}["job-cross"], "COMPLETED")
        self.assertEqual({job["id"]: job["status"] for job in detail["jobs"]}["job-analysis"], "COMPLETED")
        self.assertTrue(any(fact["evidence_ids"] == [evidence_record["id"]] for fact in detail["facts"]))
        self.assertTrue(detail["hypotheses"])
        self.assertIn("## BLUF", detail["report_markdown"])
        self.assertTrue(any("本地职责 Agent 完成" in event["message"] for event in detail["events"]))

    def test_high_confidence_entities_create_followup_jobs_from_role_agent(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Followup local role agent",
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
                    "id": "job-analysis-completed",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 1,
                    "status": "SKIPPED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "cross_verification",
                }
            ],
        )
        store.add_entity(investigation.id, "domain", "example-target.test", "operator_seed", 0.85)
        store.add_entity(investigation.id, "email", "xs@csituo.com", "operator_seed", 0.8)
        store.add_evidence(investigation.id, "example-target.test", "official_website", "operator_seed", "Operator-confirmed official site.")

        result = run_investigation_jobs(store, investigation.id, max_jobs=1, artifact_root=Path("/tmp/unused"))
        detail = store.get_investigation(investigation.id)
        job_keys = {(job["tool_name"], job["target_type"], job["target_value"]) for job in detail["jobs"]}

        self.assertEqual(result["role_completed"], 1)
        self.assertIn(("theharvester", "domain", "example-target.test"), job_keys)
        self.assertIn(("sherlock", "username", "xs"), job_keys)
        inferred = [
            job for job in detail["jobs"]
            if job["target_value"] in {"example-target.test", "xs"} and job["depends_on"].startswith("inferred_from:")
        ]
        self.assertTrue(inferred)

    def test_collection_role_agent_writes_evidence_ledger_record(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Role evidence ledger",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="deep",
        )
        result = run_role_agent(
            store,
            investigation.id,
            {
                "id": "job-enterprise",
                "investigation_id": investigation.id,
                "tool_name": "candidate_business_discovery",
                "target_type": "company",
                "target_value": "Sample Auto Parts Co.",
                "depth": 1,
                "status": "RUNNING",
                "agent_role": "enterprise_intel_agent",
                "output_contract": "entities,evidence,relationships",
                "depends_on": "",
            },
        )

        detail = store.get_investigation(investigation.id)
        ledger = detail["evidence_ledger"]

        self.assertTrue(result.completed)
        self.assertTrue(ledger)
        self.assertTrue(any(record["source_tool"] == "candidate_business_discovery" for record in ledger))
        self.assertTrue(any(record["source_type"] == "role_agent_collection" for record in ledger))
        self.assertTrue(all(record["admiralty_code"] for record in ledger))

    def test_collection_ledger_allows_cross_verification_to_promote_facts(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Ledger to facts",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="deep",
        )
        collection_result = run_role_agent(
            store,
            investigation.id,
            {
                "id": "job-enterprise",
                "investigation_id": investigation.id,
                "tool_name": "candidate_business_discovery",
                "target_type": "company",
                "target_value": "Sample Auto Parts Co.",
                "depth": 1,
                "status": "RUNNING",
                "agent_role": "enterprise_intel_agent",
                "output_contract": "entities,evidence,relationships",
                "depends_on": "",
            },
        )

        verification_result = run_role_agent(
            store,
            investigation.id,
            {
                "id": "job-cross",
                "investigation_id": investigation.id,
                "tool_name": "cross_verification",
                "target_type": "company",
                "target_value": "Sample Auto Parts Co.",
                "depth": 2,
                "status": "RUNNING",
                "agent_role": "cross_verification_agent",
                "output_contract": "claims,evidence,relationships",
                "depends_on": "candidate_business_discovery",
            },
        )

        detail = store.get_investigation(investigation.id)

        self.assertTrue(collection_result.completed)
        self.assertTrue(verification_result.completed)
        self.assertTrue(detail["facts"])
        self.assertTrue(any(fact["evidence_ids"] for fact in detail["facts"]))
        self.assertTrue(any(fact["status"] in {"LIKELY", "CONFIRMED"} for fact in detail["facts"]))

    def test_collection_role_extracts_business_and_decision_candidates_from_sparse_lead_anchors(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Sparse lead candidate enrichment",
            seed_type="sparse_lead",
            seed_value="Sample Sparse Lead / Contact A",
            strategy_name="deep",
            metadata={
                "lead_display_name": "Contact A",
                "company_name_raw": "Sample Sparse Lead",
                "privacy_state": "email_hidden_phone_hidden",
                "categories": ["Auto Parts", "Truck Spare Parts"],
            },
        )

        result = run_role_agent(
            store,
            investigation.id,
            {
                "id": "job-enterprise",
                "investigation_id": investigation.id,
                "tool_name": "candidate_business_discovery",
                "target_type": "sparse_lead",
                "target_value": "Sample Sparse Lead / Contact A",
                "depth": 1,
                "status": "RUNNING",
                "agent_role": "enterprise_intel_agent",
                "output_contract": "entities,evidence,relationships",
                "depends_on": "",
            },
        )

        detail = store.get_investigation(investigation.id)
        entity_pairs = {(item["type"], item["value"]) for item in detail["entities"]}

        self.assertTrue(result.completed)
        self.assertIn(("business_scope", "Auto Parts"), entity_pairs)
        self.assertIn(("business_scope", "Truck Spare Parts"), entity_pairs)
        self.assertIn(("identity", "Contact A"), entity_pairs)
        self.assertNotIn(("email", "email_hidden_phone_hidden"), entity_pairs)
        self.assertNotIn(("phone", "email_hidden_phone_hidden"), entity_pairs)

    def test_low_confidence_entities_do_not_create_followup_jobs(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Low confidence followup",
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
                    "id": "job-analysis-completed",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 1,
                    "status": "SKIPPED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "cross_verification",
                },
            ],
        )
        store.add_entity(investigation.id, "domain", "maybe-srr.example", "weak_source", 0.52)

        result = run_investigation_jobs(store, investigation.id, max_jobs=6, artifact_root=Path("/tmp/unused"))
        detail = store.get_investigation(investigation.id)
        job_keys = {(job["tool_name"], job["target_type"], job["target_value"]) for job in detail["jobs"]}

        inferred_jobs = [job for job in detail["jobs"] if job["depends_on"].startswith("inferred_from:")]
        self.assertFalse(inferred_jobs)
        self.assertNotIn(("theharvester", "domain", "maybe-srr.example"), job_keys)

    def test_worker_executes_new_followup_jobs_within_same_run_budget(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Iterative followup",
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
                    "id": "job-analysis-completed",
                    "investigation_id": investigation.id,
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Sample Auto Parts Co.",
                    "depth": 1,
                    "status": "SKIPPED",
                    "agent_role": "analysis_judgement_agent",
                    "output_contract": "claims,graph_slots,report",
                    "depends_on": "cross_verification",
                },
            ],
        )
        store.add_entity(investigation.id, "domain", "example-target.test", "operator_seed", 0.85)
        store.add_evidence(investigation.id, "example-target.test", "official_website", "operator_seed", "Operator-confirmed official site.")

        with TemporaryDirectory() as tmpdir:
            result = run_investigation_jobs(
                store,
                investigation.id,
                max_jobs=2,
                artifact_root=Path(tmpdir),
                adapter_factory=lambda name: DomainFollowupAdapter() if name == "theharvester" else (_raise_missing(name)),
            )

        detail = store.get_investigation(investigation.id)
        statuses = {(job["tool_name"], job["target_value"]): job["status"] for job in detail["jobs"]}

        self.assertGreaterEqual(result["role_completed"], 1)
        self.assertGreaterEqual(result["completed"], 1)
        self.assertEqual(statuses[("theharvester", "example-target.test")], "COMPLETED")
        self.assertIn(("email", "sales@example-target.test"), {(item["type"], item["value"]) for item in detail["entities"]})


def _raise_missing(name: str):
    raise RuntimeError(f"unexpected adapter: {name}")


if __name__ == "__main__":
    unittest.main()
