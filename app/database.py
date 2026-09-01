import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.config import DATABASE_PATH, GROUP_ACER_MONITORS, GROUP_OTHER_PRODUCTS

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
                product_group TEXT DEFAULT 'acer_monitors',
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
        
        # Migration: Ensure product_group column exists on pre-existing tables
        cursor.execute("PRAGMA table_info(products)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "product_group" not in columns:
            cursor.execute("ALTER TABLE products ADD COLUMN product_group TEXT DEFAULT 'acer_monitors'")
            cursor.execute("UPDATE products SET product_group = 'acer_monitors' WHERE category = 'Monitors'")
            cursor.execute("UPDATE products SET product_group = 'other_products' WHERE category != 'Monitors'")

        # Price history table (contains 22-month timeline and live scrapes)
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

        # Price alerts table (tracks daily price drop events and notifications)
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
        
        # Index on asin and timestamp for fast lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_asin ON price_history(asin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON price_history(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_group ON products(product_group)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created ON price_alerts(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_read ON price_alerts(is_read)")
        
        conn.commit()

def upsert_product(product_data: Dict[str, Any]):
    """Inserts or updates a product record including its product_group."""
    # Ensure default product_group if missing
    if "product_group" not in product_data or not product_data["product_group"]:
        cat = product_data.get("category", "")
        product_data["product_group"] = GROUP_ACER_MONITORS if ("stand" in cat.lower() or "screen" in cat.lower() or "monitor" in cat.lower()) else GROUP_OTHER_PRODUCTS

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (
                asin, title, category, product_group, mrp, current_price, currency,
                stock_status, rating, review_count, image_url, url, last_scraped_at
            ) VALUES (
                :asin, :title, :category, :product_group, :mrp, :current_price, :currency,
                :stock_status, :rating, :review_count, :image_url, :url, :last_scraped_at
            ) ON CONFLICT(asin) DO UPDATE SET
                title = excluded.title,
                category = excluded.category,
                product_group = excluded.product_group,
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
    now = datetime.now()
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

def record_price_alert(
    asin: str,
    title: str,
    category: str,
    product_group: str,
    previous_price: float,
    new_price: float,
    timestamp: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Records a price drop notification alert in the database if new_price < previous_price.
    """
    if new_price >= previous_price:
        return None

    drop_amount = round(previous_price - new_price, 2)
    drop_pct = round((drop_amount / previous_price) * 100, 1) if previous_price > 0 else 0.0
    now_str = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO price_alerts (
                asin, title, category, product_group, previous_price, new_price, drop_amount, drop_pct, created_at, is_read
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (asin, title, category, product_group, previous_price, new_price, drop_amount, drop_pct, now_str))
        conn.commit()
        alert_id = cursor.lastrowid

    return {
        "id": alert_id,
        "asin": asin,
        "title": title,
        "category": category,
        "product_group": product_group,
        "previous_price": previous_price,
        "new_price": new_price,
        "drop_amount": drop_amount,
        "drop_pct": drop_pct,
        "created_at": now_str,
        "is_read": 0
    }

def get_recent_price_alerts(limit: int = 50, unread_only: bool = False) -> List[Dict[str, Any]]:
    """Fetches recent price drop alerts ordered by timestamp descending."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if unread_only:
            cursor.execute("""
                SELECT * FROM price_alerts 
                WHERE is_read = 0 
                ORDER BY created_at DESC, id DESC 
                LIMIT ?
            """, (limit,))
        else:
            cursor.execute("""
                SELECT * FROM price_alerts 
                ORDER BY created_at DESC, id DESC 
                LIMIT ?
            """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def mark_alerts_as_read(alert_ids: Optional[List[int]] = None) -> int:
    """Marks specified alerts or all unread alerts as read."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if alert_ids:
            placeholders = ",".join("?" for _ in alert_ids)
            cursor.execute(f"UPDATE price_alerts SET is_read = 1 WHERE id IN ({placeholders})", alert_ids)
        else:
            cursor.execute("UPDATE price_alerts SET is_read = 1 WHERE is_read = 0")
        conn.commit()
        return cursor.rowcount

def get_unread_alerts_count() -> int:
    """Returns total count of unread price alerts."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(id) as cnt FROM price_alerts WHERE is_read = 0")
        row = cursor.fetchone()
        return row["cnt"] if row else 0

def clear_all_products_and_history():
    """Clears all products, price history, and alerts for a clean database reseed."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM price_alerts")
        cursor.execute("DELETE FROM price_history")
        cursor.execute("DELETE FROM products")
        conn.commit()

def get_all_products() -> List[Dict[str, Any]]:
    """Fetches all products ordered by group, category and title."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY product_group, category, title")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_products_by_group(group: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches products filtered by group ('acer_monitors' or 'other_products')."""
    if not group or group.lower() in ("all", "both"):
        return get_all_products()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM products 
            WHERE LOWER(product_group) = LOWER(?) 
            ORDER BY category, title
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
