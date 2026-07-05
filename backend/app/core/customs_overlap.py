from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import re


SUPPLIER_HEADERS = (
    "supplier",
    "exporter",
    "shipper",
    "manufacturer",
    "seller",
    "供应商",
    "出口商",
    "发货人",
    "生产商",
)

CUSTOMER_HEADERS = (
    "buyer",
    "customer",
    "consignee",
    "importer",
    "notify party",
    "purchaser",
    "客户",
    "买家",
    "收货人",
    "进口商",
    "采购商",
)


@dataclass(frozen=True)
class SupplierTarget:
    key: str
    display_name: str
    aliases: list[str]


@dataclass(frozen=True)
class CustomsOverlapResult:
    input_path: str
    output_dir: str
    supplier_column: str
    customer_column: str
    target_counts: dict[str, int]
    customer_counts: dict[str, int]
    customers_by_target: dict[str, list[str]]
    overlap_customers: list[str]
    output_files: dict[str, str]


def normalize_company_name(value: str) -> str:
    text = value.upper()
    text = re.sub(r"\bL\s*\.?\s*L\s*\.?\s*C\s*\.?\b", "LLC", text)
    text = re.sub(r"\bC\s*\.\s*O\s*\.?\b", "CO", text)
    text = text.replace("ALUMINIUM", "ALUMINUM")
    text = text.replace("&", " AND ")
    text = re.sub(r"\b(LIMITED|LTD\.?)\b", "LTD", text)
    text = re.sub(r"\b(COMPANY|CO\.?)\b", "CO", text)
    text = re.sub(r"\b(INCORPORATED|INC\.?)\b", "INC", text)
    text = re.sub(r"\b(L\.L\.C\.|LLC\.?)\b", "LLC", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def analyze_customs_overlap(
    input_path: str | Path,
    output_dir: str | Path,
    targets: list[SupplierTarget],
    supplier_column: str | None = None,
    customer_column: str | None = None,
) -> CustomsOverlapResult:
    source = Path(input_path)
    destination = Path(output_dir)
    if source.suffix.lower() not in {".csv", ".tsv"}:
        raise ValueError("Only CSV/TSV customs exports are supported by this dependency-free tool.")

    delimiter = "\t" if source.suffix.lower() == ".tsv" else ","
    with source.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("Input file has no header row.")
        fieldnames = list(reader.fieldnames)
        supplier_field = supplier_column or _detect_column(fieldnames, SUPPLIER_HEADERS, "supplier/exporter")
        customer_field = customer_column or _detect_column(fieldnames, CUSTOMER_HEADERS, "buyer/consignee")
        rows = list(reader)

    target_lookup = _build_target_lookup(targets)
    matched_rows: dict[str, list[dict[str, str]]] = {target.key: [] for target in targets}
    customer_sets: dict[str, set[str]] = {target.key: set() for target in targets}

    for row in rows:
        supplier_value = normalize_company_name(row.get(supplier_field, ""))
        target_key = target_lookup.get(supplier_value)
        if target_key is None:
            continue
        customer_value = normalize_company_name(row.get(customer_field, ""))
        if not customer_value:
            continue
        matched_rows[target_key].append(row)
        customer_sets[target_key].add(customer_value)

    overlap = sorted(set.intersection(*customer_sets.values())) if customer_sets else []
    destination.mkdir(parents=True, exist_ok=True)

    output_files: dict[str, str] = {}
    customer_counts: dict[str, int] = {}
    customers_by_target: dict[str, list[str]] = {}
    for target in targets:
        customers = sorted(customer_sets[target.key])
        customers_by_target[target.key] = customers
        customer_counts[target.key] = len(customers)
        path = destination / f"{target.key}_customers.csv"
        _write_customer_csv(path, customers)
        output_files[f"{target.key}_customers"] = str(path)

    overlap_path = destination / "overlap_customers.csv"
    _write_customer_csv(overlap_path, overlap)
    output_files["overlap_customers"] = str(overlap_path)

    summary_path = destination / "customs_overlap_summary.md"
    _write_summary(
        summary_path,
        source,
        supplier_field,
        customer_field,
        targets,
        matched_rows,
        customer_counts,
        overlap,
    )
    output_files["summary"] = str(summary_path)

    return CustomsOverlapResult(
        input_path=str(source),
        output_dir=str(destination),
        supplier_column=supplier_field,
        customer_column=customer_field,
        target_counts={key: len(value) for key, value in matched_rows.items()},
        customer_counts=customer_counts,
        customers_by_target=customers_by_target,
        overlap_customers=overlap,
        output_files=output_files,
    )


def _build_target_lookup(targets: list[SupplierTarget]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for target in targets:
        for value in [target.display_name, *target.aliases]:
            lookup[normalize_company_name(value)] = target.key
    return lookup


def _detect_column(fieldnames: list[str], candidates: tuple[str, ...], label: str) -> str:
    normalized = {normalize_company_name(name): name for name in fieldnames}
    for candidate in candidates:
        key = normalize_company_name(candidate)
        if key in normalized:
            return normalized[key]
    for name in fieldnames:
        lowered = name.lower()
        if any(candidate in lowered for candidate in candidates if candidate.isascii()):
            return name
    raise ValueError(f"Could not detect {label} column. Pass it explicitly.")


def _write_customer_csv(path: Path, customers: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["customer_normalized"])
        for customer in customers:
            writer.writerow([customer])


def _write_summary(
    path: Path,
    source: Path,
    supplier_field: str,
    customer_field: str,
    targets: list[SupplierTarget],
    matched_rows: dict[str, list[dict[str, str]]],
    customer_counts: dict[str, int],
    overlap: list[str],
) -> None:
    lines = [
        "# 海关客户重叠比对",
        "",
        f"- 源文件：`{source}`",
        f"- 供应商字段：`{supplier_field}`",
        f"- 客户字段：`{customer_field}`",
        "",
        "## 供应商客户统计",
    ]
    for target in targets:
        lines.append(
            f"- {target.display_name}: {len(matched_rows[target.key])} 条记录，{customer_counts[target.key]} 个去重客户"
        )
    lines.extend(["", "## 重叠客户", ""])
    if overlap:
        lines.extend(f"- {customer}" for customer in overlap)
    else:
        lines.append("- 未发现重叠客户")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
