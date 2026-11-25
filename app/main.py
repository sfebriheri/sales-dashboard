from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analytics import DashboardFilters, compute_dashboard
from app.parser import ParsedDataset, load_csv_file, parse_csv_text
from app.telegram_summary import build_telegram_summary

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CSV_PATH = Path(os.environ.get("SALES_CSV_PATH", BASE_DIR / "data" / "sales.csv"))
STATIC_DIR = Path(__file__).resolve().parent / "static"


class DatasetStore:
    """Thread-safe container for the active sales dataset."""

    def __init__(self, default_path: Path) -> None:
        self._default_path = default_path
        self._lock = Lock()
        self._dataset: ParsedDataset = load_csv_file(default_path)

    def get(self) -> ParsedDataset:
        with self._lock:
            return self._dataset

    def replace(self, dataset: ParsedDataset) -> ParsedDataset:
        with self._lock:
            self._dataset = dataset
            return self._dataset

    def reset(self) -> ParsedDataset:
        fresh = load_csv_file(self._default_path)
        return self.replace(fresh)


def create_app(csv_path: Path | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    target_path = csv_path or DEFAULT_CSV_PATH
    store = DatasetStore(target_path)

    app = FastAPI(
        title="Sales Pulse & Telegram Brief",
        description="Regional, brand, weakest-5 outlet analytics and Telegram summary generator.",
        version="1.0.0",
    )
    app.state.store = store
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        ds = store.get()
        return {
            "status": "ok",
            "source_name": ds.source_name,
            "raw_rows": ds.hygiene.raw_row_count,
            "deduplicated_rows": ds.hygiene.deduplicated_row_count,
            "date_min": ds.hygiene.date_min,
            "date_max": ds.hygiene.date_max,
        }

    @app.get("/api/dashboard")
    def get_dashboard(
        month: str = Query("all"),
        region: str = Query("all"),
        brand: str = Query("all"),
        outlet_type: str = Query("all"),
        deduplicate: bool = Query(True),
        include_returns: bool = Query(True),
    ) -> dict[str, object]:
        ds = store.get()
        filters = DashboardFilters(
            month=month,
            region=region,
            brand=brand,
            outlet_type=outlet_type,
            deduplicate=deduplicate,
            include_returns=include_returns,
        )
        payload = compute_dashboard(ds, filters)
        payload["telegram_summary"] = build_telegram_summary(payload)
        return payload

    @app.post("/api/upload")
    async def upload_csv(file: UploadFile = File(...)) -> dict[str, object]:
        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw_bytes.decode("latin-1")
            except UnicodeDecodeError as exc:
                raise HTTPException(
                    status_code=400, detail="Could not decode file as UTF-8 or Latin-1 CSV."
                ) from exc

        try:
            parsed = parse_csv_text(text, source_name=file.filename or "uploaded.csv")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        store.replace(parsed)
        payload = compute_dashboard(parsed, DashboardFilters())
        payload["telegram_summary"] = build_telegram_summary(payload)
        return payload

    @app.post("/api/reset")
    def reset_csv() -> dict[str, object]:
        ds = store.reset()
        payload = compute_dashboard(ds, DashboardFilters())
        payload["telegram_summary"] = build_telegram_summary(payload)
        return payload

    return app


app = create_app()
