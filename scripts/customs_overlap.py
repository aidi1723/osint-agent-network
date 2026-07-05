#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.customs_overlap import SupplierTarget, analyze_customs_overlap


DEFAULT_TARGETS = [
    SupplierTarget(
        key="princeton",
        display_name="Shandong Princeton Metal Products Co., Ltd.",
        aliases=[
            "Shandong Princeton Metal Products Co Ltd",
            "SHANDONG PRINCETON METAL PRODUCTS CO LTD",
        ],
    ),
    SupplierTarget(
        key="orient",
        display_name="Shandong Orient Aluminium Co., Ltd.",
        aliases=[
            "Shandong Orient Aluminium Co Ltd",
            "SHANDONG ORIENT ALUMINIUM CO LTD",
            "Shandong Orient Aluminum Co., Ltd.",
            "Shandong Orient Aluminum Co Ltd",
            "山东东方铝业有限公司",
        ],
    ),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare customs customers for two exact supplier targets.")
    parser.add_argument("input_file", help="CSV/TSV customs export file")
    parser.add_argument("--output-dir", default="reports/customs-overlap", help="Directory for generated CSV/Markdown files")
    parser.add_argument("--supplier-column", default="", help="Supplier/exporter/shipper column name")
    parser.add_argument("--customer-column", default="", help="Buyer/consignee/importer column name")
    args = parser.parse_args(argv)

    result = analyze_customs_overlap(
        input_path=args.input_file,
        output_dir=args.output_dir,
        targets=DEFAULT_TARGETS,
        supplier_column=args.supplier_column or None,
        customer_column=args.customer_column or None,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
