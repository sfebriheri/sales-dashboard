from __future__ import annotations

from datetime import date as dt_date


def format_idr_compact(amount: int) -> str:
    """Format Indonesian Rupiah compactly for executive messaging."""
    sign = "-" if amount < 0 else ""
    val = abs(amount)
    if val >= 1_000_000_000:
        return f"{sign}Rp {val / 1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"{sign}Rp {val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"{sign}Rp {val / 1_000:.0f}K"
    return f"{sign}Rp {val:,}"


def format_date_range(date_min: str, date_max: str) -> str:
    """Format ISO start/end dates into a compact readable range."""
    if not date_min or not date_max:
        return "selected period"
    try:
        d1 = dt_date.fromisoformat(date_min)
        d2 = dt_date.fromisoformat(date_max)
        if d1.year == d2.year and d1.month == d2.month:
            return f"{d1.strftime('%b')} {d1.day}–{d2.day}, {d2.year}"
        if d1.year == d2.year:
            return f"{d1.strftime('%b')} {d1.day}–{d2.strftime('%b')} {d2.day}, {d2.year}"
        return f"{d1.strftime('%b')} {d1.day}, {d1.year}–{d2.strftime('%b')} {d2.day}, {d2.year}"
    except ValueError:
        return f"{date_min} to {date_max}"


def build_telegram_summary(dashboard: dict[str, object]) -> dict[str, object]:
    """Generate a single-paragraph sales manager brief ready for Telegram."""
    kpis: dict[str, object] = dashboard["kpis"]  # type: ignore[assignment]
    by_region: list[dict[str, object]] = dashboard["by_region"]  # type: ignore[assignment]
    by_brand: list[dict[str, object]] = dashboard["by_brand"]  # type: ignore[assignment]
    weakest: list[dict[str, object]] = dashboard["weakest_outlets"]  # type: ignore[assignment]
    filters: dict[str, object] = dashboard["filters"]  # type: ignore[assignment]

    line_count = int(kpis["line_count"])  # type: ignore[arg-type]
    if line_count == 0:
        empty_msg = (
            "No sales invoice lines match the current dashboard filters, so there are no regional, brand, or outlet figures to report for this selection."
        )
        return {
            "plain_text": empty_msg,
            "markdown_text": empty_msg,
            "word_count": len(empty_msg.split()),
            "char_count": len(empty_msg),
        }

    period_label = format_date_range(str(kpis["date_min"]), str(kpis["date_max"]))
    net_sales = format_idr_compact(int(kpis["net_sales_idr"]))  # type: ignore[arg-type]
    cartons = int(kpis["qty_carton"])  # type: ignore[arg-type]
    invoices = int(kpis["invoice_count"])  # type: ignore[arg-type]
    active_outlets = int(kpis["active_outlets"])  # type: ignore[arg-type]

    if len(by_region) > 1:
        top_reg = by_region[0]
        low_reg = by_region[-1]
        region_text = (
            f"{top_reg['region']} led all regions at {format_idr_compact(int(top_reg['net_sales_idr']))} "
            f"({top_reg['share_pct']}% share), while {low_reg['region']} trailed at "
            f"{format_idr_compact(int(low_reg['net_sales_idr']))} ({low_reg['share_pct']}%)"
        )
    elif len(by_region) == 1:
        only_reg = by_region[0]
        region_text = (
            f"within {only_reg['region']}, performance totaled "
            f"{format_idr_compact(int(only_reg['net_sales_idr']))}"
        )
    else:
        region_text = "regional breakdown is unavailable"

    if len(by_brand) >= 3:
        b1, b2, b3 = by_brand[0], by_brand[1], by_brand[2]
        brand_text = (
            f"{b1['brand']} anchored brand revenue at {format_idr_compact(int(b1['net_sales_idr']))} "
            f"({b1['share_pct']}%), ahead of {b2['brand']} ({format_idr_compact(int(b2['net_sales_idr']))}) "
            f"and {b3['brand']} ({format_idr_compact(int(b3['net_sales_idr']))})"
        )
    elif by_brand:
        b1 = by_brand[0]
        brand_text = (
            f"{b1['brand']} led brand sales at {format_idr_compact(int(b1['net_sales_idr']))} "
            f"({b1['share_pct']}%)"
        )
    else:
        brand_text = "brand mix was empty"

    months: list[dict[str, object]] = kpis.get("month_breakdown", [])  # type: ignore[assignment]
    month_clause = ""
    if len(months) >= 2:
        m1, m2 = months[0], months[1]
        m2_end = str(m2["date_max"])
        m2_partial = (
            f" (through {format_date_range(str(m2['date_min']), m2_end)})"
            if not m2_end.endswith(("-30", "-31"))
            else ""
        )
        month_clause = (
            f" Monthly net sales stand at {format_idr_compact(int(m1['net_sales_idr']))} in {m1['month']} "
            f"and {format_idr_compact(int(m2['net_sales_idr']))} in {m2['month']}{m2_partial}."
        )

    weak_parts = [
        f"{o['outlet_name']} ({o['outlet_id']}, {o['branch']}: {format_idr_compact(int(o['net_sales_idr']))})"
        for o in weakest
    ]
    weak_list = (
        ", ".join(weak_parts[:-1]) + f", and {weak_parts[-1]}"
        if len(weak_parts) > 1
        else (weak_parts[0] if weak_parts else "none")
    )

    scope_parts = []
    if filters.get("region") != "all":
        scope_parts.append(str(filters["region"]))
    if filters.get("brand") != "all":
        scope_parts.append(str(filters["brand"]))
    if filters.get("outlet_type") != "all":
        scope_parts.append(str(filters["outlet_type"]))
    scope_suffix = f" ({' · '.join(scope_parts)})" if scope_parts else ""

    plain_paragraph = (
        f"Sales update for {period_label}{scope_suffix}: net revenue reached {net_sales} across "
        f"{cartons:,} cartons, {invoices:,} invoices, and {active_outlets} active outlets. "
        f"{region_text}. Across brands, {brand_text}.{month_clause} "
        f"Immediate field follow-up is needed on the {len(weakest)} weakest outlets—{weak_list}—which "
        f"posted minimal basket sizes and low order frequency."
    )

    markdown_paragraph = (
        f"*Sales Update ({period_label}{scope_suffix}):* Net revenue reached *{net_sales}* across "
        f"*{cartons:,} cartons*, {invoices:,} invoices, and {active_outlets} active outlets. "
        f"{region_text}. Across brands, {brand_text}.{month_clause} "
        f"Immediate field follow-up is needed on the *{len(weakest)} weakest outlets*—{weak_list}—which "
        f"posted minimal basket sizes and low order frequency."
    )

    plain_paragraph = " ".join(plain_paragraph.split())
    markdown_paragraph = " ".join(markdown_paragraph.split())

    return {
        "plain_text": plain_paragraph,
        "markdown_text": markdown_paragraph,
        "word_count": len(plain_paragraph.split()),
        "char_count": len(plain_paragraph),
    }
