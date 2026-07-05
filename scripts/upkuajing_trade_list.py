#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.upkuajing_customs import UpkuajingCustomsClient, UpkuajingCustomsError


DEFAULT_PAYLOAD: dict[str, Any] = {
    "tradeCode": "",
    "products": [],
    "hscodes": [],
    "productTags": [],
    "sellerCompanyId": 0,
    "seller": "",
    "sellerPort": "",
    "sellerCountryCodes": [],
    "originCountryCodes": [],
    "buyerCompanyId": 0,
    "buyer": "",
    "buyerPort": "",
    "buyerCountryCodes": [],
    "arrivalCountryCodes": [],
    "transportModeCodes": [],
    "isExact": True,
    "existWebsiteSeller": 0,
    "existEmailSeller": 0,
    "existPhoneSeller": 0,
    "existWhatsappSeller": 0,
    "existSocialSeller": 0,
    "existWebsiteBuyer": 0,
    "existEmailBuyer": 0,
    "existPhoneBuyer": 0,
    "existWhatsappBuyer": 0,
    "existSocialBuyer": 0,
    "sorting_field": "tradeDate",
    "sorting_direction": "desc",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query Upkuajing customs trade list API.")
    parser.add_argument("--seller", default="", help="Supplier/exporter company name")
    parser.add_argument("--buyer", default="", help="Buyer/importer company name")
    parser.add_argument("--product", action="append", default=[], help="Product keyword; can be repeated")
    parser.add_argument("--hscode", action="append", default=[], help="HS code; can be repeated")
    parser.add_argument("--date-start", default="", help="Start date in YYYY-MM-DD")
    parser.add_argument("--date-end", default="", help="End date in YYYY-MM-DD")
    parser.add_argument("--cursor", default="", help="Pagination cursor returned by the API")
    parser.add_argument("--fuzzy", action="store_true", help="Use fuzzy company matching instead of exact matching")
    parser.add_argument("--output", default="", help="Write JSON response to this path")
    args = parser.parse_args(argv)

    payload = dict(DEFAULT_PAYLOAD)
    payload.update(
        {
            "seller": args.seller,
            "buyer": args.buyer,
            "products": args.product,
            "hscodes": args.hscode,
            "isExact": not args.fuzzy,
        }
    )
    if args.date_start:
        payload["dateStart"] = _date_to_ms(args.date_start)
    if args.date_end:
        payload["dateEnd"] = _date_to_ms(args.date_end)
    if args.cursor:
        payload["cursor"] = args.cursor

    try:
        result = UpkuajingCustomsClient().trade_list(payload)
    except UpkuajingCustomsError as exc:
        print(json.dumps(exc.payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
        print(str(output_path))
    else:
        print(text)
    return 0


def _date_to_ms(value: str) -> int:
    date = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(date.timestamp() * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
