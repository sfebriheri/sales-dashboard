from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date as dt_date

from app.parser import ParsedDataset, SalesRow


@dataclass(frozen=True)
class DashboardFilters:
    """Filter and data-hygiene configuration for dashboard queries."""

    month: str = "all"
    region: str = "all"
    brand: str = "all"
    outlet_type: str = "all"
    deduplicate: bool = True
    include_returns: bool = True


def _pct(part: float, whole: float) -> float:
    return round((part / whole) * 100, 1) if whole else 0.0


def _days_between(older_iso: str, newer_iso: str) -> int:
    try:
        d1 = dt_date.fromisoformat(older_iso)
        d2 = dt_date.fromisoformat(newer_iso)
        return max(0, (d2 - d1).days)
    except ValueError:
        return 0


def _build_outlet_flags(
    outlet: dict[str, object],
    peer_avg_net: float,
    max_dataset_date: str,
    months_present: list[str],
) -> list[str]:
    flags: list[str] = []
    invoice_count = int(outlet["invoice_count"])  # type: ignore[arg-type]
    qty_carton = int(outlet["qty_carton"])  # type: ignore[arg-type]
    net_sales = int(outlet["net_sales_idr"])  # type: ignore[arg-type]
    last_order = str(outlet["last_order_date"])
    outlet_months = set(outlet["months_active"])  # type: ignore[arg-type]

    if invoice_count > 0 and qty_carton / invoice_count <= 1.5:
        flags.append("Small basket (<=1.5 ctn/inv)")
    if invoice_count <= 5:
        flags.append(f"Low frequency ({invoice_count} inv)")
    if peer_avg_net > 0 and net_sales < peer_avg_net * 0.25:
        flags.append("Below 25% of peer avg")
    if len(months_present) > 1 and months_present[-1] not in outlet_months:
        flags.append(f"No orders in {months_present[-1]}")
    elif _days_between(last_order, max_dataset_date) >= 14:
        days_gap = _days_between(last_order, max_dataset_date)
        flags.append(f"Inactive {days_gap}d")

    return flags[:3] if flags else ["Low cumulative revenue"]


def _aggregate_outlets(
    rows: list[SalesRow],
    max_dataset_date: str,
    months_present: list[str],
) -> list[dict[str, object]]:
    """Aggregate metrics strictly by outlet_id so duplicate store names stay separate."""
    buckets: dict[str, dict[str, object]] = {}

    for r in rows:
        b = buckets.get(r.outlet_id)
        if b is None:
            b = {
                "outlet_id": r.outlet_id,
                "outlet_name": r.outlet_name,
                "outlet_type": r.outlet_type,
                "region": r.region,
                "branch": r.branch,
                "net_sales_idr": 0,
                "gross_sales_idr": 0,
                "discount_idr": 0,
                "qty_carton": 0,
                "line_count": 0,
                "invoices": set(),
                "salesmen": Counter(),
                "brands": Counter(),
                "months_active": set(),
                "first_order_date": r.date,
                "last_order_date": r.date,
            }
            buckets[r.outlet_id] = b

        b["net_sales_idr"] = int(b["net_sales_idr"]) + r.net_sales_idr  # type: ignore[arg-type]
        b["gross_sales_idr"] = int(b["gross_sales_idr"]) + r.gross_sales_idr  # type: ignore[arg-type]
        b["discount_idr"] = int(b["discount_idr"]) + r.discount_idr  # type: ignore[arg-type]
        b["qty_carton"] = int(b["qty_carton"]) + r.qty_carton  # type: ignore[arg-type]
        b["line_count"] = int(b["line_count"]) + 1  # type: ignore[arg-type]
        b["invoices"].add(r.invoice_no)  # type: ignore[attr-defined]
        b["salesmen"][r.salesman] += 1  # type: ignore[index]
        b["brands"][r.brand] += r.net_sales_idr  # type: ignore[index]
        b["months_active"].add(r.month)  # type: ignore[attr-defined]
        if r.date < str(b["first_order_date"]):
            b["first_order_date"] = r.date
        if r.date > str(b["last_order_date"]):
            b["last_order_date"] = r.date

    type_totals: dict[str, list[int]] = defaultdict(list)
    for b in buckets.values():
        type_totals[str(b["outlet_type"])].append(int(b["net_sales_idr"]))  # type: ignore[arg-type]
    peer_avgs = {
        otype: sum(vals) / len(vals) for otype, vals in type_totals.items() if vals
    }

    overall_avg = (
        sum(int(b["net_sales_idr"]) for b in buckets.values()) / len(buckets)  # type: ignore[arg-type]
        if buckets
        else 0.0
    )

    outlets: list[dict[str, object]] = []
    for b in buckets.values():
        invoice_count = len(b["invoices"])  # type: ignore[arg-type]
        net_sales = int(b["net_sales_idr"])  # type: ignore[arg-type]
        peer_avg = peer_avgs.get(str(b["outlet_type"]), overall_avg)
        salesmen_counts: Counter[str] = b["salesmen"]  # type: ignore[assignment]
        brand_counts: Counter[str] = b["brands"]  # type: ignore[assignment]
        primary_salesman = (
            salesmen_counts.most_common(1)[0][0] if salesmen_counts else "Unassigned"
        )
        top_brand = brand_counts.most_common(1)[0][0] if brand_counts else "-"

        record: dict[str, object] = {
            "outlet_id": b["outlet_id"],
            "outlet_name": b["outlet_name"],
            "outlet_type": b["outlet_type"],
            "region": b["region"],
            "branch": b["branch"],
            "primary_salesman": primary_salesman,
            "net_sales_idr": net_sales,
            "gross_sales_idr": int(b["gross_sales_idr"]),  # type: ignore[arg-type]
            "discount_idr": int(b["discount_idr"]),  # type: ignore[arg-type]
            "qty_carton": int(b["qty_carton"]),  # type: ignore[arg-type]
            "line_count": int(b["line_count"]),  # type: ignore[arg-type]
            "invoice_count": invoice_count,
            "avg_order_idr": round(net_sales / invoice_count) if invoice_count else 0,
            "first_order_date": b["first_order_date"],
            "last_order_date": b["last_order_date"],
            "days_inactive": _days_between(str(b["last_order_date"]), max_dataset_date),
            "peer_avg_net_sales_idr": round(peer_avg),
            "vs_peer_pct": round((net_sales / peer_avg) * 100, 1) if peer_avg else 0.0,
            "vs_overall_avg_pct": (
                round((net_sales / overall_avg) * 100, 1) if overall_avg else 0.0
            ),
            "top_brand": top_brand,
            "distinct_brands": len(brand_counts),
            "months_active": sorted(b["months_active"]),  # type: ignore[arg-type]
        }
        record["flags"] = _build_outlet_flags(
            record, peer_avg, max_dataset_date, months_present
        )
        outlets.append(record)

    return outlets


def compute_dashboard(
    dataset: ParsedDataset, filters: DashboardFilters | None = None
) -> dict[str, object]:
    """Compute all sales breakdowns, weakest-5 outlets, and metadata for the active view."""
    active_filters = filters or DashboardFilters()

    all_months = sorted({r.month for r in dataset.rows})
    all_regions = sorted({r.region for r in dataset.rows})
    all_brands = sorted({r.brand for r in dataset.rows})
    all_outlet_types = sorted({r.outlet_type for r in dataset.rows})

    base_rows = [
        r
        for r in dataset.rows
        if (not active_filters.deduplicate or not r.is_duplicate)
        and (active_filters.include_returns or not r.is_return)
    ]

    filtered_rows = [
        r
        for r in base_rows
        if (active_filters.month == "all" or r.month == active_filters.month)
        and (active_filters.region == "all" or r.region == active_filters.region)
        and (active_filters.brand == "all" or r.brand == active_filters.brand)
        and (
            active_filters.outlet_type == "all"
            or r.outlet_type == active_filters.outlet_type
        )
    ]

    total_net = sum(r.net_sales_idr for r in filtered_rows)
    total_gross = sum(r.gross_sales_idr for r in filtered_rows)
    total_discount = sum(r.discount_idr for r in filtered_rows)
    total_qty = sum(r.qty_carton for r in filtered_rows)
    invoices = {r.invoice_no for r in filtered_rows}
    outlets_set = {r.outlet_id for r in filtered_rows}
    return_rows = [r for r in filtered_rows if r.is_return]
    return_net = sum(r.net_sales_idr for r in return_rows)

    date_min = min((r.date for r in filtered_rows), default=dataset.hygiene.date_min)
    date_max = max((r.date for r in filtered_rows), default=dataset.hygiene.date_max)

    month_buckets: dict[str, dict[str, object]] = {}
    for r in filtered_rows:
        mb = month_buckets.setdefault(
            r.month,
            {
                "month": r.month,
                "net_sales_idr": 0,
                "qty_carton": 0,
                "invoices": set(),
                "dates": set(),
            },
        )
        mb["net_sales_idr"] = int(mb["net_sales_idr"]) + r.net_sales_idr  # type: ignore[arg-type]
        mb["qty_carton"] = int(mb["qty_carton"]) + r.qty_carton  # type: ignore[arg-type]
        mb["invoices"].add(r.invoice_no)  # type: ignore[attr-defined]
        mb["dates"].add(r.date)  # type: ignore[attr-defined]

    month_breakdown = [
        {
            "month": m,
            "net_sales_idr": int(mb["net_sales_idr"]),  # type: ignore[arg-type]
            "qty_carton": int(mb["qty_carton"]),  # type: ignore[arg-type]
            "invoice_count": len(mb["invoices"]),  # type: ignore[arg-type]
            "active_days": len(mb["dates"]),  # type: ignore[arg-type]
            "date_min": min(mb["dates"]),  # type: ignore[arg-type]
            "date_max": max(mb["dates"]),  # type: ignore[arg-type]
        }
        for m, mb in sorted(month_buckets.items())
    ]

    region_buckets: dict[str, dict[str, object]] = {}
    for r in filtered_rows:
        rb = region_buckets.setdefault(
            r.region,
            {
                "region": r.region,
                "net_sales_idr": 0,
                "gross_sales_idr": 0,
                "discount_idr": 0,
                "qty_carton": 0,
                "line_count": 0,
                "invoices": set(),
                "outlets": set(),
                "branches": set(),
            },
        )
        rb["net_sales_idr"] = int(rb["net_sales_idr"]) + r.net_sales_idr  # type: ignore[arg-type]
        rb["gross_sales_idr"] = int(rb["gross_sales_idr"]) + r.gross_sales_idr  # type: ignore[arg-type]
        rb["discount_idr"] = int(rb["discount_idr"]) + r.discount_idr  # type: ignore[arg-type]
        rb["qty_carton"] = int(rb["qty_carton"]) + r.qty_carton  # type: ignore[arg-type]
        rb["line_count"] = int(rb["line_count"]) + 1  # type: ignore[arg-type]
        rb["invoices"].add(r.invoice_no)  # type: ignore[attr-defined]
        rb["outlets"].add(r.outlet_id)  # type: ignore[attr-defined]
        rb["branches"].add(r.branch)  # type: ignore[attr-defined]

    by_region = sorted(
        [
            {
                "region": rb["region"],
                "net_sales_idr": int(rb["net_sales_idr"]),  # type: ignore[arg-type]
                "gross_sales_idr": int(rb["gross_sales_idr"]),  # type: ignore[arg-type]
                "discount_idr": int(rb["discount_idr"]),  # type: ignore[arg-type]
                "qty_carton": int(rb["qty_carton"]),  # type: ignore[arg-type]
                "line_count": int(rb["line_count"]),  # type: ignore[arg-type]
                "invoice_count": len(rb["invoices"]),  # type: ignore[arg-type]
                "outlet_count": len(rb["outlets"]),  # type: ignore[arg-type]
                "branches": sorted(rb["branches"]),  # type: ignore[arg-type]
                "share_pct": _pct(int(rb["net_sales_idr"]), total_net),  # type: ignore[arg-type]
                "avg_order_idr": (
                    round(int(rb["net_sales_idr"]) / len(rb["invoices"]))  # type: ignore[arg-type]
                    if rb["invoices"]
                    else 0
                ),
            }
            for rb in region_buckets.values()
        ],
        key=lambda item: (-int(item["net_sales_idr"]), str(item["region"])),  # type: ignore[arg-type]
    )

    brand_buckets: dict[str, dict[str, object]] = {}
    sku_buckets: dict[tuple[str, str], dict[str, object]] = {}
    for r in filtered_rows:
        bb = brand_buckets.setdefault(
            r.brand,
            {
                "brand": r.brand,
                "net_sales_idr": 0,
                "gross_sales_idr": 0,
                "discount_idr": 0,
                "qty_carton": 0,
                "line_count": 0,
                "invoices": set(),
                "skus": set(),
            },
        )
        bb["net_sales_idr"] = int(bb["net_sales_idr"]) + r.net_sales_idr  # type: ignore[arg-type]
        bb["gross_sales_idr"] = int(bb["gross_sales_idr"]) + r.gross_sales_idr  # type: ignore[arg-type]
        bb["discount_idr"] = int(bb["discount_idr"]) + r.discount_idr  # type: ignore[arg-type]
        bb["qty_carton"] = int(bb["qty_carton"]) + r.qty_carton  # type: ignore[arg-type]
        bb["line_count"] = int(bb["line_count"]) + 1  # type: ignore[arg-type]
        bb["invoices"].add(r.invoice_no)  # type: ignore[attr-defined]
        bb["skus"].add(r.sku)  # type: ignore[attr-defined]

        sb = sku_buckets.setdefault(
            (r.brand, r.sku),
            {
                "brand": r.brand,
                "sku": r.sku,
                "net_sales_idr": 0,
                "qty_carton": 0,
                "line_count": 0,
            },
        )
        sb["net_sales_idr"] = int(sb["net_sales_idr"]) + r.net_sales_idr  # type: ignore[arg-type]
        sb["qty_carton"] = int(sb["qty_carton"]) + r.qty_carton  # type: ignore[arg-type]
        sb["line_count"] = int(sb["line_count"]) + 1  # type: ignore[arg-type]

    by_brand = sorted(
        [
            {
                "brand": bb["brand"],
                "net_sales_idr": int(bb["net_sales_idr"]),  # type: ignore[arg-type]
                "gross_sales_idr": int(bb["gross_sales_idr"]),  # type: ignore[arg-type]
                "discount_idr": int(bb["discount_idr"]),  # type: ignore[arg-type]
                "qty_carton": int(bb["qty_carton"]),  # type: ignore[arg-type]
                "line_count": int(bb["line_count"]),  # type: ignore[arg-type]
                "invoice_count": len(bb["invoices"]),  # type: ignore[arg-type]
                "sku_count": len(bb["skus"]),  # type: ignore[arg-type]
                "share_pct": _pct(int(bb["net_sales_idr"]), total_net),  # type: ignore[arg-type]
            }
            for bb in brand_buckets.values()
        ],
        key=lambda item: (-int(item["net_sales_idr"]), str(item["brand"])),  # type: ignore[arg-type]
    )

    by_sku = sorted(
        [
            {
                "brand": sb["brand"],
                "sku": sb["sku"],
                "net_sales_idr": int(sb["net_sales_idr"]),  # type: ignore[arg-type]
                "qty_carton": int(sb["qty_carton"]),  # type: ignore[arg-type]
                "line_count": int(sb["line_count"]),  # type: ignore[arg-type]
                "share_pct": _pct(int(sb["net_sales_idr"]), total_net),  # type: ignore[arg-type]
            }
            for sb in sku_buckets.values()
        ],
        key=lambda item: (-int(item["net_sales_idr"]), str(item["sku"])),  # type: ignore[arg-type]
    )

    matrix_regions = [str(r["region"]) for r in by_region]
    matrix_brands = [str(b["brand"]) for b in by_brand]
    cell_sales: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"net_sales_idr": 0, "qty_carton": 0}
    )
    for r in filtered_rows:
        cell = cell_sales[(r.region, r.brand)]
        cell["net_sales_idr"] += r.net_sales_idr
        cell["qty_carton"] += r.qty_carton

    region_totals_lookup = {
        str(r["region"]): int(r["net_sales_idr"]) for r in by_region  # type: ignore[arg-type]
    }
    matrix_rows = []
    for reg in matrix_regions:
        reg_total = region_totals_lookup.get(reg, 0)
        cells = []
        for br in matrix_brands:
            vals = cell_sales.get((reg, br), {"net_sales_idr": 0, "qty_carton": 0})
            cells.append(
                {
                    "brand": br,
                    "net_sales_idr": vals["net_sales_idr"],
                    "qty_carton": vals["qty_carton"],
                    "share_of_region_pct": _pct(vals["net_sales_idr"], reg_total),
                }
            )
        matrix_rows.append(
            {
                "region": reg,
                "total_net_sales_idr": reg_total,
                "cells": cells,
            }
        )

    months_in_view = sorted({r.month for r in filtered_rows})
    outlet_records = _aggregate_outlets(filtered_rows, date_max, months_in_view)
    weakest_outlets = sorted(
        outlet_records,
        key=lambda o: (
            int(o["net_sales_idr"]),  # type: ignore[arg-type]
            int(o["qty_carton"]),  # type: ignore[arg-type]
            int(o["invoice_count"]),  # type: ignore[arg-type]
            str(o["outlet_id"]),
        ),
    )[:5]

    top_outlets = sorted(
        outlet_records,
        key=lambda o: (-int(o["net_sales_idr"]), str(o["outlet_id"])),  # type: ignore[arg-type]
    )[:5]

    all_outlets_sorted = sorted(
        outlet_records,
        key=lambda o: (int(o["net_sales_idr"]), str(o["outlet_id"])),  # type: ignore[arg-type]
    )

    kpis = {
        "net_sales_idr": total_net,
        "gross_sales_idr": total_gross,
        "discount_idr": total_discount,
        "discount_rate_pct": _pct(total_discount, total_gross),
        "return_count": len(return_rows),
        "return_net_sales_idr": return_net,
        "qty_carton": total_qty,
        "invoice_count": len(invoices),
        "line_count": len(filtered_rows),
        "active_outlets": len(outlets_set),
        "avg_order_idr": round(total_net / len(invoices)) if invoices else 0,
        "date_min": date_min,
        "date_max": date_max,
        "month_breakdown": month_breakdown,
    }

    return {
        "filters": {
            "month": active_filters.month,
            "region": active_filters.region,
            "brand": active_filters.brand,
            "outlet_type": active_filters.outlet_type,
            "deduplicate": active_filters.deduplicate,
            "include_returns": active_filters.include_returns,
        },
        "filter_options": {
            "months": all_months,
            "regions": all_regions,
            "brands": all_brands,
            "outlet_types": all_outlet_types,
        },
        "dataset_info": {
            "source_name": dataset.source_name,
            "total_loaded_rows": dataset.hygiene.raw_row_count,
            "deduplicated_rows": dataset.hygiene.deduplicated_row_count,
            "date_min": dataset.hygiene.date_min,
            "date_max": dataset.hygiene.date_max,
        },
        "kpis": kpis,
        "by_region": by_region,
        "by_brand": by_brand,
        "by_sku": by_sku,
        "region_brand_matrix": {
            "brands": matrix_brands,
            "rows": matrix_rows,
        },
        "weakest_outlets": weakest_outlets,
        "top_outlets": top_outlets,
        "all_outlets": all_outlets_sorted,
        "hygiene": dataset.hygiene.to_dict(),
    }
