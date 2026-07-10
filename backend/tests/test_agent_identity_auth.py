import os
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from backend.tests.test_agent_auth import (
    ApiTestServer,
    PRODUCTION_ENV,
    cookie_from_set_cookie,
    header_value,
    json_payload,
)
from app import main as app_main
from app.core.agent_auth import (
    AGENT_ACTION_TIERS,
    AgentPrincipal,
    generate_agent_token,
    hash_agent_token,
)
from app.services.store import MemoryStore, SQLiteStore


VALID_TIERS = ("reader", "verifier", "reporter", "tool_agent")


class AgentIdentityStoreContract:
    def make_store(self):
        raise NotImplementedError

    def setUp(self):
        self.store_context = self.make_store()
        self.store = self.store_context.__enter__()

    def tearDown(self):
        self.store_context.__exit__(None, None, None)

    def register(self, name="reader-1", role_tier="reader", capabilities=None):
        return self.store.register_agent(
            agent_name=name,
            agent_type="codex",
            capabilities=["company"] if capabilities is None else capabilities,
            role_tier=role_tier,
        )

    def disable_agent(self, agent_id):
        raise NotImplementedError

    def stored_token_hash(self, agent_id):
        raise NotImplementedError

    def clear_agent_token(self, agent_id):
        raise NotImplementedError

    def clear_agent_role(self, agent_id):
        raise NotImplementedError

    def internal_agent_state(self, agent_id):
        raise NotImplementedError

    def tool_output_storage_failure(self):
        raise NotImplementedError

    def tool_output_submission_stores(self):
        return (self.store, self.store)

    def create_tool_output_claim(self, suffix):
        registration = self.register(
            name=f"amass-tool-{suffix}",
            role_tier="tool_agent",
            capabilities=["amass"],
        )
        investigation = self.store.create_investigation(
            name=f"Atomic tool output {suffix}",
            seed_type="domain",
            seed_value=f"{suffix}.example",
            strategy_name="quick",
        )
        job_id = f"amass-{suffix}-job"
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": job_id,
                    "tool_name": "amass",
                    "target_type": "domain",
                    "target_value": f"{suffix}.example",
                    "depth": 0,
                    "agent_role": "tool_agent",
                    "output_contract": "entities,evidence,relationships",
                }
            ],
        )
        claimed = self.store.claim_job(registration["id"], ["amass"])
        self.assertEqual(claimed["id"], job_id)
        payload = {
            "task_id": investigation.id,
            "tool": "amass",
            "event": {"level": "info", "message": "amass completed", "metadata": {}},
            "entities": [
                {
                    "type": "domain",
                    "value": f"found.{suffix}.example",
                    "source_tool": "amass",
                    "confidence": 0.8,
                }
            ],
            "evidence": [
                {
                    "entity_value": f"found.{suffix}.example",
                    "evidence_kind": "dns_resolution",
                    "source_tool": "amass",
                    "snippet": "Resolved publicly",
                }
            ],
            "relationships": [
                {
                    "from": f"{suffix}.example",
                    "to": f"found.{suffix}.example",
                    "relationship_type": "domain_has_subdomain",
                    "confidence": 0.8,
                }
            ],
        }
        return registration, investigation, job_id, payload

    def test_registration_validates_identity_fields_and_capabilities_before_token_generation(self):
        invalid_registrations = (
            {"agent_name": "", "agent_type": "codex", "capabilities": []},
            {"agent_name": "   ", "agent_type": "codex", "capabilities": []},
            {"agent_name": " padded ", "agent_type": "codex", "capabilities": []},
            {"agent_name": 7, "agent_type": "codex", "capabilities": []},
            {"agent_name": "n" * 129, "agent_type": "codex", "capabilities": []},
            {"agent_name": "valid", "agent_type": "", "capabilities": []},
            {"agent_name": "valid", "agent_type": "   ", "capabilities": []},
            {"agent_name": "valid", "agent_type": " padded ", "capabilities": []},
            {"agent_name": "valid", "agent_type": None, "capabilities": []},
            {"agent_name": "valid", "agent_type": "t" * 129, "capabilities": []},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": "company"},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": 1},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": {}},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": [1]},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": [["company"]]},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": [""]},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": ["   "]},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": [" padded "]},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": ["c" * 129]},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": ["c"] * 65},
            {"agent_name": "\ud800", "agent_type": "codex", "capabilities": []},
            {"agent_name": "\udc00", "agent_type": "codex", "capabilities": []},
            {"agent_name": "valid", "agent_type": "\ud800", "capabilities": []},
            {"agent_name": "valid", "agent_type": "\udc00", "capabilities": []},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": ["\ud800"]},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": ["\udc00"]},
        )
        with patch("app.services.store.generate_agent_token") as generate_token:
            for registration in invalid_registrations:
                with self.subTest(registration=registration):
                    with self.assertRaisesRegex(ValueError, "agent|capabilit") as context:
                        self.store.register_agent(role_tier="reader", **registration)
                    self.assertNotIn(str(registration), str(context.exception))

        generate_token.assert_not_called()
        self.assertEqual(self.store.list_agents(), [])
        valid = self.register(name="no-capabilities", capabilities=[])
        self.assertEqual(valid["capabilities"], [])

    def test_registration_requires_an_explicit_exact_role_tier(self):
        for invalid in (None, "", " reader", "reader ", "Reader", "admin", 1):
            with self.subTest(role_tier=invalid):
                with self.assertRaisesRegex((TypeError, ValueError), "role"):
                    self.register(name=f"invalid-{invalid!r}", role_tier=invalid)
        with self.assertRaisesRegex(TypeError, "role_tier"):
            self.store.register_agent("missing", "codex", ["company"])
        self.assertEqual(self.store.list_agents(), [])
        for role_tier in VALID_TIERS:
            with self.subTest(valid_role_tier=role_tier):
                registration = self.register(name=f"valid-{role_tier}", role_tier=role_tier)
                self.assertEqual(registration["role_tier"], role_tier)

    def test_registration_returns_token_once_and_public_views_never_expose_credentials(self):
        registration = self.register()

        self.assertIsInstance(registration, dict)
        self.assertEqual(registration["role_tier"], "reader")
        self.assertIn("agent_token", registration)
        self.assertNotIn(registration["agent_token"], repr(registration))
        resolved = self.store.resolve_agent_token(registration["agent_token"])
        self.assertEqual(resolved["id"], registration["id"])

        for public_agent in (
            self.store.list_agents()[0],
            self.store.heartbeat_agent(registration["id"]),
            resolved,
        ):
            self.assertNotIn("agent_token", public_agent)
            self.assertNotIn("token_hash", public_agent)
            self.assertEqual(public_agent["role_tier"], "reader")

    def test_only_sha256_hash_is_stored(self):
        registration = self.register()
        stored_hash = self.stored_token_hash(registration["id"])

        self.assertEqual(stored_hash, hash_agent_token(registration["agent_token"]))
        self.assertRegex(stored_hash, r"^[0-9a-f]{64}$")
        self.assertNotEqual(stored_hash, registration["agent_token"])

    def test_token_resolution_rejects_invalid_legacy_and_disabled_credentials(self):
        registration = self.register()
        for invalid in (None, "", b"token", 123, "wrong"):
            with self.subTest(token=invalid):
                self.assertIsNone(self.store.resolve_agent_token(invalid))

        legacy = self.register(name="legacy-null")
        self.clear_agent_token(legacy["id"])
        self.assertIsNone(self.store.resolve_agent_token(legacy["agent_token"]))

        self.disable_agent(registration["id"])
        self.assertIsNone(self.store.resolve_agent_token(registration["agent_token"]))

    def test_rotation_returns_new_token_once_and_invalidates_old_token(self):
        registration = self.register()

        rotated = self.store.rotate_agent_token(registration["id"])

        self.assertEqual(rotated["agent_id"], registration["id"])
        self.assertIn("agent_token", rotated)
        self.assertNotEqual(rotated["agent_token"], registration["agent_token"])
        self.assertIsNone(self.store.resolve_agent_token(registration["agent_token"]))
        self.assertEqual(
            self.store.resolve_agent_token(rotated["agent_token"])["id"],
            registration["id"],
        )
        self.assertIsNone(self.store.rotate_agent_token("missing"))

    def test_registration_and_rotation_bound_token_collision_retries(self):
        token = "fixed-token"
        with patch("app.services.store.generate_agent_token", return_value=token):
            first = self.register(name="first")
            self.assertEqual(first["agent_token"], token)
            with self.assertRaisesRegex(RuntimeError, "credential") as context:
                self.register(name="second")
            self.assertNotIn(token, str(context.exception))
            with self.assertRaisesRegex(RuntimeError, "credential"):
                self.store.rotate_agent_token(first["id"])

        self.assertEqual(len(self.store.list_agents()), 1)
        self.assertEqual(
            self.store.resolve_agent_token(first["agent_token"])["id"],
            first["id"],
        )

    def test_reregistering_same_name_reuses_identity_and_invalidates_old_token(self):
        first = self.register(name="stable-name", role_tier="reader")
        second = self.register(name="stable-name", role_tier="reporter")
        case_variant = self.register(name="Stable-name", role_tier="reader")

        self.assertEqual(second["id"], first["id"])
        self.assertNotEqual(case_variant["id"], first["id"])
        self.assertEqual(second["role_tier"], "reporter")
        self.assertEqual(len(self.store.list_agents()), 2)
        self.assertIsNone(self.store.resolve_agent_token(first["agent_token"]))
        self.assertEqual(
            self.store.resolve_agent_token(second["agent_token"])["id"],
            first["id"],
        )

    def test_disabled_and_legacy_agents_cannot_heartbeat_or_rotate(self):
        disabled = self.register(name="disabled")
        self.disable_agent(disabled["id"])
        disabled_before = self.internal_agent_state(disabled["id"])

        legacy = self.register(name="legacy-roleless")
        self.clear_agent_role(legacy["id"])
        legacy_before = self.internal_agent_state(legacy["id"])

        with patch("app.services.store.generate_agent_token") as generate_token:
            self.assertIsNone(self.store.heartbeat_agent(disabled["id"]))
            self.assertIsNone(self.store.rotate_agent_token(disabled["id"]))
            self.assertIsNone(self.store.heartbeat_agent(legacy["id"]))
            self.assertIsNone(self.store.rotate_agent_token(legacy["id"]))

        generate_token.assert_not_called()
        self.assertEqual(self.internal_agent_state(disabled["id"]), disabled_before)
        self.assertEqual(self.internal_agent_state(legacy["id"]), legacy_before)

        reenabled = self.register(name="disabled", role_tier="verifier")
        self.assertEqual(reenabled["id"], disabled["id"])
        self.assertIsNotNone(self.store.heartbeat_agent(disabled["id"]))
        self.assertIsNotNone(self.store.rotate_agent_token(disabled["id"]))

    def create_access_claims(self):
        job_claimed = self.store.create_investigation(
            name="Job claimed", seed_type="domain", seed_value="example.com", strategy_name="standard"
        )
        claimed = self.store.create_investigation(
            name="Claimed", seed_type="company", seed_value="Claimed LLC", strategy_name="standard"
        )
        unrelated = self.store.create_investigation(
            name="Other", seed_type="email", seed_value="a@example.com", strategy_name="standard"
        )
        self.store.replace_jobs(
            job_claimed.id,
            [
                {
                    "id": "reader-job",
                    "tool_name": "reader_task",
                    "target_type": "domain",
                    "target_value": "example.com",
                    "depth": 0,
                    "agent_role": "reader",
                }
            ],
        )
        registration = self.register(capabilities=["company", "reader"])
        agent_id = registration["id"]

        claimed_job = self.store.claim_job(agent_id, ["reader"])
        claimed_investigation = self.store.claim_task(agent_id, ["company"])
        self.assertIsNotNone(claimed_job)
        self.assertIsNotNone(claimed_investigation)
        return agent_id, claimed, job_claimed, unrelated

    def test_job_access_requires_exact_job_id_role_and_output_contract(self):
        agent_id, _claimed, job_claimed, _unrelated = self.create_access_claims()

        self.assertFalse(
            self.store.agent_has_investigation_access(
                agent_id, job_claimed.id, "reader"
            )
        )
        self.assertTrue(
            self.store.agent_has_investigation_access(
                agent_id,
                job_claimed.id,
                "reader",
                job_id="reader-job",
                action="entities",
            )
        )
        self.assertFalse(
            self.store.agent_has_investigation_access(
                agent_id,
                job_claimed.id,
                "reader",
                job_id="missing-job",
                action="entities",
            )
        )
        self.assertFalse(
            self.store.agent_has_investigation_access(
                agent_id,
                job_claimed.id,
                "reader",
                job_id="reader-job",
                action="complete_task",
            )
        )

    def test_investigation_access_requires_exact_role_and_matching_claim(self):
        agent_id, claimed, job_claimed, unrelated = self.create_access_claims()

        self.assertTrue(self.store.agent_has_investigation_access(agent_id, claimed.id, "reader"))
        self.assertFalse(self.store.agent_has_investigation_access(agent_id, job_claimed.id, "reader"))
        self.assertFalse(self.store.agent_has_investigation_access(agent_id, unrelated.id, "reader"))
        self.assertFalse(self.store.agent_has_investigation_access(agent_id, claimed.id, "verifier"))
        self.assertFalse(self.store.agent_has_investigation_access(agent_id, claimed.id, "Reader"))
        self.assertFalse(self.store.agent_has_investigation_access("missing", claimed.id, "reader"))
        self.disable_agent(agent_id)
        self.assertFalse(self.store.agent_has_investigation_access(agent_id, claimed.id, "reader"))

    def test_investigation_claim_grants_access_only_while_parent_is_active(self):
        agent_id, claimed, _job_claimed, _unrelated = self.create_access_claims()

        for active_status in ("CLAIMED", "RUNNING"):
            with self.subTest(active_status=active_status):
                self.store.set_investigation_status(claimed.id, active_status)
                self.assertTrue(
                    self.store.agent_has_investigation_access(agent_id, claimed.id, "reader")
                )

        for inactive_status in (
            "COMPLETED",
            "CANCELLED",
            "ARCHIVED",
            "OPEN",
            "FAILED",
            "BLOCKED",
        ):
            with self.subTest(inactive_status=inactive_status):
                self.store.set_investigation_status(claimed.id, inactive_status)
                self.assertFalse(
                    self.store.agent_has_investigation_access(agent_id, claimed.id, "reader")
                )

    def test_job_claim_requires_active_job_and_active_parent(self):
        agent_id, _claimed, job_claimed, unrelated = self.create_access_claims()

        for active_status in ("CLAIMED", "RUNNING"):
            with self.subTest(active_job_status=active_status):
                self.store.update_job_status("reader-job", active_status)
                self.assertTrue(
                    self.store.agent_has_investigation_access(
                        agent_id,
                        job_claimed.id,
                        "reader",
                        job_id="reader-job",
                        action="entities",
                    )
                )
                self.assertFalse(
                    self.store.agent_has_investigation_access(agent_id, unrelated.id, "reader")
                )

        for inactive_status in (
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "QUEUED",
            "WAITING_AGENT",
        ):
            with self.subTest(inactive_job_status=inactive_status):
                self.store.update_job_status("reader-job", inactive_status)
                self.assertFalse(
                    self.store.agent_has_investigation_access(
                        agent_id,
                        job_claimed.id,
                        "reader",
                        job_id="reader-job",
                        action="entities",
                    )
                )

        self.store.update_job_status("reader-job", "CLAIMED")
        for parent_status in ("CLAIMED", "RUNNING"):
            with self.subTest(active_parent_status=parent_status):
                self.store.set_investigation_status(job_claimed.id, parent_status)
                self.assertTrue(
                    self.store.agent_has_investigation_access(
                        agent_id,
                        job_claimed.id,
                        "reader",
                        job_id="reader-job",
                        action="entities",
                    )
                )

        for parent_status in (
            "COMPLETED",
            "CANCELLED",
            "ARCHIVED",
            "OPEN",
            "FAILED",
            "BLOCKED",
        ):
            with self.subTest(inactive_parent_status=parent_status):
                self.store.set_investigation_status(job_claimed.id, parent_status)
                self.assertFalse(
                    self.store.agent_has_investigation_access(
                        agent_id,
                        job_claimed.id,
                        "reader",
                        job_id="reader-job",
                        action="entities",
                    )
                )

    def test_claim_capabilities_cannot_expand_registered_task_or_job_authority(self):
        registration = self.register(
            name="email-only-reader",
            role_tier="reader",
            capabilities=["email"],
        )
        domain_task = self.store.create_investigation(
            name="Domain escalation",
            seed_type="domain",
            seed_value="escalation.example",
            strategy_name="quick",
        )
        job_task = self.store.create_investigation(
            name="Job escalation",
            seed_type="domain",
            seed_value="job-escalation.example",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            job_task.id,
            [
                {
                    "id": "reader-escalation-job",
                    "tool_name": "domain_reader",
                    "target_type": "domain",
                    "target_value": "job-escalation.example",
                    "depth": 0,
                    "agent_role": "reader",
                }
            ],
        )

        self.assertIsNone(
            self.store.claim_task(registration["id"], ["domain"])
        )
        self.assertIsNone(
            self.store.claim_job(registration["id"], ["reader", "domain_reader"])
        )
        self.assertEqual(
            self.store.get_investigation(domain_task.id)["status"], "OPEN"
        )
        self.assertIsNone(
            self.store.list_jobs(job_task.id)[0]["claimed_by_agent_id"]
        )

    def test_tool_agent_claims_only_compatible_tool_jobs(self):
        tool_agent = self.register(
            name="amass-tool-agent",
            role_tier="tool_agent",
            capabilities=["amass"],
        )
        investigation = self.store.create_investigation(
            name="Tool claim scope",
            seed_type="domain",
            seed_value="tool-claim.example",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "reader-amass-job",
                    "tool_name": "amass",
                    "target_type": "domain",
                    "target_value": "tool-claim.example",
                    "depth": 0,
                    "agent_role": "reader",
                },
                {
                    "id": "subfinder-tool-job",
                    "tool_name": "subfinder",
                    "target_type": "domain",
                    "target_value": "tool-claim.example",
                    "depth": 0,
                    "agent_role": "tool_agent",
                },
                {
                    "id": "amass-tool-job",
                    "tool_name": "amass",
                    "target_type": "domain",
                    "target_value": "tool-claim.example",
                    "depth": 0,
                    "agent_role": "tool_agent",
                },
            ],
        )

        claimed = self.store.claim_job(tool_agent["id"], ["amass"])

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["id"], "amass-tool-job")
        jobs = {job["id"]: job for job in self.store.list_jobs(investigation.id)}
        self.assertIsNone(jobs["reader-amass-job"]["claimed_by_agent_id"])
        self.assertIsNone(jobs["subfinder-tool-job"]["claimed_by_agent_id"])

    def test_job_claim_rejects_cross_tier_roles_despite_registered_capability(self):
        reporter = self.register(
            name="cross-tier-reporter",
            role_tier="reporter",
            capabilities=["enterprise_intel_agent"],
        )
        reader = self.register(
            name="cross-tier-reader",
            role_tier="reader",
            capabilities=["analysis_judgement_agent"],
        )
        investigation = self.store.create_investigation(
            name="Cross-tier jobs",
            seed_type="company",
            seed_value="Cross Tier LLC",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "reader-tier-job",
                    "tool_name": "company_osint",
                    "target_type": "company",
                    "target_value": "Cross Tier LLC",
                    "depth": 0,
                    "agent_role": "enterprise_intel_agent",
                },
                {
                    "id": "reporter-tier-job",
                    "tool_name": "analysis_judgement",
                    "target_type": "company",
                    "target_value": "Cross Tier LLC",
                    "depth": 1,
                    "agent_role": "analysis_judgement_agent",
                },
            ],
        )

        self.assertIsNone(
            self.store.claim_job(reporter["id"], ["enterprise_intel_agent"])
        )
        self.assertIsNone(
            self.store.claim_job(reader["id"], ["analysis_judgement_agent"])
        )

    def test_tool_output_batch_is_one_shot_under_concurrent_submission(self):
        registration, investigation, job_id, payload = self.create_tool_output_claim(
            "concurrent"
        )
        barrier = Barrier(2)
        submission_stores = self.tool_output_submission_stores()

        def submit(index):
            barrier.wait(timeout=5)
            return submission_stores[index].submit_tool_job_output(
                registration["id"], investigation.id, job_id, payload
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))

        self.assertEqual(sum(result is not None for result in results), 1)
        detail = self.store.get_investigation(investigation.id)
        self.assertEqual(len(detail["events"]), 1)
        self.assertEqual(len(detail["entities"]), 1)
        self.assertEqual(len(detail["evidence"]), 1)
        self.assertEqual(len(detail["relationships"]), 1)
        self.assertEqual(self.store.list_jobs(investigation.id)[0]["status"], "COMPLETED")

    def test_tool_output_batch_rolls_back_every_write_on_storage_failure(self):
        registration, investigation, job_id, payload = self.create_tool_output_claim(
            "rollback"
        )

        with self.tool_output_storage_failure() as expected_error:
            with self.assertRaises(expected_error):
                self.store.submit_tool_job_output(
                    registration["id"], investigation.id, job_id, payload
                )

        detail = self.store.get_investigation(investigation.id)
        for section in ("events", "entities", "evidence", "relationships"):
            self.assertEqual(detail[section], [])
        self.assertEqual(self.store.list_jobs(investigation.id)[0]["status"], "CLAIMED")

class _MemoryStoreContext:
    def __enter__(self):
        return MemoryStore()

    def __exit__(self, *args):
        return None


class MemoryAgentIdentityTests(AgentIdentityStoreContract, unittest.TestCase):
    def make_store(self):
        return _MemoryStoreContext()

    def disable_agent(self, agent_id):
        self.store.agents[agent_id].disabled_at = "2026-07-10T00:00:00+00:00"

    def stored_token_hash(self, agent_id):
        return self.store.agents[agent_id].token_hash

    def clear_agent_token(self, agent_id):
        self.store.agents[agent_id].token_hash = None

    def clear_agent_role(self, agent_id):
        self.store.agents[agent_id].role_tier = None

    def internal_agent_state(self, agent_id):
        agent = self.store.agents[agent_id]
        return (
            agent.status,
            agent.last_seen_at,
            agent.role_tier,
            agent.token_hash,
            agent.token_created_at,
            agent.disabled_at,
        )

    @contextmanager
    def tool_output_storage_failure(self):
        class FailingRelationships(dict):
            def __setitem__(self, _key, _value):
                raise RuntimeError("forced relationship storage failure")

        original = self.store.relationships
        self.store.relationships = FailingRelationships(original)
        try:
            yield RuntimeError
        finally:
            if isinstance(self.store.relationships, FailingRelationships):
                self.store.relationships = original


class _SQLiteStoreContext:
    def __init__(self):
        self.tmpdir = TemporaryDirectory()

    def __enter__(self):
        self.db_path = str(Path(self.tmpdir.name) / "identity.sqlite")
        return SQLiteStore(self.db_path)

    def __exit__(self, *args):
        self.tmpdir.cleanup()


class SQLiteAgentIdentityTests(AgentIdentityStoreContract, unittest.TestCase):
    def make_store(self):
        return _SQLiteStoreContext()

    def disable_agent(self, agent_id):
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute(
                "UPDATE agents SET disabled_at = ? WHERE id = ?",
                ("2026-07-10T00:00:00+00:00", agent_id),
            )

    def stored_token_hash(self, agent_id):
        with sqlite3.connect(self.store.db_path) as conn:
            return conn.execute(
                "SELECT token_hash FROM agents WHERE id = ?", (agent_id,)
            ).fetchone()[0]

    def clear_agent_token(self, agent_id):
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("UPDATE agents SET token_hash = NULL WHERE id = ?", (agent_id,))

    def clear_agent_role(self, agent_id):
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("UPDATE agents SET role_tier = NULL WHERE id = ?", (agent_id,))

    def internal_agent_state(self, agent_id):
        with sqlite3.connect(self.store.db_path) as conn:
            return conn.execute(
                """
                SELECT status, last_seen_at, role_tier, token_hash,
                       token_created_at, disabled_at
                FROM agents WHERE id = ?
                """,
                (agent_id,),
            ).fetchone()

    def tool_output_submission_stores(self):
        return (self.store, SQLiteStore(self.store.db_path))

    @contextmanager
    def tool_output_storage_failure(self):
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute(
                """
                CREATE TRIGGER fail_tool_relationship_insert
                BEFORE INSERT ON relationships
                BEGIN
                    SELECT RAISE(ABORT, 'forced relationship storage failure');
                END
                """
            )
        try:
            yield sqlite3.IntegrityError
        finally:
            with sqlite3.connect(self.store.db_path) as conn:
                conn.execute("DROP TRIGGER IF EXISTS fail_tool_relationship_insert")

    def test_import_agent_preserves_existing_credentials_and_safe_lifecycle_fields(self):
        registration = self.register()
        self.store.import_agent(
            {
                **self.store.list_agents()[0],
                "status": "OFFLINE",
                "token_hash": hash_agent_token("attacker-controlled"),
            }
        )
        self.store.import_agent(
            {
                "id": "imported-agent",
                "agent_name": "imported",
                "agent_type": "cli",
                "capabilities": ["domain"],
                "role_tier": "reporter",
                "token_created_at": "2026-07-10T00:00:00+00:00",
                "disabled_at": "2026-07-10T01:00:00+00:00",
            }
        )

        self.assertEqual(
            self.store.resolve_agent_token(registration["agent_token"])["id"],
            registration["id"],
        )
        imported = next(
            item for item in self.store.list_agents() if item["id"] == "imported-agent"
        )
        self.assertEqual(imported["role_tier"], "reporter")
        self.assertEqual(imported["disabled_at"], "2026-07-10T01:00:00+00:00")
        self.assertNotIn("token_hash", imported)
        with sqlite3.connect(self.store.db_path) as conn:
            imported_hash = conn.execute(
                "SELECT token_hash FROM agents WHERE id = 'imported-agent'"
            ).fetchone()[0]
        self.assertIsNone(imported_hash)


class AgentRegistrationHttpCompatibilityTests(unittest.TestCase):
    REGISTRATION_PAYLOAD = {
        "agent_name": "admin-created-reader",
        "agent_type": "test",
        "capabilities": ["domain"],
        "role_tier": "reader",
    }

    def test_registration_rejects_anonymous_default_development_without_mutation(self):
        store = MemoryStore()
        with patch.object(app_main, "store", store), ApiTestServer() as server:
            status, body, _headers = server.request(
                "POST",
                "/api/agents/register",
                payload=self.REGISTRATION_PAYLOAD,
                env={"APP_ENV": "development"},
            )

        self.assertEqual(status, 401)
        self.assertEqual(
            json_payload(body), {"detail": "unauthorized management request"}
        )
        self.assertEqual(store.list_agents(), [])

    def test_registration_accepts_admin_bearer(self):
        store = MemoryStore()
        with patch.object(app_main, "store", store), ApiTestServer() as server:
            status, body, _headers = server.request(
                "POST",
                "/api/agents/register",
                payload=self.REGISTRATION_PAYLOAD,
                headers=[("Authorization", "Bearer admin-secret")],
                env=PRODUCTION_ENV,
            )

        self.assertEqual(status, 201)
        self.assertEqual(json_payload(body)["role_tier"], "reader")
        self.assertEqual(len(store.list_agents()), 1)

    def test_registration_accepts_admin_browser_session_with_mutation_protection(self):
        store = MemoryStore()
        with patch.object(app_main, "store", store), ApiTestServer() as server:
            login_status, login_body, login_headers = server.request(
                "POST",
                "/api/auth/login",
                payload={"admin_token": "admin-secret"},
                env=PRODUCTION_ENV,
            )
            self.assertEqual(login_status, 200)
            cookie = cookie_from_set_cookie(
                header_value(login_headers, "Set-Cookie") or ""
            )
            csrf_token = json_payload(login_body)["csrf_token"]
            status, body, _headers = server.request(
                "POST",
                "/api/agents/register",
                payload=self.REGISTRATION_PAYLOAD,
                headers=[
                    ("Cookie", cookie),
                    ("Origin", PRODUCTION_ENV["CORS_ALLOWED_ORIGINS"]),
                    ("X-CSRF-Token", csrf_token),
                ],
                env=PRODUCTION_ENV,
            )

        self.assertEqual(status, 201)
        self.assertEqual(json_payload(body)["role_tier"], "reader")
        self.assertEqual(len(store.list_agents()), 1)

    def test_registration_never_falls_back_to_shared_agent_bearer(self):
        store = MemoryStore()
        env = {
            "APP_ENV": "development",
            "OSINT_REQUIRE_AUTH": "true",
            "ADMIN_API_TOKEN": "",
            "AGENT_API_TOKEN": "shared-agent-secret",
            "READ_API_TOKEN": "read-secret",
        }
        with patch.object(app_main, "store", store), ApiTestServer() as server:
            status, body, _headers = server.request(
                "POST",
                "/api/agents/register",
                payload={
                    "agent_name": "must-not-register",
                    "agent_type": "test",
                    "capabilities": ["domain"],
                    "role_tier": "reader",
                },
                headers=[("Authorization", "Bearer shared-agent-secret")],
                env=env,
            )

        self.assertEqual(status, 403)
        self.assertEqual(json_payload(body), {"detail": "forbidden management request"})
        self.assertEqual(store.list_agents(), [])

    def test_registration_endpoint_rejects_lone_surrogates_without_mutation(self):
        store = MemoryStore()
        headers = [("Authorization", "Bearer admin-secret")]
        invalid_payloads = (
            {"agent_name": "\ud800", "agent_type": "codex", "capabilities": []},
            {"agent_name": "\udc00", "agent_type": "codex", "capabilities": []},
            {"agent_name": "valid", "agent_type": "\ud800", "capabilities": []},
            {"agent_name": "valid", "agent_type": "\udc00", "capabilities": []},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": ["\ud800"]},
            {"agent_name": "valid", "agent_type": "codex", "capabilities": ["\udc00"]},
        )

        with (
            patch.object(app_main, "store", store),
            patch(
                "app.services.store.generate_agent_token",
                wraps=generate_agent_token,
            ) as token_generator,
            ApiTestServer() as server,
        ):
            for invalid in invalid_payloads:
                with self.subTest(invalid=invalid):
                    status, body, _ = server.request(
                        "POST",
                        "/api/agents/register",
                        payload={**invalid, "role_tier": "reader"},
                        headers=headers,
                        env=PRODUCTION_ENV,
                    )
                    response = json_payload(body)
                    self.assertEqual(status, 400)
                    self.assertIsInstance(response.get("detail"), str)
                    self.assertNotIn("\\ud800", body.decode("utf-8"))
                    self.assertNotIn("\\udc00", body.decode("utf-8"))

        token_generator.assert_not_called()
        self.assertEqual(store.list_agents(), [])

    def test_registration_endpoint_rejects_invalid_shapes_without_echoing_values(self):
        store = MemoryStore()
        headers = [("Authorization", "Bearer admin-secret")]
        marker = "sensitive-invalid-agent-value"
        invalid_payloads = (
            {
                "agent_name": marker * 10,
                "agent_type": "codex",
                "capabilities": [],
                "role_tier": "reader",
            },
            {
                "agent_name": "valid",
                "agent_type": {"unexpected": marker},
                "capabilities": [],
                "role_tier": "reader",
            },
            {
                "agent_name": "valid",
                "agent_type": "codex",
                "capabilities": marker,
                "role_tier": "reader",
            },
            {
                "agent_name": "valid",
                "agent_type": "codex",
                "capabilities": [[marker]],
                "role_tier": "reader",
            },
        )

        with (
            patch.object(app_main, "store", store),
            patch("app.services.store.generate_agent_token") as generate_token,
            ApiTestServer() as server,
        ):
            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    status, body, _ = server.request(
                        "POST",
                        "/api/agents/register",
                        payload=payload,
                        headers=headers,
                        env=PRODUCTION_ENV,
                    )
                    response = json_payload(body)
                    self.assertEqual(status, 400)
                    self.assertIsInstance(response.get("detail"), str)
                    self.assertNotIn(marker, body.decode("utf-8"))

        generate_token.assert_not_called()
        self.assertEqual(store.list_agents(), [])

    def test_registration_endpoint_serializes_mapping_and_validates_role(self):
        store = MemoryStore()
        headers = [("Authorization", "Bearer admin-secret")]
        with patch.object(app_main, "store", store), ApiTestServer() as server:
            status, body, _ = server.request(
                "POST",
                "/api/agents/register",
                payload={
                    "agent_name": "http-reader",
                    "agent_type": "codex",
                    "capabilities": ["company"],
                    "role_tier": "reader",
                },
                headers=headers,
                env=PRODUCTION_ENV,
            )
            missing_status, missing_body, _ = server.request(
                "POST",
                "/api/agents/register",
                payload={"agent_name": "missing", "agent_type": "codex"},
                headers=headers,
                env=PRODUCTION_ENV,
            )
            invalid_status, invalid_body, _ = server.request(
                "POST",
                "/api/agents/register",
                payload={
                    "agent_name": "invalid",
                    "agent_type": "codex",
                    "role_tier": "Reader",
                },
                headers=headers,
                env=PRODUCTION_ENV,
            )

        response = json_payload(body)
        self.assertEqual(status, 201)
        self.assertEqual(response["role_tier"], "reader")
        self.assertIn("agent_token", response)
        self.assertEqual(missing_status, 400)
        self.assertIn("role_tier", json_payload(missing_body)["detail"])
        self.assertEqual(invalid_status, 400)
        self.assertIn("role", json_payload(invalid_body)["detail"])
        self.assertEqual(len(store.list_agents()), 1)


class AgentAuthHelperTests(unittest.TestCase):
    def test_hash_agent_token_is_lowercase_sha256(self):
        self.assertEqual(
            hash_agent_token("agent-secret"),
            "cc000e626ba67bed4834794d42288b228f012823877440d2bc5a3787cc6ffce9",
        )

    def test_agent_principal_and_action_tiers_are_explicit_and_nonhierarchical(self):
        self.assertEqual(
            AGENT_ACTION_TIERS,
            {
                "entities": {"reader"},
                "evidence": {"reader"},
                "evidence_records": {"reader"},
                "relationships": {"reader"},
                "facts": {"verifier"},
                "hypotheses": {"verifier"},
                "score_hypotheses": {"verifier"},
                "complete_task": {"reporter"},
            },
        )
        principal = AgentPrincipal("agent-1", "reader", ("domain",))
        with self.assertRaises(FrozenInstanceError):
            principal.agent_id = "forged"


class AgentRouteAuthorizationHttpTests(unittest.TestCase):
    ENV = {
        **PRODUCTION_ENV,
        "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "false",
    }

    ACTIONS = {
        "entities": (
            "/api/agent/entities",
            {
                "entities": [
                    {
                        "type": "domain",
                        "value": "example.com",
                        "source_tool": "agent",
                        "confidence": 0.8,
                    }
                ]
            },
            201,
        ),
        "evidence": (
            "/api/agent/evidence",
            {
                "entity_value": "example.com",
                "evidence_kind": "search_result",
                "source_tool": "agent",
                "snippet": "Public result",
            },
            201,
        ),
        "evidence_records": (
            "/api/agent/evidence-records",
            {
                "source_url": "https://example.com/",
                "source_type": "official_website",
                "source_tool": "agent",
                "snippet": "Official source",
                "credibility": 0.8,
            },
            201,
        ),
        "relationships": (
            "/api/agent/relationships",
            {
                "from": "Example LLC",
                "to": "example.com",
                "relationship_type": "organization_has_domain",
                "confidence": 0.8,
            },
            201,
        ),
        "facts": (
            "/api/agent/facts",
            {
                "statement": "Example LLC operates example.com.",
                "subject": "Example LLC",
                "predicate": "has_domain",
                "object": "example.com",
                "status": "NEEDS_REVIEW",
                "confidence": 0.8,
                "admiralty_code": "B-2",
                "evidence_ids": [],
            },
            201,
        ),
        "hypotheses": (
            "/api/agent/hypotheses",
            {"hypothesis_id": "h1", "statement": "Example LLC is active."},
            201,
        ),
        "score_hypotheses": (
            "/api/agent/hypotheses/score",
            {"evidence_items": []},
            201,
        ),
        "complete_task": (
            "/api/agent/tasks/{task_id}/complete",
            {"status": "COMPLETED", "summary": "Done", "report_markdown": "# Done"},
            200,
        ),
    }

    def setUp(self):
        self.store = MemoryStore()
        self.original_store = app_main.store
        app_main.store = self.store
        self.server_context = ApiTestServer()
        self.server = self.server_context.__enter__()
        self.counter = 0

    def tearDown(self):
        self.server_context.__exit__(None, None, None)
        app_main.store = self.original_store

    def register(self, role_tier, capabilities=None):
        self.counter += 1
        return self.store.register_agent(
            agent_name=f"{role_tier}-{self.counter}",
            agent_type="test",
            capabilities=["domain"] if capabilities is None else list(capabilities),
            role_tier=role_tier,
        )

    def claimed_task(self, registration, seed_type=None):
        seed_type = seed_type or "domain"
        investigation = self.store.create_investigation(
            name=f"Task {self.counter}",
            seed_type=seed_type,
            seed_value=(
                f"target-{self.counter}.example"
                if seed_type == "domain"
                else f"target-{self.counter}@example.com"
            ),
            strategy_name="quick",
        )
        claimed = self.store.claim_task(registration["id"], [seed_type])
        self.assertEqual(claimed["id"], investigation.id)
        return investigation

    def post(self, path, payload, token, headers=None, env=None):
        request_headers = [("Authorization", f"Bearer {token}")]
        request_headers.extend(headers or [])
        status, body, _response_headers = self.server.request(
            "POST",
            path,
            payload=payload,
            headers=request_headers,
            env=env or self.ENV,
        )
        return status, json_payload(body)

    def test_real_http_role_matrix_allows_only_the_exact_action_tier(self):
        roles = ("reader", "verifier", "reporter", "tool_agent")
        for action, (path_template, action_payload, expected_status) in self.ACTIONS.items():
            required_role = next(iter(AGENT_ACTION_TIERS[action]))
            with self.subTest(action=action, role=required_role):
                allowed = self.register(required_role)
                investigation = self.claimed_task(allowed)
                path = path_template.format(task_id=investigation.id)
                status, _body = self.post(
                    path,
                    {"task_id": investigation.id, **action_payload},
                    allowed["agent_token"],
                )
                self.assertEqual(status, expected_status)

            for wrong_role in roles:
                if wrong_role == required_role:
                    continue
                with self.subTest(action=action, wrong_role=wrong_role):
                    denied = self.register(wrong_role)
                    investigation = self.claimed_task(denied)
                    path = path_template.format(task_id=investigation.id)
                    status, _body = self.post(
                        path,
                        {"task_id": investigation.id, **action_payload},
                        denied["agent_token"],
                    )
                    self.assertEqual(status, 403)

    def test_unknown_disabled_legacy_null_and_management_credentials_are_401(self):
        registration = self.register("reporter")
        investigation = self.claimed_task(registration)
        path = f"/api/agent/tasks/{investigation.id}/complete"
        payload = {"agent_id": registration["id"], "summary": "forbidden"}
        tokens = ("wrong", "agent-secret")
        for token in tokens:
            with self.subTest(token_kind=token):
                status, _body = self.post(path, payload, token)
                self.assertEqual(status, 401)

        for token in ("admin-secret", "read-secret"):
            with self.subTest(management_token=token):
                status, _body = self.post(path, payload, token)
                self.assertEqual(status, 403)

        self.store.agents[registration["id"]].disabled_at = "2026-07-10T00:00:00Z"
        status, _body = self.post(path, payload, registration["agent_token"])
        self.assertEqual(status, 401)
        self.store.agents[registration["id"]].disabled_at = None
        self.store.agents[registration["id"]].token_hash = None
        status, _body = self.post(path, payload, registration["agent_token"])
        self.assertEqual(status, 401)
        self.assertEqual(self.store.get_investigation(investigation.id)["summary"], "")

    def test_forged_unregistered_completion_is_403_before_store_mutation(self):
        reporter = self.register("reporter")
        investigation = self.claimed_task(reporter)
        before = self.store.get_investigation(investigation.id)

        status, body = self.post(
            f"/api/agent/tasks/{investigation.id}/complete",
            {"agent_id": "unregistered-forged", "summary": "forged"},
            reporter["agent_token"],
        )

        after = self.store.get_investigation(investigation.id)
        self.assertEqual(status, 403)
        self.assertEqual(body, {"detail": "agent identity mismatch"})
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(after["summary"], before["summary"])

    def test_body_identity_is_optional_and_store_events_use_the_principal(self):
        reader = self.register("reader")
        investigation = self.claimed_task(reader)
        status, event = self.post(
            "/api/agent/events",
            {"task_id": investigation.id, "message": "Started"},
            reader["agent_token"],
        )
        self.assertEqual(status, 201)
        self.assertEqual(event["agent_id"], reader["id"])

    def test_active_ownership_is_required_for_actions_events_and_completion(self):
        cases = (
            ("reader", "/api/agent/entities", self.ACTIONS["entities"][1]),
            ("reader", "/api/agent/events", {"message": "Started"}),
            ("reporter", "/api/agent/tasks/{task_id}/complete", {"summary": "Done"}),
        )
        for role, path_template, payload in cases:
            with self.subTest(role=role, path=path_template):
                registration = self.register(role)
                investigation = self.store.create_investigation(
                    name=f"Unclaimed {self.counter}",
                    seed_type="domain",
                    seed_value=f"unclaimed-{self.counter}.example",
                    strategy_name="quick",
                )
                path = path_template.format(task_id=investigation.id)
                status, body = self.post(
                    path,
                    {"task_id": investigation.id, **payload},
                    registration["agent_token"],
                )
                self.assertEqual(status, 409)
                self.assertEqual(body, {"detail": "active task ownership required"})

    def test_released_and_terminal_claims_are_409_but_active_exact_owner_succeeds(self):
        reader = self.register("reader")
        investigation = self.claimed_task(reader)
        payload = {"task_id": investigation.id, **self.ACTIONS["entities"][1]}
        status, _body = self.post("/api/agent/entities", payload, reader["agent_token"])
        self.assertEqual(status, 201)

        for inactive_status in ("OPEN", "COMPLETED"):
            with self.subTest(inactive_status=inactive_status):
                self.store.set_investigation_status(investigation.id, inactive_status)
                status, _body = self.post(
                    "/api/agent/entities", payload, reader["agent_token"]
                )
                self.assertEqual(status, 409)

    def test_matching_active_job_owner_can_write_and_event_scope_rejects_other_agent(self):
        reader = self.register("reader", ["reader_task"])
        investigation = self.store.create_investigation(
            name="Job owned", seed_type="domain", seed_value="example.com", strategy_name="quick"
        )
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "reader-job",
                    "tool_name": "reader_task",
                    "target_type": "domain",
                    "target_value": "example.com",
                    "depth": 0,
                    "agent_role": "reader",
                }
            ],
        )
        claimed = self.store.claim_job(reader["id"], ["reader_task"])
        self.assertEqual(claimed["id"], "reader-job")

        status, _body = self.post(
            "/api/agent/entities",
            {
                "task_id": investigation.id,
                "job_id": "reader-job",
                **self.ACTIONS["entities"][1],
            },
            reader["agent_token"],
        )
        self.assertEqual(status, 201)

        other = self.register("reader")
        status, _body = self.post(
            "/api/agent/events",
            {"task_id": investigation.id, "message": "forged scope"},
            other["agent_token"],
        )
        self.assertEqual(status, 409)

        self.store.update_job_status("reader-job", "COMPLETED")
        status, _body = self.post(
            "/api/agent/events",
            {
                "task_id": investigation.id,
                "job_id": "reader-job",
                "message": "late event",
            },
            reader["agent_token"],
        )
        self.assertEqual(status, 409)

    def test_unrelated_reader_job_cannot_authorize_reporter_completion(self):
        reporter = self.register("reporter", ["reader"])
        investigation = self.store.create_investigation(
            name="Reporter escalation",
            seed_type="domain",
            seed_value="reporter-escalation.example",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "unrelated-reader-job",
                    "tool_name": "reader_task",
                    "target_type": "domain",
                    "target_value": "reporter-escalation.example",
                    "depth": 0,
                    "agent_role": "reader",
                    "output_contract": "entities,evidence,relationships",
                }
            ],
        )
        status, claim_body = self.post(
            "/api/agent/jobs/claim",
            {"capabilities": ["reader"]},
            reporter["agent_token"],
        )
        self.assertEqual(status, 200)
        self.assertIsNone(claim_body["job"])
        job = self.store.jobs["unrelated-reader-job"]
        job.status = "CLAIMED"
        job.claimed_by_agent_id = reporter["id"]
        self.store.set_investigation_status(investigation.id, "RUNNING")

        status, _body = self.post(
            f"/api/agent/tasks/{investigation.id}/complete",
            {
                "task_id": investigation.id,
                "job_id": "unrelated-reader-job",
                "summary": "forged completion",
            },
            reporter["agent_token"],
        )
        self.assertEqual(status, 409)
        detail = self.store.get_investigation(investigation.id)
        self.assertNotEqual(detail["summary"], "forged completion")

    def test_job_derived_write_requires_exact_job_id_and_action_contract(self):
        reader = self.register("reader", ["reader"])
        investigation = self.store.create_investigation(
            name="Output contract scope",
            seed_type="domain",
            seed_value="contract.example",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "evidence-only-job",
                    "tool_name": "reader_task",
                    "target_type": "domain",
                    "target_value": "contract.example",
                    "depth": 0,
                    "agent_role": "reader",
                    "output_contract": "evidence",
                }
            ],
        )
        status, _body = self.post(
            "/api/agent/jobs/claim",
            {"capabilities": ["reader"]},
            reader["agent_token"],
        )
        self.assertEqual(status, 200)

        for job_id in (None, "wrong-job", "evidence-only-job"):
            with self.subTest(job_id=job_id):
                payload = {
                    "task_id": investigation.id,
                    **self.ACTIONS["entities"][1],
                }
                if job_id is not None:
                    payload["job_id"] = job_id
                status, _body = self.post(
                    "/api/agent/entities", payload, reader["agent_token"]
                )
                self.assertEqual(status, 409)

    def test_reader_tier_can_use_exact_enterprise_role_job_contract(self):
        reader = self.register("reader", ["enterprise_intel_agent"])
        investigation = self.store.create_investigation(
            name="Enterprise reader job",
            seed_type="company",
            seed_value="Example LLC",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "enterprise-reader-job",
                    "tool_name": "company_osint",
                    "target_type": "company",
                    "target_value": "Example LLC",
                    "depth": 0,
                    "agent_role": "enterprise_intel_agent",
                    "output_contract": "entities,evidence,relationships",
                }
            ],
        )
        status, _body = self.post(
            "/api/agent/jobs/claim",
            {"capabilities": ["enterprise_intel_agent"]},
            reader["agent_token"],
        )
        self.assertEqual(status, 200)
        status, _body = self.post(
            "/api/agent/entities",
            {
                "task_id": investigation.id,
                "job_id": "enterprise-reader-job",
                **self.ACTIONS["entities"][1],
            },
            reader["agent_token"],
        )
        self.assertEqual(status, 201)

    def test_http_tool_agent_claims_compatible_tool_job(self):
        tool_agent = self.register("tool_agent", ["theharvester"])
        investigation = self.store.create_investigation(
            name="Tool claim",
            seed_type="domain",
            seed_value="tool-claim-http.example",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "http-tool-claim-job",
                    "tool_name": "theharvester",
                    "target_type": "domain",
                    "target_value": "tool-claim-http.example",
                    "depth": 0,
                    "agent_role": "tool_agent",
                }
            ],
        )
        status, body = self.post(
            "/api/agent/jobs/claim", {}, tool_agent["agent_token"]
        )
        self.assertEqual(status, 200)
        self.assertIsNotNone(body["job"])
        self.assertEqual(body["job"]["id"], "http-tool-claim-job")

    def test_tool_output_requires_content_and_exact_claimed_tool_provenance(self):
        cases = (
            ("empty", {"task_id": None}),
            (
                "mismatched-tool",
                {
                    "task_id": None,
                    "tool": "theharvester",
                    "entities": [
                        {
                            "type": "domain",
                            "value": "found.example",
                            "source_tool": "theharvester",
                            "confidence": 0.8,
                        }
                    ],
                },
            ),
            (
                "mismatched-evidence-provenance",
                {
                    "task_id": None,
                    "tool": "amass",
                    "evidence": [
                        {
                            "entity_value": "found.example",
                            "evidence_kind": "dns_resolution",
                            "source_tool": "theharvester",
                            "snippet": "Resolved publicly",
                        }
                    ],
                },
            ),
            (
                "invalid-tool-type",
                {
                    "task_id": None,
                    "tool": {"name": "amass"},
                    "event": {"message": "Tool completed", "metadata": {}},
                },
            ),
        )
        for label, raw_payload in cases:
            with self.subTest(label=label):
                tool_agent = self.register("tool_agent", ["amass"])
                investigation = self.store.create_investigation(
                    name=f"Tool validation {label}",
                    seed_type="domain",
                    seed_value=f"{label}.example",
                    strategy_name="quick",
                )
                job_id = f"amass-{label}-job"
                self.store.replace_jobs(
                    investigation.id,
                    [
                        {
                            "id": job_id,
                            "tool_name": "amass",
                            "target_type": "domain",
                            "target_value": f"{label}.example",
                            "depth": 0,
                            "agent_role": "tool_agent",
                            "output_contract": "entities,evidence,relationships",
                        }
                    ],
                )
                claimed = self.store.claim_job(tool_agent["id"], ["amass"])
                self.assertEqual(claimed["id"], job_id)
                payload = {
                    **raw_payload,
                    "task_id": investigation.id,
                }

                status, body = self.post(
                    f"/api/agent/jobs/{job_id}/output",
                    payload,
                    tool_agent["agent_token"],
                )

                self.assertEqual(status, 400, body)
                detail = self.store.get_investigation(investigation.id)
                for section in ("events", "entities", "evidence", "relationships"):
                    self.assertEqual(detail[section], [])
                self.assertEqual(
                    self.store.list_jobs(investigation.id)[0]["status"], "CLAIMED"
                )

    def test_tool_output_http_accepts_exactly_one_concurrent_submission(self):
        tool_agent = self.register("tool_agent", ["amass"])
        investigation = self.store.create_investigation(
            name="Concurrent HTTP tool output",
            seed_type="domain",
            seed_value="concurrent-http.example",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "concurrent-http-amass-job",
                    "tool_name": "amass",
                    "target_type": "domain",
                    "target_value": "concurrent-http.example",
                    "depth": 0,
                    "agent_role": "tool_agent",
                    "output_contract": "entities,evidence,relationships",
                }
            ],
        )
        claimed = self.store.claim_job(tool_agent["id"], ["amass"])
        self.assertEqual(claimed["id"], "concurrent-http-amass-job")
        payload = {
            "task_id": investigation.id,
            "tool": "amass",
            "event": {"message": "amass completed", "metadata": {}},
        }
        request_barrier = Barrier(2)
        environment_keys = (
            "APP_ENV",
            "ADMIN_API_TOKEN",
            "AGENT_API_TOKEN",
            "READ_API_TOKEN",
            "OSINT_REQUIRE_AUTH",
            "OSINT_ALLOW_LEGACY_AGENT_TOKEN",
            "CORS_ALLOWED_ORIGINS",
            "OSINT_COOKIE_SECURE",
        )
        environment_before = {key: os.environ.get(key) for key in environment_keys}
        results = []
        try:
            with patch.dict("os.environ", self.ENV, clear=True), ApiTestServer() as server:
                def submit():
                    request_barrier.wait(timeout=5)
                    status, body, _headers = server.request_in_current_environment(
                        "POST",
                        "/api/agent/jobs/concurrent-http-amass-job/output",
                        payload=payload,
                        headers=[
                            (
                                "Authorization",
                                f"Bearer {tool_agent['agent_token']}",
                            )
                        ],
                    )
                    return status, json_payload(body)

                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(lambda _index: submit(), range(2)))
        finally:
            environment_after = {key: os.environ.get(key) for key in environment_keys}
            self.assertEqual(environment_after, environment_before)

        self.assertEqual(sorted(status for status, _body in results), [201, 409])
        detail = self.store.get_investigation(investigation.id)
        self.assertEqual(len(detail["events"]), 1)
        self.assertEqual(self.store.list_jobs(investigation.id)[0]["status"], "COMPLETED")

    def test_tool_agent_submits_atomic_bounded_output_for_exact_job(self):
        tool_agent = self.register("tool_agent", ["theharvester"])
        other_tool_agent = self.register("tool_agent", ["theharvester"])
        investigation = self.store.create_investigation(
            name="Tool output",
            seed_type="domain",
            seed_value="tool-output.example",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "theharvester-tool-job",
                    "tool_name": "theharvester",
                    "target_type": "domain",
                    "target_value": "tool-output.example",
                    "depth": 0,
                    "agent_role": "tool_agent",
                    "output_contract": "entities,evidence,relationships",
                }
            ],
        )
        job = self.store.jobs["theharvester-tool-job"]
        job.status = "CLAIMED"
        job.claimed_by_agent_id = tool_agent["id"]
        self.store.set_investigation_status(investigation.id, "RUNNING")

        invalid_payload = {
            "task_id": investigation.id,
            "tool": "theharvester",
            "entities": [
                {
                    "type": "email",
                    "value": "admin@tool-output.example",
                    "source_tool": "theharvester",
                    "confidence": 0.8,
                }
            ],
            "evidence": [],
            "relationships": [
                {
                    "from": "tool-output.example",
                    "to": "",
                    "relationship_type": "domain_has_email",
                    "confidence": 0.8,
                }
            ],
        }
        output_path = "/api/agent/jobs/theharvester-tool-job/output"
        status, _body = self.post(
            output_path, invalid_payload, tool_agent["agent_token"]
        )
        self.assertEqual(status, 400)
        detail = self.store.get_investigation(investigation.id)
        for section in ("entities", "evidence", "relationships", "events"):
            self.assertEqual(detail[section], [])
        self.assertEqual(
            self.store.list_jobs(investigation.id)[0]["status"], "CLAIMED"
        )

        valid_payload = {
            **invalid_payload,
            "relationships": [
                {
                    "from": "tool-output.example",
                    "to": "admin@tool-output.example",
                    "relationship_type": "domain_has_email",
                    "confidence": 0.8,
                }
            ],
            "event": {
                "message": "Tool output complete",
                "metadata": {"tool": "theharvester"},
            },
        }
        status, _body = self.post(
            output_path, valid_payload, other_tool_agent["agent_token"]
        )
        self.assertEqual(status, 409)
        status, body = self.post(
            output_path, valid_payload, tool_agent["agent_token"]
        )
        self.assertEqual(status, 201)
        self.assertEqual(body["created"], {"entities": 1, "evidence": 0, "relationships": 1})
        detail = self.store.get_investigation(investigation.id)
        self.assertEqual(len(detail["entities"]), 1)
        self.assertEqual(len(detail["relationships"]), 1)
        self.assertEqual(self.store.list_jobs(investigation.id)[0]["status"], "COMPLETED")

        status, _body = self.post(
            output_path, valid_payload, tool_agent["agent_token"]
        )
        self.assertEqual(status, 409)

    def test_tool_output_rejects_sections_outside_job_contract_without_mutation(self):
        tool_agent = self.register("tool_agent", ["amass"])
        investigation = self.store.create_investigation(
            name="Tool contract",
            seed_type="domain",
            seed_value="tool-contract.example",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            investigation.id,
            [
                {
                    "id": "entity-only-tool-job",
                    "tool_name": "amass",
                    "target_type": "domain",
                    "target_value": "tool-contract.example",
                    "depth": 0,
                    "agent_role": "tool_agent",
                    "output_contract": "entities",
                }
            ],
        )
        job = self.store.jobs["entity-only-tool-job"]
        job.status = "CLAIMED"
        job.claimed_by_agent_id = tool_agent["id"]
        self.store.set_investigation_status(investigation.id, "RUNNING")
        status, _body = self.post(
            "/api/agent/jobs/entity-only-tool-job/output",
            {
                "task_id": investigation.id,
                "entities": [],
                "evidence": [
                    {
                        "entity_value": "tool-contract.example",
                        "evidence_kind": "dns_resolution",
                        "source_tool": "amass",
                        "snippet": "Resolved publicly",
                    }
                ],
                "relationships": [],
            },
            tool_agent["agent_token"],
        )
        self.assertEqual(status, 400)
        detail = self.store.get_investigation(investigation.id)
        self.assertEqual(detail["evidence"], [])

    def test_claim_endpoints_bind_identity_and_define_allowed_roles(self):
        for role in ("reader", "verifier", "reporter"):
            with self.subTest(task_claim_role=role):
                registration = self.register(role, ["domain"])
                investigation = self.store.create_investigation(
                    name=role,
                    seed_type="domain",
                    seed_value=f"{role}.example",
                    strategy_name="quick",
                )
                status, body = self.post(
                    "/api/agent/tasks/claim",
                    {"capabilities": ["domain"]},
                    registration["agent_token"],
                )
                self.assertEqual(status, 200)
                self.assertEqual(body["task"]["claimed_by_agent_id"], registration["id"])
                self.assertEqual(body["task"]["id"], investigation.id)

        tool_agent = self.register("tool_agent", ["external_tool"])
        status, _body = self.post(
            "/api/agent/tasks/claim",
            {"capabilities": ["external_tool"]},
            tool_agent["agent_token"],
        )
        self.assertEqual(status, 403)

        job_investigation = self.store.create_investigation(
            name="External job",
            seed_type="domain",
            seed_value="job.example",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            job_investigation.id,
            [
                {
                    "id": "external-job",
                    "tool_name": "external_tool",
                    "target_type": "domain",
                    "target_value": "job.example",
                    "depth": 0,
                    "agent_role": "tool_agent",
                }
            ],
        )
        status, body = self.post(
            "/api/agent/jobs/claim",
            {"agent_id": tool_agent["id"], "capabilities": ["external_tool"]},
            tool_agent["agent_token"],
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["job"]["claimed_by_agent_id"], tool_agent["id"])

        forged = self.register("reader", ["email"])
        self.store.create_investigation(
            name="Forged claim",
            seed_type="email",
            seed_value="forged@example.com",
            strategy_name="quick",
        )
        status, _body = self.post(
            "/api/agent/tasks/claim",
            {"agent_id": "another-agent", "capabilities": ["email"]},
            forged["agent_token"],
        )
        self.assertEqual(status, 403)

    def test_http_claim_capabilities_cannot_expand_principal_authority(self):
        reader = self.register("reader", ["email"])
        domain_task = self.store.create_investigation(
            name="HTTP task escalation",
            seed_type="domain",
            seed_value="http-escalation.example",
            strategy_name="quick",
        )
        job_task = self.store.create_investigation(
            name="HTTP job escalation",
            seed_type="domain",
            seed_value="http-job-escalation.example",
            strategy_name="quick",
        )
        self.store.replace_jobs(
            job_task.id,
            [
                {
                    "id": "http-reader-escalation-job",
                    "tool_name": "domain_reader",
                    "target_type": "domain",
                    "target_value": "http-job-escalation.example",
                    "depth": 0,
                    "agent_role": "reader",
                }
            ],
        )

        status, task_body = self.post(
            "/api/agent/tasks/claim",
            {"capabilities": ["domain"]},
            reader["agent_token"],
        )
        self.assertEqual(status, 200)
        self.assertIsNone(task_body["task"])
        status, job_body = self.post(
            "/api/agent/jobs/claim",
            {"capabilities": ["reader", "domain_reader"]},
            reader["agent_token"],
        )
        self.assertEqual(status, 200)
        self.assertIsNone(job_body["job"])
        self.assertEqual(self.store.get_investigation(domain_task.id)["status"], "OPEN")
        self.assertIsNone(
            self.store.list_jobs(job_task.id)[0]["claimed_by_agent_id"]
        )

    def test_legacy_shared_token_requires_explicit_opt_in_and_registered_body_identity(self):
        reporter = self.register("reporter")
        investigation = self.claimed_task(reporter)
        path = f"/api/agent/tasks/{investigation.id}/complete"
        payload = {"agent_id": reporter["id"], "summary": "legacy completion"}

        status, _body = self.post(path, payload, "agent-secret")
        self.assertEqual(status, 401)

        enabled_env = {**self.ENV, "OSINT_ALLOW_LEGACY_AGENT_TOKEN": "true"}
        status, _body = self.post(path, payload, "agent-secret", env=enabled_env)
        self.assertEqual(status, 200)

        second = self.register("reporter")
        second_investigation = self.claimed_task(second)
        status, _body = self.post(
            f"/api/agent/tasks/{second_investigation.id}/complete",
            {"summary": "anonymous legacy"},
            "agent-secret",
            env=enabled_env,
        )
        self.assertEqual(status, 401)

    def test_duplicate_authorization_headers_fail_closed_without_resolving_twice(self):
        reader = self.register("reader")
        investigation = self.claimed_task(reader)
        with patch.object(
            self.store,
            "resolve_agent_token",
            wraps=self.store.resolve_agent_token,
        ) as resolve:
            status, _body = self.post(
                "/api/agent/entities",
                {"task_id": investigation.id, **self.ACTIONS["entities"][1]},
                reader["agent_token"],
                headers=[("Authorization", f"Bearer {reader['agent_token']}")],
            )
        self.assertEqual(status, 401)
        resolve.assert_not_called()

        with patch.object(
            self.store,
            "resolve_agent_token",
            wraps=self.store.resolve_agent_token,
        ) as resolve:
            status, _body = self.post(
                "/api/agent/entities",
                {"task_id": investigation.id, **self.ACTIONS["entities"][1]},
                reader["agent_token"],
            )
        self.assertEqual(status, 201)
        resolve.assert_called_once_with(reader["agent_token"])


if __name__ == "__main__":
    unittest.main()
