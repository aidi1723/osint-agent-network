import unittest
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from app.core.agent_auth import hash_agent_token
from app.services.store import MemoryStore, SQLiteStore


class _MigrationBarrierConnection:
    def __init__(self, connection, barrier):
        object.__setattr__(self, "_connection", connection)
        object.__setattr__(self, "_barrier", barrier)
        object.__setattr__(self, "_has_write_lock", False)

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        setattr(self._connection, name, value)

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, *args):
        return self._connection.__exit__(*args)

    def execute(self, sql, *args):
        normalized = " ".join(sql.upper().split())
        if normalized == "BEGIN IMMEDIATE":
            result = self._connection.execute(sql, *args)
            self._has_write_lock = True
            return result
        if normalized == "PRAGMA TABLE_INFO(AGENTS)" and not self._has_write_lock:
            self._barrier.wait(timeout=5)
        return self._connection.execute(sql, *args)


def _prepare_legacy_agent_schema(db_path):
    SQLiteStore(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP INDEX IF EXISTS idx_agents_unique_token_hash")
        conn.execute("ALTER TABLE agents RENAME TO agents_with_credentials")
        conn.execute(
            """
            CREATE TABLE agents (
                id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                status TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
            """
        )
        conn.execute("DROP TABLE agents_with_credentials")
        conn.execute(
            "DELETE FROM schema_migrations WHERE version = ?",
            ("20260710_agent_credentials",),
        )


class SQLiteDedupTests(unittest.TestCase):
    def test_sqlite_store_invalidates_every_ambiguous_duplicate_agent_token(self):
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "duplicate-agent-token.sqlite")
            SQLiteStore(db_path)
            shared_hash = hash_agent_token("shared-token")
            with sqlite3.connect(db_path) as conn:
                conn.execute("DROP INDEX idx_agents_unique_token_hash")
                conn.executemany(
                    """
                    INSERT INTO agents (
                        id, agent_name, agent_type, capabilities_json, status,
                        registered_at, last_seen_at, role_tier, token_hash,
                        token_created_at, disabled_at
                    ) VALUES (?, ?, 'cli', '["company"]', 'ONLINE', ?, ?,
                              'reader', ?, ?, NULL)
                    """,
                    (
                        (
                            "duplicate-a",
                            "duplicate-a",
                            "2026-07-10T00:00:00+00:00",
                            "2026-07-10T00:01:00+00:00",
                            shared_hash,
                            "2026-07-10T00:00:30+00:00",
                        ),
                        (
                            "duplicate-b",
                            "duplicate-b",
                            "2026-07-10T00:02:00+00:00",
                            "2026-07-10T00:03:00+00:00",
                            shared_hash,
                            "2026-07-10T00:02:30+00:00",
                        ),
                    ),
                )
                conn.execute(
                    "DELETE FROM schema_migrations WHERE version = ?",
                    ("20260710_agent_credentials",),
                )

            first = SQLiteStore(db_path)
            self.assertIsNone(first.resolve_agent_token("shared-token"))
            SQLiteStore(db_path)

            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT id, agent_name, status, role_tier, token_hash, token_created_at
                    FROM agents ORDER BY id
                    """
                ).fetchall()
                unique_index = conn.execute(
                    """
                    SELECT 1 FROM sqlite_master
                    WHERE type = 'index' AND name = 'idx_agents_unique_token_hash'
                    """
                ).fetchone()

        self.assertEqual([row[1] for row in rows], ["duplicate-a", "duplicate-b"])
        self.assertTrue(all(row[2] == "ONLINE" and row[3] == "reader" for row in rows))
        self.assertTrue(all(row[4] is None and row[5] is None for row in rows))
        self.assertIsNotNone(unique_index)

    def test_sqlite_store_serializes_concurrent_legacy_agent_migrations(self):
        original_connect = sqlite3.connect
        with TemporaryDirectory() as tmpdir:
            for attempt in range(3):
                with self.subTest(attempt=attempt):
                    db_path = str(Path(tmpdir) / f"concurrent-{attempt}.sqlite")
                    _prepare_legacy_agent_schema(db_path)
                    barrier = Barrier(2)

                    def connect_with_barrier(*args, **kwargs):
                        return _MigrationBarrierConnection(
                            original_connect(*args, **kwargs), barrier
                        )

                    with (
                        patch(
                            "app.services.store.sqlite3.connect",
                            side_effect=connect_with_barrier,
                        ),
                        ThreadPoolExecutor(max_workers=2) as executor,
                    ):
                        futures = [executor.submit(SQLiteStore, db_path) for _ in range(2)]
                        stores = [future.result(timeout=10) for future in futures]

                    self.assertEqual(len(stores), 2)
                    with original_connect(db_path) as conn:
                        columns = {
                            row[1] for row in conn.execute("PRAGMA table_info(agents)")
                        }
                        marker_count = conn.execute(
                            """
                            SELECT COUNT(*) FROM schema_migrations WHERE version = ?
                            """,
                            ("20260710_agent_credentials",),
                        ).fetchone()[0]
                    self.assertTrue(
                        {"role_tier", "token_hash", "token_created_at", "disabled_at"}
                        <= columns
                    )
                    self.assertEqual(marker_count, 1)

    def test_failed_agent_migration_does_not_record_success_marker(self):
        with TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "failed-agent-migration.sqlite")
            _prepare_legacy_agent_schema(db_path)

            with patch(
                "app.services.store._dedupe_existing_rows",
                side_effect=RuntimeError("forced migration failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "forced migration failure"):
                    SQLiteStore(db_path)

            with sqlite3.connect(db_path) as conn:
                marker = conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?",
                    ("20260710_agent_credentials",),
                ).fetchone()
        self.assertIsNone(marker)

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
