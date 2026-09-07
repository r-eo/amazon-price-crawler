import os
import gc
import asyncio
import threading
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, Body
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    STATIC_DIR, CURRENCY_SYMBOL,
    GROUP_ACER_MONITORS, GROUP_OTHER_PRODUCTS, GROUP_ALL,
    EXCEL_MONITORS_FILENAME, EXCEL_OTHER_FILENAME, EXCEL_ALL_FILENAME,
    SYNC_INTERVAL_HOURS, now_ist, now_ist_str
)
from app.database import (
    get_all_products, get_products_by_group, get_product_by_asin,
    get_price_history_for_asin, get_all_price_history, get_product_statistics,
    delete_product_by_asin, get_recent_price_changes, mark_price_changes_as_read,
    get_unread_price_changes_count, clear_all_price_changes, get_tab_counts
)
from app.history_engine import seed_database_if_empty, get_22_month_labels
from app.scraper import scrape_asin_details, scrape_all_asins
from app.excel_exporter import (
    export_monitors_excel, export_other_products_excel,
    export_all_portfolio_excel, export_excel_by_group
)

logger = logging.getLogger("tracker_app")

# Global crawl mutex to protect Render 256MB RAM against concurrent crawl jobs / stress tests
_crawl_lock = threading.Lock()

def get_next_sync_target(now: Optional[datetime] = None) -> datetime:
    """Calculates next scheduled sync timestamp from the 2-hour IST intervals (9 AM, 11 AM, 1 PM, 3 PM, 5 PM, 7 PM, 9 PM)."""
    now = now or now_ist()
    for h in sorted(SYNC_INTERVAL_HOURS):
        target = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if target > now:
            return target
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=sorted(SYNC_INTERVAL_HOURS)[0], minute=0, second=0, microsecond=0)

async def scheduled_sync_loop():
    """
    Background worker that runs automatically every 2 hours daily starting at 9:00 AM IST.
    Crawls active products and sequentially pre-generates 6-Month Excel reports with memory cleanup.
    """
    logger.info(f"Daily automated scheduler active (IST): 2-hour intervals starting at 9 AM: {', '.join(f'{h:02d}:00' for h in SYNC_INTERVAL_HOURS)}.")
    while True:
        try:
            now = now_ist()
            target_time = get_next_sync_target(now)
            delay_seconds = max(5, (target_time - now).total_seconds())
            hours, remainder = divmod(int(delay_seconds), 3600)
            minutes, _ = divmod(remainder, 60)
            logger.info(f"Daily scheduler: next run at {target_time.strftime('%I:%M %p IST')} (in {hours}h {minutes}m).")
            
            await asyncio.sleep(delay_seconds)
            
            # Non-blocking crawl lock
            if not _crawl_lock.acquire(blocking=False):
                logger.warning("Scheduled sync skipped: crawl lock currently held.")
                continue

            try:
                logger.info(f"Executing scheduled {target_time.strftime('%I:%M %p IST')} crawl & Excel generation...")
                # Crawl accessories catalog (all 90 items)
                await asyncio.to_thread(scrape_all_asins, GROUP_OTHER_PRODUCTS)
                gc.collect()
                # Sequentially generate Excel workbooks to conserve memory
                await asyncio.to_thread(export_other_products_excel)
                await asyncio.to_thread(export_all_portfolio_excel)
                gc.collect()
                logger.info("Scheduled crawl & Excel generation completed successfully.")
            finally:
                _crawl_lock.release()
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in daily scheduler: {e}")
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes database, ensures correct ordering and categorization, and starts 2-hour IST scheduler."""
    seed_database_if_empty()
    scheduler_task = asyncio.create_task(scheduled_sync_loop())
    yield
    scheduler_task.cancel()

app = FastAPI(
    title="Acer Amazon Price Intelligence Platform",
    description="Intelligence dashboards for Acer Accessories and Monitors with dynamic Excel exports and Real-Time Price Change Tracking.",
    version="4.0.0",
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
    if (request.url.path.startswith("/api") or
        request.url.path.startswith("/js") or
        request.url.path.startswith("/css") or
        request.url.path == "/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Pydantic models
class AddAsinRequest(BaseModel):
    asin: str
    group: str = GROUP_OTHER_PRODUCTS
    title: Optional[str] = None
    category: Optional[str] = None
    mrp: Optional[float] = None

class BatchImportRequest(BaseModel):
    asins: List[str]
    group: str = GROUP_OTHER_PRODUCTS
    category: Optional[str] = None

class MarkAlertsRequest(BaseModel):
    alert_ids: Optional[List[int]] = None

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "version": "4.0.0", "timestamp": now_ist_str()}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(content=b"", media_type="image/x-icon")

@app.get("/api/scheduler/status")
def scheduler_status():
    """Returns status and next execution time of the 2-hour IST sync schedule."""
    now = now_ist()
    target_time = get_next_sync_target(now)
    diff = target_time - now
    hours, remainder = divmod(max(0, int(diff.total_seconds())), 3600)
    minutes, _ = divmod(remainder, 60)
    
    formatted_time = target_time.strftime("%I:%M %p IST").lstrip("0")
    intervals_display = [datetime.strptime(str(h), "%H").strftime("%I:%M %p IST").lstrip("0") for h in sorted(SYNC_INTERVAL_HOURS)]
    
    return {
        "schedule_type": "Every 2 Hours (IST)",
        "intervals": intervals_display,
        "next_run_at": target_time.strftime("%Y-%m-%d %H:%M:%S IST"),
        "next_time_display": formatted_time,
        "time_remaining": f"{hours}h {minutes}m",
        "excel_auto_updates": True
    }

@app.get("/api/tabs/counts")
def tabs_counts():
    """Lightweight endpoint returning product counts per tab."""
    return get_tab_counts()

# =========================================================================
# Price Change Notifications Center
# =========================================================================

@app.get("/api/notifications")
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False)
):
    """Returns recent verified price changes (drops and increases) detected after checks."""
    changes = get_recent_price_changes(limit=limit, unread_only=unread_only)
    unread_cnt = get_unread_price_changes_count()
    return {
        "notifications": changes,
        "price_changes": changes,
        "unread_count": unread_cnt,
        "total": len(changes),
        "currency": CURRENCY_SYMBOL
    }

@app.get("/api/notifications/unread-count")
def unread_notifications_count():
    """Returns count of unread price changes for the bell badge."""
    return {"unread_count": get_unread_price_changes_count()}

@app.post("/api/notifications/mark-read")
def mark_notifications_read(payload: Optional[MarkAlertsRequest] = None):
    """Marks price changes as read."""
    ids = payload.alert_ids if payload else None
    count = mark_price_changes_as_read(ids)
    return {"status": "success", "marked_count": count, "unread_count": get_unread_price_changes_count()}

@app.post("/api/notifications/clear")
def clear_notifications():
    """Clears all price change logs."""
    clear_all_price_changes()
    return {"status": "success", "message": "All price change notifications cleared.", "unread_count": 0}

# Legacy aliases for alerts
@app.get("/api/alerts")
def list_price_alerts(limit: int = Query(50, ge=1, le=200), unread_only: bool = Query(False)):
    return list_notifications(limit=limit, unread_only=unread_only)

@app.get("/api/alerts/unread-count")
def unread_alerts_count_endpoint():
    return unread_notifications_count()

@app.post("/api/alerts/mark-read")
def mark_alerts_read_endpoint(payload: Optional[MarkAlertsRequest] = None):
    return mark_notifications_read(payload)

# =========================================================================
# Live Price Check & Crawler
# =========================================================================

@app.post("/api/check-prices-daily")
def trigger_daily_price_check(
    group: Optional[str] = Query(None)
):
    """
    Triggers a live crawl check to detect real price changes.
    Protected by crawl lock against concurrent execution under stress tests.
    """
    target_group = group or GROUP_OTHER_PRODUCTS
    grp_name = "Acer Accessories" if target_group == GROUP_OTHER_PRODUCTS else ("Acer Monitors" if target_group == GROUP_ACER_MONITORS else "All Products")
    
    if not _crawl_lock.acquire(blocking=False):
        return {
            "status": "busy",
            "group": target_group,
            "message": "A price check crawl is already actively running. Please wait a moment for it to finish."
        }

    try:
        res = scrape_all_asins(target_group)
        products = get_products_by_group(target_group)
        for p in products:
            p["stats"] = get_product_statistics(p["asin"])
        
        changes_cnt = res.get("price_changes_count", 0)
        return {
            "status": "completed",
            "group": target_group,
            "total_scraped": res.get("total", 0),
            "price_changes_count": changes_cnt,
            "products": products,
            "message": f"Price check complete for {grp_name}! Scanned {res.get('total', 0)} items ({changes_cnt} price changes logged)."
        }
    finally:
        _crawl_lock.release()

@app.post("/api/scrape")
def api_scrape_endpoint(
    background_tasks: BackgroundTasks,
    asin: Optional[str] = Query(None),
    group: Optional[str] = Query(None)
):
    """Crawls Amazon live for a single ASIN synchronously or an entire group."""
    if asin:
        clean_asin = asin.strip().upper()
        res = scrape_asin_details(asin=clean_asin)
        prod = get_product_by_asin(clean_asin)
        if prod:
            prod["stats"] = get_product_statistics(clean_asin)
            background_tasks.add_task(export_excel_by_group, prod.get("product_group", GROUP_OTHER_PRODUCTS))
        return {
            "status": "completed" if res.get("success") else "failed",
            "asin": clean_asin,
            "data": prod or res.get("data"),
            "message": res.get("message")
        }
    
    if not _crawl_lock.acquire(blocking=False):
        return {
            "status": "busy",
            "message": "A crawl job is already in progress. Please wait for it to complete."
        }
    
    def _run_scrape():
        try:
            scrape_all_asins(group)
        finally:
            _crawl_lock.release()

    background_tasks.add_task(_run_scrape)
    return {
        "status": "queued",
        "message": f"Crawl job queued for {group or 'all products'}."
    }

@app.api_route("/api/cron/sync", methods=["GET", "POST"])
def vercel_cron_sync(background_tasks: BackgroundTasks):
    """Vercel Cron endpoint triggered every 2 hours during daytime."""
    if not _crawl_lock.acquire(blocking=False):
        return {"status": "busy", "message": "Crawl already running."}
    
    def _run_cron():
        try:
            scrape_all_asins(GROUP_OTHER_PRODUCTS)
            export_other_products_excel()
            export_all_portfolio_excel()
            gc.collect()
        finally:
            _crawl_lock.release()

    background_tasks.add_task(_run_cron)
    return {
        "status": "success",
        "message": "2-Hour sync triggered via cron across active catalog.",
        "timestamp": now_ist_str()
    }

# =========================================================================
# Products & Catalog Endpoints
# =========================================================================

@app.get("/api/products")
def list_products(
    group: Optional[str] = Query(None),
    category: Optional[str] = None,
    search: Optional[str] = None,
    price_drops_only: bool = Query(False)
):
    """
    Returns list of tracked products strictly ordered by sort_order ASC.
    Memory-efficient: no automatic background crawl tasks attached to regular page views.
    """
    products = get_products_by_group(group)
    if not products and not get_all_products():
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
        if price_drops_only:
            hist = get_price_history_for_asin(p["asin"])
            if len(hist) < 2 or hist[-1]["price"] >= hist[-2]["price"]:
                continue

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
    """Returns single product details, statistics, and 6-month timeline."""
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
            scrape_asin_details(asin=clean, group=payload.group, category=payload.category)
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
        
    grp = prod.get("product_group", GROUP_OTHER_PRODUCTS)
    delete_product_by_asin(clean_asin)
    background_tasks.add_task(export_excel_by_group, grp)
    
    return {"status": "success", "message": f"Deleted ASIN {clean_asin}."}

@app.get("/api/stats")
def get_dashboard_stats(
    group: Optional[str] = Query(None)
):
    """Calculates overall statistics and KPI aggregations for the requested dashboard group."""
    products = get_products_by_group(group)
    if not products and not get_all_products():
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
            "price_drops_count": 0,
            "unread_alerts_count": get_unread_price_changes_count(),
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
                        "drop_pct": drop_pct,
                        "url": p["url"]
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
        "price_drops_count": len(price_drops),
        "top_price_drop": top_drop,
        "recent_price_drops": price_drops[:10],
        "unread_alerts_count": get_unread_price_changes_count(),
        "category_breakdown": category_breakdown,
        "month_labels": month_labels,
        "category_trends": category_trends,
        "currency": CURRENCY_SYMBOL
    }

@app.get("/api/export/excel")
def download_excel_export(group: Optional[str] = Query(None)):
    """Generates and returns the formatted Excel file strictly preserving sort order."""
    grp = (group or GROUP_ALL).lower()
    
    if grp == GROUP_ACER_MONITORS:
        excel_path = export_monitors_excel()
        filename = f"Acer_Monitors_Price_Tracker_{now_ist().strftime('%Y%m%d')}.xlsx"
    elif grp == GROUP_OTHER_PRODUCTS:
        excel_path = export_other_products_excel()
        filename = f"Other_Products_Price_Tracker_{now_ist().strftime('%Y%m%d')}.xlsx"
    else:
        excel_path = export_all_portfolio_excel()
        filename = f"All_Products_Price_Tracker_{now_ist().strftime('%Y%m%d')}.xlsx"
    
    return FileResponse(
        path=excel_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Mount static frontend
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
