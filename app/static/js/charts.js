/**
 * Cyber & Slate Visual Analytics & Chart.js Controllers v3.0
 * Multi-Color Palette: Indigo (#6366F1), Emerald (#10B981), Amber (#F59E0B), Cyan (#06B6D4), Purple (#A855F7), Rose (#F43F5E)
 */

let timelineChartInstance = null;
let modalProductChartInstance = null;

const CYBER_PALETTE = [
  { line: "#4F46E5", bg: "rgba(79, 70, 229, 0.08)" }, // Astra Indigo
  { line: "#059669", bg: "rgba(5, 150, 105, 0.08)" }, // Emerald
  { line: "#D97706", bg: "rgba(217, 119, 6, 0.08)" }, // Amber
  { line: "#0284C7", bg: "rgba(2, 132, 199, 0.08)" },  // Sky/Cyan
  { line: "#9333EA", bg: "rgba(147, 51, 234, 0.08)" }, // Purple
  { line: "#E11D48", bg: "rgba(225, 29, 72, 0.08)" },  // Rose
  { line: "#0D9488", bg: "rgba(13, 148, 136, 0.08)" }, // Teal
  { line: "#65A30D", bg: "rgba(101, 163, 13, 0.08)" }, // Lime
];

function renderTimelineChart(monthLabels, categoryTrends, currencySymbol = "₹") {
  const ctx = document.getElementById("timelineChart");
  if (!ctx) return;

  const categories = Object.keys(categoryTrends);
  const datasets = categories.map((cat, idx) => {
    const style = CYBER_PALETTE[idx % CYBER_PALETTE.length];
    return {
      label: cat,
      data: categoryTrends[cat],
      borderColor: style.line,
      backgroundColor: style.bg,
      borderWidth: 2.2,
      tension: 0.35,
      pointRadius: 3,
      pointHoverRadius: 6,
      pointBackgroundColor: style.line,
      pointBorderColor: "#FFFFFF",
      pointBorderWidth: 1.5,
      fill: true,
    };
  });

  if (timelineChartInstance) {
    timelineChartInstance.destroy();
  }

  timelineChartInstance = new Chart(ctx, {
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
          align: "end",
          labels: {
            color: "#334155",
            font: { family: "Inter", size: 11, weight: "600" },
            usePointStyle: true,
            boxWidth: 7,
            boxHeight: 7,
            padding: 14,
          },
        },
        tooltip: {
          backgroundColor: "#FFFFFF",
          titleColor: "#0F172A",
          bodyColor: "#334155",
          borderColor: "#E2E8F0",
          borderWidth: 1,
          padding: 12,
          boxPadding: 6,
          usePointStyle: true,
          callbacks: {
            label: function (context) {
              let label = context.dataset.label || "";
              if (label) label += ": ";
              if (context.parsed.y !== null) {
                label += currencySymbol + Math.round(context.parsed.y).toLocaleString();
              }
              return label;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#F1F5F9" },
          ticks: {
            color: "#64748B",
            font: { family: "Inter", size: 10 },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 11,
          },
        },
        y: {
          grid: { color: "#F1F5F9" },
          ticks: {
            color: "#64748B",
            font: { family: "Inter", size: 10 },
            callback: function (val) {
              return currencySymbol + (val >= 1000 ? (val / 1000).toFixed(0) + "k" : val);
            },
          },
        },
      },
    },
  });
}

function updateChartMetric() {
  const metric = document.getElementById("selectChartMetric")?.value;
  if (!dashboardStats.month_labels) return;

  if (metric === "portfolio") {
    // Render single weighted average portfolio line
    const ctx = document.getElementById("timelineChart");
    if (!ctx) return;

    const monthLabels = dashboardStats.month_labels;
    const catTrends = dashboardStats.category_trends || {};
    const categories = Object.keys(catTrends);

    const portfolioAvg = monthLabels.map((_, mIdx) => {
      let sum = 0, count = 0;
      categories.forEach(cat => {
        const val = catTrends[cat][mIdx];
        if (val) { sum += val; count++; }
      });
      return count > 0 ? Math.round(sum / count) : 0;
    });

    if (timelineChartInstance) timelineChartInstance.destroy();

    timelineChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: monthLabels,
        datasets: [{
          label: "Overall Portfolio Benchmark",
          data: portfolioAvg,
          borderColor: "#6366F1",
          backgroundColor: "rgba(99, 102, 241, 0.18)",
          borderWidth: 3,
          tension: 0.35,
          pointRadius: 4,
          pointBackgroundColor: "#6366F1",
          pointBorderColor: "#FFFFFF",
          pointBorderWidth: 2,
          fill: true,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "top",
            align: "end",
            labels: { color: "#334155", font: { family: "Inter", size: 11, weight: "600" } }
          },
          tooltip: {
            backgroundColor: "#FFFFFF",
            titleColor: "#0F172A",
            bodyColor: "#334155",
            borderColor: "#E2E8F0",
            borderWidth: 1,
            padding: 12,
            callbacks: {
              label: (ctx) => `Portfolio Avg: ${currencySymbol}${Math.round(ctx.parsed.y).toLocaleString()}`
            }
          }
        },
        scales: {
          x: { grid: { color: "#F1F5F9" }, ticks: { color: "#64748B", font: { family: "Inter", size: 10 } } },
          y: {
            grid: { color: "#F1F5F9" },
            ticks: {
              color: "#64748B",
              font: { family: "Inter", size: 10 },
              callback: (val) => currencySymbol + (val >= 1000 ? (val / 1000).toFixed(0) + "k" : val)
            }
          }
        }
      }
    });
  } else {
    renderTimelineChart(dashboardStats.month_labels, dashboardStats.category_trends, currencySymbol);
  }
}

function renderProductDetailModalChart(historyPoints, currencySymbol = "₹") {
  const ctx = document.getElementById("modalProductHistoryChart");
  if (!ctx) return;

  const labels = historyPoints.map((h) => h.month_label);
  const prices = historyPoints.map((h) => h.price);
  const minPrice = Math.min(...prices);

  const pointBackgrounds = historyPoints.map((h) =>
    h.price === minPrice ? "#10B981" : (h.is_sale ? "#F59E0B" : "#6366F1")
  );
  const pointRadii = historyPoints.map((h) => (h.price === minPrice ? 6 : (h.is_sale ? 4 : 3)));

  if (modalProductChartInstance) {
    modalProductChartInstance.destroy();
  }

  modalProductChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Price History",
          data: prices,
          borderColor: "#4F46E5",
          backgroundColor: "rgba(79, 70, 229, 0.08)",
          borderWidth: 2.2,
          tension: 0.3,
          pointBackgroundColor: pointBackgrounds,
          pointBorderColor: "#FFFFFF",
          pointBorderWidth: 2,
          pointRadius: pointRadii,
          pointHoverRadius: 7,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#FFFFFF",
          titleColor: "#0F172A",
          bodyColor: "#334155",
          borderColor: "#E2E8F0",
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: function (context) {
              const h = historyPoints[context.dataIndex];
              let str = "Price: " + currencySymbol + Math.round(h.price).toLocaleString();
              if (h.price === minPrice) str += " ★ ALL-TIME LOW";
              if (h.sale_tag) str += ` (${h.sale_tag})`;
              return str;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#F1F5F9" },
          ticks: { color: "#64748B", font: { size: 10 }, maxTicksLimit: 11 },
        },
        y: {
          grid: { color: "#F1F5F9" },
          ticks: {
            color: "#64748B",
            font: { size: 10 },
            callback: function (val) {
              return currencySymbol + (val >= 1000 ? (val / 1000).toFixed(0) + "k" : val);
            },
          },
        },
      },
    },
  });
}
