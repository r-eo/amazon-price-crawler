/**
 * Acer Amazon Intelligence Platform — Executive Controller v3.0
 * Features: Dual Dashboards, Real-Time Price Drops, Notification Center, Daily Scans & Charts
 */

let currentGroup = "other_products";
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
  await switchDashboard(currentGroup);
  await fetchNotifications();
  await checkSchedulerStatus();
  updateBrowserNotificationButton();
  
  // Refresh scheduler & notifications every 2 minutes
  setInterval(checkSchedulerStatus, 120000);
  setInterval(fetchNotifications, 120000);
}

/**
 * Fetch counts for each tab badge using lightweight API
 */
async function fetchTabCounts() {
  try {
    const res = await fetch(`/api/tabs/counts?_t=${Date.now()}`, { cache: "no-store" });
    const data = await res.json();

    const mCount = document.getElementById("badgeMonitorsCount");
    const oCount = document.getElementById("badgeOtherCount");
    const aCount = document.getElementById("badgeAllCount");

    if (mCount) mCount.textContent = data.acer_monitors || 0;
    if (oCount) oCount.textContent = data.other_products || 0;
    if (aCount) aCount.textContent = data.all || 0;
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
  const downloadTableBtn = document.getElementById("btnDownloadExcelTable");
  const scrapeText = document.getElementById("scrapeBtnText");
  const viewLabel = document.getElementById("currentViewLabel");
  const kpiScopeLabel = document.getElementById("kpiLabelProducts");
  const chartTitle = document.getElementById("chartTitle");

  if (group === "acer_monitors") {
    if (downloadBtn) downloadBtn.href = "/api/export/excel?group=acer_monitors";
    if (downloadText) downloadText.textContent = "Export Excel";
    if (downloadTableBtn) downloadTableBtn.href = "/api/export/excel?group=acer_monitors";
    if (scrapeText) scrapeText.textContent = "Scrape Monitors Tab";
    if (viewLabel) viewLabel.innerHTML = "Viewing: <strong>Acer Monitors Dashboard (Catalog Pending)</strong>";
    if (kpiScopeLabel) kpiScopeLabel.textContent = "Tracked Monitors";
    if (chartTitle) chartTitle.textContent = "Acer Monitors — 6-Month Price Trajectory";
  } else if (group === "other_products") {
    if (downloadBtn) downloadBtn.href = "/api/export/excel?group=other_products";
    if (downloadText) downloadText.textContent = "Export Excel";
    if (downloadTableBtn) downloadTableBtn.href = "/api/export/excel?group=other_products";
    if (scrapeText) scrapeText.textContent = "Scrape Accessories Tab";
    if (viewLabel) viewLabel.innerHTML = "Viewing: <strong>Other Accessories Dashboard (90 Products)</strong>";
    if (kpiScopeLabel) kpiScopeLabel.textContent = "Tracked Accessories";
    if (chartTitle) chartTitle.textContent = "Other Accessories — 6-Month Price Trajectory";
  } else {
    if (downloadBtn) downloadBtn.href = "/api/export/excel?group=all";
    if (downloadText) downloadText.textContent = "Export Excel";
    if (downloadTableBtn) downloadTableBtn.href = "/api/export/excel?group=all";
    if (scrapeText) scrapeText.textContent = "Scrape All Portfolio";
    if (viewLabel) viewLabel.innerHTML = "Viewing: <strong>Full 90-Product Portfolio</strong>";
    if (kpiScopeLabel) kpiScopeLabel.textContent = "Total Products";
    if (chartTitle) chartTitle.textContent = "Overall Portfolio — 6-Month Price Trajectory";
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
    const timestamp = Date.now();
    const [prodRes, statsRes] = await Promise.all([
      fetch(`/api/products?group=${currentGroup}&_t=${timestamp}`, { cache: "no-store" }),
      fetch(`/api/stats?group=${currentGroup}&_t=${timestamp}`, { cache: "no-store" })
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
      kpiSubtextScope.textContent = "Catalog Pending Tomorrow";
    } else if (currentGroup === "other_products") {
      kpiSubtextScope.textContent = "Complete Accessories Portfolio (Excel 1-90)";
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
    bannerText.innerHTML = `<strong>${topDrop.title}</strong> dropped by <span style="color: #d97706; font-weight: 700;">${topDrop.drop_pct}%</span> (Saved ₹${Math.round(topDrop.drop_amount).toLocaleString()})! Live Price: <strong>${currencySymbol}${Math.round(topDrop.current_price).toLocaleString()}</strong>`;
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
      const stats = p.stats || {};
      if (!stats.has_price_drop) return false;
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
    const isMonitors = currentGroup === "acer_monitors";
    tbody.innerHTML = `
      <tr>
        <td colspan="10" class="text-center" style="padding: 48px 20px; color: var(--text-muted);">
          <i class="fa-solid ${isMonitors ? 'fa-display' : 'fa-box-open'}" style="font-size: 36px; margin-bottom: 12px; display: block; color: var(--color-indigo);"></i>
          <h4 style="color: var(--text-main); margin-bottom: 6px; font-size: 15px;">${isMonitors ? 'Acer Monitors Catalog Pending' : 'No products found'}</h4>
          <p style="max-width: 460px; margin: 0 auto; font-size: 13px; line-height: 1.5;">
            ${isMonitors ? 'Monitor stands & privacy screens have been moved into the Other Accessories tab. Real Acer Monitors catalog will be uploaded here tomorrow.' : 'No products found matching the current filters.'}
          </p>
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
    const hasPriceDrop = !!stats.has_price_drop;

    const imgTag = p.image_url
      ? `<img src="${p.image_url}" alt="thumb" class="product-thumb" loading="lazy" referrerpolicy="no-referrer" onerror="this.src='https://placehold.co/48x48/1E293B/94A3B8?text=Acer'">`
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
            ${p.part_no ? `<span class="product-part-no" style="font-family: var(--font-mono); font-weight: 600; color: var(--color-indigo);"><i class="fa-solid fa-barcode" style="font-size: 10px;"></i> ${p.part_no}</span> <span>&bull;</span>` : ''}
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
        <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 2px;">
          <span class="price-val" style="color: #0f172a; font-weight: 700; font-size: 14px;">${currencySymbol}${Math.round(p.current_price || 0).toLocaleString()}</span>
          ${isAtl ? `<span class="badge-atl"><i class="fa-solid fa-star"></i> ATL DEAL</span>` : ""}
          ${hasPriceDrop ? `<span class="badge-drop" title="Dropped by ${currencySymbol}${Math.round(stats.drop_amount || 0).toLocaleString()} (${stats.drop_pct || 0}%) from previous price ${currencySymbol}${Math.round(stats.prev_price || 0).toLocaleString()}"><i class="fa-solid fa-arrow-trend-down"></i> ${stats.drop_pct ? `-${stats.drop_pct}%` : 'DROPPED'}</span>` : ""}
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
          <button class="btn btn-icon btn-outline" onclick="openProductDetailModal('${p.asin}')" title="View 6-Month Price Timeline">
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

async function fetchNotifications() {
  try {
    const res = await fetch(`/api/notifications?limit=40&_t=${Date.now()}`, { cache: "no-store" });
    const data = await res.json();
    const notifications = data.notifications || data.price_changes || [];
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

    if (countPill) countPill.textContent = notifications.length;

    if (notifList) {
      if (notifications.length === 0) {
        notifList.innerHTML = `
          <div class="notification-empty">
            <i class="fa-solid fa-bell-slash"></i>
            <p>No price changes logged yet. Click 'Check Prices' to run a live check!</p>
          </div>
        `;
      } else {
        notifList.innerHTML = "";
        notifications.forEach((item) => {
          const isDrop = item.change_type === "drop" || item.previous_price > item.new_price;
          const div = document.createElement("div");
          div.className = `notification-item ${item.is_read ? '' : 'unread'}`;
          div.innerHTML = `
            <div class="notif-item-icon" style="background: ${isDrop ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)'}; color: ${isDrop ? '#10b981' : '#f59e0b'};">
              <i class="fa-solid ${isDrop ? 'fa-arrow-trend-down' : 'fa-arrow-trend-up'}"></i>
            </div>
            <div class="notif-item-body">
              <div class="notif-item-title">${item.title}</div>
              <div class="notif-item-prices">
                <span class="notif-old-price">${currencySymbol}${Math.round(item.previous_price).toLocaleString()}</span>
                <span>→</span>
                <span class="notif-new-price">${currencySymbol}${Math.round(item.new_price).toLocaleString()}</span>
                <span class="notif-savings-pill" style="background: ${isDrop ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)'}; color: ${isDrop ? '#10b981' : '#f59e0b'};">
                  ${isDrop ? '-' : '+'}${item.change_pct}%
                </span>
              </div>
              <div class="notif-item-time">
                <i class="fa-regular fa-clock" style="font-size: 10px;"></i> ${item.timestamp || 'Recently'} &bull; ASIN: ${item.asin}
              </div>
            </div>
            <a href="https://www.amazon.in/dp/${item.asin}" target="_blank" rel="noopener" class="btn btn-xs btn-outline" style="align-self: center;" title="View on Amazon">
              <i class="fa-solid fa-arrow-up-right-from-square"></i>
            </a>
          `;
          notifList.appendChild(div);
        });
      }
    }
  } catch (e) {
    console.error("Error fetching notifications:", e);
  }
}

// Backwards compatibility alias
const fetchPriceAlerts = fetchNotifications;

async function markAllNotificationsAsRead() {
  try {
    await fetch("/api/notifications/mark-read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    showToast("All notifications marked as read.", "info");
    await fetchNotifications();
  } catch (err) {
    showToast("Failed to mark notifications as read.", "error");
  }
}
const markAllAlertsAsRead = markAllNotificationsAsRead;

async function clearAllNotifications() {
  try {
    await fetch("/api/notifications/clear", { method: "POST" });
    showToast("Price change notifications cleared.", "info");
    await fetchNotifications();
  } catch (err) {
    showToast("Failed to clear notifications.", "error");
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

  showToast("Scanning Amazon live prices for updates...", "amber");

  try {
    const res = await fetch(`/api/check-prices-daily?group=${currentGroup}&_t=${Date.now()}`, { 
      method: "POST",
      cache: "no-store"
    });
    const data = await res.json();
    
    if (data.status === "busy") {
      showToast(data.message || "A scan is already actively in progress. Please wait.", "amber");
    } else if (data.status === "completed") {
      showToast(data.message || "Live price check completed!", "success");
      if (data.products && data.products.length > 0) {
        allProducts = data.products;
        applyFiltersAndRenderTable();
      }
      await loadDashboardData();
      await fetchNotifications();
      await fetchTabCounts();
    } else {
      showToast(data.message || "Price scan initiated.", "info");
      setTimeout(async () => {
        await loadDashboardData();
        await fetchNotifications();
        await fetchTabCounts();
      }, 3000);
    }

    // Send Browser Push Notification if supported & permitted
    if (Notification.permission === "granted") {
      new Notification("Acer Amazon Price Check Complete", {
        body: `Live price crawl completed for ${currentGroup === 'acer_monitors' ? 'Monitors & Stands' : 'Accessories'}.`,
        icon: "https://m.media-amazon.com/images/I/61Nl-F3kGLL._SX679_.jpg"
      });
    }
  } catch (err) {
    showToast("Error triggering daily scan.", "error");
  } finally {
    if (checkBtn) {
      checkBtn.disabled = false;
      checkBtn.innerHTML = `<i class="fa-solid fa-bolt"></i> <span>Check Prices</span>`;
    }
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
    const res = await fetch(`/api/scrape?asin=${asin}&_t=${Date.now()}`, { 
      method: "POST",
      cache: "no-store"
    });
    const data = await res.json();
    if (data.status === "completed") {
      const prod = data.data;
      const priceStr = prod && prod.current_price ? `₹${Number(prod.current_price).toLocaleString()}` : "live price";
      showToast(`ASIN ${asin} updated: ${priceStr}`, "success");
      
      // Instantly update DOM row
      if (prod) {
        const idx = allProducts.findIndex(p => p.asin === asin);
        if (idx !== -1) {
          allProducts[idx] = { ...allProducts[idx], ...prod };
          applyFiltersAndRenderTable();
        }
      }
      await loadDashboardData();
      await fetchPriceAlerts();
    } else {
      showToast(data.message || `Scrape failed for ASIN ${asin}`, "amber");
    }
  } catch (err) {
    showToast(`Failed to crawl ASIN ${asin}`, "error");
  }
}

/**
 * Scrape Active Group
 */
async function triggerActiveGroupScrape() {
  await triggerDailyPriceCheck();
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
  showToast(`Preparing ${currentGroup} 6-Month Excel report...`, "info");
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
      <p style="margin-top: 10px;">Loading historical 6-month timeline...</p>
    </div>
  `;

  try {
    const res = await fetch(`/api/products/${asin}?_t=${Date.now()}`, { cache: "no-store" });
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
          <span class="modal-stat-val" style="color: var(--text-primary); font-weight: 700;">${currencySymbol}${Math.round(p.current_price).toLocaleString()}</span>
        </div>
        <div class="modal-stat-box">
          <span class="modal-stat-label">Baseline MRP</span>
          <span class="modal-stat-val">${currencySymbol}${Math.round(p.mrp).toLocaleString()}</span>
        </div>
        <div class="modal-stat-box">
          <span class="modal-stat-label">6-Month Lowest</span>
          <span class="modal-stat-val" style="color: var(--color-emerald);">${currencySymbol}${Math.round(stats.min_price || p.current_price).toLocaleString()}</span>
        </div>
        <div class="modal-stat-box">
          <span class="modal-stat-label">6-Month Average</span>
          <span class="modal-stat-val" style="color: var(--color-indigo); font-weight: 700;">${currencySymbol}${Math.round(stats.avg_price || p.current_price).toLocaleString()}</span>
        </div>
        ${stats.has_price_drop ? `
        <div class="modal-stat-box" style="border-color: rgba(217, 119, 6, 0.4); background: rgba(217, 119, 6, 0.05);">
          <span class="modal-stat-label" style="color: #d97706;"><i class="fa-solid fa-arrow-trend-down"></i> Active Price Drop</span>
          <span class="modal-stat-val" style="color: #d97706; font-weight: 700;">-${stats.drop_pct}% (-${currencySymbol}${Math.round(stats.drop_amount).toLocaleString()})</span>
        </div>` : ''}
      </div>

      <div style="background-color: var(--bg-input); border: 1px solid var(--border-card); border-radius: var(--radius-md); padding: 18px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
          <span style="font-size: 13px; font-weight: 700; color: var(--text-primary);">6-Month Trajectory & Seasonal Deals</span>
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
  if (e && e.target && e.target !== document.getElementById("productDetailModal") && !e.target.classList.contains("modal-close-btn")) {
    return;
  }
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
  if (e && e.target && e.target !== document.getElementById("addAsinModal") && !e.target.classList.contains("modal-close-btn") && e.target.tagName !== "BUTTON") {
    return;
  }
  const modal = document.getElementById("addAsinModal");
  if (modal) modal.classList.remove("active");
  const form = document.getElementById("addAsinForm");
  if (form) form.reset();
}

// Global Escape Key Listener for Modals & Panels
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeAddAsinModal();
    closeProductModal();
    closeNotificationPanel();
  }
});

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
    const res = await fetch(`/api/scheduler/status?_t=${Date.now()}`, { cache: "no-store" });
    const data = await res.json();
    const el = document.getElementById("schedulerStatusText");
    const ind = document.getElementById("schedulerStatusIndicator");
    if (el && data.time_remaining) {
      const nextDisplay = data.next_time_display || "9:00 AM IST";
      el.textContent = `Sync: ${nextDisplay} (${data.time_remaining})`;
    }
    if (ind && data.intervals) {
      ind.title = `Automated sync runs every 2 hours in IST (9 AM to 9 PM). Next: ${data.next_run_at || ''}`;
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
