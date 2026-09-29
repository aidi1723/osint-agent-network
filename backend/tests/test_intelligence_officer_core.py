import unittest

from app.core.ach_engine import (
    EvidenceItem,
    Hypothesis,
    default_sparse_lead_hypotheses,
    load_indicator_matrix,
    load_intel_schema,
    run_ach_analysis,
    score_triggered_indicators,
)
from app.core.verification import admiralty_code


class IntelligenceAssetLoaderTests(unittest.TestCase):
    def test_loads_intel_schema_required_sections(self):
        schema = load_intel_schema()

        self.assertIn("entities", schema)
        self.assertIn("evidence", schema)
        self.assertIn("claims", schema)
        self.assertIn("admiralty_code", schema)
        self.assertIn("reports", schema)
        self.assertIn("unknown_markers", schema)
        self.assertIn("identity_confidence_fields", schema["entities"])
        self.assertIn("record_confidence", schema["entities"]["identity_confidence_fields"])
        self.assertIn("identity_match_confidence", schema["entities"]["identity_confidence_fields"])

    def test_loads_indicator_matrix_expected_ids(self):
        matrix = load_indicator_matrix()
        indicator_ids = {indicator["id"] for indicator in matrix["indicators"]}

        self.assertIn("IND_PROJECT_SPEC_PROVIDED", indicator_ids)
        self.assertIn("IND_GENERIC_PRICE_ONLY", indicator_ids)
        self.assertIn("IND_HARD_ASSET_IMPORT", indicator_ids)
        self.assertIn("IND_OFFICIAL_REGISTRY_MATCH", indicator_ids)
        self.assertIn("IND_SAME_NAME_NOISE", indicator_ids)
        self.assertIn("IND_SUPPLY_CHAIN_SHIFT", indicator_ids)


class IndicatorScoringTests(unittest.TestCase):
    def test_scores_triggered_indicators_from_kinds_and_keywords(self):
        evidence = [
            EvidenceItem(
                id="E1",
                summary="Buyer provided drawings, destination, and project timeline.",
                kinds=("project_specification",),
                supports=("alpha_real_procurement",),
                source_reliability="B",
                credibility=0.8,
                keywords=("drawings", "destination", "timeline"),
            ),
            EvidenceItem(
                id="E2",
                summary="Authorized import record includes HS 7604.",
                kinds=("customs_record",),
                supports=("alpha_real_procurement",),
                source_reliability="B",
                credibility=0.75,
                keywords=("HS", "7604", "import"),
            ),
        ]

        result = score_triggered_indicators(evidence)

        self.assertIn("IND_PROJECT_SPEC_PROVIDED", result.triggered_ids)
        self.assertIn("IND_HARD_ASSET_IMPORT", result.triggered_ids)
        self.assertGreater(result.activation_rate, 0)
        self.assertLessEqual(result.activation_rate, 1)
        self.assertGreater(result.score, 0)

    def test_empty_evidence_has_zero_activation(self):
        result = score_triggered_indicators([])

        self.assertEqual(result.triggered_ids, [])
        self.assertEqual(result.activation_rate, 0.0)
        self.assertEqual(result.score, 0.0)


class AchEngineTests(unittest.TestCase):
    def test_ach_prefers_fewest_weighted_contradictions(self):
        hypotheses = [
            Hypothesis("alpha_real_procurement", "Real B2B buyer comparing suppliers for a live project"),
            Hypothesis("beta_price_benchmarking", "Buyer is benchmarking price to pressure an incumbent supplier"),
            Hypothesis("gamma_noise_or_unmatched_identity", "Same-name noise or insufficient identity match"),
        ]
        evidence = [
            EvidenceItem(
                id="E1",
                summary="Buyer supplied drawings, quantity, destination, and timeline.",
                kinds=("project_specification",),
                supports=("alpha_real_procurement",),
                contradicts=("gamma_noise_or_unmatched_identity",),
                source_reliability="B",
                credibility=0.8,
                keywords=("drawings", "quantity", "destination", "timeline"),
            ),
            EvidenceItem(
                id="E2",
                summary="Official registry confirms a matching active company.",
                kinds=("government_registry",),
                supports=("alpha_real_procurement",),
                contradicts=("gamma_noise_or_unmatched_identity",),
                source_reliability="A",
                credibility=0.92,
                keywords=("registry", "active"),
            ),
            EvidenceItem(
                id="E3",
                summary="Buyer also asked for generic MOQ.",
                kinds=("generic_price_request",),
                supports=("beta_price_benchmarking",),
                source_reliability="C",
                credibility=0.55,
                keywords=("moq", "price"),
            ),
        ]

        result = run_ach_analysis(hypotheses, evidence)

        self.assertEqual(result.most_likely_hypothesis, "alpha_real_procurement")
        statuses = {item["id"]: item["status"] for item in result.hypotheses}
        self.assertEqual(statuses["alpha_real_procurement"], "MOST_LIKELY")
        self.assertIn(statuses["gamma_noise_or_unmatched_identity"], {"DISFAVORED", "REJECTED"})
        self.assertIn("IND_PROJECT_SPEC_PROVIDED", result.triggered_indicators)
        self.assertGreater(result.indicator_activation_rate, 0)

    def test_ach_does_not_force_winner_without_evidence(self):
        hypotheses = [
            Hypothesis("alpha_real_procurement", "Real B2B buyer"),
            Hypothesis("beta_price_benchmarking", "Price benchmarking"),
        ]

        result = run_ach_analysis(hypotheses, [])

        self.assertEqual(result.most_likely_hypothesis, "")
        self.assertEqual(result.indicator_activation_rate, 0.0)
        self.assertTrue(all(item["status"] == "UNVERIFIED" for item in result.hypotheses))
        self.assertEqual(result.confidence_language, "很不可能")


class DefaultHypothesisAndAdmiraltyTests(unittest.TestCase):
    def test_default_sparse_lead_hypotheses_include_three_competing_scenarios(self):
        hypotheses = default_sparse_lead_hypotheses()
        ids = [hypothesis.id for hypothesis in hypotheses]

        self.assertEqual(
            ids,
            [
                "alpha_real_procurement",
                "beta_price_benchmarking",
                "gamma_noise_or_unmatched_identity",
            ],
        )

    def test_admiralty_examples_cover_strong_and_weak_sources(self):
        official = admiralty_code("government_registry", 0.96)
        weak = admiralty_code("single_weak_signal", 0.55)

        self.assertEqual(official["code"], "A-1")
        self.assertEqual(weak["code"], "D-3")


if __name__ == "__main__":
    unittest.main()
