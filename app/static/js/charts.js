/**
 * Executive Monotone Visual Analytics & Chart.js Controllers
 */

let timelineChartInstance = null;
let modalProductChartInstance = null;

// Executive Muted Palette
const MONOTONE_PALETTE = [
  { line: "#E2E8F0", bg: "rgba(226, 232, 240, 0.08)" }, // Silver
  { line: "#38BDF8", bg: "rgba(56, 189, 248, 0.08)" },  // Steel Sky
  { line: "#94A3B8", bg: "rgba(148, 163, 184, 0.08)" }, // Slate Gray
  { line: "#818CF8", bg: "rgba(129, 140, 248, 0.08)" }, // Indigo Slate
  { line: "#34D399", bg: "rgba(52, 211, 153, 0.08)" },  // Muted Mint
  { line: "#F59E0B", bg: "rgba(245, 158, 11, 0.08)" },  // Bronze Amber
];

function renderTimelineChart(monthLabels, categoryTrends, currencySymbol = "₹") {
  const ctx = document.getElementById("timelineChart");
  if (!ctx) return;

  const categories = Object.keys(categoryTrends);
  const datasets = categories.map((cat, idx) => {
    const style = MONOTONE_PALETTE[idx % MONOTONE_PALETTE.length];
    return {
      label: cat,
      data: categoryTrends[cat],
      borderColor: style.line,
      backgroundColor: style.bg,
      borderWidth: 2,
      tension: 0.3,
      pointRadius: 2.5,
      pointHoverRadius: 5,
      pointBackgroundColor: style.line,
      pointBorderColor: "#090D16",
      pointBorderWidth: 1.5,
      fill: false,
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
            color: "#94A3B8",
            font: { family: "Inter", size: 11, weight: "500" },
            usePointStyle: true,
            boxWidth: 6,
            boxHeight: 6,
          },
        },
        tooltip: {
          backgroundColor: "#141B2A",
          titleColor: "#F8FAFC",
          bodyColor: "#CBD5E1",
          borderColor: "#28354A",
          borderWidth: 1,
          padding: 10,
          boxPadding: 4,
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
          grid: { color: "rgba(255, 255, 255, 0.03)" },
          ticks: {
            color: "#64748B",
            font: { family: "Inter", size: 10 },
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 11,
          },
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.03)" },
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

function renderProductDetailModalChart(historyPoints, currencySymbol = "₹") {
  const ctx = document.getElementById("modalProductHistoryChart");
  if (!ctx) return;

  const labels = historyPoints.map((h) => h.month_label);
  const prices = historyPoints.map((h) => h.price);
  const minPrice = Math.min(...prices);

  const pointBackgrounds = historyPoints.map((h) =>
    h.price === minPrice ? "#10B981" : (h.is_sale ? "#38BDF8" : "#E2E8F0")
  );
  const pointRadii = historyPoints.map((h) => (h.price === minPrice ? 5 : 2.5));

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
          borderColor: "#E2E8F0",
          backgroundColor: "rgba(226, 232, 240, 0.05)",
          borderWidth: 2,
          tension: 0.25,
          pointBackgroundColor: pointBackgrounds,
          pointBorderColor: "#090D16",
          pointBorderWidth: 1.5,
          pointRadius: pointRadii,
          pointHoverRadius: 6,
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
          backgroundColor: "#141B2A",
          titleColor: "#F8FAFC",
          bodyColor: "#CBD5E1",
          borderColor: "#28354A",
          borderWidth: 1,
          padding: 10,
          callbacks: {
            label: function (context) {
              const h = historyPoints[context.dataIndex];
              let str = "Price: " + currencySymbol + h.price.toLocaleString();
              if (h.price === minPrice) str += " ★ ALL-TIME LOW";
              if (h.sale_tag) str += ` (${h.sale_tag})`;
              return str;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.03)" },
          ticks: { color: "#64748B", font: { size: 10 }, maxTicksLimit: 11 },
        },
        y: {
          grid: { color: "rgba(255, 255, 255, 0.03)" },
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
