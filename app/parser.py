from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_COLUMNS = (
    "date",
    "invoice_no",
    "region",
    "branch",
    "outlet_id",
    "outlet_name",
    "outlet_type",
    "salesman",
    "brand",
    "sku",
    "qty_carton",
    "price_per_carton_idr",
    "gross_sales_idr",
    "discount_idr",
    "net_sales_idr",
)

REGION_ALIASES: dict[str, str] = {
    "jabodetabek": "Jabodetabek",
    "jawa barat": "Jawa Barat",
    "jabar": "Jawa Barat",
    "jawa tengah": "Jawa Tengah",
    "jateng": "Jawa Tengah",
    "jawa timur": "Jawa Timur",
    "jatim": "Jawa Timur",
    "sumatera": "Sumatera",
    "sumatra": "Sumatera",
    "kalimantan": "Kalimantan",
}


@dataclass(frozen=True)
class SalesRow:
    """Single normalized invoice line."""

    date: str
    month: str
    invoice_no: str
    region: str
    raw_region: str
    branch: str
    outlet_id: str
    outlet_name: str
    outlet_type: str
    salesman: str
    brand: str
    sku: str
    qty_carton: int
    price_per_carton_idr: int
    gross_sales_idr: int
    discount_idr: int
    net_sales_idr: int
    is_return: bool
    is_duplicate: bool


@dataclass
class HygieneReport:
    """Audit details collected during CSV ingestion and cleaning."""

    raw_row_count: int = 0
    deduplicated_row_count: int = 0
    region_normalized_count: int = 0
    region_alias_examples: dict[str, str] = field(default_factory=dict)
    trimmed_whitespace_count: int = 0
    missing_salesman_count: int = 0
    duplicate_count: int = 0
    duplicate_net_sales_idr: int = 0
    duplicate_examples: list[dict[str, object]] = field(default_factory=list)
    return_count: int = 0
    return_net_sales_idr: int = 0
    return_examples: list[dict[str, object]] = field(default_factory=list)
    shared_outlet_names: dict[str, list[str]] = field(default_factory=dict)
    date_min: str = ""
    date_max: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_row_count": self.raw_row_count,
            "deduplicated_row_count": self.deduplicated_row_count,
            "region_normalized_count": self.region_normalized_count,
            "region_alias_examples": self.region_alias_examples,
            "trimmed_whitespace_count": self.trimmed_whitespace_count,
            "missing_salesman_count": self.missing_salesman_count,
            "duplicate_count": self.duplicate_count,
            "duplicate_net_sales_idr": self.duplicate_net_sales_idr,
            "duplicate_examples": self.duplicate_examples,
            "return_count": self.return_count,
            "return_net_sales_idr": self.return_net_sales_idr,
            "return_examples": self.return_examples,
            "shared_outlet_names": self.shared_outlet_names,
            "date_min": self.date_min,
            "date_max": self.date_max,
        }


@dataclass
class ParsedDataset:
    """Complete parsed dataset including raw-order rows and hygiene audit."""

    rows: list[SalesRow]
    hygiene: HygieneReport
    source_name: str = "sales.csv"


def canonicalize_region(raw_region: str) -> str:
    """Map region casing variants and abbreviations to canonical region names."""
    cleaned = " ".join(raw_region.strip().split())
    key = cleaned.lower()
    if key in REGION_ALIASES:
        return REGION_ALIASES[key]
    return cleaned.title() if cleaned else "Unknown"


def _parse_int(value: str, field_name: str, row_idx: int) -> int:
    try:
        return int(float(value.strip()))
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"Invalid numeric value for '{field_name}' at row {row_idx}: {value!r}"
        ) from exc


def parse_csv_text(csv_text: str, source_name: str = "uploaded.csv") -> ParsedDataset:
    """Parse and clean sales CSV text into normalized rows plus an audit report."""
    if not csv_text or not csv_text.strip():
        raise ValueError("CSV input is empty.")

    normalized_text = csv_text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(normalized_text))
    if not reader.fieldnames:
        raise ValueError("CSV header row is missing.")

    header_set = {col.strip() for col in reader.fieldnames if col}
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in header_set]
    if missing_cols:
        raise ValueError(
            f"Missing required CSV columns: {', '.join(missing_cols)}"
        )

    report = HygieneReport()
    rows: list[SalesRow] = []
    seen_exact: set[tuple[object, ...]] = set()
    outlet_names_to_ids: dict[str, set[str]] = defaultdict(set)

    for idx, raw_row in enumerate(reader, start=2):
        if not any(v and v.strip() for v in raw_row.values()):
            continue

        cleaned_fields: dict[str, str] = {}
        for col in REQUIRED_COLUMNS:
            raw_val = raw_row.get(col)
            raw_str = "" if raw_val is None else str(raw_val)
            trimmed = raw_str.strip()
            if trimmed != raw_str:
                report.trimmed_whitespace_count += 1
            cleaned_fields[col] = trimmed

        date_val = cleaned_fields["date"]
        if len(date_val) < 7 or date_val[4] != "-":
            raise ValueError(f"Invalid date format at row {idx}: {date_val!r}")

        raw_region = cleaned_fields["region"]
        canonical_region = canonicalize_region(raw_region)
        if raw_region != canonical_region:
            report.region_normalized_count += 1
            report.region_alias_examples[raw_region] = canonical_region

        salesman = cleaned_fields["salesman"]
        if not salesman:
            salesman = "Unassigned"
            report.missing_salesman_count += 1

        qty = _parse_int(cleaned_fields["qty_carton"], "qty_carton", idx)
        price = _parse_int(
            cleaned_fields["price_per_carton_idr"], "price_per_carton_idr", idx
        )
        gross = _parse_int(cleaned_fields["gross_sales_idr"], "gross_sales_idr", idx)
        discount = _parse_int(cleaned_fields["discount_idr"], "discount_idr", idx)
        net = _parse_int(cleaned_fields["net_sales_idr"], "net_sales_idr", idx)

        invoice_no = cleaned_fields["invoice_no"]
        is_return = invoice_no.upper().startswith("RTR") or qty < 0 or net < 0

        dedup_key = (
            date_val,
            invoice_no,
            canonical_region,
            cleaned_fields["branch"],
            cleaned_fields["outlet_id"],
            cleaned_fields["outlet_name"],
            cleaned_fields["outlet_type"],
            salesman,
            cleaned_fields["brand"],
            cleaned_fields["sku"],
            qty,
            price,
            gross,
            discount,
            net,
        )
        is_duplicate = dedup_key in seen_exact
        seen_exact.add(dedup_key)

        row_obj = SalesRow(
            date=date_val,
            month=date_val[:7],
            invoice_no=invoice_no,
            region=canonical_region,
            raw_region=raw_region,
            branch=cleaned_fields["branch"],
            outlet_id=cleaned_fields["outlet_id"],
            outlet_name=cleaned_fields["outlet_name"],
            outlet_type=cleaned_fields["outlet_type"],
            salesman=salesman,
            brand=cleaned_fields["brand"],
            sku=cleaned_fields["sku"],
            qty_carton=qty,
            price_per_carton_idr=price,
            gross_sales_idr=gross,
            discount_idr=discount,
            net_sales_idr=net,
            is_return=is_return,
            is_duplicate=is_duplicate,
        )
        rows.append(row_obj)
        outlet_names_to_ids[row_obj.outlet_name].add(row_obj.outlet_id)

        if is_duplicate:
            report.duplicate_count += 1
            report.duplicate_net_sales_idr += net
            report.duplicate_examples.append(
                {
                    "date": date_val,
                    "invoice_no": invoice_no,
                    "outlet_id": row_obj.outlet_id,
                    "outlet_name": row_obj.outlet_name,
                    "sku": row_obj.sku,
                    "net_sales_idr": net,
                }
            )
        if is_return:
            report.return_count += 1
            report.return_net_sales_idr += net
            report.return_examples.append(
                {
                    "date": date_val,
                    "invoice_no": invoice_no,
                    "outlet_id": row_obj.outlet_id,
                    "outlet_name": row_obj.outlet_name,
                    "sku": row_obj.sku,
                    "qty_carton": qty,
                    "net_sales_idr": net,
                }
            )

    if not rows:
        raise ValueError("CSV contains a header but no data rows.")

    report.raw_row_count = len(rows)
    report.deduplicated_row_count = len(rows) - report.duplicate_count
    report.date_min = min(r.date for r in rows)
    report.date_max = max(r.date for r in rows)
    report.shared_outlet_names = {
        name: sorted(ids)
        for name, ids in sorted(outlet_names_to_ids.items())
        if len(ids) > 1
    }

    return ParsedDataset(rows=rows, hygiene=report, source_name=source_name)


def load_csv_file(path: Path) -> ParsedDataset:
    """Load and parse a CSV file from disk."""
    text = path.read_text(encoding="utf-8")
    return parse_csv_text(text, source_name=path.name)
