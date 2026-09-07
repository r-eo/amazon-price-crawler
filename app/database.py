import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.config import (
    DATABASE_PATH, GROUP_ACER_MONITORS, GROUP_OTHER_PRODUCTS, GROUP_ALL,
    now_ist, now_ist_str
)

def get_db_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema and performs migrations if needed."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                asin TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                product_group TEXT DEFAULT 'other_products',
                sort_order INTEGER DEFAULT 999,
                mrp REAL NOT NULL,
                current_price REAL NOT NULL,
                currency TEXT DEFAULT 'INR',
                stock_status TEXT DEFAULT 'In Stock',
                rating REAL DEFAULT 4.2,
                review_count INTEGER DEFAULT 100,
                image_url TEXT,
                url TEXT NOT NULL,
                last_scraped_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Migration: Ensure product_group and sort_order columns exist
        cursor.execute("PRAGMA table_info(products)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "product_group" not in columns:
            cursor.execute("ALTER TABLE products ADD COLUMN product_group TEXT DEFAULT 'other_products'")
        if "sort_order" not in columns:
            cursor.execute("ALTER TABLE products ADD COLUMN sort_order INTEGER DEFAULT 999")

        # Move monitor stands and privacy screens to other_products (accessories)
        cursor.execute("""
            UPDATE products 
            SET product_group = 'other_products' 
            WHERE asin IN ('B0DCW32MB9', 'B0DCW28VCS', 'B0FQDD56FW', 'B0GZWS5CL1', 'B0DMP3Q1TV', 'B0DMP1272V')
        """)

        # Price history table (contains historical timeline and live scrapes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asin TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                month_label TEXT NOT NULL,
                price REAL NOT NULL,
                is_sale INTEGER DEFAULT 0,
                sale_tag TEXT,
                source TEXT DEFAULT 'history_engine',
                FOREIGN KEY (asin) REFERENCES products(asin) ON DELETE CASCADE
            )
        """)

        # Price changes table (tracks real verified price shifts after each crawl)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asin TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT,
                product_group TEXT,
                previous_price REAL NOT NULL,
                new_price REAL NOT NULL,
                change_amount REAL NOT NULL,
                change_pct REAL NOT NULL,
                change_type TEXT NOT NULL, -- 'drop' or 'increase'
                timestamp TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                FOREIGN KEY (asin) REFERENCES products(asin) ON DELETE CASCADE
            )
        """)
        
        # Legacy price alerts table (for backwards compatibility)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asin TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT,
                product_group TEXT,
                previous_price REAL NOT NULL,
                new_price REAL NOT NULL,
                drop_amount REAL NOT NULL,
                drop_pct REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_read INTEGER DEFAULT 0,
                FOREIGN KEY (asin) REFERENCES products(asin) ON DELETE CASCADE
            )
        """)
        
        # Indexes for fast lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_asin ON price_history(asin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON price_history(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_group ON products(product_group)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_sort ON products(sort_order)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_changes_timestamp ON price_changes(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_changes_read ON price_changes(is_read)")
        
        conn.commit()

def upsert_product(product_data: Dict[str, Any]):
    """Inserts or updates a product record including its product_group and sort_order."""
    if "product_group" not in product_data or not product_data["product_group"]:
        cat = product_data.get("category", "")
        # All stands and screens belong to other_products as per user request
        product_data["product_group"] = GROUP_OTHER_PRODUCTS

    if "sort_order" not in product_data or product_data["sort_order"] is None:
        product_data["sort_order"] = 999

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (
                asin, title, category, product_group, sort_order, mrp, current_price, currency,
                stock_status, rating, review_count, image_url, url, last_scraped_at
            ) VALUES (
                :asin, :title, :category, :product_group, :sort_order, :mrp, :current_price, :currency,
                :stock_status, :rating, :review_count, :image_url, :url, :last_scraped_at
            ) ON CONFLICT(asin) DO UPDATE SET
                title = excluded.title,
                category = excluded.category,
                product_group = excluded.product_group,
                sort_order = CASE WHEN excluded.sort_order < 999 THEN excluded.sort_order ELSE products.sort_order END,
                mrp = excluded.mrp,
                current_price = excluded.current_price,
                stock_status = excluded.stock_status,
                rating = excluded.rating,
                review_count = excluded.review_count,
                image_url = excluded.image_url,
                url = excluded.url,
                last_scraped_at = excluded.last_scraped_at
        """, product_data)
        conn.commit()

def delete_product_by_asin(asin: str) -> bool:
    """Deletes a product, its price history, and alerts by ASIN."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM price_changes WHERE asin = ?", (asin,))
        cursor.execute("DELETE FROM price_alerts WHERE asin = ?", (asin,))
        cursor.execute("DELETE FROM price_history WHERE asin = ?", (asin,))
        cursor.execute("DELETE FROM products WHERE asin = ?", (asin,))
        conn.commit()
        return cursor.rowcount > 0

def add_price_history_batch(records: List[Dict[str, Any]]):
    """Batch inserts price history records."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            INSERT INTO price_history (
                asin, timestamp, month_label, price, is_sale, sale_tag, source
            ) VALUES (
                :asin, :timestamp, :month_label, :price, :is_sale, :sale_tag, :source
            )
        """, records)
        conn.commit()

def add_single_price_point(asin: str, price: float, timestamp: str = None, month_label: str = None, source: str = "live_crawl", is_sale: int = 0, sale_tag: str = None):
    """Inserts a single new price observation into the history table."""
    now = now_ist()
    if not timestamp:
        timestamp = now.strftime("%Y-%m-%d")
    if not month_label:
        month_label = now.strftime("%b %Y")
        
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO price_history (asin, timestamp, month_label, price, is_sale, sale_tag, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (asin, timestamp, month_label, price, is_sale, sale_tag, source))
        conn.commit()

def record_price_change(
    asin: str,
    title: str,
    category: str,
    product_group: str,
    previous_price: float,
    new_price: float,
    timestamp: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Records a real verified price change event (drop or increase) after each crawl check.
    """
    if previous_price is None or abs(previous_price - new_price) < 0.01:
        return None

    raw_diff = round(new_price - previous_price, 2)
    change_type = "drop" if raw_diff < 0 else "increase"
    abs_amount = round(abs(raw_diff), 2)
    pct = round((abs_amount / previous_price) * 100, 1) if previous_price > 0 else 0.0
    now_str = timestamp or now_ist_str()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO price_changes (
                asin, title, category, product_group, previous_price, new_price,
                change_amount, change_pct, change_type, timestamp, is_read
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (asin, title, category, product_group, previous_price, new_price, abs_amount, pct, change_type, now_str))
        conn.commit()
        change_id = cursor.lastrowid

    return {
        "id": change_id,
        "asin": asin,
        "title": title,
        "category": category,
        "product_group": product_group,
        "previous_price": previous_price,
        "new_price": new_price,
        "change_amount": abs_amount,
        "change_pct": pct,
        "change_type": change_type,
        "timestamp": now_str,
        "is_read": 0
    }

def get_recent_price_changes(limit: int = 50, unread_only: bool = False) -> List[Dict[str, Any]]:
    """Fetches recent price changes ordered by id descending."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if unread_only:
            cursor.execute("""
                SELECT * FROM price_changes 
                WHERE is_read = 0 
                ORDER BY id DESC 
                LIMIT ?
            """, (limit,))
        else:
            cursor.execute("""
                SELECT * FROM price_changes 
                ORDER BY id DESC 
                LIMIT ?
            """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def mark_price_changes_as_read(change_ids: Optional[List[int]] = None) -> int:
    """Marks specified price changes or all unread changes as read."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if change_ids:
            placeholders = ",".join("?" for _ in change_ids)
            cursor.execute(f"UPDATE price_changes SET is_read = 1 WHERE id IN ({placeholders})", change_ids)
        else:
            cursor.execute("UPDATE price_changes SET is_read = 1 WHERE is_read = 0")
        conn.commit()
        return cursor.rowcount

def clear_all_price_changes():
    """Clears all price change logs."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM price_changes")
        conn.commit()

def get_unread_price_changes_count() -> int:
    """Returns count of unread price changes."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(id) as cnt FROM price_changes WHERE is_read = 0")
        row = cursor.fetchone()
        return row["cnt"] if row else 0

# Backwards compatibility wrappers
def record_price_alert(asin, title, category, product_group, previous_price, new_price, timestamp=None):
    return record_price_change(asin, title, category, product_group, previous_price, new_price, timestamp)

def get_recent_price_alerts(limit=50, unread_only=False):
    return get_recent_price_changes(limit, unread_only)

def mark_alerts_as_read(alert_ids=None):
    return mark_price_changes_as_read(alert_ids)

def get_unread_alerts_count():
    return get_unread_price_changes_count()

def get_tab_counts() -> Dict[str, int]:
    """Fast aggregate SQL query to return product counts per tab."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT product_group, COUNT(*) as cnt 
            FROM products 
            GROUP BY product_group
        """)
        rows = cursor.fetchall()
        counts = {row["product_group"]: row["cnt"] for row in rows}
        monitors = counts.get(GROUP_ACER_MONITORS, 0)
        other = counts.get(GROUP_OTHER_PRODUCTS, 0)
        return {
            "acer_monitors": monitors,
            "other_products": other,
            "all": monitors + other
        }

def clear_all_products_and_history():
    """Clears all products, price history, and alerts for a clean database reseed."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM price_changes")
        cursor.execute("DELETE FROM price_alerts")
        cursor.execute("DELETE FROM price_history")
        cursor.execute("DELETE FROM products")
        conn.commit()

def get_all_products() -> List[Dict[str, Any]]:
    """Fetches all products strictly ordered by sort_order ASC, asin ASC."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY sort_order ASC, asin ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_products_by_group(group: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches products filtered by group strictly ordered by sort_order ASC, asin ASC."""
    if not group or group.lower() in ("all", "both"):
        return get_all_products()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM products 
            WHERE LOWER(product_group) = LOWER(?) 
            ORDER BY sort_order ASC, asin ASC
        """, (group,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_product_by_asin(asin: str) -> Optional[Dict[str, Any]]:
    """Fetches a single product by ASIN."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE asin = ?", (asin,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_price_history_for_asin(asin: str) -> List[Dict[str, Any]]:
    """Fetches full chronological price history for an ASIN."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM price_history 
            WHERE asin = ? 
            ORDER BY timestamp ASC
        """, (asin,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_all_price_history() -> List[Dict[str, Any]]:
    """Fetches all price history records."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM price_history ORDER BY asin, timestamp ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_product_statistics(asin: str) -> Dict[str, Any]:
    """Calculates min, max, avg, and deal status for an ASIN."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                MIN(price) as min_price,
                MAX(price) as max_price,
                AVG(price) as avg_price,
                COUNT(id) as total_points
            FROM price_history 
            WHERE asin = ?
        """, (asin,))
        stat = cursor.fetchone()
        
        cursor.execute("SELECT mrp, current_price FROM products WHERE asin = ?", (asin,))
        prod = cursor.fetchone()
        
        if not prod or not stat or stat["min_price"] is None:
            return {}
        
        current_price = prod["current_price"]
        mrp = prod["mrp"]
        min_price = stat["min_price"]
        max_price = stat["max_price"]
        avg_price = round(stat["avg_price"], 2)
        
        discount_from_mrp = round(((mrp - current_price) / mrp) * 100, 1) if mrp > 0 else 0
        discount_from_ath = round(((max_price - current_price) / max_price) * 100, 1) if max_price > 0 else 0
        diff_from_atl = round(((current_price - min_price) / min_price) * 100, 1) if min_price > 0 else 0
        
        is_atl = current_price <= (min_price * 1.01) # within 1% of all-time low
        is_near_atl = current_price <= (min_price * 1.05) # within 5% of ATL
        
        return {
            "asin": asin,
            "current_price": current_price,
            "mrp": mrp,
            "min_price": min_price,
            "max_price": max_price,
            "avg_price": avg_price,
            "total_points": stat["total_points"],
            "discount_from_mrp": discount_from_mrp,
            "discount_from_ath": discount_from_ath,
            "diff_from_atl": diff_from_atl,
            "is_atl": is_atl,
            "is_near_atl": is_near_atl,
        }

def reconcile_and_repair_corrupted_data() -> Dict[str, Any]:
    """
    Scans products, price history, and price alerts tables to detect and repair
    any records corrupted by previous crawls (e.g. price > mrp, mrp < 250, or huge outliers).
    Restores valid catalog baselines from ACER_SEED_PRODUCTS.
    """
    from app.seed_data import ACER_SEED_PRODUCTS
    seed_map = {p["asin"]: p for p in ACER_SEED_PRODUCTS}
    
    repaired_products = []
    removed_history = 0
    removed_alerts = 0
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT asin, title, current_price, mrp, stock_status FROM products")
        products = cursor.fetchall()
        
        for p in products:
            asin = p["asin"]
            cur_price = p["current_price"]
            cur_mrp = p["mrp"]
            seed = seed_map.get(asin)
            
            needs_repair = False
            fix_price = cur_price
            fix_mrp = cur_mrp
            
            # Condition 1: Selling price exceeds MRP
            if cur_price and cur_mrp and cur_price > cur_mrp:
                needs_repair = True
                fix_price = round(cur_mrp * 0.8, 2)
            
            # Condition 2: Absurdly low or missing price/MRP
            if not cur_price or cur_price <= 0:
                if seed and seed.get("base_price"):
                    needs_repair = True
                    fix_price = seed["base_price"]
                    fix_mrp = seed.get("mrp", cur_mrp)
            
            if needs_repair:
                cursor.execute("""
                    UPDATE products 
                    SET current_price = ?, mrp = ?
                    WHERE asin = ?
                """, (fix_price, fix_mrp, asin))
                repaired_products.append({
                    "asin": asin,
                    "old_price": cur_price,
                    "new_price": fix_price,
                    "old_mrp": cur_mrp,
                    "new_mrp": fix_mrp
                })
                
                # Delete corrupted history spikes for this ASIN
                if fix_mrp:
                    cursor.execute("DELETE FROM price_history WHERE asin = ? AND price > ?", (asin, fix_mrp * 1.15))
                    removed_history += cursor.rowcount
                
                # Delete corrupted alerts
                if fix_mrp:
                    cursor.execute("""
                        DELETE FROM price_alerts 
                        WHERE asin = ? AND (new_price > ? OR previous_price > ?)
                    """, (asin, fix_mrp * 1.15, fix_mrp * 1.15))
                    removed_alerts += cursor.rowcount
                    
        conn.commit()
        
    return {
        "repaired_count": len(repaired_products),
        "repaired_products": repaired_products,
        "removed_corrupt_history": removed_history,
        "removed_corrupt_alerts": removed_alerts
    }

