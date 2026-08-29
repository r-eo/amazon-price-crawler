/**
 * Visual Analytics & Chart.js Controllers for Acer Price Intelligence
 */

let mainHistoryChartInstance = null;
let categoryDonutChartInstance = null;
let modalProductChartInstance = null;

// Modern vibrant palette
const CATEGORY_COLORS = {
  "Gaming Laptops": { line: "#06B6D4", bg: "rgba(6, 182, 212, 0.15)" },     // Cyan
  "Everyday Laptops": { line: "#10B981", bg: "rgba(16, 185, 129, 0.15)" },   // Emerald
  "Monitors": { line: "#8B5CF6", bg: "rgba(139, 92, 246, 0.15)" },          // Purple
  "Desktops & AIO": { line: "#F59E0B", bg: "rgba(245, 158, 11, 0.15)" },    // Amber
  "Accessories": { line: "#EC4899", bg: "rgba(236, 72, 153, 0.15)" },       // Pink
};

function initMainHistoryChart(monthLabels, categoryTrends, currencySymbol = "₹") {
  const ctx = document.getElementById("mainHistoryChart");
  if (!ctx) return;

  const datasets = Object.keys(categoryTrends).map((cat) => {
    const styling = CATEGORY_COLORS[cat] || { line: "#38BDF8", bg: "rgba(56, 189, 248, 0.1)" };
    return {
      label: cat,
      data: categoryTrends[cat],
      borderColor: styling.line,
      backgroundColor: styling.bg,
      borderWidth: 2.5,
      tension: 0.35,
      pointRadius: 3,
      pointHoverRadius: 6,
      pointBackgroundColor: styling.line,
      pointBorderColor: "#0F172A",
      pointBorderWidth: 2,
      fill: false,
    };
  });

  if (mainHistoryChartInstance) {
    mainHistoryChartInstance.destroy();
  }

  mainHistoryChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: monthLabels,
      datasets: datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          position: "top",
          labels: {
            color: "#94A3B8",
            font: { family: "Plus Jakarta Sans", size: 11, weight: "600" },
            usePointStyle: true,
            boxWidth: 8,
            boxHeight: 8,
          },
        },
        tooltip: {
          backgroundColor: "#0F172A",
          titleColor: "#F8FAFC",
          bodyColor: "#94A3B8",
          borderColor: "rgba(255, 255, 255, 0.1)",
          borderWidth: 1,
          padding: 12,
          boxPadding: 6,
          usePointStyle: true,
          callbacks: {
            label: function (context) {
              let label = context.dataset.label || "";
              if (label) label += ": ";
              if (context.parsed.y !== null) {
                label += currencySymbol + context.parsed.y.toLocaleString();
              }
              return label;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: {
            color: "#64748B",
            font: { family: "Plus Jakarta Sans", size: 10 },
            maxRotation: 45,
            minRotation: 0,
            autoSkip: true,
            maxTicksLimit: 11,
          },
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: {
            color: "#64748B",
            font: { family: "Plus Jakarta Sans", size: 10 },
            callback: function (val) {
              return currencySymbol + (val >= 1000 ? (val / 1000).toFixed(0) + "k" : val);
            },
          },
        },
      },
    },
  });
}

function initCategoryDonutChart(categoryBreakdown) {
  const ctx = document.getElementById("categoryDonutChart");
  if (!ctx) return;

  const labels = Object.keys(categoryBreakdown);
  const data = Object.values(categoryBreakdown);
  const bgColors = labels.map((l) => (CATEGORY_COLORS[l] ? CATEGORY_COLORS[l].line : "#38BDF8"));

  if (categoryDonutChartInstance) {
    categoryDonutChartInstance.destroy();
  }

  categoryDonutChartInstance = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: labels,
      datasets: [
        {
          data: data,
          backgroundColor: bgColors,
          borderColor: "#0F172A",
          borderWidth: 3,
          hoverOffset: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            color: "#94A3B8",
            font: { family: "Plus Jakarta Sans", size: 10, weight: "500" },
            boxWidth: 8,
            boxHeight: 8,
            usePointStyle: true,
          },
        },
        tooltip: {
          backgroundColor: "#0F172A",
          titleColor: "#F8FAFC",
          bodyColor: "#94A3B8",
          borderColor: "rgba(255, 255, 255, 0.1)",
          borderWidth: 1,
          padding: 10,
        },
      },
      cutout: "68%",
    },
  });
}

function renderModalProductChart(historyPoints, currencySymbol = "₹") {
  const ctx = document.getElementById("modalProductChart");
  if (!ctx) return;

  const labels = historyPoints.map((p) => p.month_label);
  const prices = historyPoints.map((p) => p.price);
  const minPrice = Math.min(...prices);

  // Point styling: Highlight the lowest price point in gold/emerald
  const pointBg = prices.map((p) => (p === minPrice ? "#F59E0B" : "#06B6D4"));
  const pointRad = prices.map((p) => (p === minPrice ? 7 : 4));

  if (modalProductChartInstance) {
    modalProductChartInstance.destroy();
  }

  modalProductChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Price History (22 Months)",
          data: prices,
          borderColor: "#06B6D4",
          backgroundColor: "rgba(6, 182, 212, 0.12)",
          borderWidth: 3,
          tension: 0.3,
          fill: true,
          pointBackgroundColor: pointBg,
          pointBorderColor: "#0F172A",
          pointBorderWidth: 2,
          pointRadius: pointRad,
          pointHoverRadius: 8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0F172A",
          titleColor: "#F8FAFC",
          bodyColor: "#94A3B8",
          borderColor: "rgba(255, 255, 255, 0.1)",
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: function (context) {
              const idx = context.dataIndex;
              const point = historyPoints[idx];
              let str = `Price: ${currencySymbol}${context.parsed.y.toLocaleString()}`;
              if (point.sale_tag) {
                str += ` [${point.sale_tag}]`;
              }
              if (context.parsed.y === minPrice) {
                str += ` (★ 22-Mo Lowest)`;
              }
              return str;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: {
            color: "#64748B",
            font: { family: "Plus Jakarta Sans", size: 10 },
            autoSkip: true,
            maxTicksLimit: 11,
          },
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: {
            color: "#64748B",
            font: { family: "Plus Jakarta Sans", size: 10 },
            callback: function (val) {
              return currencySymbol + val.toLocaleString();
            },
          },
        },
      },
    },
  });
}
