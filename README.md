# Sales Pulse — Region, Brand & Weakest Outlets Dashboard

A lightweight Python (**FastAPI + Uvicorn**) web application that analyzes distributor invoice-line CSV data across regions and brands, flags the **5 weakest outlets**, and generates a **one-paragraph Telegram summary** ready to copy and send to sales managers.

## Requirements

- Python 3.9+

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser.

## Running Tests

```bash
pytest
```

## Features & Data Hygiene

- **Sales by Region & Brand:** Interactive bar charts (click to cross-filter), SKU breakdown view, and a **Region × Brand** revenue matrix.
- **5 Weakest Outlets Flagged:** Aggregates strictly by `outlet_id` (preventing identically named stores such as `Toko Sinar Abadi` or `Toko Mandiri` across different cities from colliding), computes `% vs peer outlet-type average`, and surfaces diagnostic tags (small basket, low frequency, inactivity).
- **Telegram Manager Brief:** Generates a single-paragraph executive summary dynamically from active filters with **Plain Text** and **Markdown** copy modes.
- **Automatic Data Normalization + Audit Modal:**
  - Canonicalizes region casing/aliases (`Jabar`, `JAWA BARAT` → `Jawa Barat`; `JABODETABEK` → `Jabodetabek`).
  - Trims leading/trailing whitespace and maps missing salesman values to `Unassigned`.
  - Flags exact duplicate invoice lines (`INV500201`, `INV500386`) and return credit lines (`RTR900001`) with live toggles in the UI.
- **CSV Upload:** Replace `data/sales.csv` or upload a new `.csv` directly from the top bar without restarting the server.

> **Dataset Note:** The bundled `data/sales.csv` contains the `1,348` complete invoice lines (`2026-09-01` to `2026-10-14`, `1,346` after exact-line deduplication) captured from the pasted prompt before chat truncation. Use **Upload CSV** in the top bar (or replace `data/sales.csv`) to load the full ~1,900-line file.
