import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = BASE_DIR / "exports"
STATIC_DIR = BASE_DIR / "app" / "static"

DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_PATH = str(DATA_DIR / "tracker.db")

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
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Number of historical months to generate/track
HISTORY_MONTHS_COUNT = 22
CURRENCY_SYMBOL = "₹" if DEFAULT_REGION == "in" else "$"
CURRENCY_CODE = "INR" if DEFAULT_REGION == "in" else "USD"
