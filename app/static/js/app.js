/**
 * Acer Amazon Intelligence Platform — Executive Controller v3.0
 * Features: Dual Dashboards, Real-Time Price Drops, Notification Center, Daily Scans & Charts
 */

let currentGroup = "acer_monitors";
let allProducts = [];
let filteredProducts = [];
let dashboardStats = {};
let atlFilterActive = false;
let priceDropFilterActive = false;
let currencySymbol = "₹";
let notificationPanelOpen = false;

document.addEventListener("DOMContentLoaded", () => {
  initApp();
  
  // Close dropdown on outside click
  document.addEventListener("click", (e) => {
    const notifWrapper = document.querySelector(".notification-wrapper");
    if (notifWrapper && !notifWrapper.contains(e.target) && notificationPanelOpen) {
      closeNotificationPanel();
    }
  });
});

async function initApp() {
  await fetchTabCounts();
  await loadDashboardData();
  await fetchPriceAlerts();
  await checkSchedulerStatus();
  updateBrowserNotificationButton();
  
  // Refresh scheduler & alerts every 2 minutes
  setInterval(checkSchedulerStatus, 120000);
  setInterval(fetchPriceAlerts, 120000);
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
  priceDropFilterActive = false;
  updateFilterPills();

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
    scrapeText.textContent = "Scrape Monitors Tab";
    viewLabel.innerHTML = "Viewing: <strong>Acer Monitors & Stands Dashboard</strong>";
    kpiScopeLabel.textContent = "Tracked Hardware";
    chartTitle.textContent = "Acer Monitors & Stands — 22-Month Price Trajectory";
  } else if (group === "other_products") {
    downloadBtn.href = "/api/export/excel?group=other_products";
    downloadText.textContent = "Download Accessories Excel (.xlsx)";
    scrapeText.textContent = "Scrape Accessories Tab";
    viewLabel.innerHTML = "Viewing: <strong>Other Accessories Dashboard</strong>";
    kpiScopeLabel.textContent = "Tracked Accessories";
    chartTitle.textContent = "Other Accessories — 22-Month Price Trajectory";
  } else {
    downloadBtn.href = "/api/export/excel?group=all";
    downloadText.textContent = "Download All Portfolio (.xlsx)";
    scrapeText.textContent = "Scrape All Portfolio";
    viewLabel.innerHTML = "Viewing: <strong>Full 90-Product Portfolio</strong>";
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
    checkPriceDropBanner(dashboardStats);

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
  document.getElementById("kpiPriceDrops").textContent = stats.price_drops_count || 0;
  document.getElementById("kpiAtlDeals").textContent = stats.atl_deals_count || 0;

  const kpiSubtextScope = document.getElementById("kpiSubtextScope");
  if (kpiSubtextScope) {
    if (currentGroup === "acer_monitors") {
      kpiSubtextScope.textContent = "Monitor Stands & Privacy Screens";
    } else if (currentGroup === "other_products") {
      kpiSubtextScope.textContent = "Mice, Keyboards, Audio & Bags";
    } else {
      kpiSubtextScope.textContent = "Unified 90-Item Portfolio";
    }
  }
}

/**
 * Price Drop Banner Controller
 */
function checkPriceDropBanner(stats) {
  const banner = document.getElementById("priceDropBanner");
  const bannerText = document.getElementById("bannerDropText");
  if (!banner || !bannerText) return;

  const topDrop = stats.top_price_drop;
  if (topDrop && topDrop.drop_pct > 0) {
    bannerText.innerHTML = `<strong>${topDrop.title}</strong> dropped by <span style="color: #FBBF24; font-weight: 700;">${topDrop.drop_pct}%</span> (Saved ₹${Math.round(topDrop.drop_amount).toLocaleString()})! Live Price: <strong>${currencySymbol}${Math.round(topDrop.current_price).toLocaleString()}</strong>`;
    banner.style.display = "block";
  } else {
    banner.style.display = "none";
  }
}

function dismissPriceDropBanner() {
  const banner = document.getElementById("priceDropBanner");
  if (banner) banner.style.display = "none";
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
 * Apply filters (search, category, ATL, Price Drop) and render table
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
    if (priceDropFilterActive) {
      // Check if price is lower than average or has price drop
      const stats = p.stats || {};
      const hasDrop = (stats.avg_price && p.current_price < stats.avg_price) || stats.is_atl;
      if (!hasDrop) return false;
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
  priceDropFilterActive = false;
  updateFilterPills();
  if (atlFilterActive) {
    showToast("Filtering table: Showing All-Time Low deals only.", "info");
  } else {
    showToast("Cleared All-Time Low filter.", "info");
  }
  applyFiltersAndRenderTable();
}

function filterByPriceDrops() {
  priceDropFilterActive = !priceDropFilterActive;
  atlFilterActive = false;
  updateFilterPills();
  if (priceDropFilterActive) {
    showToast("Filtering table: Showing items with Price Drops.", "amber");
  } else {
    showToast("Cleared Price Drops filter.", "info");
  }
  applyFiltersAndRenderTable();
}

function clearPillFilters() {
  atlFilterActive = false;
  priceDropFilterActive = false;
  updateFilterPills();
  applyFiltersAndRenderTable();
}

function togglePriceDropPill() {
  filterByPriceDrops();
}

function toggleAtlPill() {
  filterByAtl();
}

function updateFilterPills() {
  const pillAll = document.getElementById("pillFilterAll");
  const pillDrops = document.getElementById("pillFilterDrops");
  const pillAtl = document.getElementById("pillFilterAtl");
  const cardDrops = document.getElementById("kpiCardPriceDrops");
  const cardAtl = document.getElementById("kpiCardAtl");

  if (pillAll) pillAll.classList.toggle("active", !atlFilterActive && !priceDropFilterActive);
  if (pillDrops) pillDrops.classList.toggle("active", priceDropFilterActive);
  if (pillAtl) pillAtl.classList.toggle("active", atlFilterActive);

  if (cardDrops) cardDrops.classList.toggle("active-filter", priceDropFilterActive);
  if (cardAtl) cardAtl.classList.toggle("active-filter", atlFilterActive);
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
          <i class="fa-solid fa-box-open" style="font-size: 32px; margin-bottom: 12px; display: block; color: var(--color-indigo);"></i>
          No products found matching the current filters.
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
    const hasPriceDrop = stats.avg_price && p.current_price < stats.avg_price;

    const imgTag = p.image_url
      ? `<img src="${p.image_url}" alt="thumb" class="product-thumb" loading="lazy" onerror="this.src='https://placehold.co/48x48/1E293B/94A3B8?text=Acer'">`
      : `<i class="fa-solid fa-microchip" style="color: var(--color-indigo); font-size: 20px;"></i>`;

    tr.innerHTML = `
      <td>
        <div class="product-thumb-container">
          ${imgTag}
        </div>
      </td>
      <td>
        <span class="asin-code" title="Click to copy ASIN" onclick="copyAsin('${p.asin}')">
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
            <span>${(p.review_count || 100).toLocaleString()} reviews</span>
            <span>&bull;</span>
            <a href="${p.url}" target="_blank" rel="noopener" style="color: var(--color-cyan); text-decoration: none;">
              Amazon <i class="fa-solid fa-arrow-up-right-from-square" style="font-size: 9px;"></i>
            </a>
          </div>
        </div>
      </td>
      <td>
        <span class="badge badge-indigo">${p.category}</span>
      </td>
      <td class="text-right">
        <div style="display: flex; flex-direction: column; align-items: flex-end;">
          <span class="price-val" style="color: #F8FAFC;">${currencySymbol}${Math.round(p.current_price || 0).toLocaleString()}</span>
          ${isAtl ? `<span class="badge-atl"><i class="fa-solid fa-star"></i> ATL DEAL</span>` : (hasPriceDrop ? `<span class="badge-drop"><i class="fa-solid fa-arrow-trend-down"></i> DROPPED</span>` : "")}
        </div>
      </td>
      <td class="text-right">
        <span class="mrp-val">${currencySymbol}${Math.round(p.mrp || 0).toLocaleString()}</span>
      </td>
      <td class="text-center">
        <span class="badge badge-emerald">${discount}% OFF</span>
      </td>
      <td class="text-center">
        <span class="price-val" style="color: var(--color-emerald); font-size: 12px;">
          ${currencySymbol}${Math.round(stats.min_price || p.current_price).toLocaleString()}
        </span>
      </td>
      <td class="text-center">
        <span class="badge ${inStock ? 'badge-emerald' : 'badge-red'}">
          ${inStock ? 'In Stock' : 'Unavailable'}
        </span>
      </td>
      <td class="text-center">
        <div class="action-buttons">
          <button class="btn btn-icon btn-outline" onclick="openProductDetailModal('${p.asin}')" title="View 22-Month Price Timeline">
            <i class="fa-solid fa-chart-line" style="color: var(--color-indigo);"></i>
          </button>
          <button class="btn btn-icon btn-outline" onclick="scrapeSingleAsin('${p.asin}')" title="Live Crawl Amazon Price">
            <i class="fa-solid fa-rotate" style="color: var(--color-emerald);"></i>
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
 * Notification Center Controller
 */
function toggleNotificationPanel(e) {
  e.stopPropagation();
  notificationPanelOpen = !notificationPanelOpen;
  const panel = document.getElementById("notificationPanel");
  if (panel) {
    panel.classList.toggle("active", notificationPanelOpen);
  }
}

function closeNotificationPanel() {
  notificationPanelOpen = false;
  const panel = document.getElementById("notificationPanel");
  if (panel) panel.classList.remove("active");
}

async function fetchPriceAlerts() {
  try {
    const res = await fetch("/api/alerts?limit=30");
    const data = await res.json();
    const alerts = data.alerts || [];
    const unreadCount = data.unread_count || 0;

    const badge = document.getElementById("unreadAlertBadge");
    const countPill = document.getElementById("notifPanelCount");
    const notifList = document.getElementById("notificationList");

    if (badge) {
      if (unreadCount > 0) {
        badge.textContent = unreadCount > 99 ? "99+" : unreadCount;
        badge.style.display = "flex";
      } else {
        badge.style.display = "none";
      }
    }

    if (countPill) countPill.textContent = alerts.length;

    if (notifList) {
      if (alerts.length === 0) {
        notifList.innerHTML = `
          <div class="notification-empty">
            <i class="fa-solid fa-bell-slash"></i>
            <p>No price drop alerts yet. Run a daily check to scan for deals!</p>
          </div>
        `;
      } else {
        notifList.innerHTML = "";
        alerts.forEach((alt) => {
          const item = document.createElement("div");
          item.className = `notification-item ${alt.is_read ? '' : 'unread'}`;
          item.innerHTML = `
            <div class="notif-item-icon">
              <i class="fa-solid fa-arrow-trend-down"></i>
            </div>
            <div class="notif-item-body">
              <div class="notif-item-title">${alt.title}</div>
              <div class="notif-item-prices">
                <span class="notif-old-price">${currencySymbol}${Math.round(alt.previous_price).toLocaleString()}</span>
                <span>→</span>
                <span class="notif-new-price">${currencySymbol}${Math.round(alt.new_price).toLocaleString()}</span>
                <span class="notif-savings-pill">-${alt.drop_pct}%</span>
              </div>
              <div class="notif-item-time">
                <i class="fa-regular fa-clock" style="font-size: 10px;"></i> ${alt.created_at || 'Recently'} &bull; ASIN: ${alt.asin}
              </div>
            </div>
            <a href="https://www.amazon.in/dp/${alt.asin}" target="_blank" rel="noopener" class="btn btn-xs btn-outline" style="align-self: center;" title="View on Amazon">
              <i class="fa-solid fa-arrow-up-right-from-square"></i>
            </a>
          `;
          notifList.appendChild(item);
        });
      }
    }
  } catch (e) {
    console.error("Error fetching alerts:", e);
  }
}

async function markAllAlertsAsRead() {
  try {
    const res = await fetch("/api/alerts/mark-read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    showToast("All price alerts marked as read.", "info");
    await fetchPriceAlerts();
  } catch (err) {
    showToast("Failed to mark alerts as read.", "error");
  }
}

/**
 * Trigger Instant Daily Price Scan
 */
async function triggerDailyPriceCheck() {
  const checkBtn = document.getElementById("btnCheckPrices");
  if (checkBtn) {
    checkBtn.disabled = true;
    checkBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Checking Amazon...`;
  }

  showToast("Scanning Amazon prices for price drops...", "amber");

  try {
    const res = await fetch(`/api/check-prices-daily?group=${currentGroup}`, { method: "POST" });
    const data = await res.json();
    showToast(data.message || "Price scan initiated.", "success");

    // Send Browser Push Notification if supported & permitted
    if (Notification.permission === "granted") {
      new Notification("Acer Amazon Price Check Initiated", {
        body: `Daily price crawl running for ${currentGroup === 'acer_monitors' ? 'Monitors & Stands' : 'Accessories'}.`,
        icon: "https://m.media-amazon.com/images/I/61Nl-F3kGLL._SX679_.jpg"
      });
    }

    setTimeout(async () => {
      await loadDashboardData();
      await fetchPriceAlerts();
      await fetchTabCounts();
    }, 3500);
  } catch (err) {
    showToast("Error triggering daily scan.", "error");
  } finally {
    setTimeout(() => {
      if (checkBtn) {
        checkBtn.disabled = false;
        checkBtn.innerHTML = `<i class="fa-solid fa-bolt"></i> <span>Check Prices Now</span>`;
      }
    }, 2000);
  }
}

/**
 * Request Web Push Notification Permission
 */
async function requestBrowserNotificationPermission() {
  if (!("Notification" in window)) {
    showToast("This browser does not support desktop notifications.", "error");
    return;
  }

  if (Notification.permission === "granted") {
    showToast("Desktop notifications are already enabled!", "success");
    return;
  }

  const perm = await Notification.requestPermission();
  updateBrowserNotificationButton();

  if (perm === "granted") {
    showToast("Desktop notifications enabled! You will be alerted on price drops.", "success");
    new Notification("Acer Price Alerts Active", {
      body: "You will now receive desktop notifications whenever a product price drops!",
      icon: "https://m.media-amazon.com/images/I/61Nl-F3kGLL._SX679_.jpg"
    });
  } else {
    showToast("Notification permission was dismissed or blocked.", "info");
  }
}

function updateBrowserNotificationButton() {
  const permBtn = document.getElementById("btnEnableBrowserNotif");
  const text = document.getElementById("notifPermText");
  if (!permBtn || !text) return;

  if ("Notification" in window && Notification.permission === "granted") {
    permBtn.style.borderColor = "var(--color-emerald-border)";
    permBtn.style.color = "var(--color-emerald)";
    text.textContent = "Push Alerts Active";
  } else {
    text.textContent = "Enable Push Alerts";
  }
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
      await fetchPriceAlerts();
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
    setTimeout(async () => {
      await loadDashboardData();
      await fetchPriceAlerts();
    }, 3500);
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
      <i class="fa-solid fa-spinner fa-spin" style="font-size: 24px; color: var(--color-indigo);"></i>
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
          <span class="modal-stat-val" style="color: #F8FAFC;">${currencySymbol}${Math.round(p.current_price).toLocaleString()}</span>
        </div>
        <div class="modal-stat-box">
          <span class="modal-stat-label">Baseline MRP</span>
          <span class="modal-stat-val">${currencySymbol}${Math.round(p.mrp).toLocaleString()}</span>
        </div>
        <div class="modal-stat-box">
          <span class="modal-stat-label">22-Month Lowest</span>
          <span class="modal-stat-val" style="color: var(--color-emerald);">${currencySymbol}${Math.round(stats.min_price || p.current_price).toLocaleString()}</span>
        </div>
        <div class="modal-stat-box">
          <span class="modal-stat-label">22-Month Average</span>
          <span class="modal-stat-val" style="color: #93C5FD;">${currencySymbol}${Math.round(stats.avg_price || p.current_price).toLocaleString()}</span>
        </div>
      </div>

      <div style="background-color: var(--bg-input); border: 1px solid var(--border-card); border-radius: var(--radius-md); padding: 18px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
          <span style="font-size: 13px; font-weight: 700; color: var(--text-primary);">22-Month Trajectory & Seasonal Deals</span>
          <span style="font-size: 11px; color: var(--text-muted);"><i class="fa-solid fa-circle" style="color: var(--color-emerald); font-size: 8px;"></i> All-Time Low Deal Markers</span>
        </div>
        <div style="height: 270px; position: relative;">
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
  if (type === "amber") icon = '<i class="fa-solid fa-fire"></i>';

  toast.innerHTML = `${icon}<span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(20px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
