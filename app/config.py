import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Indian Standard Time (IST) definitions
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist() -> datetime:
    """Returns current datetime in Indian Standard Time (IST, UTC+5:30)."""
    return datetime.now(timezone.utc).astimezone(IST)

def now_ist_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Returns formatted string of current IST datetime."""
    return now_ist().strftime(fmt)

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent

# Check if running in Vercel Serverless environment
IS_VERCEL = os.getenv("VERCEL") == "1" or os.getenv("NOW_REGION") is not None

if IS_VERCEL:
    DATA_DIR = Path("/tmp/data")
    EXPORTS_DIR = Path("/tmp/exports")
else:
    DATA_DIR = BASE_DIR / "data"
    EXPORTS_DIR = BASE_DIR / "exports"

DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_PATH = str(DATA_DIR / "tracker.db")
STATIC_DIR = BASE_DIR / "app" / "static"

# Scraper Settings
DEFAULT_REGION = os.getenv("AMAZON_REGION", "in")  # 'in' for amazon.in, 'com' for amazon.com
AMAZON_DOMAINS = {
    "in": "https://www.amazon.in",
    "com": "https://www.amazon.com",
    "co.uk": "https://www.amazon.co.uk",
    "de": "https://www.amazon.de",
}
BASE_AMAZON_URL = AMAZON_DOMAINS.get(DEFAULT_REGION, "https://www.amazon.in")

# Request Headers rotation
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Number of historical months to generate/track
HISTORY_MONTHS_COUNT = 6
CURRENCY_SYMBOL = "₹" if DEFAULT_REGION == "in" else "$"
CURRENCY_CODE = "INR" if DEFAULT_REGION == "in" else "USD"

# Product Groups
GROUP_ACER_MONITORS = "acer_monitors"
GROUP_OTHER_PRODUCTS = "other_products"
GROUP_ALL = "all"

# Excel Export File Names
EXCEL_MONITORS_FILENAME = "Acer_Monitors_Price_Tracker.xlsx"
EXCEL_OTHER_FILENAME = "Other_Products_Price_Tracker.xlsx"
EXCEL_ALL_FILENAME = "All_Products_Price_Tracker.xlsx"

# ScraperAPI Settings (Residential proxy rotation to bypass Amazon bot blocks)
SCRAPER_API_KEY = (
    os.getenv("SCRAPER_API") or
    os.getenv("SCRAPERAPI_KEY") or
    os.getenv("SCRAPER_API_KEY") or
    ""
).strip("\"' \t\r\n")

SCRAPERAPI_URL = "https://api.scraperapi.com"
SCRAPERAPI_COUNTRY = os.getenv("SCRAPERAPI_COUNTRY", "in")
SCRAPERAPI_TIMEOUT = int(os.getenv("SCRAPERAPI_TIMEOUT", "50"))

# Automated Crawl Schedule (IST hours):
# Default: 10 AM IST daily (conserves API credits for 30 days continuous operation within free tier)
# Can be overridden via SYNC_HOURS env var (e.g. "9,11,13,15,17,19,21" or "10")
_env_sync_hours = os.getenv("SYNC_HOURS")
if _env_sync_hours:
    SYNC_INTERVAL_HOURS = [int(h.strip()) for h in _env_sync_hours.split(",") if h.strip().isdigit()]
elif SCRAPER_API_KEY:
    SYNC_INTERVAL_HOURS = [10]  # 10:00 AM IST daily (~4,500 credits/mo, safely within 5,000 free tier)
else:
    SYNC_INTERVAL_HOURS = [9, 11, 13, 15, 17, 19, 21]

# Render Free Tier Memory Optimization (256MB RAM):
# Limit scraper threads to 2 to prevent RAM spikes from concurrent DOM parsers
SCRAPER_MAX_WORKERS = 2

# Approved Authorized Amazon Vendors (Case-insensitive matching)
# Only offers from these verified vendors are accepted as "In Stock".
# Unapproved third-party or scalper sellers will be marked "Out of Stock".
DEFAULT_APPROVED_VENDORS = [
    "appario retail",
    "cocoblu retail",
    "acer official",
    "acer india",
    "dawntech electronics",
    "amazon retail",
    "amazon.in"
]
_env_vendors = os.getenv("APPROVED_VENDORS")
if _env_vendors:
    APPROVED_VENDORS = [v.strip().lower() for v in _env_vendors.split(",") if v.strip()]
else:
    APPROVED_VENDORS = DEFAULT_APPROVED_VENDORS


