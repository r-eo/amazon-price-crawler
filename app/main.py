import os
import asyncio
import threading
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
    EXCEL_MONITORS_FILENAME, EXCEL_OTHER_FILENAME, EXCEL_ALL_FILENAME,
    SYNC_INTERVAL_HOURS
)
from app.database import (
    get_all_products, get_products_by_group, get_product_by_asin,
    get_price_history_for_asin, get_all_price_history, get_product_statistics,
    delete_product_by_asin, get_recent_price_alerts, mark_alerts_as_read,
    get_unread_alerts_count, reconcile_and_repair_corrupted_data
)
from app.history_engine import seed_database_if_empty, get_22_month_labels
from app.scraper import scrape_asin_details, scrape_all_asins
from app.excel_exporter import (
    export_monitors_excel, export_other_products_excel,
    export_all_portfolio_excel, export_excel_by_group
)

logger = logging.getLogger("tracker_app")

_last_auto_sync_lock = threading.Lock()
_last_auto_sync_time: Optional[datetime] = None

def get_next_sync_target(now: Optional[datetime] = None) -> datetime:
    """Calculates next scheduled sync timestamp from the 3 daily intervals (9:00 AM, 1:00 PM, 5:00 PM)."""
    now = now or datetime.now()
    for h in sorted(SYNC_INTERVAL_HOURS):
        target = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if target > now:
            return target
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=sorted(SYNC_INTERVAL_HOURS)[0], minute=0, second=0, microsecond=0)

def get_most_recent_scheduled_sync(now: Optional[datetime] = None) -> datetime:
    """Finds the most recent sync milestone that should have occurred."""
    now = now or datetime.now()
    passed_today = [h for h in sorted(SYNC_INTERVAL_HOURS) if now.hour >= h]
    if passed_today:
        return now.replace(hour=max(passed_today), minute=0, second=0, microsecond=0)
    yesterday = now - timedelta(days=1)
    return yesterday.replace(hour=sorted(SYNC_INTERVAL_HOURS)[-1], minute=0, second=0, microsecond=0)

def check_and_auto_sync_if_stale(force: bool = False):
    """
    Checks if products data has missed the most recent scheduled 4-hour sync window.
    If stale (or on cold start after a scheduled milestone), automatically triggers
    a background refresh to ensure live data integrity.
    Throttled to run at most once per 70 minutes.
    """
    global _last_auto_sync_time
    now = datetime.now()
    if _last_auto_sync_time and (now - _last_auto_sync_time).total_seconds() < 4200 and not force:
        return

    if not _last_auto_sync_lock.acquire(blocking=False):
        return

    try:
        if _last_auto_sync_time and (now - _last_auto_sync_time).total_seconds() < 4200 and not force:
            return
        
        products = get_all_products()
        if not products:
            return

        is_stale = False
        scraped_dates = [p.get("last_scraped_at") for p in products if p.get("last_scraped_at")]
        if not scraped_dates:
            is_stale = True
        else:
            latest_str = max(scraped_dates)
            try:
                latest_dt = datetime.strptime(latest_str, "%Y-%m-%d %H:%M:%S")
                recent_milestone = get_most_recent_scheduled_sync(now)
                if latest_dt < recent_milestone and (now - recent_milestone).total_seconds() > 300:
                    is_stale = True
                elif (now - latest_dt).total_seconds() > 21600:
                    is_stale = True
            except Exception:
                is_stale = True

        if is_stale or force:
            _last_auto_sync_time = now
            logger.info("Auto-sync: Detected stale data past scheduled milestone. Launching refresh...")
            try:
                scrape_all_asins(GROUP_ACER_MONITORS)
                scrape_all_asins(GROUP_OTHER_PRODUCTS)
                export_monitors_excel()
                export_other_products_excel()
                export_all_portfolio_excel()
                logger.info("Auto-sync refresh completed successfully.")
            except Exception as ex:
                logger.error(f"Auto-sync refresh failed: {ex}")
    finally:
        _last_auto_sync_lock.release()

async def scheduled_sync_loop():
    """
    Background worker that runs automatically every hour daily starting at 9:00 AM.
    Crawls products and pre-generates daily 22-Month Excel reports.
    """
    logger.info(f"Daily automated scheduler active: hourly intervals starting at 9 AM: {', '.join(f'{h:02d}:00' for h in SYNC_INTERVAL_HOURS)}.")
    while True:
        try:
            now = datetime.now()
            target_time = get_next_sync_target(now)
            delay_seconds = max(5, (target_time - now).total_seconds())
            hours, remainder = divmod(int(delay_seconds), 3600)
            minutes, _ = divmod(remainder, 60)
            logger.info(f"Daily scheduler: next automated run at {target_time.strftime('%Y-%m-%d %H:%M:%S')} (in {hours}h {minutes}m).")
            
            await asyncio.sleep(delay_seconds)
            
            logger.info(f"Executing scheduled {target_time.strftime('%I:%M %p')} crawl & Excel generation...")
            await asyncio.to_thread(scrape_all_asins, GROUP_ACER_MONITORS)
            await asyncio.to_thread(scrape_all_asins, GROUP_OTHER_PRODUCTS)
            await asyncio.to_thread(export_monitors_excel)
            await asyncio.to_thread(export_other_products_excel)
            await asyncio.to_thread(export_all_portfolio_excel)
            logger.info("Scheduled crawl & Excel generation completed successfully.")
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in daily scheduler: {e}")
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes database, runs data integrity check, auto-refreshes if stale, and starts 3-interval daily scheduler."""
    seed_database_if_empty()
    reconcile_and_repair_corrupted_data()
    asyncio.create_task(asyncio.to_thread(check_and_auto_sync_if_stale))
    scheduler_task = asyncio.create_task(scheduled_sync_loop())
    yield
    scheduler_task.cancel()

app = FastAPI(
    title="Acer Amazon Price Intelligence Platform",
    description="Dedicated intelligence dashboards for Acer Monitors and Other Amazon Products with dynamic/daily Excel exports and Price Drop Notifications.",
    version="3.0.0",
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
    group: str = GROUP_ACER_MONITORS
    title: Optional[str] = None
    category: Optional[str] = None
    mrp: Optional[float] = None

class BatchImportRequest(BaseModel):
    asins: List[str]
    group: str = GROUP_ACER_MONITORS
    category: Optional[str] = None

class MarkAlertsRequest(BaseModel):
    alert_ids: Optional[List[int]] = None

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "version": "3.2.0", "timestamp": datetime.now().isoformat()}

@app.get("/api/scheduler/status")
def scheduler_status():
    """Returns status and next execution time of the hourly daily sync schedule starting at 9 AM."""
    now = datetime.now()
    target_time = get_next_sync_target(now)
    diff = target_time - now
    hours, remainder = divmod(max(0, int(diff.total_seconds())), 3600)
    minutes, _ = divmod(remainder, 60)
    
    formatted_time = target_time.strftime("%I:%M %p").lstrip("0")
    intervals_display = [datetime.strptime(str(h), "%H").strftime("%I:%M %p").lstrip("0") for h in sorted(SYNC_INTERVAL_HOURS)]
    
    return {
        "schedule_type": "Hourly Intervals (from 9 AM)",
        "intervals": intervals_display,
        "next_run_at": target_time.strftime("%Y-%m-%d %H:%M:%S"),
        "next_time_display": formatted_time,
        "time_remaining": f"{hours}h {minutes}m",
        "excel_auto_updates": True
    }

# =========================================================================
# Price Drop Alerts & Notifications Endpoints
# =========================================================================

@app.get("/api/alerts")
def list_price_alerts(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False)
):
    """Returns recent price drop alerts."""
    alerts = get_recent_price_alerts(limit=limit, unread_only=unread_only)
    unread_cnt = get_unread_alerts_count()
    return {
        "alerts": alerts,
        "unread_count": unread_cnt,
        "total": len(alerts),
        "currency": CURRENCY_SYMBOL
    }

@app.get("/api/alerts/unread-count")
def unread_alerts_count_endpoint():
    """Returns count of unread price alerts for the notification bell badge."""
    return {"unread_count": get_unread_alerts_count()}

@app.post("/api/alerts/mark-read")
def mark_alerts_read_endpoint(payload: Optional[MarkAlertsRequest] = None):
    """Marks alerts as read."""
    ids = payload.alert_ids if payload else None
    count = mark_alerts_as_read(ids)
    return {"status": "success", "marked_count": count, "unread_count": get_unread_alerts_count()}

@app.post("/api/check-prices-daily")
def trigger_daily_price_check(
    background_tasks: BackgroundTasks,
    group: Optional[str] = Query(None)
):
    """
    Triggers an instant scan across products to check prices, detect drops,
    and issue alerts immediately. Scans current tab synchronously when possible.
    """
    target_group = group or GROUP_ACER_MONITORS
    grp_name = "Acer Monitors & Stands" if target_group == GROUP_ACER_MONITORS else ("Other Products" if target_group == GROUP_OTHER_PRODUCTS else "All Products")
    
    if target_group == GROUP_ACER_MONITORS:
        res = scrape_all_asins(target_group)
        products = get_products_by_group(target_group)
        for p in products:
            p["stats"] = get_product_statistics(p["asin"])
        return {
            "status": "completed",
            "group": target_group,
            "total_scraped": res.get("total", 0),
            "price_drops_count": res.get("price_drops_count", 0),
            "products": products,
            "message": f"Live Amazon crawl complete for {grp_name}! Scanned {res.get('total', 0)} items ({res.get('price_drops_count', 0)} price drops detected)."
        }
    else:
        # For larger groups: Crawl the first 12 visible items synchronously so table updates immediately!
        all_prods = get_products_by_group(target_group)
        first_batch = all_prods[:12]
        rest_batch = all_prods[12:]
        
        from concurrent.futures import ThreadPoolExecutor
        def _task(p):
            return scrape_asin_details(p["asin"], group=p.get("product_group"), category=p.get("category"))
        
        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(_task, first_batch))
        
        # Queue the remaining items in background
        def _crawl_rest():
            with ThreadPoolExecutor(max_workers=4) as ex:
                list(ex.map(_task, rest_batch))
            from app.excel_exporter import export_excel_by_group
            export_excel_by_group(target_group)
        
        background_tasks.add_task(_crawl_rest)
        
        updated_products = get_products_by_group(target_group)
        for p in updated_products:
            p["stats"] = get_product_statistics(p["asin"])
            
        drops_count = sum(1 for r in results if r.get("price_dropped"))
        return {
            "status": "completed",
            "group": target_group,
            "total_scraped": len(first_batch),
            "price_drops_count": drops_count,
            "products": updated_products,
            "message": f"Live Amazon scan updated visible items for {grp_name}! ({len(first_batch)} items scanned, background continuing for remaining)."
        }

@app.post("/api/scrape")
def api_scrape_endpoint(
    background_tasks: BackgroundTasks,
    asin: Optional[str] = Query(None),
    group: Optional[str] = Query(None)
):
    """
    Crawls Amazon live for a single ASIN synchronously or an entire group asynchronously.
    """
    if asin:
        clean_asin = asin.strip().upper()
        res = scrape_asin_details(asin=clean_asin)
        prod = get_product_by_asin(clean_asin)
        if prod:
            prod["stats"] = get_product_statistics(clean_asin)
            background_tasks.add_task(export_excel_by_group, prod.get("product_group", GROUP_ACER_MONITORS))
        return {
            "status": "completed" if res.get("success") else "failed",
            "asin": clean_asin,
            "data": prod or res.get("data"),
            "message": res.get("message")
        }
    
    background_tasks.add_task(scrape_all_asins, group)
    return {
        "status": "queued",
        "message": f"Crawl job queued for {group or 'all products'}."
    }

@app.api_route("/api/cron/sync", methods=["GET", "POST"])
def vercel_cron_sync(background_tasks: BackgroundTasks):
    """Vercel Cron endpoint triggered at 9 AM, 1 PM, 5 PM IST (every 4 hours)."""
    background_tasks.add_task(scrape_all_asins, GROUP_ACER_MONITORS)
    background_tasks.add_task(scrape_all_asins, GROUP_OTHER_PRODUCTS)
    background_tasks.add_task(export_monitors_excel)
    background_tasks.add_task(export_other_products_excel)
    background_tasks.add_task(export_all_portfolio_excel)
    return {
        "status": "success",
        "message": "3-Interval sync triggered via cron across all products.",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

# =========================================================================
# Products & Catalog Endpoints
# =========================================================================

@app.get("/api/products")
def list_products(
    background_tasks: BackgroundTasks,
    group: Optional[str] = Query(None),
    category: Optional[str] = None,
    search: Optional[str] = None,
    price_drops_only: bool = Query(False)
):
    """Returns list of tracked products filtered by group, category, search, or price drops."""
    background_tasks.add_task(check_and_auto_sync_if_stale)
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
        if price_drops_only:
            # Check if there's a recent drop
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
def get_dashboard_stats(
    background_tasks: BackgroundTasks,
    group: Optional[str] = Query(None)
):
    """Calculates overall statistics and KPI aggregations for the requested dashboard group."""
    background_tasks.add_task(check_and_auto_sync_if_stale)
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
            "price_drops_count": 0,
            "unread_alerts_count": get_unread_alerts_count(),
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
        "unread_alerts_count": get_unread_alerts_count(),
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
        grp_name = "Acer Monitors & Stands" if group == GROUP_ACER_MONITORS else ("Other Products" if group == GROUP_OTHER_PRODUCTS else "All Products")
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

