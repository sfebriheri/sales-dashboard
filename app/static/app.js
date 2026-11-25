const state = {
  dashboard: null,
  tgMode: "plain",
  brandView: "brand",
  showBenchmark: false,
  outletQuery: "",
};

const el = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatIdr(amount) {
  const num = Number(amount || 0);
  const sign = num < 0 ? "-" : "";
  return `${sign}Rp ${Math.abs(num).toLocaleString("en-US")}`;
}

function formatIdrCompact(amount) {
  const num = Number(amount || 0);
  const sign = num < 0 ? "-" : "";
  const abs = Math.abs(num);
  if (abs >= 1_000_000_000) return `${sign}Rp ${(abs / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${sign}Rp ${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}Rp ${(abs / 1_000).toFixed(0)}K`;
  return `${sign}Rp ${abs.toLocaleString("en-US")}`;
}

function showBanner(message, type = "info") {
  const banner = el("statusBanner");
  banner.textContent = message;
  banner.className = `status-banner ${type}`;
  banner.classList.remove("hidden");
  if (type === "info") {
    window.clearTimeout(showBanner._timer);
    showBanner._timer = window.setTimeout(() => {
      banner.classList.add("hidden");
    }, 4500);
  }
}

function getActiveFilters() {
  return {
    month: el("monthFilter").value,
    region: el("regionFilter").value,
    brand: el("brandFilter").value,
    outlet_type: el("outletTypeFilter").value,
    deduplicate: el("dedupToggle").checked,
    include_returns: el("returnsToggle").checked,
  };
}

function syncSelectOptions(selectId, values, defaultLabel, currentValue) {
  const select = el(selectId);
  const options = [`<option value="all">${escapeHtml(defaultLabel)}</option>`];
  for (const val of values) {
    options.push(`<option value="${escapeHtml(val)}">${escapeHtml(val)}</option>`);
  }
  select.innerHTML = options.join("");
  select.value = values.includes(currentValue) ? currentValue : "all";
}

function renderHorizontalBarChart(containerId, items, labelKey, activeValue, onSelect, fillHex) {
  const container = el(containerId);
  if (!items || items.length === 0) {
    container.innerHTML = `<div class="empty-state">No records match the current filters.</div>`;
    return;
  }

  const maxVal = Math.max(...items.map((item) => Math.max(0, Number(item.net_sales_idr))), 1);
  const rowHeight = 32;
  const labelWidth = 155;
  const valueWidth = 115;
  const chartWidth = 560;
  const barAreaWidth = chartWidth - labelWidth - valueWidth - 12;
  const height = items.length * rowHeight + 10;

  const rowsSvg = items
    .map((item, idx) => {
      const label = String(item[labelKey]);
      const val = Number(item.net_sales_idr);
      const barWidth = Math.max(3, Math.round((Math.max(0, val) / maxVal) * barAreaWidth));
      const y = idx * rowHeight + 6;
      const isSelected = activeValue !== "all" && activeValue === label;
      const dimmed = activeValue !== "all" && !isSelected;
      const barColor = isSelected ? "#0f172a" : fillHex;
      const opacity = dimmed ? 0.35 : 1;
      const shortLabel = label.length > 22 ? `${label.slice(0, 20)}…` : label;

      return `
        <g class="bar-row" data-key="${escapeHtml(label)}" opacity="${opacity}">
          <title>${escapeHtml(label)}: ${formatIdr(val)} (${item.share_pct}% | ${Number(item.qty_carton).toLocaleString("en-US")} cartons)</title>
          <text x="${labelWidth - 8}" y="${y + 15}" text-anchor="end" font-size="12" font-weight="${isSelected ? "700" : "500"}" fill="#0f172a">${escapeHtml(shortLabel)}</text>
          <rect x="${labelWidth}" y="${y + 3}" width="${barAreaWidth}" height="18" rx="4" fill="#f1f5f9"></rect>
          <rect class="bar-fill" x="${labelWidth}" y="${y + 3}" width="${barWidth}" height="18" rx="4" fill="${barColor}"></rect>
          <text x="${labelWidth + barAreaWidth + 8}" y="${y + 15}" font-size="12" font-weight="600" fill="#334155">${escapeHtml(formatIdrCompact(val))} (${item.share_pct}%)</text>
        </g>
      `;
    })
    .join("");

  container.innerHTML = `
    <svg viewBox="0 0 ${chartWidth} ${height}" width="100%" role="img" aria-label="Sales breakdown bar chart">
      ${rowsSvg}
    </svg>
  `;

  if (onSelect) {
    container.querySelectorAll(".bar-row").forEach((node) => {
      node.addEventListener("click", () => {
        onSelect(node.getAttribute("data-key"));
      });
    });
  }
}

function renderTelegram(summary) {
  const text =
    state.tgMode === "markdown" ? summary.markdown_text : summary.plain_text;
  el("telegramText").textContent = text;
  el("telegramStats").textContent =
    `1 paragraph · ${summary.word_count} words · ${summary.char_count} chars`;
}

function renderKpis(data) {
  const k = data.kpis;
  el("kpiNetSales").textContent = formatIdrCompact(k.net_sales_idr);
  el("kpiNetSub").textContent = `${formatIdr(k.net_sales_idr)} (${k.line_count.toLocaleString("en-US")} lines)`;

  el("kpiCartons").textContent = k.qty_carton.toLocaleString("en-US");
  const months = k.month_breakdown || [];
  el("kpiCartonsSub").textContent =
    months.length > 0
      ? months.map((m) => `${m.month}: ${formatIdrCompact(m.net_sales_idr)}`).join(" · ")
      : "No active months";

  el("kpiInvoices").textContent = k.invoice_count.toLocaleString("en-US");
  el("kpiAovSub").textContent = `Avg order: ${formatIdrCompact(k.avg_order_idr)}`;

  el("kpiOutlets").textContent = k.active_outlets.toLocaleString("en-US");
  el("kpiOutletsSub").textContent = `${data.by_region.length} regions · ${data.by_brand.length} brands`;

  el("kpiDiscounts").textContent = formatIdrCompact(k.discount_idr);
  el("kpiReturnsSub").textContent = `${k.discount_rate_pct}% disc · ${k.return_count} returns (${formatIdrCompact(k.return_net_sales_idr)})`;
}

function renderRegionSection(data) {
  const regions = data.by_region;
  const activeRegion = data.filters.region;
  el("regionCountNote").textContent = `${regions.length} region${regions.length === 1 ? "" : "s"}`;

  const toggleRegion = (regionName) => {
    el("regionFilter").value = activeRegion === regionName ? "all" : regionName;
    loadDashboard();
  };

  renderHorizontalBarChart(
    "regionChart",
    regions,
    "region",
    activeRegion,
    toggleRegion,
    "#0f766e"
  );

  const tbody = el("regionTable").querySelector("tbody");
  if (!regions.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No regional data</td></tr>`;
    return;
  }

  tbody.innerHTML = regions
    .map((r) => {
      const selectedClass = activeRegion === r.region ? "selected-row" : "";
      return `
        <tr class="clickable-row ${selectedClass}" data-region="${escapeHtml(r.region)}">
          <td>
            <strong>${escapeHtml(r.region)}</strong>
            <div class="outlet-meta">${escapeHtml(r.branches.join(", "))}</div>
          </td>
          <td class="num">${escapeHtml(formatIdr(r.net_sales_idr))}</td>
          <td class="num">${r.share_pct}%</td>
          <td class="num">${r.qty_carton.toLocaleString("en-US")}</td>
          <td class="num">${r.outlet_count}</td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll("tr.clickable-row").forEach((tr) => {
    tr.addEventListener("click", () => toggleRegion(tr.getAttribute("data-region")));
  });
}

function renderBrandSection(data) {
  const activeBrand = data.filters.brand;
  const isSkuView = state.brandView === "sku";
  const items = isSkuView ? data.by_sku : data.by_brand;
  const labelKey = isSkuView ? "sku" : "brand";

  el("brandColHeader").textContent = isSkuView ? "SKU" : "Brand";
  el("brandExtraHeader").textContent = isSkuView ? "Lines" : "Invoices";

  const toggleBrand = (brandName) => {
    el("brandFilter").value = activeBrand === brandName ? "all" : brandName;
    loadDashboard();
  };

  renderHorizontalBarChart(
    "brandChart",
    items,
    labelKey,
    isSkuView ? "all" : activeBrand,
    isSkuView ? null : toggleBrand,
    "#0284c7"
  );

  const tbody = el("brandTable").querySelector("tbody");
  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No brand data</td></tr>`;
    return;
  }

  tbody.innerHTML = items
    .map((item) => {
      const selectedClass = !isSkuView && activeBrand === item.brand ? "selected-row" : "";
      const rowAttrs = !isSkuView
        ? `class="clickable-row ${selectedClass}" data-brand="${escapeHtml(item.brand)}"`
        : "";
      const titleCell = isSkuView
        ? `<strong>${escapeHtml(item.sku)}</strong><div class="outlet-meta">${escapeHtml(item.brand)}</div>`
        : `<strong>${escapeHtml(item.brand)}</strong><div class="outlet-meta">${item.sku_count} SKU${item.sku_count === 1 ? "" : "s"}</div>`;
      const extraVal = isSkuView ? item.line_count : item.invoice_count;
      return `
        <tr ${rowAttrs}>
          <td>${titleCell}</td>
          <td class="num">${escapeHtml(formatIdr(item.net_sales_idr))}</td>
          <td class="num">${item.share_pct}%</td>
          <td class="num">${item.qty_carton.toLocaleString("en-US")}</td>
          <td class="num">${extraVal.toLocaleString("en-US")}</td>
        </tr>
      `;
    })
    .join("");

  if (!isSkuView) {
    tbody.querySelectorAll("tr.clickable-row").forEach((tr) => {
      tr.addEventListener("click", () => toggleBrand(tr.getAttribute("data-brand")));
    });
  }
}

function renderMatrix(data) {
  const table = el("matrixTable");
  const { brands, rows } = data.region_brand_matrix;
  if (!rows.length || !brands.length) {
    table.innerHTML = `<tbody><tr><td class="empty-state">No Region × Brand intersections match the filters.</td></tr></tbody>`;
    return;
  }

  const maxCell = Math.max(
    ...rows.flatMap((r) => r.cells.map((c) => Math.max(0, Number(c.net_sales_idr)))),
    1
  );

  const thead = `
    <thead>
      <tr>
        <th>Region</th>
        ${brands.map((b) => `<th class="num">${escapeHtml(b)}</th>`).join("")}
        <th class="num">Total</th>
      </tr>
    </thead>
  `;

  const tbodyRows = rows
    .map((r) => {
      const cellsHtml = r.cells
        .map((c) => {
          const val = Number(c.net_sales_idr);
          const intensity = val > 0 ? 0.08 + (val / maxCell) * 0.34 : 0;
          const style = val > 0 ? `style="background: rgba(13, 148, 136, ${intensity.toFixed(2)});"` : "";
          return `
            <td class="matrix-cell" ${style}>
              <span class="matrix-val">${escapeHtml(val ? formatIdrCompact(val) : "—")}</span>
              <span class="matrix-pct">${val ? `${c.share_of_region_pct}%` : ""}</span>
            </td>
          `;
        })
        .join("");
      return `
        <tr>
          <td><strong>${escapeHtml(r.region)}</strong></td>
          ${cellsHtml}
          <td class="num"><strong>${escapeHtml(formatIdrCompact(r.total_net_sales_idr))}</strong></td>
        </tr>
      `;
    })
    .join("");

  table.innerHTML = `${thead}<tbody>${tbodyRows}</tbody>`;
}

function renderWeakestOutlets(data) {
  const tbody = el("weakestTable").querySelector("tbody");
  const outlets = data.weakest_outlets;

  if (!outlets.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No outlets match the current filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = outlets
    .map((o, idx) => {
      const flagsHtml = (o.flags || [])
        .map((f) => `<span class="flag-pill">${escapeHtml(f)}</span>`)
        .join("");
      return `
        <tr>
          <td><span class="rank-pill">#${idx + 1}</span></td>
          <td>
            <div class="outlet-title">${escapeHtml(o.outlet_name)}</div>
            <div class="outlet-meta">${escapeHtml(o.outlet_id)} · ${escapeHtml(o.outlet_type)}</div>
          </td>
          <td>
            <div>${escapeHtml(o.branch)}, ${escapeHtml(o.region)}</div>
            <div class="outlet-meta">Rep: ${escapeHtml(o.primary_salesman)}</div>
          </td>
          <td class="num">
            <strong>${escapeHtml(formatIdr(o.net_sales_idr))}</strong>
            <div class="outlet-meta">AOV ${escapeHtml(formatIdrCompact(o.avg_order_idr))}</div>
          </td>
          <td class="num">${o.qty_carton} ctn · ${o.invoice_count} inv</td>
          <td class="num">
            <strong>${o.vs_peer_pct}%</strong>
            <div class="outlet-meta">peer avg ${escapeHtml(formatIdrCompact(o.peer_avg_net_sales_idr))}</div>
          </td>
          <td>
            <div>${escapeHtml(o.last_order_date)}</div>
            <div class="outlet-meta">${o.days_inactive}d before period end</div>
          </td>
          <td><div class="flag-list">${flagsHtml}</div></td>
        </tr>
      `;
    })
    .join("");
}

function renderAllOutletsBenchmark(data) {
  const tbody = el("allOutletsTable").querySelector("tbody");
  const query = state.outletQuery.trim().toLowerCase();
  const rows = (data.all_outlets || []).filter((o) => {
    if (!query) return true;
    return (
      o.outlet_id.toLowerCase().includes(query) ||
      o.outlet_name.toLowerCase().includes(query) ||
      o.branch.toLowerCase().includes(query) ||
      o.region.toLowerCase().includes(query) ||
      o.primary_salesman.toLowerCase().includes(query)
    );
  });

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No outlets match your search.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows
    .map(
      (o) => `
      <tr>
        <td><strong>${escapeHtml(o.outlet_name)}</strong> <span class="outlet-meta">(${escapeHtml(o.outlet_id)})</span></td>
        <td>${escapeHtml(o.outlet_type)}</td>
        <td>${escapeHtml(o.region)} / ${escapeHtml(o.branch)}</td>
        <td>${escapeHtml(o.primary_salesman)}</td>
        <td class="num">${escapeHtml(formatIdr(o.net_sales_idr))}</td>
        <td class="num">${o.qty_carton.toLocaleString("en-US")}</td>
        <td class="num">${o.invoice_count}</td>
        <td class="num">${escapeHtml(o.last_order_date)}</td>
      </tr>
    `
    )
    .join("");
}

function renderHygieneModal(data) {
  const h = data.hygiene;
  const totalIssues =
    h.region_normalized_count +
    h.trimmed_whitespace_count +
    h.missing_salesman_count +
    h.duplicate_count +
    h.return_count;
  el("hygieneCountBadge").textContent = totalIssues;

  const aliasList = Object.entries(h.region_alias_examples || {})
    .map(([raw, canon]) => `<code>${escapeHtml(raw)}</code> → <strong>${escapeHtml(canon)}</strong>`)
    .join(", ");

  const dupList = (h.duplicate_examples || [])
    .map((d) => `<li><code>${escapeHtml(d.invoice_no)}</code> (${escapeHtml(d.date)}, ${escapeHtml(d.outlet_id)} ${escapeHtml(d.outlet_name)}, ${escapeHtml(d.sku)}: ${escapeHtml(formatIdr(d.net_sales_idr))})</li>`)
    .join("");

  const retList = (h.return_examples || [])
    .map((r) => `<li><code>${escapeHtml(r.invoice_no)}</code> (${escapeHtml(r.date)}, ${escapeHtml(r.outlet_id)} ${escapeHtml(r.outlet_name)}, ${r.qty_carton} ctn, ${escapeHtml(formatIdr(r.net_sales_idr))})</li>`)
    .join("");

  const sharedNames = Object.entries(h.shared_outlet_names || {})
    .map(([name, ids]) => `<li><strong>${escapeHtml(name)}</strong>: ${ids.map((id) => `<code>${escapeHtml(id)}</code>`).join(", ")}</li>`)
    .join("");

  el("hygieneBody").innerHTML = `
    <div class="hygiene-grid">
      <div class="hygiene-item">
        <strong>${h.raw_row_count.toLocaleString("en-US")} → ${h.deduplicated_row_count.toLocaleString("en-US")}</strong>
        <span>Invoice lines (${h.duplicate_count} exact duplicates flagged)</span>
      </div>
      <div class="hygiene-item">
        <strong>${h.region_normalized_count}</strong>
        <span>Region casing/alias fixes (${aliasList || "none"})</span>
      </div>
      <div class="hygiene-item">
        <strong>${h.trimmed_whitespace_count}</strong>
        <span>Fields with leading/trailing whitespace trimmed</span>
      </div>
      <div class="hygiene-item">
        <strong>${h.missing_salesman_count}</strong>
        <span>Blank salesman fields defaulted to <code>Unassigned</code></span>
      </div>
    </div>
    <div>
      <strong>Duplicate Lines Detected (${h.duplicate_count})</strong>
      <ul>${dupList || "<li>None</li>"}</ul>
    </div>
    <div>
      <strong>Return / Negative Credit Lines (${h.return_count})</strong>
      <ul>${retList || "<li>None</li>"}</ul>
    </div>
    <div>
      <strong>Shared Store Names Across Distinct <code>outlet_id</code>s</strong>
      <p class="panel-sub">All outlet rankings group strictly by <code>outlet_id</code> so distinct stores never merge.</p>
      <ul>${sharedNames || "<li>None</li>"}</ul>
    </div>
  `;
}

function renderDashboard(data) {
  state.dashboard = data;

  const info = data.dataset_info;
  el("datasetSubtitle").textContent =
    `${info.source_name} · ${Number(info.deduplicated_rows || 0).toLocaleString("en-US")} clean lines (${Number(info.total_loaded_rows || 0).toLocaleString("en-US")} raw) · ${info.date_min} to ${info.date_max}`;

  syncSelectOptions("monthFilter", data.filter_options.months, "All Months", data.filters.month);
  syncSelectOptions("regionFilter", data.filter_options.regions, "All Regions", data.filters.region);
  syncSelectOptions("brandFilter", data.filter_options.brands, "All Brands", data.filters.brand);
  syncSelectOptions("outletTypeFilter", data.filter_options.outlet_types, "All Types", data.filters.outlet_type);

  const hasFilters =
    data.filters.month !== "all" ||
    data.filters.region !== "all" ||
    data.filters.brand !== "all" ||
    data.filters.outlet_type !== "all" ||
    !data.filters.deduplicate ||
    !data.filters.include_returns;
  el("clearFiltersBtn").classList.toggle("hidden", !hasFilters);

  renderTelegram(data.telegram_summary);
  renderKpis(data);
  renderRegionSection(data);
  renderBrandSection(data);
  renderMatrix(data);
  renderWeakestOutlets(data);
  renderAllOutletsBenchmark(data);
  renderHygieneModal(data);
}

async function loadDashboard() {
  const f = getActiveFilters();
  const params = new URLSearchParams({
    month: f.month,
    region: f.region,
    brand: f.brand,
    outlet_type: f.outlet_type,
    deduplicate: String(f.deduplicate),
    include_returns: String(f.include_returns),
  });
  try {
    const res = await fetch(`/api/dashboard?${params.toString()}`);
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.detail || "Failed to load dashboard.");
    renderDashboard(payload);
  } catch (err) {
    showBanner(err.message, "error");
  }
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}

function wireEvents() {
  ["monthFilter", "regionFilter", "brandFilter", "outletTypeFilter", "dedupToggle", "returnsToggle"].forEach((id) => {
    el(id).addEventListener("change", loadDashboard);
  });

  el("clearFiltersBtn").addEventListener("click", () => {
    el("monthFilter").value = "all";
    el("regionFilter").value = "all";
    el("brandFilter").value = "all";
    el("outletTypeFilter").value = "all";
    el("dedupToggle").checked = true;
    el("returnsToggle").checked = true;
    loadDashboard();
  });

  document.querySelectorAll("[data-tg-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.tgMode = btn.getAttribute("data-tg-mode");
      document.querySelectorAll("[data-tg-mode]").forEach((b) => b.classList.toggle("active", b === btn));
      if (state.dashboard) renderTelegram(state.dashboard.telegram_summary);
    });
  });

  document.querySelectorAll("[data-brand-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.brandView = btn.getAttribute("data-brand-view");
      document.querySelectorAll("[data-brand-view]").forEach((b) => b.classList.toggle("active", b === btn));
      if (state.dashboard) renderBrandSection(state.dashboard);
    });
  });

  el("copyTelegramBtn").addEventListener("click", async () => {
    if (!state.dashboard) return;
    const text =
      state.tgMode === "markdown"
        ? state.dashboard.telegram_summary.markdown_text
        : state.dashboard.telegram_summary.plain_text;
    try {
      await copyTextToClipboard(text);
      const btn = el("copyTelegramBtn");
      btn.textContent = "Copied!";
      window.setTimeout(() => {
        btn.textContent = "Copy for Telegram";
      }, 1800);
    } catch {
      showBanner("Clipboard write blocked by browser; please select and copy the message manually.", "error");
    }
  });

  el("csvUploadInput").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Upload failed.");
      renderDashboard(payload);
      showBanner(`Loaded ${file.name} (${payload.dataset_info.total_loaded_rows.toLocaleString("en-US")} invoice lines).`, "info");
    } catch (err) {
      showBanner(err.message, "error");
    } finally {
      event.target.value = "";
    }
  });

  el("resetBtn").addEventListener("click", async () => {
    try {
      const res = await fetch("/api/reset", { method: "POST" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Reset failed.");
      renderDashboard(payload);
      showBanner("Restored bundled dataset (sales.csv).", "info");
    } catch (err) {
      showBanner(err.message, "error");
    }
  });

  el("toggleAllOutletsBtn").addEventListener("click", () => {
    state.showBenchmark = !state.showBenchmark;
    el("benchmarkDrawer").classList.toggle("hidden", !state.showBenchmark);
    el("toggleAllOutletsBtn").textContent = state.showBenchmark
      ? "Hide All Outlets Benchmark"
      : "Benchmark vs Top & All Outlets";
  });

  el("outletSearchInput").addEventListener("input", (e) => {
    state.outletQuery = e.target.value;
    if (state.dashboard) renderAllOutletsBenchmark(state.dashboard);
  });

  el("hygieneBtn").addEventListener("click", () => {
    el("hygieneModal").classList.remove("hidden");
  });
  el("closeHygieneBtn").addEventListener("click", () => {
    el("hygieneModal").classList.add("hidden");
  });
  el("hygieneModal").addEventListener("click", (e) => {
    if (e.target === el("hygieneModal")) {
      el("hygieneModal").classList.add("hidden");
    }
  });
}

wireEvents();
loadDashboard();
