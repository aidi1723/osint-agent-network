import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.tests.test_agent_auth import ApiTestServer, PRODUCTION_ENV, json_payload
from app import main as app_main
from app.core.agent_auth import hash_agent_token
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
            capabilities=capabilities or ["company"],
            role_tier=role_tier,
        )

    def disable_agent(self, agent_id):
        raise NotImplementedError

    def stored_token_hash(self, agent_id):
        raise NotImplementedError

    def clear_agent_token(self, agent_id):
        raise NotImplementedError

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

        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["role_tier"], "reporter")
        self.assertEqual(len(self.store.list_agents()), 1)
        self.assertIsNone(self.store.resolve_agent_token(first["agent_token"]))
        self.assertEqual(
            self.store.resolve_agent_token(second["agent_token"])["id"],
            first["id"],
        )

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
        registration = self.register(capabilities=["company"])
        agent_id = registration["id"]

        claimed_job = self.store.claim_job(agent_id, ["reader"])
        claimed_investigation = self.store.claim_task(agent_id, ["company"])
        self.assertIsNotNone(claimed_job)
        self.assertIsNotNone(claimed_investigation)
        return agent_id, claimed, job_claimed, unrelated

    def test_investigation_access_requires_exact_role_and_matching_claim(self):
        agent_id, claimed, job_claimed, unrelated = self.create_access_claims()

        self.assertTrue(self.store.agent_has_investigation_access(agent_id, claimed.id, "reader"))
        self.assertTrue(self.store.agent_has_investigation_access(agent_id, job_claimed.id, "reader"))
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
                        agent_id, job_claimed.id, "reader"
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
                        agent_id, job_claimed.id, "reader"
                    )
                )

        self.store.update_job_status("reader-job", "CLAIMED")
        for parent_status in ("CLAIMED", "RUNNING"):
            with self.subTest(active_parent_status=parent_status):
                self.store.set_investigation_status(job_claimed.id, parent_status)
                self.assertTrue(
                    self.store.agent_has_investigation_access(
                        agent_id, job_claimed.id, "reader"
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
                        agent_id, job_claimed.id, "reader"
                    )
                )


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


if __name__ == "__main__":
    unittest.main()
