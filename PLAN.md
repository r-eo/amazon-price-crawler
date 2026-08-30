# Acer Amazon Price Intelligence & Dual-Dashboard Platform — Blueprint & Roadmap

## 1. Executive Overview

This project is a dedicated price intelligence, crawling, and historical analytics platform featuring **two specialized dashboards**:
1. **🖥️ Acer Monitors Dashboard:** Dedicated tracking, KPIs, 22-month price trajectory, and independent dynamic/daily Excel reports for Acer monitors.
2. **📦 Other Products Dashboard:** Dedicated tracking for other Amazon product ASINs (laptops, desktops, projectors, accessories) with independent analytics and Excel reports.
3. **🌐 All Portfolio View:** Consolidated aggregate view across all tracked inventory.

### Key Capabilities:
- **Executive Monotone Design System:** Modern corporate dark palette (`#090D16`, `#141B2A`, `#1E293B`) with high-contrast typography, clear tabular layout, and subdued status badges.
- **22-Month Historical Price Matrix:** Full monthly price tracking and seasonal fluctuation analysis (accounting for Prime Day, Diwali / Great Indian Festival, Black Friday, Republic Day, and natural depreciation).
- **Dynamic & Daily Excel Generation (.xlsx):** Generates separate multi-sheet Excel reports (`Acer_Monitors_Price_Tracker.xlsx` and `Other_Products_Price_Tracker.xlsx`) on automated daily schedules (10:00 AM) and **dynamically re-generates whenever live price fluctuations are detected**.
- **Interactive ASIN Ingestion:** Built-in modal and API endpoints to easily add single ASINs or batch import multi-line lists of ASINs directly to either dashboard.
- **Amazon Live Web Scraper:** Anti-bot resistant scraping engine using `curl_cffi` (Chrome TLS fingerprinting) and fallback to `requests` + `BeautifulSoup4`.
- **Cloud-Ready Architecture:** Zero-configuration SQLite local run, easily deployable to **Render** or **Vercel**.

---

## 2. System Architecture

```
                          ┌─────────────────────────────────────┐
                          │   Professional Monotone Dashboard   │
                          │   (Slate / Charcoal / Zinc Theme)   │
                          └──────┬───────────────────────┬──────┘
                                 │                       │
              ┌──────────────────┴──┐                 ┌──┴──────────────────┐
              │ Acer Monitors Tab   │                 │ Other Products Tab  │
              │ - Dedicated KPIs    │                 │ - Dedicated KPIs    │
              │ - Monitor 22-Mo Chart                 │ - Other 22-Mo Chart │
              │ - Live Product Grid │                 │ - Live Product Grid │
              │ - Add ASIN Modal    │                 │ - Add ASIN Modal    │
              └──────────┬──────────┘                 └──────────┬──────────┘
                         │                                       │
                         ▼                                       ▼
        ┌────────────────────────────────┐     ┌────────────────────────────────┐
        │ Acer Monitors Excel Generator  │     │ Other Products Excel Generator │
        │ - Daily Scheduled Sync (10 AM) │     │ - Daily Scheduled Sync (10 AM) │
        │ - Dynamic on Price Fluctuation │     │ - Dynamic on Price Fluctuation │
        └────────────────────────────────┘     └────────────────────────────────┘
```

---

## 3. Product Groups & Dynamic ASIN Ingestion

### Group A: Acer Monitors (`acer_monitors`)
- Tracks user-provided and verified Acer monitor ASINs.
- Features dedicated statistics (Average Monitor Discount, Monitor ATL Deals, Stock Health).
- Produces `Acer_Monitors_Price_Tracker.xlsx`.

### Group B: Other Products (`other_products`)
- Tracks user-provided laptops, desktops, and other Amazon ASINs.
- Produces `Other_Products_Price_Tracker.xlsx`.

---

## 4. Excel Schema (Monotone Executive Styling)

Each generated workbook features 3 dedicated tabs:

### Sheet 1: `Product_Overview`
- **Columns:** ASIN, Product Title, Category, Today's Price (`₹`), MRP (`₹`), Discount %, Stock Status, 22-Mo Lowest Price (`₹`), 22-Mo Highest Price (`₹`), 22-Mo Avg Price (`₹`), % Off ATH, Rating, Amazon Link.
- **Styling:** Charcoal/Slate headers (`#1E293B`), thin borders (`#CBD5E1`), alternating rows (`#F8FAFC`), subtle muted mint highlights on All-Time Low deals, and direct Amazon product links.

### Sheet 2: `22_Months_Price_History`
- **Columns:** ASIN, Product Title, Category, Baseline MRP, 22 Monthly Columns (e.g., Nov 2024 to Aug 2026), 22-Mo Min, 22-Mo Max.
- **Styling:** Highlights the specific month when the lowest historical price occurred.

### Sheet 3: `Monthly_Statistics`
- **Columns:** Category / Scope, Metric, 22 Monthly Average Price Benchmarks + Overall Portfolio Benchmark row.

---

## 5. Deployment Guides

### A. Local Run
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start server
python run.py
# Access dashboard at: http://127.0.0.1:8000
```

### B. Deploying to Render.com (Web Service)
1. Push repository to GitHub / GitLab.
2. In [Render Dashboard](https://dashboard.render.com), click **New +** -> **Web Service**.
3. Render detects `render.yaml` or you can manually set:
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Click **Deploy**.

### C. Deploying to Vercel (Serverless)
1. Install Vercel CLI: `npm i -g vercel` or link GitHub repo in [Vercel Dashboard](https://vercel.com).
2. The included `vercel.json` routes all requests to `app/main.py`.
3. Run `vercel deploy` or push to main branch.
