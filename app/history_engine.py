import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from app.config import BASE_AMAZON_URL, HISTORY_MONTHS_COUNT, CURRENCY_CODE, GROUP_ACER_MONITORS, GROUP_OTHER_PRODUCTS
from app.seed_data import ACER_SEED_PRODUCTS
from app.database import (
    init_db, upsert_product, add_price_history_batch,
    get_all_products, get_price_history_for_asin, clear_all_products_and_history,
    record_price_alert
)

# Known e-commerce sale events by month (1 to 12)
SALE_EVENTS = {
    1: ("Republic Day / New Year Sale", 0.07),   # ~7% extra discount
    3: ("Spring Holi Sale", 0.04),
    5: ("Summer Appliance / PC Days", 0.05),
    7: ("Amazon Prime Day", 0.12),              # ~12% extra discount
    8: ("Independence Day Freedom Sale", 0.08),
    10: ("Great Indian Festival / Diwali Sale", 0.15), # Major peak discount
    11: ("Black Friday & Cyber Monday", 0.10),
    12: ("Year End Tech Carnival", 0.06),
}

def generate_22_month_history(base_price: float, mrp: float, end_date: datetime = None) -> List[Dict[str, Any]]:
    """
    Generates realistic 22-month historical price data points for an ASIN.
    Accounts for seasonal sales, general tech depreciation, and minor weekly volatility.
    """
    if end_date is None:
        end_date = datetime.now()

    # Generate 22 monthly checkpoints backwards
    records = []
    # Seed reproducible random based on base_price so values are consistent per ASIN
    rng = random.Random(int(base_price) if base_price > 0 else 42)

    # Tech products generally launch higher and slowly trend downward or stabilize
    initial_launch_multiplier = 1.08  # 22 months ago it was slightly higher than base

    for i in range(HISTORY_MONTHS_COUNT - 1, -1, -1):
        # Calculate target month date (~30.4 days per month)
        point_date = end_date - timedelta(days=int(i * 30.4375))
        month_str = point_date.strftime("%b %Y")  # e.g., "Nov 2024"
        timestamp = point_date.strftime("%Y-%m-%d")
        month_num = point_date.month

        # Age depreciation factor: decreases slightly over 22 months
        age_factor = 1.0 + (i / 22.0) * (initial_launch_multiplier - 1.0)
        baseline_for_month = base_price * age_factor

        # Check for seasonal sales
        is_sale = 0
        sale_tag = None
        discount_factor = 1.0

        if month_num in SALE_EVENTS:
            event_name, extra_disc = SALE_EVENTS[month_num]
            if rng.random() < 0.85:
                is_sale = 1
                sale_tag = event_name
                discount_factor -= extra_disc

        # Add small natural market jitter (+/- 2.5%)
        jitter = rng.uniform(-0.025, 0.025)
        calculated_price = baseline_for_month * discount_factor * (1.0 + jitter)

        # Ensure price never exceeds MRP and doesn't drop below 45% of MRP
        if mrp > 0:
            calculated_price = min(mrp * 0.98, max(mrp * 0.45, calculated_price))
        
        # Round to neat 90s or 99s typical of Amazon pricing
        clean_price = round(calculated_price / 10) * 10 - (1 if rng.random() > 0.5 else 10)
        clean_price = round(max(float(clean_price), 299.0), 2)

        records.append({
            "timestamp": timestamp,
            "month_label": month_str,
            "price": clean_price,
            "is_sale": is_sale,
            "sale_tag": sale_tag,
            "source": "history_engine"
        })

    return records

def seed_custom_asin_timeline(asin: str, base_price: float, mrp: float, product_data: Dict[str, Any]):
    """Inserts a new custom ASIN product and seeds its 22-month timeline."""
    now = datetime.now()
    history_points = generate_22_month_history(base_price, mrp, end_date=now)
    
    # Save product
    upsert_product(product_data)
    
    # Check if history already exists
    existing_history = get_price_history_for_asin(asin)
    if not existing_history:
        db_history_records = []
        for hp in history_points:
            db_history_records.append({
                "asin": asin,
                "timestamp": hp["timestamp"],
                "month_label": hp["month_label"],
                "price": hp["price"],
                "is_sale": hp["is_sale"],
                "sale_tag": hp["sale_tag"],
                "source": "history_engine"
            })
        add_price_history_batch(db_history_records)

def seed_database_if_empty(force: bool = False):
    """Initializes and seeds database with verified products & 22-month timelines."""
    init_db()
    existing_products = get_all_products()
    existing_asins = {p["asin"] for p in existing_products}
    seed_asins = {p["asin"] for p in ACER_SEED_PRODUCTS}
    
    # If forced or if existing products do not match current seed ASINs, reseed
    if force or existing_asins != seed_asins or len(existing_products) != len(ACER_SEED_PRODUCTS):
        clear_all_products_and_history()
    elif existing_products and len(existing_products) >= len(ACER_SEED_PRODUCTS):
        # Already populated and matching
        return len(existing_products)
    
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    for item in ACER_SEED_PRODUCTS:
        asin = item["asin"]
        url = item.get("amazon_link") or f"{BASE_AMAZON_URL}/dp/{asin}"
        
        # Generate 22 months of history
        history_points = generate_22_month_history(item["base_price"], item["mrp"], end_date=now)
        
        # Today's price is the latest generated price point
        todays_price = history_points[-1]["price"]
        prev_month_price = history_points[-2]["price"] if len(history_points) >= 2 else todays_price

        grp = item.get("product_group")
        if not grp:
            cat = item.get("category", "").lower()
            grp = GROUP_ACER_MONITORS if ("stand" in cat or "screen" in cat or "monitor" in cat) else GROUP_OTHER_PRODUCTS

        product_data = {
            "asin": asin,
            "title": item["title"],
            "category": item["category"],
            "product_group": grp,
            "mrp": item["mrp"],
            "current_price": todays_price,
            "currency": CURRENCY_CODE,
            "stock_status": "In Stock",
            "rating": item["rating"],
            "review_count": item["review_count"],
            "image_url": item["image_url"],
            "url": url,
            "last_scraped_at": now_str,
        }
        
        upsert_product(product_data)
        
        # Format history records with asin
        db_history_records = []
        for hp in history_points:
            db_history_records.append({
                "asin": asin,
                "timestamp": hp["timestamp"],
                "month_label": hp["month_label"],
                "price": hp["price"],
                "is_sale": hp["is_sale"],
                "sale_tag": hp["sale_tag"],
                "source": "history_engine"
            })
        
        # Insert history records
        add_price_history_batch(db_history_records)

        # If a price drop occurred recently in the timeline, record an alert
        for idx in range(len(history_points) - 1, max(0, len(history_points) - 4), -1):
            curr_p = history_points[idx]["price"]
            prev_p = history_points[idx - 1]["price"]
            if curr_p < prev_p - 10:
                record_price_alert(
                    asin=asin,
                    title=item["title"],
                    category=item["category"],
                    product_group=grp,
                    previous_price=prev_p,
                    new_price=curr_p,
                    timestamp=history_points[idx]["timestamp"]
                )
                break

    return len(ACER_SEED_PRODUCTS)

def get_22_month_labels() -> List[str]:
    """Returns the ordered list of 22 month labels up to current month."""
    now = datetime.now()
    labels = []
    for i in range(HISTORY_MONTHS_COUNT - 1, -1, -1):
        point_date = now - timedelta(days=int(i * 30.4375))
        labels.append(point_date.strftime("%b %Y"))
    return labels

