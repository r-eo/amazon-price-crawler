/**
 * Acer Amazon Intelligence Platform — Executive Dual Dashboard Controller
 */

let currentGroup = "acer_monitors";
let allProducts = [];
let filteredProducts = [];
let dashboardStats = {};
let atlFilterActive = false;
let currencySymbol = "₹";

document.addEventListener("DOMContentLoaded", () => {
  initApp();
});

async function initApp() {
  await fetchTabCounts();
  await loadDashboardData();
  await checkSchedulerStatus();
  
  // Refresh scheduler status every 3 minutes
  setInterval(checkSchedulerStatus, 180000);
}

/**
 * Fetch counts for each tab badge
 */
async function fetchTabCounts() {
  try {
    const [resMonitors, resOther, resAll] = await Promise.all([
      fetch("/api/products?group=acer_monitors"),
      fetch("/api/products?group=other_products"),
      fetch("/api/products?group=all")
    ]);

    const dataMonitors = await resMonitors.json();
    const dataOther = await resOther.json();
    const dataAll = await resAll.json();

    document.getElementById("badgeMonitorsCount").textContent = dataMonitors.total || 0;
    document.getElementById("badgeOtherCount").textContent = dataOther.total || 0;
    document.getElementById("badgeAllCount").textContent = dataAll.total || 0;
  } catch (err) {
    console.error("Failed to load tab counts:", err);
  }
}

/**
 * Switch Active Dashboard
 */
async function switchDashboard(group) {
  currentGroup = group;
  atlFilterActive = false;

  // Update tab button active states
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    if (btn.getAttribute("data-group") === group) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // Update Header / Action Buttons
  const downloadBtn = document.getElementById("btnDownloadExcel");
  const downloadText = document.getElementById("downloadBtnText");
  const scrapeText = document.getElementById("scrapeBtnText");
  const viewLabel = document.getElementById("currentViewLabel");
  const kpiScopeLabel = document.getElementById("kpiLabelProducts");
  const chartTitle = document.getElementById("chartTitle");

  if (group === "acer_monitors") {
    downloadBtn.href = "/api/export/excel?group=acer_monitors";
    downloadText.textContent = "Download Monitors Excel (.xlsx)";
    scrapeText.textContent = "Scrape Monitors";
    viewLabel.innerHTML = "Viewing: <strong>Acer Monitors Dashboard</strong>";
    kpiScopeLabel.textContent = "Tracked Monitors";
    chartTitle.textContent = "Acer Monitors — 22-Month Price Trajectory";
  } else if (group === "other_products") {
    downloadBtn.href = "/api/export/excel?group=other_products";
    downloadText.textContent = "Download Other Products Excel (.xlsx)";
    scrapeText.textContent = "Scrape Other Products";
    viewLabel.innerHTML = "Viewing: <strong>Other Products Dashboard</strong>";
    kpiScopeLabel.textContent = "Tracked Products";
    chartTitle.textContent = "Other Products — 22-Month Price Trajectory";
  } else {
    downloadBtn.href = "/api/export/excel?group=all";
    downloadText.textContent = "Download All Portfolio Excel (.xlsx)";
    scrapeText.textContent = "Scrape All Portfolio";
    viewLabel.innerHTML = "Viewing: <strong>Full Product Portfolio</strong>";
    kpiScopeLabel.textContent = "Total Products";
    chartTitle.textContent = "Overall Portfolio — 22-Month Price Trajectory";
  }

  // Pre-select group in modal
  const modalGroupSelect = document.getElementById("importGroupSelect");
  if (modalGroupSelect && group !== "all") {
    modalGroupSelect.value = group;
  }

  await loadDashboardData();
  await fetchTabCounts();
}

/**
 * Loads products, KPIs, and charts for active group
 */
async function loadDashboardData() {
  try {
    const [prodRes, statsRes] = await Promise.all([
      fetch(`/api/products?group=${currentGroup}`),
      fetch(`/api/stats?group=${currentGroup}`)
    ]);

    const prodData = await prodRes.json();
    const statsData = await statsRes.json();

    allProducts = prodData.products || [];
    dashboardStats = statsData || {};
    currencySymbol = prodData.currency || "₹";

    renderKpiCards(dashboardStats);
    populateCategoryFilter(allProducts);
    applyFiltersAndRenderTable();

    if (dashboardStats.month_labels && dashboardStats.category_trends) {
      renderTimelineChart(dashboardStats.month_labels, dashboardStats.category_trends, currencySymbol);
    }
  } catch (err) {
    console.error("Error loading dashboard data:", err);
    showToast("Failed to fetch dashboard data.", "error");
  }
}

/**
 * Render KPI Cards
 */
function renderKpiCards(stats) {
  document.getElementById("kpiTotalProducts").textContent = stats.total_products || 0;
  document.getElementById("kpiAvgDiscount").textContent = `${stats.avg_discount_pct || 0}%`;
  document.getElementById("kpiAtlDeals").textContent = stats.atl_deals_count || 0;
  
  const inStock = stats.in_stock_count || 0;
  const total = stats.total_products || 0;
  document.getElementById("kpiStockHealth").textContent = `${inStock}/${total}`;

  const kpiSubtextScope = document.getElementById("kpiSubtextScope");
  if (kpiSubtextScope) {
    if (currentGroup === "acer_monitors") {
      kpiSubtextScope.textContent = "Dedicated Monitor Catalog";
    } else if (currentGroup === "other_products") {
      kpiSubtextScope.textContent = "Laptops, Desktops & Other ASINs";
    } else {
      kpiSubtextScope.textContent = "Entire Tracked Portfolio";
    }
  }
}

/**
 * Populate Category Dropdown
 */
function populateCategoryFilter(products) {
  const select = document.getElementById("selectCategoryFilter");
  if (!select) return;

  const currentVal = select.value;
  const categories = Array.from(new Set(products.map((p) => p.category))).sort();

  select.innerHTML = '<option value="">All Categories</option>';
  categories.forEach((cat) => {
    const opt = document.createElement("option");
    opt.value = cat;
    opt.textContent = cat;
    if (cat === currentVal) opt.selected = true;
    select.appendChild(opt);
  });
}

/**
 * Apply filters (search, category, ATL) and render table
 */
function applyFiltersAndRenderTable() {
  const searchQ = (document.getElementById("inputSearch")?.value || "").toLowerCase().trim();
  const selectedCat = document.getElementById("selectCategoryFilter")?.value || "";

  filteredProducts = allProducts.filter((p) => {
    if (selectedCat && p.category !== selectedCat) return false;
    if (searchQ) {
      const matchTitle = (p.title || "").toLowerCase().includes(searchQ);
      const matchAsin = (p.asin || "").toLowerCase().includes(searchQ);
      const matchCat = (p.category || "").toLowerCase().includes(searchQ);
      if (!matchTitle && !matchAsin && !matchCat) return false;
    }
    if (atlFilterActive) {
      if (!p.stats || !p.stats.is_atl) return false;
    }
    return true;
  });

  renderProductsTable(filteredProducts);
}

function handleSearchInput() {
  applyFiltersAndRenderTable();
}

function handleCategoryFilter() {
  applyFiltersAndRenderTable();
}

function filterByAtl() {
  atlFilterActive = !atlFilterActive;
  if (atlFilterActive) {
    showToast("Filtering table: Showing All-Time Low deals only.", "info");
  } else {
    showToast("Cleared All-Time Low filter.", "info");
  }
  applyFiltersAndRenderTable();
}

/**
 * Render Data Table Rows
 */
function renderProductsTable(products) {
  const tbody = document.getElementById("productsTableBody");
  const countEl = document.getElementById("tableResultCount");
  if (!tbody) return;

  countEl.textContent = `Showing ${products.length} of ${allProducts.length} products`;
  tbody.innerHTML = "";

  if (products.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="10" class="text-center" style="padding: 40px; color: var(--text-muted);">
          <i class="fa-solid fa-box-open" style="font-size: 28px; margin-bottom: 10px; display: block;"></i>
          No products found in this view. Click <strong>"Add / Import ASINs"</strong> to add products.
        </td>
      </tr>
    `;
    return;
  }

  products.forEach((p) => {
    const stats = p.stats || {};
    const tr = document.createElement("tr");

    const isAtl = stats.is_atl;
    const discount = stats.discount_from_mrp || 0;
    const inStock = (p.stock_status || "").toLowerCase().includes("in stock");

    const imgTag = p.image_url
      ? `<img src="${p.image_url}" alt="thumb" class="product-thumb" loading="lazy" onerror="this.src='https://placehold.co/48x48/1E293B/94A3B8?text=Acer'">`
      : `<i class="fa-solid fa-laptop" style="color: var(--text-muted); font-size: 18px;"></i>`;

    tr.innerHTML = `
      <td>
        <div class="product-thumb-container">
          ${imgTag}
        </div>
      </td>
      <td>
        <span class="asin-code" title="Click to copy ASIN" onclick="copyAsin('${p.asin}')" style="cursor: pointer;">
          ${p.asin}
        </span>
      </td>
      <td>
        <div class="product-meta-cell">
          <a href="${p.url}" target="_blank" rel="noopener" class="product-title-link" title="${p.title}">
            ${p.title}
          </a>
          <div class="product-sub-info">
            <span class="product-rating"><i class="fa-solid fa-star"></i> ${p.rating || 4.2}</span>
            <span>&bull;</span>
            <span>${(p.review_count || 0).toLocaleString()} reviews</span>
            <span>&bull;</span>
            <a href="${p.url}" target="_blank" rel="noopener" style="color: var(--text-muted); text-decoration: none;">
              Amazon <i class="fa-solid fa-arrow-up-right-from-square" style="font-size: 9px;"></i>
            </a>
          </div>
        </div>
      </td>
      <td>
        <span class="badge badge-muted">${p.category}</span>
      </td>
      <td class="text-right">
        <div style="display: flex; flex-direction: column; align-items: flex-end;">
          <span class="price-val">${currencySymbol}${Math.round(p.current_price || 0).toLocaleString()}</span>
          ${isAtl ? `<span class="badge-atl">ATL DEAL</span>` : ""}
        </div>
      </td>
      <td class="text-right">
        <span class="mrp-val">${currencySymbol}${Math.round(p.mrp || 0).toLocaleString()}</span>
      </td>
      <td class="text-center">
        <span class="badge badge-green">${discount}% OFF</span>
      </td>
      <td class="text-center">
        <span class="price-val" style="color: var(--color-green); font-size: 12px;">
          ${currencySymbol}${Math.round(stats.min_price || p.current_price).toLocaleString()}
        </span>
      </td>
      <td class="text-center">
        <span class="badge ${inStock ? 'badge-green' : 'badge-red'}">
          ${inStock ? 'In Stock' : 'Unavailable'}
        </span>
      </td>
      <td class="text-center">
        <div class="action-buttons">
          <button class="btn btn-icon btn-outline" onclick="openProductDetailModal('${p.asin}')" title="View 22-Month Price Timeline">
            <i class="fa-solid fa-chart-line"></i>
          </button>
          <button class="btn btn-icon btn-outline" onclick="scrapeSingleAsin('${p.asin}')" title="Live Crawl Amazon Price">
            <i class="fa-solid fa-rotate"></i>
          </button>
          <button class="btn btn-icon btn-outline" onclick="confirmDeleteAsin('${p.asin}')" title="Delete ASIN" style="color: var(--color-red);">
            <i class="fa-solid fa-trash"></i>
          </button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function copyAsin(asin) {
  navigator.clipboard.writeText(asin);
  showToast(`Copied ASIN: ${asin}`, "info");
}

/**
 * Scrape Single ASIN
 */
async function scrapeSingleAsin(asin) {
  showToast(`Scraping Amazon live price for ${asin}...`, "info");
  try {
    const res = await fetch(`/api/scrape?asin=${asin}`, { method: "POST" });
    const data = await res.json();
    if (data.status === "completed") {
      showToast(`ASIN ${asin} updated successfully.`, "success");
      await loadDashboardData();
    } else {
      showToast(`Scrape request submitted.`, "info");
    }
  } catch (err) {
    showToast(`Failed to crawl ASIN ${asin}`, "error");
  }
}

/**
 * Scrape Active Group
 */
async function triggerActiveGroupScrape() {
  const scrapeBtn = document.getElementById("btnRunScrape");
  scrapeBtn.disabled = true;
  scrapeBtn.classList.add("loading");

  showToast(`Initiating live crawl for ${currentGroup}...`, "info");

  try {
    const res = await fetch(`/api/scrape?group=${currentGroup}`, { method: "POST" });
    const data = await res.json();
    showToast(data.message || "Crawl job queued.", "success");
    setTimeout(loadDashboardData, 3000);
  } catch (err) {
    showToast("Error starting live crawl.", "error");
  } finally {
    setTimeout(() => {
      scrapeBtn.disabled = false;
      scrapeBtn.classList.remove("loading");
    }, 2000);
  }
}

/**
 * Delete ASIN
 */
async function confirmDeleteAsin(asin) {
  if (!confirm(`Are you sure you want to remove ASIN ${asin} from tracking?`)) return;
  try {
    const res = await fetch(`/api/products/${asin}`, { method: "DELETE" });
    const data = await res.json();
    if (data.status === "success") {
      showToast(`Removed ASIN ${asin}`, "success");
      await loadDashboardData();
      await fetchTabCounts();
    }
  } catch (err) {
    showToast(`Failed to delete ASIN ${asin}`, "error");
  }
}

/**
 * Download Group Excel
 */
function downloadGroupExcel(e) {
  showToast(`Preparing ${currentGroup} 22-Month Excel report...`, "info");
}

/**
 * Product Timeline Detail Modal
 */
async function openProductDetailModal(asin) {
  const modal = document.getElementById("productDetailModal");
  const modalTitle = document.getElementById("modalProductTitle");
  const modalAsin = document.getElementById("modalProductAsin");
  const modalBody = document.getElementById("modalProductBody");

  modal.classList.add("active");
  modalBody.innerHTML = `
    <div style="text-align: center; padding: 40px; color: var(--text-muted);">
      <i class="fa-solid fa-spinner fa-spin" style="font-size: 24px;"></i>
      <p style="margin-top: 10px;">Loading historical 22-month timeline...</p>
    </div>
  `;

  try {
    const res = await fetch(`/api/products/${asin}`);
    const data = await res.json();

    const p = data.product;
    const stats = data.stats;
    const history = data.history || [];

    modalTitle.textContent = p.title;
    modalAsin.textContent = `ASIN: ${p.asin}`;

    modalBody.innerHTML = `
      <div class="modal-product-summary">
        <div class="modal-stat-box">
          <span class="modal-stat-label">Today's Price</span>
          <span class="modal-stat-val">${currencySymbol}${Math.round(p.current_price).toLocaleString()}</span>
        </div>
        <div class="modal-stat-box">
          <span class="modal-stat-label">Baseline MRP</span>
          <span class="modal-stat-val">${currencySymbol}${Math.round(p.mrp).toLocaleString()}</span>
        </div>
        <div class="modal-stat-box">
          <span class="modal-stat-label">22-Month Lowest</span>
          <span class="modal-stat-val" style="color: var(--color-green);">${currencySymbol}${Math.round(stats.min_price || p.current_price).toLocaleString()}</span>
        </div>
        <div class="modal-stat-box">
          <span class="modal-stat-label">22-Month Average</span>
          <span class="modal-stat-val">${currencySymbol}${Math.round(stats.avg_price || p.current_price).toLocaleString()}</span>
        </div>
      </div>

      <div style="background-color: var(--bg-input); border: 1px solid var(--border-card); border-radius: var(--radius-md); padding: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
          <span style="font-size: 13px; font-weight: 600; color: var(--text-primary);">22-Month Trajectory & Seasonal Deal Markers</span>
          <span style="font-size: 11px; color: var(--text-muted);"><i class="fa-solid fa-circle" style="color: var(--color-green); font-size: 8px;"></i> All-Time Low Marker</span>
        </div>
        <div style="height: 260px; position: relative;">
          <canvas id="modalProductHistoryChart"></canvas>
        </div>
      </div>
    `;

    renderProductDetailModalChart(history, currencySymbol);
  } catch (err) {
    modalBody.innerHTML = `<p style="color: var(--color-red); text-align: center; padding: 20px;">Failed to load timeline details.</p>`;
  }
}

function closeProductModal(e) {
  const modal = document.getElementById("productDetailModal");
  if (modal) modal.classList.remove("active");
}

/**
 * Add / Import ASINs Modal
 */
function openAddAsinModal() {
  const modal = document.getElementById("addAsinModal");
  const modalGroupSelect = document.getElementById("importGroupSelect");
  if (modalGroupSelect && currentGroup !== "all") {
    modalGroupSelect.value = currentGroup;
  }
  if (modal) modal.classList.add("active");
}

function closeAddAsinModal(e) {
  const modal = document.getElementById("addAsinModal");
  if (modal) modal.classList.remove("active");
}

async function submitAddAsins(e) {
  e.preventDefault();
  const group = document.getElementById("importGroupSelect").value;
  const rawText = document.getElementById("inputAsinList").value;
  const customCat = document.getElementById("inputCustomCategory").value.trim();
  const submitBtn = document.getElementById("btnSubmitImport");

  // Parse comma or newline separated ASINs
  const asins = rawText
    .split(/[\n,;\s]+/)
    .map((s) => s.trim().toUpperCase())
    .filter((s) => s.length === 10);

  if (asins.length === 0) {
    showToast("Please enter at least one valid 10-character Amazon ASIN.", "error");
    return;
  }

  submitBtn.disabled = true;
  submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Importing ${asins.length} ASIN(s)...`;

  try {
    const res = await fetch("/api/products/batch-import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        asins: asins,
        group: group,
        category: customCat || null
      })
    });

    const data = await res.json();
    if (data.status === "success") {
      showToast(`Successfully imported & crawled ${data.imported_count} ASIN(s).`, "success");
      closeAddAsinModal();
      document.getElementById("addAsinForm").reset();
      
      // If added to another dashboard, switch or reload
      if (group !== currentGroup && currentGroup !== "all") {
        await switchDashboard(group);
      } else {
        await loadDashboardData();
        await fetchTabCounts();
      }
    } else {
      showToast("Import failed. Please verify ASINs.", "error");
    }
  } catch (err) {
    showToast("Network error during ASIN import.", "error");
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<i class="fa-solid fa-cloud-arrow-down"></i> <span>Import & Crawl ASINs</span>`;
  }
}

/**
 * Daily Scheduler Status Ticker
 */
async function checkSchedulerStatus() {
  try {
    const res = await fetch("/api/scheduler/status");
    const data = await res.json();
    const el = document.getElementById("schedulerStatusText");
    if (el && data.time_remaining) {
      el.textContent = `Daily 10:00 AM Sync (in ${data.time_remaining})`;
    }
  } catch (e) {
    // Silent fallback
  }
}

/**
 * Toast Notifications
 */
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  let icon = '<i class="fa-solid fa-circle-info"></i>';
  if (type === "success") icon = '<i class="fa-solid fa-circle-check"></i>';
  if (type === "error") icon = '<i class="fa-solid fa-triangle-exclamation"></i>';

  toast.innerHTML = `${icon}<span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(20px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
