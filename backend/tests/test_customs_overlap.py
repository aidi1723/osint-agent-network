from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import unittest

from app.core.customs_overlap import (
    SupplierTarget,
    analyze_customs_overlap,
    normalize_company_name,
)


class CustomsOverlapTest(unittest.TestCase):
    def test_normalize_company_name_handles_punctuation_and_ltd_variants(self):
        self.assertEqual(
            normalize_company_name(" Shandong Orient Aluminium Co., Ltd. "),
            normalize_company_name("SHANDONG ORIENT ALUMINIUM CO LTD"),
        )
        self.assertEqual(
            normalize_company_name("Shandong Orient Aluminium Co Ltd"),
            normalize_company_name("Shandong Orient Aluminum Co Ltd"),
        )

    def test_analyze_customs_overlap_filters_targets_and_finds_shared_buyers(self):
        with TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "customs.csv"
            output_dir = Path(tmp) / "out"
            with input_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=["Exporter", "Consignee", "HS Code", "Date"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Exporter": "SHANDONG PRINCETON METAL PRODUCTS CO LTD",
                        "Consignee": "Acme Windows LLC",
                        "HS Code": "7604",
                        "Date": "2025-01-10",
                    }
                )
                writer.writerow(
                    {
                        "Exporter": "Shandong Orient Aluminium Co., Ltd.",
                        "Consignee": "ACME WINDOWS, L.L.C.",
                        "HS Code": "7604",
                        "Date": "2025-02-11",
                    }
                )
                writer.writerow(
                    {
                        "Exporter": "Shandong Orient Aluminium Co Ltd",
                        "Consignee": "Delta Facade Inc",
                        "HS Code": "7610",
                        "Date": "2025-03-12",
                    }
                )
                writer.writerow(
                    {
                        "Exporter": "Unrelated Supplier",
                        "Consignee": "Acme Windows LLC",
                        "HS Code": "7604",
                        "Date": "2025-04-13",
                    }
                )

            result = analyze_customs_overlap(
                input_path=input_path,
                output_dir=output_dir,
                targets=[
                    SupplierTarget(
                        key="princeton",
                        display_name="Shandong Princeton Metal Products Co., Ltd.",
                        aliases=["Shandong Princeton Metal Products Co Ltd"],
                    ),
                    SupplierTarget(
                        key="orient",
                        display_name="Shandong Orient Aluminium Co., Ltd.",
                        aliases=["Shandong Orient Aluminium Co Ltd"],
                    ),
                ],
            )

            self.assertEqual(result.supplier_column, "Exporter")
            self.assertEqual(result.customer_column, "Consignee")
            self.assertEqual(result.target_counts["princeton"], 1)
            self.assertEqual(result.target_counts["orient"], 2)
            self.assertEqual(result.overlap_customers, ["ACME WINDOWS LLC"])
            self.assertTrue((output_dir / "princeton_customers.csv").exists())
            self.assertTrue((output_dir / "orient_customers.csv").exists())
            self.assertTrue((output_dir / "overlap_customers.csv").exists())
            self.assertTrue((output_dir / "customs_overlap_summary.md").exists())


if __name__ == "__main__":
    unittest.main()
