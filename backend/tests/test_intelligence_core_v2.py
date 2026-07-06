import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.evidence_ledger import EvidenceLedgerRecord, build_evidence_record
from app.core.fact_pool import FactRecord, supersede_fact, validate_fact_record
from app.services.store import SQLiteStore


class IntelligenceCoreV2DomainTests(unittest.TestCase):
    def test_confirmed_fact_requires_evidence_and_admiralty_code(self):
        fact = FactRecord(
            id="fact-1",
            investigation_id="inv-1",
            statement="SampleCo uses xs@csituo.com as a public contact email.",
            subject="Sample Auto Parts Co.",
            predicate="uses_contact_email",
            object="xs@csituo.com",
            status="CONFIRMED",
            confidence=0.82,
            admiralty_code="A-2",
            evidence_ids=["ev-1"],
            observed_at="2026-05-21T00:00:00+00:00",
            valid_from="2026-05-21T00:00:00+00:00",
        )

        validate_fact_record(fact)

    def test_confirmed_fact_without_evidence_fails_validation(self):
        fact = FactRecord(
            id="fact-1",
            investigation_id="inv-1",
            statement="SampleCo uses xs@csituo.com as a public contact email.",
            subject="Sample Auto Parts Co.",
            predicate="uses_contact_email",
            object="xs@csituo.com",
            status="CONFIRMED",
            confidence=0.82,
            admiralty_code="A-2",
            evidence_ids=[],
            observed_at="2026-05-21T00:00:00+00:00",
            valid_from="2026-05-21T00:00:00+00:00",
        )

        with self.assertRaises(ValueError):
            validate_fact_record(fact)

    def test_superseded_fact_keeps_old_validity_window(self):
        old_fact = FactRecord(
            id="fact-old",
            investigation_id="inv-1",
            statement="Company phone is +86-991-3966766.",
            subject="Sample Auto Parts Branch",
            predicate="has_phone",
            object="+86-991-3966766",
            status="CONFIRMED",
            confidence=0.86,
            admiralty_code="A-2",
            evidence_ids=["ev-1"],
            observed_at="2026-05-20T00:00:00+00:00",
            valid_from="2026-05-20T00:00:00+00:00",
        )

        retired, replacement = supersede_fact(
            old_fact,
            new_id="fact-new",
            new_object="+86-991-3966788",
            observed_at="2026-05-21T00:00:00+00:00",
            evidence_ids=["ev-2"],
        )

        self.assertEqual(retired.status, "RETIRED")
        self.assertEqual(retired.valid_to, "2026-05-21T00:00:00+00:00")
        self.assertEqual(replacement.supersedes_fact_id, "fact-old")
        self.assertEqual(replacement.object, "+86-991-3966788")


class EvidenceLedgerTests(unittest.TestCase):
    def test_evidence_record_assigns_admiralty_and_hash(self):
        record = build_evidence_record(
            id="ev-1",
            investigation_id="inv-1",
            source_url="https://www.example-target.test/en/",
            source_type="official_website",
            source_tool="official_web",
            snippet="SampleCo contact page lists xs@csituo.com.",
            observed_at="2026-05-21T00:00:00+00:00",
            credibility=0.82,
        )

        self.assertIsInstance(record, EvidenceLedgerRecord)
        self.assertEqual(record.admiralty_code, "A-2")
        self.assertEqual(len(record.content_hash), 16)


class CoreV2StoreTests(unittest.TestCase):
    def test_sqlite_store_persists_facts_and_evidence_ledger(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = store.create_investigation(
                name="SampleCo core v2",
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

            detail = SQLiteStore(str(Path(tmpdir) / "osint.sqlite")).get_investigation(
                investigation.id
            )

        self.assertEqual(detail["evidence_ledger"][0]["admiralty_code"], "A-2")
        self.assertEqual(detail["facts"][0]["id"], fact["id"])
        self.assertEqual(detail["facts"][0]["evidence_ids"], [evidence["id"]])


class HypothesisPoolStoreTests(unittest.TestCase):
    def test_store_scores_hypotheses_with_ach(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = store.create_investigation(
                name="SampleCo ACH",
                seed_type="company",
                seed_value="Sample Auto Parts Co.",
                strategy_name="deep",
            )
            store.add_hypothesis(
                investigation.id,
                "h1",
                "SampleCo is an active export brand network.",
            )
            store.add_hypothesis(
                investigation.id,
                "h2",
                "SampleCo is only a dormant brand shell.",
            )
            store.add_hypothesis(
                investigation.id,
                "h3",
                "SampleCo evidence is mostly same-name noise.",
            )
            result = store.score_hypotheses(
                investigation.id,
                [
                    {
                        "id": "ev-export",
                        "summary": "MIMS exhibitor page shows SampleCo export contact and product categories.",
                        "kinds": ["company_news_report"],
                        "supports": ["h1"],
                        "contradicts": ["h2", "h3"],
                        "source_reliability": "B",
                        "credibility": 0.72,
                        "keywords": ["exhibitor", "export"],
                    }
                ],
            )

            detail = SQLiteStore(str(Path(tmpdir) / "osint.sqlite")).get_investigation(
                investigation.id
            )

        self.assertEqual(result["most_likely_hypothesis"], "h1")
        self.assertTrue(any(row["id"] == "h1" for row in result["hypotheses"]))
        self.assertEqual(detail["hypothesis_analysis"]["most_likely_hypothesis"], "h1")
        self.assertTrue(
            any(item["id"] == "h1" and item["status"] == "MOST_LIKELY" for item in detail["hypotheses"])
        )
