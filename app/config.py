import os
from pathlib import Path

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
HISTORY_MONTHS_COUNT = 22
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

# Automated Daily Crawl Schedule (Hourly intervals daily starting at 9:00 AM)
SYNC_INTERVAL_HOURS = list(range(9, 23))  # 9 AM, 10 AM, 11 AM, 12 PM, 1 PM, ..., 10 PM


