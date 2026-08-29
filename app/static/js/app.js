/**
 * Acer Amazon Price Intelligence - Dashboard State & Controller
 */

let allProducts = [];
let portfolioStats = {};
let currentCategory = "all";
let currentSearchQuery = "";
let currentModalAsin = null;
const CURRENCY = "₹";

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  loadDashboardData();
  
  // Set automatic live time ticker
  updateLiveTimestamp();
  setInterval(updateLiveTimestamp, 60000);

  // Keyboard shortcut to close modal on Escape
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
});

function updateLiveTimestamp() {
  const el = document.getElementById("lastUpdatedText");
  if (el) {
    const now = new Date();
    el.textContent = `Live: ${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  }
}

async function loadDashboardData() {
  try {
    // 1. Fetch portfolio stats
    const statsRes = await fetch("/api/stats");
    portfolioStats = await statsRes.json();
    updateKPICards(portfolioStats);

    // Render Charts
    if (portfolioStats.month_labels && portfolioStats.category_trends) {
      initMainHistoryChart(portfolioStats.month_labels, portfolioStats.category_trends, CURRENCY);
      initCategoryDonutChart(portfolioStats.category_breakdown);
    }

    // 2. Fetch products table data
    const prodRes = await fetch("/api/products");
    const prodData = await prodRes.json();
    allProducts = prodData.products || [];
    renderTable();

  } catch (err) {
    console.error("Failed to load dashboard data:", err);
    showToast("Error connecting to tracker backend", "warning");
  }
}

function updateKPICards(stats) {
  if (!stats || !stats.total_products) return;

  document.getElementById("kpiTotalProducts").textContent = stats.total_products;
  document.getElementById("kpiAvgDiscount").textContent = `${stats.avg_discount_pct}%`;
  document.getElementById("kpiAtlDeals").textContent = `${stats.atl_deals_count} Products`;
  
  document.getElementById("kpiStockHealth").textContent = `${stats.in_stock_count}/${stats.total_products}`;
  document.getElementById("kpiStockSubtext").textContent = stats.out_of_stock_count > 0 
    ? `${stats.out_of_stock_count} units out of stock` 
    : "100% catalog available";

  if (stats.top_price_drop) {
    const drop = stats.top_price_drop;
    document.getElementById("kpiTopDrop").textContent = `-${drop.drop_pct}% (${CURRENCY}${drop.drop_amount.toLocaleString()})`;
    document.getElementById("kpiTopDropProduct").textContent = drop.title;
    document.getElementById("kpiTopDropProduct").title = drop.title;
  } else {
    document.getElementById("kpiTopDrop").textContent = "Stable";
    document.getElementById("kpiTopDropProduct").textContent = "No recent price cut";
  }
}

function renderTable() {
  const tbody = document.getElementById("tableBody");
  if (!tbody) return;

  const filtered = allProducts.filter(p => {
    const matchesCat = (currentCategory === "all" || p.category === currentCategory);
    const matchesSearch = !currentSearchQuery || 
      p.title.toLowerCase().includes(currentSearchQuery) ||
      p.asin.toLowerCase().includes(currentSearchQuery) ||
      p.category.toLowerCase().includes(currentSearchQuery);
    return matchesCat && matchesSearch;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9" class="text-center py-5 text-muted">
          <i class="fa-solid fa-circle-exclamation fa-2x mb-2 text-dim"></i>
          <p>No Acer products match the selected filter criteria.</p>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map(p => {
    const stats = p.stats || {};
    const discPct = stats.discount_from_mrp || 0;
    const isAtl = stats.is_atl;
    const isNearAtl = stats.is_near_atl;
    const isOutOfStock = (p.stock_status || "").toLowerCase().includes("out of stock");

    return `
      <tr>
        <td>
          <div class="asin-badge" title="Click to copy ASIN" onclick="copyToClipboard('${p.asin}')">
            <span>${p.asin}</span>
            <i class="fa-regular fa-copy" style="font-size: 10px; cursor: pointer;"></i>
          </div>
        </td>
        <td>
          <div class="product-cell">
            <img class="product-thumb" src="${p.image_url || 'https://via.placeholder.com/60'}" alt="${p.asin}" onerror="this.src='https://via.placeholder.com/60'">
            <div class="product-info-text">
              <a class="product-title-link" onclick="openProductModal('${p.asin}')" title="${p.title}">
                ${p.title}
              </a>
              <div class="product-rating">
                <i class="fa-solid fa-star text-gold"></i> ${p.rating} &bull; ${p.review_count.toLocaleString()} reviews
              </div>
            </div>
          </div>
        </td>
        <td>
          <span class="category-tag">${p.category}</span>
        </td>
        <td class="text-right">
          <span class="price-current">${CURRENCY}${p.current_price.toLocaleString()}</span>
        </td>
        <td class="text-right">
          <span class="price-mrp">${CURRENCY}${p.mrp.toLocaleString()}</span>
        </td>
        <td class="text-center">
          <span class="discount-pill">-${discPct}%</span>
        </td>
        <td class="text-right">
          <div class="low-price-stat">
            <span class="low-price-val">${CURRENCY}${(stats.min_price || p.current_price).toLocaleString()}</span>
            ${isAtl ? '<span class="atl-indicator"><i class="fa-solid fa-fire"></i> ATL Deal</span>' : ''}
            ${(!isAtl && isNearAtl) ? '<span class="atl-indicator" style="color: #38BDF8;">Near ATL</span>' : ''}
          </div>
        </td>
        <td class="text-center">
          <span class="stock-badge ${isOutOfStock ? 'out-stock' : 'in-stock'}">
            <i class="fa-solid ${isOutOfStock ? 'fa-circle-xmark' : 'fa-circle-check'}"></i>
            ${p.stock_status}
          </span>
        </td>
        <td class="text-center">
          <div class="action-buttons">
            <button class="btn-icon" title="View 22-Month Price History" onclick="openProductModal('${p.asin}')">
              <i class="fa-solid fa-chart-line"></i>
            </button>
            <button class="btn-icon btn-scrape-single" title="Live Scrape this ASIN" onclick="scrapeSingleAsin('${p.asin}', this)">
              <i class="fa-solid fa-arrows-rotate"></i>
            </button>
            <a class="btn-icon btn-amazon-action" title="Open on Amazon" href="${p.url}" target="_blank" rel="noopener noreferrer" onclick="window.open('${p.url}', '_blank'); return false;">
              <i class="fa-brands fa-amazon"></i>
            </a>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

// Category filter
function setCategoryFilter(cat, btn) {
  currentCategory = cat;
  document.querySelectorAll(".cat-tab").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  renderTable();
}

// Search filter
function filterTable() {
  currentSearchQuery = document.getElementById("searchInput").value.trim().toLowerCase();
  renderTable();
}

// Main Chart Category Dropdown Switcher
function updateMainChartCategory(selectedCategory) {
  if (!portfolioStats.month_labels || !portfolioStats.category_trends) return;

  if (selectedCategory === "all") {
    initMainHistoryChart(portfolioStats.month_labels, portfolioStats.category_trends, CURRENCY);
  } else {
    // Show only the selected category
    const singleCatTrends = {};
    singleCatTrends[selectedCategory] = portfolioStats.category_trends[selectedCategory] || [];
    initMainHistoryChart(portfolioStats.month_labels, singleCatTrends, CURRENCY);
  }
}

// Open Product 22-Month Modal
async function openProductModal(asin) {
  currentModalAsin = asin;
  const modal = document.getElementById("productModal");
  
  try {
    const res = await fetch(`/api/products/${asin}`);
    const data = await res.json();
    const prod = data.product;
    const stats = data.stats;
    const history = data.history;

    document.getElementById("modalProductImg").src = prod.image_url || "";
    document.getElementById("modalProductTitle").textContent = prod.title;
    document.getElementById("modalCategory").textContent = prod.category;
    document.getElementById("modalAsin").textContent = `ASIN: ${prod.asin}`;
    document.getElementById("modalRating").innerHTML = `<i class="fa-solid fa-star text-gold"></i> ${prod.rating} &bull; ${prod.review_count.toLocaleString()} Customer Reviews`;
    document.getElementById("modalAmazonLink").href = prod.url;

    // Deal badge
    const dealBadge = document.getElementById("modalDealBadge");
    if (stats.is_atl) {
      dealBadge.textContent = "★ All-Time Low Deal";
      dealBadge.style.display = "inline-block";
    } else if (stats.is_near_atl) {
      dealBadge.textContent = "Near 22-Month Low (5%)";
      dealBadge.style.display = "inline-block";
    } else {
      dealBadge.style.display = "none";
    }

    // Metrics
    document.getElementById("modalCurrentPrice").textContent = `${CURRENCY}${prod.current_price.toLocaleString()}`;
    document.getElementById("modalMrp").textContent = `${CURRENCY}${prod.mrp.toLocaleString()}`;
    document.getElementById("modalMinPrice").textContent = `${CURRENCY}${stats.min_price.toLocaleString()}`;
    document.getElementById("modalMaxPrice").textContent = `${CURRENCY}${stats.max_price.toLocaleString()}`;
    document.getElementById("modalAvgPrice").textContent = `${CURRENCY}${stats.avg_price.toLocaleString()}`;

    // Render single product chart
    renderModalProductChart(history, CURRENCY);

    modal.classList.add("active");
  } catch (err) {
    console.error("Failed to load product modal data:", err);
    showToast("Failed to fetch ASIN details", "warning");
  }
}

function closeModal() {
  const modal = document.getElementById("productModal");
  if (modal) modal.classList.remove("active");
}

function closeModalOnBackdrop(e) {
  if (e.target.id === "productModal") {
    closeModal();
  }
}

// Live scrape triggers
async function triggerScrapeAll() {
  const btn = document.getElementById("btnRunScrape");
  const origText = btn.innerHTML;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Crawling 25 ASINs...</span>`;
  btn.disabled = true;

  try {
    const res = await fetch("/api/scrape", { method: "POST" });
    const data = await res.json();
    showToast(data.message || "Live crawl initiated in background!", "success");
    
    // Refresh table data after a short interval
    setTimeout(loadDashboardData, 3000);
  } catch (err) {
    showToast("Live scraper request failed", "warning");
  } finally {
    setTimeout(() => {
      btn.innerHTML = origText;
      btn.disabled = false;
    }, 2500);
  }
}

async function scrapeSingleAsin(asin, btn) {
  if (btn) {
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;
  }

  try {
    const res = await fetch(`/api/scrape?asin=${asin}`, { method: "POST" });
    const data = await res.json();
    showToast(`Live scrape completed for ASIN ${asin}`, "success");
    await loadDashboardData();
  } catch (err) {
    showToast(`Failed to scrape ASIN ${asin}`, "warning");
  } finally {
    if (btn) {
      btn.innerHTML = `<i class="fa-solid fa-arrows-rotate"></i>`;
    }
  }
}

async function scrapeSingleModalAsin() {
  if (!currentModalAsin) return;
  await scrapeSingleAsin(currentModalAsin);
  openProductModal(currentModalAsin);
}

// Utility: Copy ASIN to clipboard
function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast(`ASIN ${text} copied to clipboard!`, "success");
  }).catch(() => {
    showToast(`Copied ${text}`, "success");
  });
}

// Explicit Excel Download Handler with Guaranteed File Naming
async function downloadExcelReport(event) {
  if (event) event.preventDefault();
  
  const btn = document.getElementById("btnDownloadExcel");
  const origHtml = btn.innerHTML;
  btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> <span>Generating Excel...</span>`;
  btn.style.pointerEvents = "none";
  
  try {
    const response = await fetch("/api/export/excel");
    if (!response.ok) throw new Error("Failed to generate Excel file");
    
    const blob = await response.blob();
    const filename = `Acer_Amazon_Price_Tracker_22Months_${new Date().toISOString().slice(0,10).replace(/-/g, '')}.xlsx`;
    
    // Create temporary blob download link with explicit filename
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.style.display = "none";
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    
    setTimeout(() => {
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    }, 2000);
    
    showToast(`Downloaded ${filename} successfully!`, "success");
  } catch (err) {
    console.error("Excel download error:", err);
    showToast("Failed to download Excel file. Please try again.", "warning");
  } finally {
    btn.innerHTML = origHtml;
    btn.style.pointerEvents = "auto";
  }
}

// Toast Notifications
function showToast(message, type = "success") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <i class="fa-solid ${type === 'success' ? 'fa-circle-check text-emerald' : 'fa-triangle-exclamation text-gold'}"></i>
    <span>${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
