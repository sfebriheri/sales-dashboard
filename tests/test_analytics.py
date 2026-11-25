from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.analytics import DashboardFilters, compute_dashboard
from app.main import create_app
from app.parser import canonicalize_region, load_csv_file, parse_csv_text
from app.telegram_summary import build_telegram_summary

DATA_CSV = Path(__file__).resolve().parent.parent / "data" / "sales.csv"


def test_region_canonicalization() -> None:
    assert canonicalize_region("Jabar") == "Jawa Barat"
    assert canonicalize_region("JAWA BARAT") == "Jawa Barat"
    assert canonicalize_region("  JABODETABEK ") == "Jabodetabek"
    assert canonicalize_region("Kalimantan") == "Kalimantan"


def test_bundled_csv_hygiene_and_metrics() -> None:
    dataset = load_csv_file(DATA_CSV)
    assert dataset.hygiene.raw_row_count == 1348
    assert dataset.hygiene.deduplicated_row_count == 1346
    assert dataset.hygiene.duplicate_count == 2
    assert dataset.hygiene.return_count == 1
    assert dataset.hygiene.missing_salesman_count == 2
    assert dataset.hygiene.region_normalized_count == 8
    assert "Toko Sinar Abadi" in dataset.hygiene.shared_outlet_names

    dashboard = compute_dashboard(dataset, DashboardFilters())
    assert dashboard["kpis"]["net_sales_idr"] == 1240106500
    assert len(dashboard["by_region"]) == 6
    assert dashboard["by_region"][0]["region"] == "Jabodetabek"
    assert len(dashboard["by_brand"]) == 8
    assert dashboard["by_brand"][0]["brand"] == "Kacang Dua Kelinci"

    weakest_ids = [o["outlet_id"] for o in dashboard["weakest_outlets"]]
    assert weakest_ids == ["OUT1003", "OUT1026", "OUT1035", "OUT1042", "OUT1045"]


def test_duplicate_and_return_toggles() -> None:
    dataset = load_csv_file(DATA_CSV)
    no_dedup = compute_dashboard(dataset, DashboardFilters(deduplicate=False))
    assert no_dedup["kpis"]["line_count"] == 1348
    assert no_dedup["kpis"]["net_sales_idr"] == 1240106500 + 1024300 + 744000

    no_returns = compute_dashboard(dataset, DashboardFilters(include_returns=False))
    assert no_returns["kpis"]["return_count"] == 0
    assert no_returns["kpis"]["net_sales_idr"] == 1240106500 + 528000


def test_duplicate_outlet_names_do_not_merge() -> None:
    sample = "\n".join(
        [
            "date,invoice_no,region,branch,outlet_id,outlet_name,outlet_type,salesman,brand,sku,qty_carton,price_per_carton_idr,gross_sales_idr,discount_idr,net_sales_idr",
            "2026-09-01,INV1,Jabodetabek,Jakarta Barat,OUT1003,Toko Sinar Abadi,Toko Kelontong,Andi,Sukro,Sukro Pedas 100g,1,186000,186000,0,186000",
            "2026-09-02,INV2,Sumatera,Medan,OUT1040,Toko Sinar Abadi,Toko Kelontong,Wahyu,Sukro,Sukro Pedas 100g,5,186000,930000,0,930000",
        ]
    )
    dataset = parse_csv_text(sample)
    dash = compute_dashboard(dataset)
    assert dash["kpis"]["active_outlets"] == 2
    assert [o["outlet_id"] for o in dash["weakest_outlets"]] == ["OUT1003", "OUT1040"]


def test_telegram_summary_is_single_paragraph() -> None:
    dataset = load_csv_file(DATA_CSV)
    dash = compute_dashboard(dataset)
    summary = build_telegram_summary(dash)
    plain = summary["plain_text"]
    assert "\n" not in plain
    assert "Jabodetabek" in plain
    assert "Kacang Dua Kelinci" in plain
    for oid in ("OUT1003", "OUT1026", "OUT1035", "OUT1042", "OUT1045"):
        assert oid in plain


def test_api_endpoints() -> None:
    client = TestClient(create_app(DATA_CSV))

    res_home = client.get("/")
    assert res_home.status_code == 200
    assert "Sales Pulse" in res_home.text

    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    assert res_health.json()["deduplicated_rows"] == 1346

    res_dash = client.get("/api/dashboard?region=Jabodetabek")
    assert res_dash.status_code == 200
    body = res_dash.json()
    assert len(body["by_region"]) == 1
    assert body["by_region"][0]["region"] == "Jabodetabek"
    assert body["dataset_info"]["total_loaded_rows"] == 1348
    assert body["dataset_info"]["deduplicated_rows"] == 1346

    bad_upload = client.post(
        "/api/upload",
        files={"file": ("bad.csv", b"wrong,headers\n1,2\n", "text/csv")},
    )
    assert bad_upload.status_code == 400
