import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
import json
from unittest.mock import patch
from urllib.error import HTTPError

from app import main as app_main
from app.main import ApiHandler
from app.services.store import Investigation, Job, MemoryStore, SQLiteStore, create_default_store
from app.services.worker import run_investigation_jobs


class AgentProtocolTests(unittest.TestCase):
    def test_external_agent_claims_open_task_by_capability(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="example.com 深度调查",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="deep",
        )
        agent = store.register_agent(
            agent_name="codex-desktop",
            agent_type="codex",
            capabilities=["domain", "theharvester", "amass"],
        )

        claimed = store.claim_task(
            agent_id=agent.id,
            capabilities=["domain", "theharvester"],
        )

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["id"], investigation.id)
        self.assertEqual(claimed["status"], "CLAIMED")
        self.assertEqual(claimed["claimed_by_agent_id"], agent.id)
        self.assertEqual(store.get_investigation(investigation.id)["status"], "CLAIMED")

    def test_agent_writes_events_entities_evidence_relationships_and_report(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="example.com 深度调查",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="deep",
        )
        agent = store.register_agent(
            agent_name="open-human-production-host",
            agent_type="openhuman",
            capabilities=["domain", "sherlock", "amass"],
        )
        store.claim_task(agent.id, ["domain"])

        event = store.add_event(
            investigation_id=investigation.id,
            agent_id=agent.id,
            level="info",
            message="开始运行 Amass",
            metadata={"tool": "amass"},
        )
        entity = store.add_entity(
            investigation_id=investigation.id,
            entity_type="subdomain",
            value="vpn.example.com",
            source_tool="amass",
            confidence=0.72,
        )
        evidence = store.add_evidence(
            investigation_id=investigation.id,
            entity_value="vpn.example.com",
            evidence_kind="dns_resolution",
            source_tool="amass",
            snippet="A record resolved",
        )
        relationship = store.add_relationship(
            investigation_id=investigation.id,
            from_value="example.com",
            to_value="vpn.example.com",
            relationship_type="domain_has_subdomain",
            confidence=0.8,
        )
        store.complete_task(
            investigation_id=investigation.id,
            agent_id=agent.id,
            status="COMPLETED",
            summary="发现 1 个子域名",
            report_markdown="# 报告\n\n发现 vpn.example.com",
            confidence=0.81,
        )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(event["message"], "开始运行 Amass")
        self.assertEqual(entity["value"], "vpn.example.com")
        self.assertEqual(evidence["entity_value"], "vpn.example.com")
        self.assertEqual(relationship["relationship_type"], "domain_has_subdomain")
        self.assertEqual(detail["status"], "NEEDS_REVIEW")
        self.assertEqual(detail["summary"], "发现 1 个子域名")
        self.assertEqual(detail["confidence"], 0.81)
        self.assertFalse(detail["quality_assessment"]["completion_ready"])
        self.assertIn("## BLUF", detail["report_markdown"])
        self.assertIn("开始运行 Amass", {item["message"] for item in detail["events"]})
        self.assertEqual(len(detail["entities"]), 1)
        self.assertEqual(len(detail["evidence"]), 1)
        self.assertEqual(len(detail["relationships"]), 1)

    def test_sqlite_store_persists_core_v2_protocol_data_across_instances(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "osint.sqlite"
            first_store = SQLiteStore(str(db_path))
            investigation = first_store.create_investigation(
                name="SampleCo core v2",
                seed_type="company",
                seed_value="Sample Auto Parts Co.",
                strategy_name="deep",
            )
            evidence = first_store.add_evidence_record(
                investigation_id=investigation.id,
                source_url="https://www.example-target.test/en/",
                source_type="official_website",
                source_tool="official_web",
                snippet="SampleCo contact page lists xs@csituo.com.",
                credibility=0.82,
            )
            first_store.add_fact(
                investigation_id=investigation.id,
                statement="SampleCo uses xs@csituo.com as a public contact email.",
                subject="Sample Auto Parts Co.",
                predicate="uses_contact_email",
                object_value="xs@csituo.com",
                status="CONFIRMED",
                confidence=0.82,
                admiralty_code=evidence["admiralty_code"],
                evidence_ids=[evidence["id"]],
            )
            first_store.add_hypothesis(
                investigation.id,
                "h1",
                "SampleCo is an active export brand network.",
            )
            first_store.score_hypotheses(
                investigation.id,
                [
                    {
                        "id": "ev-export",
                        "summary": "MIMS exhibitor page shows SampleCo export contact.",
                        "kinds": ["company_news_report"],
                        "supports": ["h1"],
                        "contradicts": [],
                        "source_reliability": "B",
                        "credibility": 0.72,
                        "keywords": ["export"],
                    }
                ],
            )

            detail = SQLiteStore(str(db_path)).get_investigation(investigation.id)

        self.assertEqual(len(detail["evidence_ledger"]), 1)
        self.assertEqual(detail["facts"][0]["object"], "xs@csituo.com")
        self.assertEqual(detail["hypotheses"][0]["id"], "h1")
        self.assertEqual(detail["hypothesis_analysis"]["most_likely_hypothesis"], "h1")

    def test_sqlite_import_detail_preserves_core_v2_protocol_data(self):
        source = MemoryStore()
        investigation = source.create_investigation(
            name="SampleCo imported core v2",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="deep",
        )
        evidence = source.add_evidence_record(
            investigation_id=investigation.id,
            source_url="https://www.example-target.test/en/",
            source_type="official_website",
            source_tool="official_web",
            snippet="SampleCo contact page lists xs@csituo.com.",
            credibility=0.82,
        )
        source.add_fact(
            investigation_id=investigation.id,
            statement="SampleCo uses xs@csituo.com as a public contact email.",
            subject="Sample Auto Parts Co.",
            predicate="uses_contact_email",
            object_value="xs@csituo.com",
            status="CONFIRMED",
            confidence=0.82,
            admiralty_code=evidence["admiralty_code"],
            evidence_ids=[evidence["id"]],
        )
        source.add_hypothesis(investigation.id, "h1", "SampleCo is an active export brand network.")
        source.score_hypotheses(
            investigation.id,
            [
                {
                    "id": "ev-export",
                    "summary": "MIMS exhibitor page shows SampleCo export contact.",
                    "kinds": ["company_news_report"],
                    "supports": ["h1"],
                    "contradicts": [],
                    "source_reliability": "B",
                    "credibility": 0.72,
                    "keywords": ["export"],
                }
            ],
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "osint.sqlite"
            target = SQLiteStore(str(db_path))
            target.import_detail(source.get_investigation(investigation.id))
            detail = SQLiteStore(str(db_path)).get_investigation(investigation.id)

        self.assertEqual(detail["evidence_ledger"][0]["id"], evidence["id"])
        self.assertEqual(detail["facts"][0]["object"], "xs@csituo.com")
        self.assertEqual(detail["hypotheses"][0]["id"], "h1")
        self.assertEqual(detail["hypothesis_analysis"]["most_likely_hypothesis"], "h1")

    def test_memory_store_tracks_core_v2_protocol_data_in_detail(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="SampleCo memory core v2",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="deep",
        )

        evidence = store.add_evidence_record(
            investigation_id=investigation.id,
            source_url="https://www.example-target.test/en/",
            source_type="official_website",
            source_tool="official_web",
            snippet="SampleCo contact page lists xs@csituo.com.",
            credibility=0.82,
        )
        fact = store.add_fact(
            investigation_id=investigation.id,
            statement="SampleCo uses xs@csituo.com as a public contact email.",
            subject="Sample Auto Parts Co.",
            predicate="uses_contact_email",
            object_value="xs@csituo.com",
            status="CONFIRMED",
            confidence=0.82,
            admiralty_code=evidence["admiralty_code"],
            evidence_ids=[evidence["id"]],
        )
        store.add_hypothesis(investigation.id, "h1", "SampleCo is an active export brand network.")
        result = store.score_hypotheses(
            investigation.id,
            [
                {
                    "id": "ev-export",
                    "summary": "MIMS exhibitor page shows SampleCo export contact.",
                    "kinds": ["company_news_report"],
                    "supports": ["h1"],
                    "contradicts": [],
                    "source_reliability": "B",
                    "credibility": 0.72,
                    "keywords": ["export"],
                }
            ],
        )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(detail["evidence_ledger"][0]["id"], evidence["id"])
        self.assertEqual(detail["facts"][0]["id"], fact["id"])
        self.assertEqual(detail["hypotheses"][0]["status"], "MOST_LIKELY")
        self.assertEqual(result["most_likely_hypothesis"], "h1")
        self.assertEqual(detail["hypothesis_analysis"]["most_likely_hypothesis"], "h1")

    def test_agent_http_routes_accept_core_v2_protocol_writes(self):
        memory_store = MemoryStore()
        investigation = memory_store.create_investigation(
            name="SampleCo API core v2",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="deep",
        )
        original_store = app_main.store
        app_main.store = memory_store
        server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            evidence = _post_json(
                f"{base_url}/api/agent/evidence-records",
                {
                    "task_id": investigation.id,
                    "source_url": "https://www.example-target.test/en/",
                    "source_type": "official_website",
                    "source_tool": "official_web",
                    "snippet": "SampleCo contact page lists xs@csituo.com.",
                    "credibility": 0.82,
                },
            )
            _post_json(
                f"{base_url}/api/agent/facts",
                {
                    "task_id": investigation.id,
                    "statement": "SampleCo uses xs@csituo.com as a public contact email.",
                    "subject": "Sample Auto Parts Co.",
                    "predicate": "uses_contact_email",
                    "object": "xs@csituo.com",
                    "status": "CONFIRMED",
                    "confidence": 0.82,
                    "admiralty_code": evidence["admiralty_code"],
                    "evidence_ids": [evidence["id"]],
                },
            )
            _post_json(
                f"{base_url}/api/agent/hypotheses",
                {
                    "task_id": investigation.id,
                    "hypothesis_id": "h1",
                    "statement": "SampleCo is an active export brand network.",
                },
            )
            analysis = _post_json(
                f"{base_url}/api/agent/hypotheses/score",
                {
                    "task_id": investigation.id,
                    "evidence_items": [
                        {
                            "id": "ev-export",
                            "summary": "MIMS exhibitor page shows SampleCo export contact.",
                            "kinds": ["company_news_report"],
                            "supports": ["h1"],
                            "contradicts": [],
                            "source_reliability": "B",
                            "credibility": 0.72,
                            "keywords": ["export"],
                        }
                    ],
                },
            )
        finally:
            server.shutdown()
            server.server_close()
            app_main.store = original_store

        detail = memory_store.get_investigation(investigation.id)
        self.assertEqual(detail["facts"][0]["object"], "xs@csituo.com")
        self.assertEqual(detail["hypothesis_analysis"]["most_likely_hypothesis"], "h1")
        self.assertEqual(analysis["most_likely_hypothesis"], "h1")

    def test_agent_http_rejects_invalid_entity_payload(self):
        status, payload = _post_json_expect_error(
            "/api/agent/entities",
            {"task_id": "task-1", "entities": [{"type": "domain", "value": "", "source_tool": "agent", "confidence": 1.2}]},
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["detail"], "validation failed")
        self.assertTrue(any("entities[0].value is required" in error for error in payload["errors"]))
        self.assertTrue(any("entities[0].confidence must be between 0 and 1" in error for error in payload["errors"]))

    def test_agent_http_rejects_oversized_body_before_business_logic(self):
        with patch.dict("os.environ", {"MAX_REQUEST_BODY_BYTES": "2"}):
            status, payload = _post_json_expect_error(
                "/api/investigations",
                {"name": "too large"},
            )

        self.assertEqual(status, 413)
        self.assertEqual(payload["detail"], "request body too large")

    def test_agent_http_rejects_invalid_evidence_payload(self):
        status, payload = _post_json_expect_error(
            "/api/agent/evidence",
            {"task_id": "task-1", "entity_value": "example.com", "evidence_kind": "", "source_tool": "agent", "snippet": ""},
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["detail"], "validation failed")
        self.assertTrue(any("evidence_kind is required" in error for error in payload["errors"]))
        self.assertTrue(any("snippet is required" in error for error in payload["errors"]))

    def test_agent_http_rejects_invalid_evidence_record_source_type(self):
        status, payload = _post_json_expect_error(
            "/api/agent/evidence-records",
            {
                "task_id": "task-1",
                "source_url": "https://example.com",
                "source_type": "private_database",
                "source_tool": "agent",
                "snippet": "Example evidence",
                "credibility": 0.7,
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["detail"], "validation failed")
        self.assertTrue(any("source_type is invalid" in error for error in payload["errors"]))

    def test_agent_http_rejects_confirmed_fact_without_evidence_ids(self):
        status, payload = _post_json_expect_error(
            "/api/agent/facts",
            {
                "task_id": "task-1",
                "statement": "Example LLC operates example.com.",
                "subject": "Example LLC",
                "predicate": "has_domain",
                "object": "example.com",
                "status": "CONFIRMED",
                "confidence": 0.8,
                "admiralty_code": "A-2",
                "evidence_ids": [],
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["detail"], "validation failed")
        self.assertTrue(any("evidence_ids is required for confirmed or likely facts" in error for error in payload["errors"]))

    def test_agent_http_rejects_invalid_relationship_payload(self):
        status, payload = _post_json_expect_error(
            "/api/agent/relationships",
            {"task_id": "task-1", "from": "Example LLC", "to": "", "relationship_type": "", "confidence": -0.1},
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["detail"], "validation failed")
        self.assertTrue(any("to is required" in error for error in payload["errors"]))
        self.assertTrue(any("relationship_type is required" in error for error in payload["errors"]))
        self.assertTrue(any("confidence must be between 0 and 1" in error for error in payload["errors"]))

    def test_claim_skips_task_when_agent_capabilities_do_not_match_seed_type(self):
        store = MemoryStore()
        store.create_investigation(
            name="example.com 深度调查",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="deep",
        )
        agent = store.register_agent(
            agent_name="username-only-agent",
            agent_type="cli",
            capabilities=["username", "sherlock"],
        )

        self.assertIsNone(store.claim_task(agent.id, ["username", "sherlock"]))

    def test_company_investigation_jobs_include_agent_roles_and_output_contracts(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="美国企业背调：Sample Hospitality LLC / Sample Contact",
            seed_type="company",
            seed_value="Sample Hospitality LLC / Sample Contact",
            strategy_name="deep",
        )

        jobs = store.get_investigation(investigation.id)["jobs"]
        roles = {job["agent_role"] for job in jobs}
        self.assertIn("enterprise_intel_agent", roles)
        self.assertIn("analysis_judgement_agent", roles)
        analysis_job = next(job for job in jobs if job["tool_name"] == "analysis_judgement")
        self.assertEqual(analysis_job["target_type"], "company")
        self.assertIn("claims", analysis_job["output_contract"])
        self.assertIn("graph_slots", analysis_job["output_contract"])
        self.assertIn("cross_verification", analysis_job["depends_on"])

    def test_memory_store_creates_sparse_lead_with_metadata(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Alibaba 买家弱线索：Sample Lead",
            seed_type="sparse_lead",
            seed_value="Sample Lead / member-redacted",
            strategy_name="deep",
            metadata={
                "platform": "Alibaba",
                "lead_display_name": "Sample Lead",
                "member_id": "member-redacted",
                "country_region": "IN",
            },
        )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(detail["seed_type"], "sparse_lead")
        self.assertEqual(detail["metadata"]["platform"], "Alibaba")
        self.assertEqual(detail["metadata"]["member_id"], "member-redacted")

    def test_sqlite_store_persists_sparse_lead_metadata(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "osint.sqlite"
            first_store = SQLiteStore(str(db_path))
            investigation = first_store.create_investigation(
                name="Alibaba 买家弱线索：Sample Lead",
                seed_type="sparse_lead",
                seed_value="Sample Lead / member-redacted",
                strategy_name="deep",
                metadata={
                    "platform": "Alibaba",
                    "lead_display_name": "Sample Lead",
                    "member_id": "member-redacted",
                    "country_region": "IN",
                    "categories": ["Induction Cookers", "Gas Cooktops"],
                },
            )

            second_store = SQLiteStore(str(db_path))
            detail = second_store.get_investigation(investigation.id)

        self.assertEqual(detail["metadata"]["platform"], "Alibaba")
        self.assertEqual(detail["metadata"]["categories"], ["Induction Cookers", "Gas Cooktops"])

    def test_sparse_lead_investigation_jobs_include_agent_roles_and_contracts(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Alibaba 买家弱线索：Sample Lead",
            seed_type="sparse_lead",
            seed_value="Sample Lead / member-redacted",
            strategy_name="deep",
            metadata={"platform": "Alibaba", "member_id": "member-redacted"},
        )

        jobs = store.get_investigation(investigation.id)["jobs"]
        anchor_job = next(job for job in jobs if job["tool_name"] == "lead_anchor_extraction")
        match_job = next(job for job in jobs if job["tool_name"] == "identity_match_review")

        self.assertEqual(anchor_job["agent_role"], "tool_agent")
        self.assertIn("platform anchors", anchor_job["output_contract"])
        self.assertEqual(match_job["agent_role"], "cross_verification_agent")
        self.assertIn("identity_match_confidence", match_job["output_contract"])

    def test_legacy_company_like_task_gets_orchestration_jobs_on_detail_load(self):
        store = MemoryStore()
        investigation = Investigation(
            id="legacy-family-hospitality",
            name="美国企业背调：Sample Hospitality LLC / Sample Contact",
            seed_type="username",
            seed_value="Sample Hospitality LLC / Sample Contact",
            strategy="deep",
            status="NEEDS_REVIEW",
            created_at="2026-05-19T00:00:00+00:00",
            updated_at="2026-05-19T00:00:00+00:00",
            max_depth=5,
            max_jobs=250,
            max_entities=2500,
        )
        store.investigations[investigation.id] = investigation
        store.jobs["legacy-tool-job"] = Job(
            id="legacy-tool-job",
            investigation_id=investigation.id,
            tool_name="maigret",
            target_type="username",
            target_value="Sample Contact",
            depth=0,
            status="COMPLETED",
        )

        detail = store.get_investigation(investigation.id)

        roles = {job["agent_role"] for job in detail["jobs"]}
        self.assertIn("analysis_judgement_agent", roles)
        self.assertIn("enterprise_intel_agent", roles)
        self.assertIn("tool_agent", roles)
        self.assertEqual(
            len([job for job in detail["jobs"] if job["tool_name"] == "analysis_judgement"]),
            1,
        )

    def test_sqlite_store_persists_agent_protocol_data_across_instances(self):
        with TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"SPIDERFOOT_BASE_URL": "http://127.0.0.1:5001", "RECONNG_COMMAND": "/opt/recon-ng/recon-ng"},
        ):
            db_path = Path(tmpdir) / "osint.sqlite"
            first_store = SQLiteStore(str(db_path))
            investigation = first_store.create_investigation(
                name="example.com 深度调查",
                seed_type="domain",
                seed_value="example.com",
                strategy_name="deep",
            )
            agent = first_store.register_agent(
                agent_name="codex-desktop",
                agent_type="codex",
                capabilities=["domain", "amass"],
            )
            first_store.claim_task(agent.id, ["domain"])
            first_store.add_event(
                investigation_id=investigation.id,
                agent_id=agent.id,
                level="info",
                message="开始运行 Amass",
                metadata={"tool": "amass"},
            )
            first_store.add_entity(
                investigation_id=investigation.id,
                entity_type="subdomain",
                value="vpn.example.com",
                source_tool="amass",
                confidence=0.72,
            )
            first_store.add_evidence(
                investigation_id=investigation.id,
                entity_value="vpn.example.com",
                evidence_kind="dns_resolution",
                source_tool="amass",
                snippet="A record resolved",
            )
            first_store.add_relationship(
                investigation_id=investigation.id,
                from_value="example.com",
                to_value="vpn.example.com",
                relationship_type="domain_has_subdomain",
                confidence=0.8,
            )
            first_store.complete_task(
                investigation_id=investigation.id,
                agent_id=agent.id,
                status="COMPLETED",
                summary="发现 1 个子域名",
                report_markdown="# 报告\n\n发现 vpn.example.com",
                confidence=0.81,
            )

            second_store = SQLiteStore(str(db_path))
            detail = second_store.get_investigation(investigation.id)
            agents = second_store.list_agents()

            self.assertEqual(detail["status"], "NEEDS_REVIEW")
            self.assertEqual(detail["summary"], "发现 1 个子域名")
            self.assertEqual(detail["confidence"], 0.81)
            self.assertFalse(detail["quality_assessment"]["completion_ready"])
            self.assertIn("## BLUF", detail["report_markdown"])
            self.assertEqual(detail["claimed_by_agent_name"], "codex-desktop")
            self.assertEqual(len(detail["jobs"]), 6)
            self.assertEqual(len(detail["events"]), 1)
            self.assertEqual(len(detail["entities"]), 1)
            self.assertEqual(len(detail["evidence"]), 1)
            self.assertEqual(len(detail["relationships"]), 1)
            self.assertEqual(agents[0]["agent_name"], "codex-desktop")

    def test_default_sqlite_store_uses_project_data_directory(self):
        store = create_default_store()

        self.assertEqual(store.db_path, str(Path.cwd() / "data" / "osint.sqlite"))

    def test_investigation_detail_includes_job_counts_and_risk_report(self):
        with patch.dict(
            "os.environ",
            {"SPIDERFOOT_BASE_URL": "http://127.0.0.1:5001", "RECONNG_COMMAND": "/opt/recon-ng/recon-ng"},
        ):
            store = MemoryStore()
            investigation = store.create_investigation(
                name="admin 风险复核",
                seed_type="username",
                seed_value="admin",
                strategy_name="standard",
            )
        store.save_risk_report(
            investigation.id,
            {
                "overall_risk_score": 42,
                "overall_risk_level": "medium",
                "review_required": True,
            },
        )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(detail["job_counts"]["QUEUED"], 3)
        self.assertEqual(detail["risk_report"]["overall_risk_score"], 42)

    def test_task_lifecycle_cancel_reopen_and_retry(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="example.com 深度调查",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="deep",
        )

        cancelled = store.cancel_task(investigation.id)
        self.assertEqual(cancelled["status"], "CANCELLED")

        reopened = store.reopen_task(investigation.id)
        self.assertEqual(reopened["status"], "OPEN")
        self.assertIsNone(reopened["claimed_by_agent_id"])
        self.assertIsNone(reopened["claimed_by_agent_name"])

        failed = store.complete_task(
            investigation_id=investigation.id,
            agent_id="missing-agent",
            status="FAILED",
            summary="工具失败",
            report_markdown="",
            confidence=None,
        )
        self.assertEqual(failed["status"], "FAILED")

        retried = store.retry_task(investigation.id)
        self.assertEqual(retried["status"], "OPEN")
        self.assertEqual(retried["summary"], "")
        self.assertIsNone(retried["confidence"])
        self.assertTrue(all(job["status"] == "QUEUED" for job in retried["jobs"]))

    def test_releases_stale_claims_to_open(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="example.com 深度调查",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="deep",
        )
        agent = store.register_agent(
            agent_name="stale-agent",
            agent_type="cli",
            capabilities=["domain"],
        )
        store.claim_task(agent.id, ["domain"])
        store.set_investigation_updated_at(investigation.id, "2026-05-19T00:00:00+00:00")

        released = store.release_stale_claims(
            now_iso="2026-05-19T00:31:00+00:00",
            stale_after_seconds=1800,
        )
        detail = store.get_investigation(investigation.id)

        self.assertEqual(released, 1)
        self.assertEqual(detail["status"], "OPEN")
        self.assertIsNone(detail["claimed_by_agent_id"])
        self.assertIsNone(detail["claimed_by_agent_name"])

    def test_sqlite_persists_lifecycle_changes(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "osint.sqlite"
            store = SQLiteStore(str(db_path))
            investigation = store.create_investigation(
                name="example.com 深度调查",
                seed_type="domain",
                seed_value="example.com",
                strategy_name="deep",
            )
            agent = store.register_agent(
                agent_name="stale-agent",
                agent_type="cli",
                capabilities=["domain"],
            )
            store.claim_task(agent.id, ["domain"])
            store.set_investigation_updated_at(investigation.id, "2026-05-19T00:00:00+00:00")

            released = store.release_stale_claims(
                now_iso="2026-05-19T00:31:00+00:00",
                stale_after_seconds=1800,
            )
            failed = store.complete_task(
                investigation_id=investigation.id,
                agent_id=agent.id,
                status="FAILED",
                summary="工具失败",
                report_markdown="失败报告",
                confidence=0.2,
            )
            retried = store.retry_task(investigation.id)
            persisted = SQLiteStore(str(db_path)).get_investigation(investigation.id)

            self.assertEqual(released, 1)
            self.assertEqual(failed["status"], "FAILED")
            self.assertEqual(retried["status"], "OPEN")
            self.assertEqual(persisted["status"], "OPEN")
            self.assertEqual(persisted["summary"], "")
            self.assertIsNone(persisted["confidence"])
            self.assertTrue(all(job["status"] == "QUEUED" for job in persisted["jobs"]))

    def test_archive_hides_task_from_default_list_but_keeps_detail(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="example.com 深度调查",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="deep",
        )

        archived = store.archive_task(investigation.id)

        self.assertEqual(archived["status"], "ARCHIVED")
        self.assertEqual(store.list_investigations(), [])
        self.assertEqual(len(store.list_investigations(include_archived=True)), 1)
        self.assertEqual(store.get_investigation(investigation.id)["status"], "ARCHIVED")

    def test_delete_removes_task_and_child_rows(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="example.com 深度调查",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="deep",
        )
        store.add_entity(
            investigation_id=investigation.id,
            entity_type="subdomain",
            value="vpn.example.com",
            source_tool="amass",
            confidence=0.72,
        )

        deleted = store.delete_task(investigation.id)

        self.assertTrue(deleted)
        self.assertIsNone(store.get_investigation(investigation.id))
        self.assertEqual(store.list_investigations(include_archived=True), [])

    def test_sqlite_persists_archive_and_delete(self):
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "osint.sqlite"
            store = SQLiteStore(str(db_path))
            archived_task = store.create_investigation(
                name="archived.example 调查",
                seed_type="domain",
                seed_value="archived.example",
                strategy_name="quick",
            )
            deleted_task = store.create_investigation(
                name="deleted.example 调查",
                seed_type="domain",
                seed_value="deleted.example",
                strategy_name="quick",
            )

            store.archive_task(archived_task.id)
            deleted = store.delete_task(deleted_task.id)
            reloaded = SQLiteStore(str(db_path))

            self.assertTrue(deleted)
            self.assertEqual(reloaded.list_investigations(), [])
            self.assertEqual(len(reloaded.list_investigations(include_archived=True)), 1)
            self.assertEqual(reloaded.get_investigation(archived_task.id)["status"], "ARCHIVED")
            self.assertIsNone(reloaded.get_investigation(deleted_task.id))


def _post_json(url: str, payload: dict) -> dict:
    encoded = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=encoded,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json_expect_error(path: str, payload: dict) -> tuple[int, dict]:
    memory_store = MemoryStore()
    original_store = app_main.store
    app_main.store = memory_store
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        request = Request(
            f"{base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()
    finally:
        server.shutdown()
        server.server_close()
        app_main.store = original_store


if __name__ == "__main__":
    unittest.main()
