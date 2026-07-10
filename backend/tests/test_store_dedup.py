import unittest
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.store import MemoryStore, SQLiteStore


class SQLiteDedupTests(unittest.TestCase):
    def test_sqlite_store_migrates_legacy_agent_identity_columns_idempotently(self):
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "legacy-agent.sqlite")
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE agents (
                    id TEXT PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    agent_type TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                INSERT INTO agents VALUES (
                    'legacy-agent', 'legacy', 'cli', '["company"]', 'OFFLINE',
                    '2026-05-21T00:00:00+00:00', '2026-05-21T01:00:00+00:00'
                );
                """
            )
            conn.commit()
            conn.close()

            SQLiteStore(db_path)
            SQLiteStore(db_path)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM agents WHERE id = 'legacy-agent'").fetchone()
            migrations = {
                item[0]
                for item in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            conn.close()

        self.assertEqual(row["agent_name"], "legacy")
        self.assertEqual(row["capabilities_json"], '["company"]')
        self.assertIsNone(row["role_tier"])
        self.assertIsNone(row["token_hash"])
        self.assertIsNone(row["token_created_at"])
        self.assertIsNone(row["disabled_at"])
        self.assertIn("20260710_agent_credentials", migrations)

    def test_memory_store_deduplicates_facts_by_claim(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Fact dedupe",
            seed_type="company",
            seed_value="Example LLC",
            strategy_name="deep",
        )

        first = store.add_fact(
            investigation.id,
            "Example LLC has company identity Example LLC.",
            "Example LLC",
            "has_company_identity",
            "Example LLC",
            "LIKELY",
            0.62,
            "F-3",
            ["ev1"],
        )
        second = store.add_fact(
            investigation.id,
            "Example LLC has company identity Example LLC.",
            "Example LLC",
            "has_company_identity",
            "Example LLC",
            "CONFIRMED",
            0.9,
            "A-2",
            ["ev2"],
        )

        detail = store.get_investigation(investigation.id)

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(detail["facts"]), 1)
        self.assertEqual(detail["facts"][0]["status"], "CONFIRMED")
        self.assertEqual(detail["facts"][0]["confidence"], 0.9)
        self.assertEqual(set(detail["facts"][0]["evidence_ids"]), {"ev1", "ev2"})

    def test_sqlite_store_deduplicates_facts_by_claim(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = store.create_investigation(
                name="Fact dedupe",
                seed_type="company",
                seed_value="Example LLC",
                strategy_name="deep",
            )

            first = store.add_fact(
                investigation.id,
                "Example LLC has company identity Example LLC.",
                "Example LLC",
                "has_company_identity",
                "Example LLC",
                "LIKELY",
                0.62,
                "F-3",
                ["ev1"],
            )
            second = store.add_fact(
                investigation.id,
                "Example LLC has company identity Example LLC.",
                "Example LLC",
                "has_company_identity",
                "Example LLC",
                "CONFIRMED",
                0.9,
                "A-2",
                ["ev2"],
            )

            detail = store.get_investigation(investigation.id)

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(detail["facts"]), 1)
        self.assertEqual(detail["facts"][0]["status"], "CONFIRMED")
        self.assertEqual(detail["facts"][0]["confidence"], 0.9)
        self.assertEqual(set(detail["facts"][0]["evidence_ids"]), {"ev1", "ev2"})

    def test_sqlite_store_deduplicates_entities_evidence_relationships_and_ledger(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = store.create_investigation(
                name="Dedup target",
                seed_type="company",
                seed_value="Dedup LLC",
                strategy_name="standard",
            )

            store.add_entity(investigation.id, "email", "info@example.com", "agent", 0.5)
            store.add_entity(investigation.id, "email", "info@example.com", "agent", 0.8)
            store.add_evidence(investigation.id, "info@example.com", "contact_page", "agent", "first")
            store.add_evidence(investigation.id, "info@example.com", "contact_page", "agent", "second")
            store.add_relationship(investigation.id, "Dedup LLC", "info@example.com", "has_email", 0.5)
            store.add_relationship(investigation.id, "Dedup LLC", "info@example.com", "has_email", 0.8)
            first_record = store.add_evidence_record(
                investigation.id,
                "https://example.com/contact",
                "official_website",
                "agent",
                "Contact page lists info@example.com.",
                0.7,
            )
            second_record = store.add_evidence_record(
                investigation.id,
                "https://example.com/contact?utm=duplicate",
                "official_website",
                "agent",
                "Contact page lists info@example.com.",
                0.7,
            )

            detail = store.get_investigation(investigation.id)

        self.assertEqual(len(detail["entities"]), 1)
        self.assertEqual(detail["entities"][0]["confidence"], 0.8)
        self.assertEqual(len(detail["evidence"]), 1)
        self.assertEqual(detail["evidence"][0]["snippet"], "second")
        self.assertEqual(len(detail["relationships"]), 1)
        self.assertEqual(detail["relationships"][0]["confidence"], 0.8)
        self.assertEqual(first_record["content_hash"], second_record["content_hash"])
        self.assertEqual(len(detail["evidence_ledger"]), 1)

    def test_sqlite_store_migrates_existing_duplicate_evidence_before_unique_index(self):
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "legacy.sqlite")
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE investigations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    seed_type TEXT NOT NULL,
                    seed_value TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    max_depth INTEGER NOT NULL,
                    max_jobs INTEGER NOT NULL,
                    max_entities INTEGER NOT NULL,
                    claimed_by_agent_id TEXT,
                    claimed_by_agent_name TEXT,
                    updated_at TEXT,
                    summary TEXT NOT NULL DEFAULT '',
                    report_markdown TEXT NOT NULL DEFAULT '',
                    confidence REAL,
                    risk_report_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE evidence (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    entity_value TEXT NOT NULL,
                    evidence_kind TEXT NOT NULL,
                    source_tool TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO investigations (
                    id, name, seed_type, seed_value, strategy, status, created_at,
                    max_depth, max_jobs, max_entities, updated_at
                ) VALUES (
                    'inv-legacy', 'Legacy duplicate', 'company', 'Legacy LLC',
                    'standard', 'OPEN', '2026-05-21T00:00:00+00:00',
                    2, 10, 25, '2026-05-21T00:00:00+00:00'
                );
                INSERT INTO evidence (
                    id, investigation_id, entity_value, evidence_kind, source_tool, snippet, created_at
                ) VALUES
                    ('ev-old', 'inv-legacy', 'info@example.com', 'contact_page', 'agent', 'old', '2026-05-21T00:00:00+00:00'),
                    ('ev-new', 'inv-legacy', 'info@example.com', 'contact_page', 'agent', 'new', '2026-05-21T01:00:00+00:00');
                """
            )
            conn.commit()
            conn.close()

            store = SQLiteStore(db_path)
            detail = store.get_investigation("inv-legacy")

        self.assertEqual(len(detail["evidence"]), 1)
        self.assertEqual(detail["evidence"][0]["snippet"], "new")

    def test_sqlite_store_migrates_existing_duplicate_facts(self):
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "legacy-facts.sqlite")
            store = SQLiteStore(db_path)
            investigation = store.create_investigation(
                name="Legacy fact duplicate",
                seed_type="company",
                seed_value="Example LLC",
                strategy_name="deep",
            )
            store.add_fact(
                investigation.id,
                "Example LLC has company identity Example LLC.",
                "Example LLC",
                "has_company_identity",
                "Example LLC",
                "LIKELY",
                0.62,
                "F-3",
                ["ev1"],
            )
            store.add_fact(
                investigation.id,
                "Example LLC has company identity Example LLC.",
                "Example LLC",
                "has_company_identity",
                "Example LLC",
                "CONFIRMED",
                0.9,
                "A-2",
                ["ev2"],
            )
            conn = sqlite3.connect(db_path)
            conn.execute("DROP INDEX IF EXISTS idx_facts_unique_claim")
            conn.execute(
                """
                INSERT INTO facts (
                    id, investigation_id, statement, subject, predicate, object_value,
                    status, promotion_stage, confidence, admiralty_code, evidence_ids_json,
                    observed_at, valid_from, valid_to, supersedes_fact_id
                ) VALUES (
                    'legacy-dup', ?, 'Example LLC has company identity Example LLC.',
                    'Example LLC', 'has_company_identity', 'Example LLC',
                    'LIKELY', 'ASSESSED_FACT', 0.7, 'B-2', '[\"ev3\"]',
                    '2026-05-21T00:00:00+00:00', '2026-05-21T00:00:00+00:00', NULL, NULL
                )
                """,
                (investigation.id,),
            )
            conn.commit()
            conn.close()

            migrated = SQLiteStore(db_path)
            detail = migrated.get_investigation(investigation.id)

        self.assertEqual(len(detail["facts"]), 1)
        self.assertEqual(detail["facts"][0]["status"], "CONFIRMED")
        self.assertGreaterEqual(detail["facts"][0]["confidence"], 0.9)


if __name__ == "__main__":
    unittest.main()
