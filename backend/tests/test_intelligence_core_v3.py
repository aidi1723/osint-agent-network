import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.fact_pool import FactRecord, validate_fact_record
from app.services.store import SQLiteStore


class IntelligenceCoreV3Tests(unittest.TestCase):
    def test_fact_record_accepts_and_validates_promotion_stage(self):
        fact = FactRecord(
            id="fact-1",
            investigation_id="inv-1",
            statement="Example LLC operates example.com.",
            subject="Example LLC",
            predicate="operates",
            object="example.com",
            status="CONFIRMED",
            promotion_stage="ACCEPTED_FACT",
            confidence=0.9,
            admiralty_code="A-2",
            evidence_ids=["ev-1"],
            observed_at="2026-05-22T00:00:00+00:00",
            valid_from="2026-05-22T00:00:00+00:00",
        )

        validate_fact_record(fact)

    def test_invalid_promotion_stage_is_rejected(self):
        fact = FactRecord(
            id="fact-1",
            investigation_id="inv-1",
            statement="Example LLC operates example.com.",
            subject="Example LLC",
            predicate="operates",
            object="example.com",
            status="CONFIRMED",
            promotion_stage="FINAL_TRUTH",
            confidence=0.9,
            admiralty_code="A-2",
            evidence_ids=["ev-1"],
            observed_at="2026-05-22T00:00:00+00:00",
            valid_from="2026-05-22T00:00:00+00:00",
        )

        with self.assertRaises(ValueError):
            validate_fact_record(fact)

    def test_store_migrates_legacy_facts_to_promotion_stage(self):
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
                CREATE TABLE facts (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_value TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    admiralty_code TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    supersedes_fact_id TEXT
                );
                INSERT INTO investigations (
                    id, name, seed_type, seed_value, strategy, status, created_at,
                    max_depth, max_jobs, max_entities, updated_at
                ) VALUES (
                    'inv-legacy', 'Legacy', 'company', 'Legacy LLC',
                    'standard', 'OPEN', '2026-05-21T00:00:00+00:00',
                    2, 10, 25, '2026-05-21T00:00:00+00:00'
                );
                INSERT INTO facts (
                    id, investigation_id, statement, subject, predicate, object_value,
                    status, confidence, admiralty_code, evidence_ids_json, observed_at, valid_from
                ) VALUES (
                    'fact-1', 'inv-legacy', 'Legacy LLC operates publicly.', 'Legacy LLC',
                    'operates', 'publicly', 'CONFIRMED', 0.9, 'A-2', '["ev-1"]',
                    '2026-05-21T00:00:00+00:00', '2026-05-21T00:00:00+00:00'
                );
                """
            )
            conn.commit()
            conn.close()

            store = SQLiteStore(db_path)
            detail = store.get_investigation("inv-legacy")

        self.assertEqual(detail["facts"][0]["promotion_stage"], "ACCEPTED_FACT")

    def test_investigation_detail_includes_requirements_and_matrix(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            inv = store.create_investigation("Example", "company", "Example LLC", "standard")
            store.add_entity(inv.id, "company", "Example LLC", "official_web", 0.9)
            store.add_entity(inv.id, "domain", "example.com", "official_web", 0.9)
            detail = store.get_investigation(inv.id)

        self.assertIn("intelligence_requirements", detail)
        self.assertIn("cross_verification_matrix", detail)
        self.assertTrue(detail["intelligence_requirements"]["pirs"])
        identity = next(row for row in detail["cross_verification_matrix"] if row["field_key"] == "company_identity")
        self.assertEqual(identity["candidate_value"], "Example LLC")


if __name__ == "__main__":
    unittest.main()
