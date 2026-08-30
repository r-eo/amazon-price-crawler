import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    STATIC_DIR, CURRENCY_SYMBOL,
    GROUP_ACER_MONITORS, GROUP_OTHER_PRODUCTS, GROUP_ALL,
    EXCEL_MONITORS_FILENAME, EXCEL_OTHER_FILENAME, EXCEL_ALL_FILENAME
)
from app.database import (
    get_all_products, get_products_by_group, get_product_by_asin,
    get_price_history_for_asin, get_all_price_history, get_product_statistics,
    delete_product_by_asin
)
from app.history_engine import seed_database_if_empty, get_22_month_labels
from app.scraper import scrape_asin_details, scrape_all_asins
from app.excel_exporter import (
    export_monitors_excel, export_other_products_excel,
    export_all_portfolio_excel, export_excel_by_group
)

logger = logging.getLogger("tracker_app")

# Automated Daily Crawl Schedule (Default: 10:00 AM)
DAILY_SCHEDULE_HOUR = int(os.getenv("DAILY_SCHEDULE_HOUR", 10))
DAILY_SCHEDULE_MINUTE = int(os.getenv("DAILY_SCHEDULE_MINUTE", 0))

async def daily_10am_scheduler_loop():
    """
    Background worker that runs automatically every day at 10:00 AM to crawl
    all Acer Monitors and Other Products and pre-generate the fresh daily 22-Month Excel reports.
    """
    logger.info(f"Daily automated scheduler active: target sync at {DAILY_SCHEDULE_HOUR:02d}:{DAILY_SCHEDULE_MINUTE:02d}.")
    while True:
        try:
            now = datetime.now()
            target_time = now.replace(hour=DAILY_SCHEDULE_HOUR, minute=DAILY_SCHEDULE_MINUTE, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
                
            delay_seconds = (target_time - now).total_seconds()
            logger.info(f"Daily scheduler: next automated run at {target_time.strftime('%Y-%m-%d %H:%M:%S')} (in {int(delay_seconds//60)} minutes).")
            
            await asyncio.sleep(delay_seconds)
            
            logger.info("Executing scheduled 10:00 AM daily Amazon crawl & dual Excel generation...")
            await asyncio.to_thread(scrape_all_asins, GROUP_ACER_MONITORS)
            await asyncio.to_thread(scrape_all_asins, GROUP_OTHER_PRODUCTS)
            await asyncio.to_thread(export_monitors_excel)
            await asyncio.to_thread(export_other_products_excel)
            await asyncio.to_thread(export_all_portfolio_excel)
            logger.info("Scheduled 10:00 AM daily crawl & Excel generation completed successfully.")
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in daily scheduler: {e}")
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes database on startup and starts the 10:00 AM daily background worker."""
    seed_database_if_empty()
    scheduler_task = asyncio.create_task(daily_10am_scheduler_loop())
    yield
    scheduler_task.cancel()

app = FastAPI(
    title="Acer Amazon Price Intelligence Platform",
    description="Dedicated intelligence dashboards for Acer Monitors and Other Amazon Products with dynamic/daily Excel exports.",
    version="2.0.0",
    lifespan=lifespan
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
    if request.url.path.startswith("/js") or request.url.path.startswith("/css") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.on_event("startup")
def on_startup():
    seed_database_if_empty()

# Pydantic models for ASIN import
class AddAsinRequest(BaseModel):
    asin: str
    group: str = GROUP_ACER_MONITORS
    title: Optional[str] = None
    category: Optional[str] = None
    mrp: Optional[float] = None

class BatchImportRequest(BaseModel):
    asins: List[str]
    group: str = GROUP_ACER_MONITORS
    category: Optional[str] = None

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "version": "2.0.0", "timestamp": datetime.now().isoformat()}

@app.get("/api/scheduler/status")
def scheduler_status():
    """Returns status and next execution time of the automated daily 10:00 AM sync."""
    now = datetime.now()
    target_time = now.replace(hour=DAILY_SCHEDULE_HOUR, minute=DAILY_SCHEDULE_MINUTE, second=0, microsecond=0)
    if target_time <= now:
        target_time += timedelta(days=1)
    diff = target_time - now
    hours, remainder = divmod(int(diff.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    
    return {
        "daily_schedule": f"Every day at {DAILY_SCHEDULE_HOUR:02d}:{DAILY_SCHEDULE_MINUTE:02d}",
        "next_run_at": target_time.strftime("%Y-%m-%d %H:%M:%S"),
        "time_remaining": f"{hours}h {minutes}m",
        "excel_auto_updates": True
    }

@app.get("/api/products")
def list_products(
    group: Optional[str] = Query(None),
    category: Optional[str] = None,
    search: Optional[str] = None
):
    """Returns list of tracked products filtered by group, category, or search query."""
    products = get_products_by_group(group)
    if not products:
        seed_database_if_empty()
        products = get_products_by_group(group)

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
        "group": group or "all",
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

@app.post("/api/products/add-asin")
def add_single_asin(payload: AddAsinRequest, background_tasks: BackgroundTasks):
    """Adds a new ASIN to a specific dashboard, triggers immediate live crawl & timeline generation."""
    clean_asin = payload.asin.strip().upper()
    if not clean_asin or len(clean_asin) != 10:
        raise HTTPException(status_code=400, detail="Invalid ASIN format (must be 10 alphanumeric characters).")
        
    res = scrape_asin_details(
        asin=clean_asin,
        group=payload.group,
        category=payload.category,
        custom_title=payload.title,
        custom_mrp=payload.mrp
    )
    
    # Trigger dynamic Excel re-export for this group in background
    background_tasks.add_task(export_excel_by_group, payload.group)
    
    return {
        "status": "success",
        "message": f"ASIN {clean_asin} successfully registered in {payload.group}.",
        "product": res.get("data")
    }

@app.post("/api/products/batch-import")
def batch_import_asins(payload: BatchImportRequest, background_tasks: BackgroundTasks):
    """Batch imports multiple ASINs into a selected dashboard."""
    imported = []
    for raw_asin in payload.asins:
        clean = raw_asin.strip().upper()
        if clean and len(clean) == 10:
            res = scrape_asin_details(asin=clean, group=payload.group, category=payload.category)
            imported.append(clean)
            
    background_tasks.add_task(export_excel_by_group, payload.group)
    return {
        "status": "success",
        "imported_count": len(imported),
        "asins": imported,
        "group": payload.group
    }

@app.delete("/api/products/{asin}")
def delete_product(asin: str, background_tasks: BackgroundTasks):
    """Deletes an ASIN and its history from the platform."""
    clean_asin = asin.strip().upper()
    prod = get_product_by_asin(clean_asin)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
        
    grp = prod.get("product_group", GROUP_ACER_MONITORS)
    delete_product_by_asin(clean_asin)
    background_tasks.add_task(export_excel_by_group, grp)
    
    return {"status": "success", "message": f"Deleted ASIN {clean_asin}."}

@app.get("/api/stats")
def get_dashboard_stats(group: Optional[str] = Query(None)):
    """Calculates overall statistics and KPI aggregations for the requested dashboard group."""
    products = get_products_by_group(group)
    if not products:
        seed_database_if_empty()
        products = get_products_by_group(group)
    if not products:
        return {
            "total_products": 0,
            "total_portfolio_value": 0,
            "total_mrp_value": 0,
            "avg_discount_pct": 0,
            "in_stock_count": 0,
            "out_of_stock_count": 0,
            "atl_deals_count": 0,
            "near_atl_count": 0,
            "category_breakdown": {},
            "month_labels": get_22_month_labels(),
            "category_trends": {},
            "currency": CURRENCY_SYMBOL
        }
        
    total_products = len(products)
    total_mrp = sum(p["mrp"] for p in products)
    total_current = sum(p["current_price"] for p in products)
    avg_discount_pct = round(((total_mrp - total_current) / total_mrp) * 100, 1) if total_mrp > 0 else 0
    
    in_stock_count = sum(1 for p in products if "in stock" in p["stock_status"].lower())
    out_of_stock_count = total_products - in_stock_count
    
    all_history = get_all_price_history()
    history_by_asin = {}
    for h in all_history:
        history_by_asin.setdefault(h["asin"], []).append(h)
    
    atl_deals_count = 0
    near_atl_count = 0
    price_drops = []
    category_breakdown = {}
    
    for p in products:
        asin = p["asin"]
        cat = p["category"]
        curr_price = p["current_price"]
        category_breakdown[cat] = category_breakdown.get(cat, 0) + 1
        
        hist = history_by_asin.get(asin, [])
        if hist:
            prices = [h["price"] for h in hist]
            min_p = min(prices)
            if curr_price <= (min_p * 1.01):
                atl_deals_count += 1
            elif curr_price <= (min_p * 1.05):
                near_atl_count += 1
                
            if len(hist) >= 2:
                prev_price = hist[-2]["price"]
                drop_amount = prev_price - curr_price
                drop_pct = round((drop_amount / prev_price) * 100, 1) if prev_price > 0 else 0
                if drop_amount > 0:
                    price_drops.append({
                        "asin": asin,
                        "title": p["title"],
                        "category": cat,
                        "previous_price": prev_price,
                        "current_price": curr_price,
                        "drop_amount": round(drop_amount, 2),
                        "drop_pct": drop_pct
                    })

    price_drops.sort(key=lambda x: x["drop_pct"], reverse=True)
    top_drop = price_drops[0] if price_drops else None

    # Category monthly trend trajectories
    month_labels = get_22_month_labels()
    category_trends = {}
    cat_month_map = {}
    for p in products:
        asin = p["asin"]
        cat = p["category"]
        hist = history_by_asin.get(asin, [])
        for h in hist:
            cat_month_map.setdefault((cat, h["month_label"]), []).append(h["price"])

    for cat in category_breakdown.keys():
        monthly_avgs = []
        for m in month_labels:
            prices = cat_month_map.get((cat, m), [])
            avg_p = (sum(prices) / len(prices)) if prices else 0
            monthly_avgs.append(round(avg_p, 2))
        category_trends[cat] = monthly_avgs

    return {
        "total_products": total_products,
        "group": group or "all",
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
def trigger_scrape(
    background_tasks: BackgroundTasks,
    asin: Optional[str] = Query(None),
    group: Optional[str] = Query(None)
):
    """Triggers an Amazon crawl for a single ASIN or a specific dashboard group."""
    if asin:
        res = scrape_asin_details(asin)
        # Auto update Excel for that product's group
        prod = get_product_by_asin(asin)
        if prod:
            background_tasks.add_task(export_excel_by_group, prod.get("product_group", GROUP_ACER_MONITORS))
        return {"status": "completed", "result": res}
    else:
        background_tasks.add_task(scrape_all_asins, group)
        grp_name = "Acer Monitors" if group == GROUP_ACER_MONITORS else ("Other Products" if group == GROUP_OTHER_PRODUCTS else "All Products")
        return {
            "status": "queued",
            "message": f"Live Amazon crawl started for {grp_name}. Dashboard will update dynamically."
        }

@app.get("/api/export/excel")
def download_excel_export(group: Optional[str] = Query(None)):
    """Generates and returns the formatted Excel file for the requested group."""
    grp = (group or GROUP_ALL).lower()
    
    if grp == GROUP_ACER_MONITORS:
        excel_path = export_monitors_excel()
        filename = f"Acer_Monitors_Price_Tracker_{datetime.now().strftime('%Y%m%d')}.xlsx"
    elif grp == GROUP_OTHER_PRODUCTS:
        excel_path = export_other_products_excel()
        filename = f"Other_Products_Price_Tracker_{datetime.now().strftime('%Y%m%d')}.xlsx"
    else:
        excel_path = export_all_portfolio_excel()
        filename = f"All_Products_Price_Tracker_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    return FileResponse(
        path=excel_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Mount static frontend
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
