from datetime import datetime
from typing import Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import STATIC_DIR, CURRENCY_SYMBOL
from app.database import (
    get_all_products, get_product_by_asin,
    get_price_history_for_asin, get_product_statistics
)
from app.history_engine import seed_database_if_empty, get_22_month_labels
from app.scraper import scrape_asin_details, scrape_all_asins
from app.excel_exporter import export_excel_to_file, export_excel_to_bytes

app = FastAPI(
    title="Acer Amazon Price Tracker & Intelligence API",
    description="Automated price tracking, 22-month historical analysis, and Excel exports for 25 Acer Amazon products.",
    version="1.0.0"
)

# Enable CORS with exposed headers for download filenames
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Type", "Content-Length"],
)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    # Prevent aggressive Chrome localhost asset caching
    if request.url.path.startswith("/js") or request.url.path.startswith("/css") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.on_event("startup")
def on_startup():
    """Initialize database and seed 25 Acer ASINs on server startup."""
    seed_database_if_empty()

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/products")
def list_products(category: Optional[str] = None, search: Optional[str] = None):
    """Returns list of tracked products with current stats and price metrics."""
    products = get_all_products()
    results = []
    
    for p in products:
        if category and p["category"].lower() != category.lower():
            continue
        if search:
            q = search.lower()
            if q not in p["title"].lower() and q not in p["asin"].lower() and q not in p["category"].lower():
                continue
                
        stats = get_product_statistics(p["asin"])
        p_dict = dict(p)
        p_dict["stats"] = stats
        results.append(p_dict)
        
    return {
        "total": len(results),
        "currency": CURRENCY_SYMBOL,
        "products": results
    }

@app.get("/api/products/{asin}")
def get_product_details(asin: str):
    """Returns single product details, statistics, and full 22-month timeline."""
    product = get_product_by_asin(asin)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    history = get_price_history_for_asin(asin)
    stats = get_product_statistics(asin)
    
    return {
        "product": product,
        "stats": stats,
        "history": history,
        "currency": CURRENCY_SYMBOL
    }

@app.get("/api/stats")
def get_portfolio_stats():
    """Calculates overall statistics and KPI aggregations across all tracked products."""
    products = get_all_products()
    if not products:
        return {}
        
    total_products = len(products)
    total_mrp = sum(p["mrp"] for p in products)
    total_current = sum(p["current_price"] for p in products)
    avg_discount_pct = round(((total_mrp - total_current) / total_mrp) * 100, 1) if total_mrp > 0 else 0
    
    in_stock_count = sum(1 for p in products if "in stock" in p["stock_status"].lower())
    out_of_stock_count = total_products - in_stock_count
    
    atl_deals_count = 0
    near_atl_count = 0
    price_drops = []
    
    category_breakdown = {}
    for p in products:
        cat = p["category"]
        category_breakdown[cat] = category_breakdown.get(cat, 0) + 1
        
        stats = get_product_statistics(p["asin"])
        if stats.get("is_atl"):
            atl_deals_count += 1
        elif stats.get("is_near_atl"):
            near_atl_count += 1
            
        # 30-day price comparison (diff from previous month)
        hist = get_price_history_for_asin(p["asin"])
        if len(hist) >= 2:
            prev_price = hist[-2]["price"]
            curr_price = p["current_price"]
            drop_amount = prev_price - curr_price
            drop_pct = round((drop_amount / prev_price) * 100, 1) if prev_price > 0 else 0
            if drop_amount > 0:
                price_drops.append({
                    "asin": p["asin"],
                    "title": p["title"],
                    "category": p["category"],
                    "previous_price": prev_price,
                    "current_price": curr_price,
                    "drop_amount": round(drop_amount, 2),
                    "drop_pct": drop_pct
                })

    price_drops.sort(key=lambda x: x["drop_pct"], reverse=True)
    top_drop = price_drops[0] if price_drops else None

    # Category monthly trend series
    month_labels = get_22_month_labels()
    category_trends = {}
    for cat in category_breakdown.keys():
        cat_asins = [p["asin"] for p in products if p["category"] == cat]
        monthly_avgs = []
        for m in month_labels:
            prices = []
            for asin in cat_asins:
                hist = get_price_history_for_asin(asin)
                for h in hist:
                    if h["month_label"] == m:
                        prices.append(h["price"])
                        break
            avg_p = (sum(prices) / len(prices)) if prices else 0
            monthly_avgs.append(round(avg_p, 2))
        category_trends[cat] = monthly_avgs

    return {
        "total_products": total_products,
        "total_portfolio_value": round(total_current, 2),
        "total_mrp_value": round(total_mrp, 2),
        "avg_discount_pct": avg_discount_pct,
        "in_stock_count": in_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "atl_deals_count": atl_deals_count,
        "near_atl_count": near_atl_count,
        "top_price_drop": top_drop,
        "category_breakdown": category_breakdown,
        "month_labels": month_labels,
        "category_trends": category_trends,
        "currency": CURRENCY_SYMBOL
    }

@app.post("/api/scrape")
def trigger_scrape(background_tasks: BackgroundTasks, asin: Optional[str] = Query(None)):
    """Triggers an Amazon crawl for a single ASIN or all tracked products."""
    if asin:
        res = scrape_asin_details(asin)
        return {"status": "completed", "result": res}
    else:
        # Run batch crawl in background
        background_tasks.add_task(scrape_all_asins)
        return {
            "status": "queued",
            "message": "Full 25 ASIN crawl started in background. Refresh dashboard in a moment."
        }

@app.get("/api/export/excel")
def download_excel_export():
    """Generates and returns the formatted 22-Month Acer Intelligence Excel file."""
    excel_path = export_excel_to_file()
    filename = f"Acer_Amazon_Price_Tracker_22Months_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    return FileResponse(
        path=excel_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Mount static frontend
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
