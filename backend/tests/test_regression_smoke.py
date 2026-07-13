import unittest

from scripts.regression_smoke import run_regression_cases


class RegressionSmokeTests(unittest.TestCase):
    def test_fixed_cases_cover_requirements_matrix_and_report_sections(self):
        result = run_regression_cases()

        self.assertEqual(result["case_count"], 4)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["suite_kind"], "synthetic_contract")
        self.assertFalse(result["network_accessed"])
        for case in result["cases"]:
            self.assertGreater(case["pir_count"], 0)
            self.assertGreater(case["eei_count"], 0)
            self.assertEqual(case["matrix_rows"], 10)
            self.assertIn("BLUF", case["report_sections"])
            self.assertIn("PIR", case["report_sections"])
            self.assertIn("I&W", case["report_sections"])


if __name__ == "__main__":
    unittest.main()
