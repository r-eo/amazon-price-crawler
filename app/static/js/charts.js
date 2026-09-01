/**
 * Cyber & Slate Visual Analytics & Chart.js Controllers v3.0
 * Multi-Color Palette: Indigo (#6366F1), Emerald (#10B981), Amber (#F59E0B), Cyan (#06B6D4), Purple (#A855F7), Rose (#F43F5E)
 */

let timelineChartInstance = null;
let modalProductChartInstance = null;

const CYBER_PALETTE = [
  { line: "#6366F1", bg: "rgba(99, 102, 241, 0.12)" }, // Royal Indigo
  { line: "#10B981", bg: "rgba(16, 185, 129, 0.12)" }, // Acer Emerald
  { line: "#F59E0B", bg: "rgba(245, 158, 11, 0.12)" }, // Sunset Amber
  { line: "#06B6D4", bg: "rgba(6, 182, 212, 0.12)" },  // Cyber Cyan
  { line: "#A855F7", bg: "rgba(168, 85, 247, 0.12)" }, // Electric Purple
  { line: "#F43F5E", bg: "rgba(244, 63, 94, 0.12)" },  // Coral Rose
  { line: "#38BDF8", bg: "rgba(56, 189, 248, 0.12)" }, // Sky Blue
  { line: "#84CC16", bg: "rgba(132, 204, 22, 0.12)" }, // Lime
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
      borderWidth: 2.5,
      tension: 0.35,
      pointRadius: 3,
      pointHoverRadius: 6,
      pointBackgroundColor: style.line,
      pointBorderColor: "#0F172A",
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
            color: "#CBD5E1",
            font: { family: "Inter", size: 11, weight: "600" },
            usePointStyle: true,
            boxWidth: 7,
            boxHeight: 7,
            padding: 14,
          },
        },
        tooltip: {
          backgroundColor: "#151E33",
          titleColor: "#F8FAFC",
          bodyColor: "#CBD5E1",
          borderColor: "#22304D",
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
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: {
            color: "#94A3B8",
            font: { family: "Inter", size: 10 },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 11,
          },
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: {
            color: "#94A3B8",
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
            labels: { color: "#CBD5E1", font: { family: "Inter", size: 11, weight: "600" } }
          },
          tooltip: {
            backgroundColor: "#151E33",
            titleColor: "#F8FAFC",
            bodyColor: "#CBD5E1",
            borderColor: "#22304D",
            borderWidth: 1,
            padding: 12,
            callbacks: {
              label: (ctx) => `Portfolio Avg: ${currencySymbol}${Math.round(ctx.parsed.y).toLocaleString()}`
            }
          }
        },
        scales: {
          x: { grid: { color: "rgba(255, 255, 255, 0.05)" }, ticks: { color: "#94A3B8" } },
          y: {
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: {
              color: "#94A3B8",
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
          borderColor: "#6366F1",
          backgroundColor: "rgba(99, 102, 241, 0.12)",
          borderWidth: 2.5,
          tension: 0.3,
          pointBackgroundColor: pointBackgrounds,
          pointBorderColor: "#0F172A",
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
          backgroundColor: "#151E33",
          titleColor: "#F8FAFC",
          bodyColor: "#CBD5E1",
          borderColor: "#22304D",
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
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#94A3B8", font: { size: 10 }, maxTicksLimit: 11 },
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: {
            color: "#94A3B8",
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
