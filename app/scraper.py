import re
import time
import gc
import logging
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime
from bs4 import BeautifulSoup

from app.config import (
    BASE_AMAZON_URL, DEFAULT_HEADERS,
    GROUP_ACER_MONITORS, GROUP_OTHER_PRODUCTS, GROUP_ALL,
    SCRAPER_MAX_WORKERS, now_ist, now_ist_str,
    SCRAPER_API_KEYS, SCRAPER_API_KEY, SCRAPERAPI_URL, SCRAPERAPI_COUNTRY, SCRAPERAPI_TIMEOUT,
    APPROVED_VENDORS
)
from app.database import (
    upsert_product, add_price_history_batch, get_product_by_asin,
    get_products_by_group, get_all_products, record_price_change
)
from app.seed_data import ACER_SEED_PRODUCTS
from app.history_engine import seed_custom_asin_timeline

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("amazon_scraper")

# Thread-safe round-robin ScraperAPI key selector
_scraper_key_lock = threading.Lock()
_scraper_key_idx = 0

def get_ordered_scraper_keys() -> List[str]:
    """Returns all ScraperAPI keys starting with the next round-robin key, for load-balancing and failover."""
    global _scraper_key_idx
    pool = [k for k in SCRAPER_API_KEYS if k]
    if not pool:
        return [SCRAPER_API_KEY] if SCRAPER_API_KEY else []
    with _scraper_key_lock:
        start_idx = _scraper_key_idx % len(pool)
        _scraper_key_idx += 1
    return pool[start_idx:] + pool[:start_idx]

def extract_seller_name(soup) -> Optional[str]:
    """Extracts the active winning seller / merchant name from the Amazon page."""
    seller_el = soup.select_one("#sellerProfileTriggerId")
    if seller_el and seller_el.get_text().strip():
        return seller_el.get_text().strip()
    tabular = soup.select_one('#tabular-buybox .tabular-buybox-text[tabular-attribute-name="Sold by"]')
    if tabular and tabular.get_text().strip():
        return tabular.get_text().strip()
    merchant_info = soup.select_one("#merchant-info")
    if merchant_info:
        m_text = merchant_info.get_text().strip()
        match = re.search(r"sold by\s+([^.\n\r]+?)(?:\s+and\s+fulfilled|\s+and\s+ships|\.|$)", m_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        if m_text and len(m_text) < 80:
            return m_text
    mob_seller = soup.select_one("#shipsFromSoldBy_feature_div, #shipsFromSoldByInsideBuyBox_feature_div")
    if mob_seller:
        m_text = mob_seller.get_text().strip()
        match = re.search(r"sold by\s+([^.\n\r]+?)(?:\s+and|\.|$)", m_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def get_seed_fallback(asin: str) -> Optional[Dict[str, Any]]:
    """Returns baseline metadata from verified seed catalog if database record is missing."""
    for p in ACER_SEED_PRODUCTS:
        if p["asin"] == asin:
            grp = p.get("product_group")
            if not grp:
                cat = p.get("category", "").lower()
                grp = GROUP_ACER_MONITORS if ("stand" in cat or "screen" in cat or "monitor" in cat) else GROUP_OTHER_PRODUCTS
            return {
                "asin": p["asin"],
                "title": p["title"],
                "category": p["category"],
                "product_group": grp,
                "mrp": p["mrp"],
                "current_price": p["base_price"],
                "currency": "INR",
                "stock_status": p.get("stock_status", "In Stock"),
                "rating": p.get("rating", 4.2),
                "review_count": p.get("review_count", 100),
                "image_url": p.get("image_url"),
                "url": p.get("amazon_link") or f"{BASE_AMAZON_URL}/dp/{asin}",
                "last_scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    return None

def parse_price(price_str: Optional[str]) -> Optional[float]:
    """Cleans and extracts a numeric price float from an Amazon price string.
    Handles Indian number formatting (₹1,29,999.00), stray dots, trailing commas,
    and whitespace/newlines injected by Amazon's DOM rendering.
    """
    if not price_str:
        return None
    text = price_str.strip()
    # Remove currency symbols, whitespace, and non-numeric chars except digits, dots, commas
    text = re.sub(r'[₹$€£\s\xa0]', '', text)
    # Remove commas used as thousands separators (Indian: 1,29,999 or Western: 129,999)
    text = text.replace(',', '')
    # Handle multiple dots — keep only the last one as decimal point
    parts = text.split('.')
    if len(parts) > 2:
        text = ''.join(parts[:-1]) + '.' + parts[-1]
    # Remove any remaining non-numeric chars except the decimal dot
    text = re.sub(r'[^\d.]', '', text)
    # Strip trailing dot (e.g. "12999.")
    text = text.rstrip('.')
    if not text:
        return None
    try:
        val = float(text)
        return val if val > 0 else None
    except ValueError:
        return None

def _extract_complete_price_from_element(elem) -> Optional[float]:
    """Extracts a complete price from an .a-price element by combining
    .a-price-whole and .a-price-fraction, or using .a-offscreen as the clean source.
    """
    if not elem:
        return None
    # Best: .a-offscreen contains the full formatted price string (e.g. "₹12,999.00")
    offscreen = elem.select_one('span.a-offscreen')
    if offscreen:
        val = parse_price(offscreen.get_text())
        if val and val > 0:
            return val
    # Fallback: combine .a-price-whole + .a-price-fraction
    whole_el = elem.select_one('.a-price-whole')
    if whole_el:
        whole_text = whole_el.get_text().strip().rstrip('.')
        frac_el = elem.select_one('.a-price-fraction')
        frac_text = frac_el.get_text().strip() if frac_el else '00'
        combined = f"{whole_text}.{frac_text}"
        val = parse_price(combined)
        if val and val > 0:
            return val
    return None

def _extract_json_ld_price(soup) -> Optional[float]:
    """Extracts product price from JSON-LD structured data embedded in the page.
    This is the most stable source — Amazon serves it for SEO/accessibility.
    """
    import json
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
            # Handle both single object and array of objects
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get('@type') == 'Product':
                    offers = item.get('offers', {})
                    # 'offers' can be a single Offer or AggregateOffer
                    if isinstance(offers, list):
                        prices = []
                        for o in offers:
                            p = o.get('price') or o.get('lowPrice')
                            if p:
                                try:
                                    prices.append(float(p))
                                except (ValueError, TypeError):
                                    pass
                        if prices:
                            return min(p for p in prices if p > 0)
                    elif isinstance(offers, dict):
                        # AggregateOffer has lowPrice; Offer has price
                        for key in ('lowPrice', 'price'):
                            p = offers.get(key)
                            if p:
                                try:
                                    pf = float(p)
                                    if pf > 0:
                                        return pf
                                except (ValueError, TypeError):
                                    pass
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue
    return None

def fetch_page_content(url: str, asin: Optional[str] = None) -> Optional[str]:
    """
    Fetches HTML content from Amazon.
    If SCRAPER_API_KEY is configured:
      Routes the request through ScraperAPI Indian residential proxies with Indian locale cookies,
      completely bypassing Amazon datacenter IP blocks & CAPTCHAs.
    Otherwise (or if ScraperAPI fails):
      Falls back to curl_cffi with Chrome TLS impersonation, mobile web fallback (/gp/aw/d/{asin}),
      and standard requests.
    """
    cookies = {
        "i18n-prefs": "INR",
        "lc-acbin": "en_IN",
    }

    # 0. Primary Attempt: ScraperAPI Residential Proxy Pool with automatic failover
    keys_to_try = get_ordered_scraper_keys()
    if keys_to_try:
        import requests
        for k_idx, key in enumerate(keys_to_try):
            masked_key = f"{key[:6]}...{key[-4:]}"
            try:
                scraper_params = {
                    "api_key": key,
                    "url": url,
                    "country_code": SCRAPERAPI_COUNTRY,
                    "keep_headers": "true"
                }
                scraper_headers = {
                    "Cookie": "i18n-prefs=INR; lc-acbin=en_IN;",
                    "Accept-Language": "en-IN,en;q=0.9",
                }
                resp = requests.get(
                    SCRAPERAPI_URL,
                    params=scraper_params,
                    headers=scraper_headers,
                    timeout=SCRAPERAPI_TIMEOUT
                )
                if resp.status_code == 200 and "Type the characters you see in this image" not in resp.text:
                    logger.info(f"ScraperAPI residential fetch succeeded for ASIN {asin or url} via key {masked_key}.")
                    return resp.text
                elif resp.status_code == 404:
                    logger.info(f"ASIN {asin or url} returned 404 Not Found from Amazon via ScraperAPI.")
                    return "404_NOT_FOUND"
                elif resp.status_code in (401, 403, 429):
                    logger.warning(f"ScraperAPI key {masked_key} returned status {resp.status_code}. Failing over to next key ({k_idx+1}/{len(keys_to_try)})...")
                    continue
                else:
                    logger.warning(f"ScraperAPI returned status {resp.status_code} for {url} via key {masked_key}.")
            except Exception as e:
                logger.warning(f"ScraperAPI fetch failed ({e}) for {url} via key {masked_key}. Trying next key...")
                continue

    # 1. Direct Attempt: Standard /dp/ URL with Chrome impersonation
    try:
        from curl_cffi import requests as curl_requests
        response = curl_requests.get(
            url,
            headers=DEFAULT_HEADERS,
            cookies=cookies,
            impersonate="chrome124",
            timeout=15,
            allow_redirects=True
        )
        if response.status_code == 200 and "Type the characters you see in this image" not in response.text:
            return response.text
        if response.status_code == 404:
            return "404_NOT_FOUND"
        logger.warning(f"curl_cffi primary attempt for {url} returned status {response.status_code} or CAPTCHA.")
    except Exception as e:
        logger.warning(f"curl_cffi primary fetch failed ({e}), trying fallback...")

    # 2. Secondary Attempt: Mobile Web (/gp/aw/d/{asin}) which bypasses bot detection
    if asin:
        mobile_url = f"https://www.amazon.in/gp/aw/d/{asin}"
        mobile_headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        }
        try:
            from curl_cffi import requests as curl_requests
            response = curl_requests.get(
                mobile_url,
                headers=mobile_headers,
                cookies=cookies,
                impersonate="safari15_5",
                timeout=15,
                allow_redirects=True
            )
            if response.status_code == 200 and "Type the characters you see in this image" not in response.text:
                logger.info(f"Mobile web fallback succeeded for ASIN {asin}.")
                return response.text
            if response.status_code == 404:
                return "404_NOT_FOUND"
        except Exception as e:
            logger.warning(f"Mobile fallback failed ({e}) for ASIN {asin}.")

    # 3. Tertiary Attempt: Standard Python requests with session
    try:
        import requests
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        response = session.get(url, cookies=cookies, timeout=15)
        if response.status_code == 200 and "Type the characters you see in this image" not in response.text:
            return response.text
        if response.status_code == 404:
            return "404_NOT_FOUND"
    except Exception as e:
        logger.error(f"All fetch attempts failed for {url}: {e}")

    return None

def scrape_asin_details(
    asin: str,
    group: Optional[str] = None,
    category: Optional[str] = None,
    custom_title: Optional[str] = None,
    custom_mrp: Optional[float] = None
) -> Dict[str, Any]:
    """
    Scrapes live product details for a given ASIN from Amazon.
    Detects price changes and updates database records & history.
    """
    url = f"{BASE_AMAZON_URL}/dp/{asin}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html = fetch_page_content(url, asin=asin)
    
    # Existing product in DB or fallback
    existing = get_product_by_asin(asin) or get_seed_fallback(asin)
    prev_price = existing.get("current_price") if existing else None

    # Handle delisted / 404 products immediately
    if html == "404_NOT_FOUND":
        logger.info(f"ASIN {asin}: Page is delisted or 404 on Amazon. Updating as Out of Stock.")
        if existing:
            updated_product = dict(existing)
            updated_product["stock_status"] = "Out of Stock"
            updated_product["last_scraped_at"] = now_str
            upsert_product(updated_product)
            return {
                "asin": asin,
                "success": True,
                "price_changed": False,
                "price_dropped": False,
                "previous_price": prev_price,
                "new_price": prev_price,
                "change_info": None,
                "drop_info": None,
                "message": f"Product {asin} is delisted/unavailable on Amazon. Marked Out of Stock.",
                "data": updated_product
            }
    
    if not html:
        logger.warning(f"Could not retrieve HTML for ASIN {asin}, maintaining database state.")
        if not existing and (custom_title or custom_mrp):
            # Create synthetic fallback entry for new custom ASIN
            est_price = (custom_mrp * 0.85) if custom_mrp else 14999.0
            new_prod = {
                "asin": asin,
                "title": custom_title or f"Product {asin}",
                "category": category or ("Monitors" if group == GROUP_ACER_MONITORS else "Other"),
                "product_group": group or GROUP_ACER_MONITORS,
                "mrp": custom_mrp or (est_price * 1.25),
                "current_price": est_price,
                "currency": "INR",
                "stock_status": "In Stock",
                "rating": 4.2,
                "review_count": 50,
                "image_url": "https://m.media-amazon.com/images/I/41x9hS0F8oL._SX300_SY300_QL70_FMwebp_.jpg",
                "url": url,
                "last_scraped_at": now_str
            }
            seed_custom_asin_timeline(asin, est_price, new_prod["mrp"], new_prod)
            return {
                "asin": asin,
                "success": True,
                "price_changed": True,
                "message": f"Initialized ASIN {asin} with synthetic historical baseline.",
                "data": new_prod
            }
            
        return {
            "asin": asin,
            "success": False,
            "price_changed": False,
            "message": "Amazon rate-limited live crawl. Retaining verified catalog state.",
            "data": existing
        }

    soup = BeautifulSoup(html, "html.parser")
    
    # Check for CAPTCHA / bot detection page
    if "Type the characters you see in this image" in html or "api-services-support@amazon.com" in html:
        logger.warning(f"Amazon CAPTCHA encountered for ASIN {asin}")
        return {
            "asin": asin,
            "success": False,
            "price_changed": False,
            "message": "Amazon CAPTCHA encountered",
            "data": existing
        }

    # 1. Title Extraction
    title = None
    title_elem = soup.select_one("#productTitle")
    if title_elem:
        title = title_elem.get_text().strip()
    elif custom_title:
        title = custom_title
    elif existing:
        title = existing.get("title")

    # 2. Main Product Container, Seller Identification & Out-of-Stock Detection
    center_col = soup.select_one("#centerCol") or soup.select_one("#desktop_buybox") or soup.select_one("#apex_desktop") or soup.select_one("#ppd")
    
    seller_name = extract_seller_name(soup)

    stock_status = "In Stock"
    avail_blocks = [
        soup.select_one("#availability"),
        soup.select_one("#outOfStock"),
        soup.select_one("#outOfStockBuyBox_feature_div"),
        soup.select_one("#availabilityInsideBuyBox_feature_div"),
        soup.select_one("#shipsFromSoldByInsideBuyBox_feature_div")
    ]
    for ab in avail_blocks:
        if ab:
            txt = ab.get_text().strip().lower()
            if "currently unavailable" in txt or "out of stock" in txt or "we don't know when or if" in txt or "temporarily out of stock" in txt:
                stock_status = "Out of Stock"
                break
            elif "left in stock" in txt or "in stock" in txt:
                stock_status = "In Stock"

    # Check buybox container text directly for out-of-stock signals
    buybox_container = soup.select_one("#desktop_buybox, #buybox, #mobile_buybox")
    if buybox_container and stock_status != "Out of Stock":
        bb_txt = buybox_container.get_text().lower()
        if "currently unavailable" in bb_txt or "we don't know when or if this item will be back in stock" in bb_txt:
            stock_status = "Out of Stock"

    # Verify an active purchase button exists in the buybox
    has_buybox_button = bool(soup.select_one(
        "#add-to-cart-button:not([disabled]), #buy-now-button:not([disabled]), "
        "input[name='submit.add-to-cart']:not([disabled]), #addToCart, #turbo-checkout-pyo-button, "
        "input#add-to-cart-button, input#buy-now-button"
    ))
    unqualified = bool(soup.select_one("#unqualifiedBuyBox, #outOfStockBuyBox_feature_div"))

    if stock_status != "Out of Stock":
        if unqualified and not has_buybox_button:
            is_explicitly_unavailable = any(
                any(neg in (ab.get_text().lower() if ab else "") for neg in ["currently unavailable", "out of stock", "we don't know"])
                for ab in avail_blocks
            )
            if is_explicitly_unavailable:
                stock_status = "Out of Stock"
        elif not has_buybox_button:
            is_explicitly_unavailable = any(
                any(neg in (ab.get_text().lower() if ab else "") for neg in ["currently unavailable", "out of stock", "we don't know"])
                for ab in avail_blocks
            )
            if is_explicitly_unavailable:
                stock_status = "Out of Stock"

    # 3. Live Price Extraction (Strictly prioritizing the current ASIN's displayed buybox price)
    price = None

    # Priority 1: Primary Desktop & Mobile Buybox Price Display
    buybox_price = None
    target_blocks = [
        soup.select_one("#corePriceDisplay_desktop_feature_div"),
        soup.select_one("#corePrice_desktop"),
        soup.select_one("#corePrice_feature_div"),
        soup.select_one("#apex_desktop"),
        soup.select_one("#desktop_buybox"),
        soup.select_one("#buybox"),
        center_col
    ]

    # Selectors using .a-offscreen within primary price block (canonical visible price)
    offscreen_selectors = [
        ".priceToPay span.a-offscreen",
        ".apexPriceToPay span.a-offscreen",
        ".reinventPricePriceToPayMargin span.a-offscreen",
        "#priceblock_dealprice",
        "#priceblock_ourprice",
        "#priceblock_saleprice",
        "span.apex-pricetopay-value",
        "#price_inside_buybox",
        "#newBuyBoxPrice",
        ".a-color-price",
    ]
    for block in target_blocks:
        if not block:
            continue
        for sel in offscreen_selectors:
            elem = block.select_one(sel)
            if elem:
                val = parse_price(elem.get_text())
                if val and val > 0:
                    buybox_price = val
                    break
        if buybox_price:
            break

    # If offscreen selectors didn't match, extract from .priceToPay / .apexPriceToPay elements
    if not buybox_price:
        for block in target_blocks:
            if not block:
                continue
            for a_price_el in block.select('.priceToPay, .apexPriceToPay, .reinventPricePriceToPayMargin, .a-price:not(.a-text-price)'):
                val = _extract_complete_price_from_element(a_price_el)
                if val and val > 0:
                    buybox_price = val
                    break
            if buybox_price:
                break

    # Check hidden buybox price input (canonical customerVisiblePrice)
    if not buybox_price:
        buybox = soup.select_one("#desktop_buybox") or soup.select_one("#buybox")
        if buybox:
            hidden_price_elem = buybox.select_one('input[name*="customerVisiblePrice"][name*="amount"]')
            if hidden_price_elem and hidden_price_elem.get("value"):
                try:
                    val = float(hidden_price_elem.get("value"))
                    if val > 0:
                        buybox_price = val
                except ValueError:
                    pass

    # Priority 2: JSON-LD Structured Data (Only if direct buybox price was not found)
    jsonld_price = None
    if not buybox_price:
        jsonld_price = _extract_json_ld_price(soup)

    # Priority 3: Twister structured buying options (ONLY if exact ASIN match, avoiding multi-variant min() bleed)
    twister_price = None
    if not buybox_price and not jsonld_price:
        twister = soup.select_one(".twister-plus-buying-options-price-data, [data-twister-buying-options]")
        if twister:
            try:
                import json as _json
                t_data = _json.loads(twister.get_text())
                if isinstance(t_data, dict):
                    asin_opts = t_data.get(asin) or t_data.get("desktop_buybox_group_1")
                    if isinstance(asin_opts, list) and asin_opts:
                        pa = asin_opts[0].get("priceAmount")
                        if pa:
                            twister_price = float(pa)
                    elif isinstance(asin_opts, dict):
                        pa = asin_opts.get("priceAmount")
                        if pa:
                            twister_price = float(pa)
            except Exception:
                pass

    # Priority 4: AOD (All Offers Display) / Other Buying Options fallback
    aod_price = None
    if not buybox_price and not jsonld_price and not twister_price:
        for aod_sel in [
            "#aod-ingress-link .a-offscreen",
            "#all-offers-display .a-offscreen",
            "#olp_feature_div .a-offscreen",
            "#dynamic-aod-ingress-box .a-offscreen"
        ]:
            aod_elem = soup.select_one(aod_sel)
            if aod_elem:
                val = parse_price(aod_elem.get_text())
                if val and val > 0:
                    aod_price = val
                    break

    # Final price selection:
    if buybox_price and buybox_price > 0:
        price = buybox_price
    elif jsonld_price and jsonld_price > 0:
        price = jsonld_price
    elif twister_price and twister_price > 0:
        price = twister_price
    elif aod_price and aod_price > 0:
        price = aod_price

    # 4. MRP Extraction (Strictly within center_col / main area)
    mrp = custom_mrp
    scraped_mrp = None
    if center_col:
        mrp_offscreen_selectors = [
            ".apex-basisprice-value .a-offscreen",
            ".basisPrice .a-offscreen",
            "span.a-price.a-text-price .a-offscreen",
            "#corePrice_desktop .a-text-price .a-offscreen",
            "#corePriceDisplay_desktop_feature_div .a-text-price .a-offscreen",
            "#corePrice_feature_div .a-text-price .a-offscreen",
        ]
        for sel in mrp_offscreen_selectors:
            elem = center_col.select_one(sel)
            if elem:
                extracted = parse_price(elem.get_text())
                if extracted and extracted > 0:
                    scraped_mrp = extracted
                    break
        if not scraped_mrp:
            for mrp_el in center_col.select('span.a-price.a-text-price'):
                extracted = _extract_complete_price_from_element(mrp_el)
                if extracted and extracted > 0:
                    scraped_mrp = extracted
                    break

    # Authoritative Seed Catalog Baseline
    seed_item = next((p for p in ACER_SEED_PRODUCTS if p["asin"] == asin), None)
    official_mrp = seed_item.get("mrp") if seed_item else None
    official_base_price = seed_item.get("base_price") if seed_item else None
    existing_mrp = official_mrp or (existing.get("mrp") if existing else None)

    # Use scraped MRP if valid, otherwise fallback to existing/official MRP
    if scraped_mrp and scraped_mrp > 0:
        mrp = scraped_mrp
    elif existing_mrp and existing_mrp > 0:
        mrp = existing_mrp

    # If price was found and mrp is less than price, update mrp to at least price
    if price and mrp and price > mrp:
        mrp = price

    # If no price was found at all on page, set Out of Stock
    if price is None:
        stock_status = "Out of Stock"
        price = official_base_price or (existing.get("current_price") if existing else mrp)

    # 5. Price Sanity Validation (protect against zero/corrupt scrape < 40 INR)
    if price and price < 40:
        logger.warning(f"ASIN {asin}: Scraped price {price} < 40 INR. Retaining previous price.")
        price = official_base_price or (existing.get("current_price") if existing else mrp)

    # 6. Rating and Reviews
    rating = existing.get("rating", 4.2) if existing else 4.2
    rating_elem = soup.select_one("#acrPopover span.a-icon-alt")
    if rating_elem:
        match = re.search(r"([\d.]+)\s+out of", rating_elem.get_text())
        if match:
            try:
                rating = float(match.group(1))
            except ValueError:
                pass

    review_count = existing.get("review_count", 100) if existing else 100
    rev_elem = soup.select_one("#acrCustomerReviewText")
    if rev_elem:
        match = re.search(r"([\d,]+)", rev_elem.get_text())
        if match:
            try:
                review_count = int(match.group(1).replace(",", ""))
            except ValueError:
                pass

    # 7. Real Product Image Extraction
    image_url = None
    # Priority 1: Check main product images for high-res / dynamic URLs
    for img in soup.select("#landingImage, #imgBlkFront, #main-image"):
        if img.get("data-old-hires") and img.get("data-old-hires").startswith("http"):
            image_url = img.get("data-old-hires")
            break
        dyn = img.get("data-a-dynamic-image")
        if dyn:
            try:
                import json
                urls = list(json.loads(dyn).keys())
                if urls and urls[0].startswith("http"):
                    image_url = urls[0]
                    break
            except Exception:
                pass
        src = img.get("src") or ""
        if src.startswith("http") and not src.startswith("data:"):
            image_url = src
            break

    # Priority 2: Fallback to any valid Amazon media image in the left column
    if not image_url:
        for img in soup.select("#imageBlock img, #leftCol img"):
            src = img.get("src") or ""
            if "media-amazon.com/images/I/" in src and not src.startswith("data:"):
                image_url = src
                break

    if not image_url and existing:
        image_url = existing.get("image_url")

    # Render Free Tier Memory Optimization: Free DOM tree from memory immediately
    try:
        del soup
    except Exception:
        pass
    try:
        del html
    except Exception:
        pass
    gc.collect()

    now_str = now_ist_str()
    now_date_str = now_ist_str("%Y-%m-%d")
    now_month_str = now_ist_str("%b %Y")

    # Group determination - default to other_products (accessories)
    target_group = group or (existing.get("product_group") if existing else GROUP_OTHER_PRODUCTS)
    target_category = category or (existing.get("category") if existing else "General")

    final_price = price if price else (existing.get("current_price") if existing else 14999.0)
    final_mrp = mrp if mrp else (existing.get("mrp") if existing else (final_price * 1.25))
    
    # Preserve verified catalog title format matching Model & Part No
    final_title = existing.get("title") if (existing and existing.get("title")) else (title or f"Product {asin}")
    
    # Prevent Prime badge or low-quality fallback from overwriting verified image
    if not image_url or "prime" in image_url or "marketing" in image_url or "transparent" in image_url:
        if existing and existing.get("image_url"):
            image_url = existing.get("image_url")

    updated_product = {
        "asin": asin,
        "title": final_title,
        "model": existing.get("model") if existing else None,
        "part_no": existing.get("part_no") if existing else None,
        "category": target_category,
        "product_group": target_group,
        "sort_order": existing.get("sort_order", 999) if existing else 999,
        "mrp": final_mrp,
        "current_price": final_price,
        "currency": existing.get("currency", "INR") if existing else "INR",
        "stock_status": stock_status,
        "seller_name": seller_name,
        "rating": rating,
        "review_count": review_count,
        "image_url": image_url,
        "url": url,
        "last_scraped_at": now_str
    }

    # If first time seeing this product, seed historical timeline
    if not existing:
        seed_custom_asin_timeline(asin, final_price, final_mrp, updated_product)
    else:
        upsert_product(updated_product)

    # Check if price changed (either dropped or increased)
    price_changed = (prev_price is not None and abs(prev_price - final_price) > 0.01)
    price_dropped = (prev_price is not None and final_price < prev_price - 0.01)
    change_info = None

    if price_changed:
        change_info = record_price_change(
            asin=asin,
            title=final_title,
            category=target_category,
            product_group=target_group,
            previous_price=prev_price,
            new_price=final_price,
            timestamp=now_str
        )
        logger.info(f"PRICE CHANGE: ASIN {asin} changed from ₹{prev_price} to ₹{final_price} ({'drop' if price_dropped else 'increase'})!")

    # Append live point to history
    add_price_history_batch([{
        "asin": asin,
        "timestamp": now_date_str,
        "month_label": now_month_str,
        "price": final_price,
        "is_sale": 1 if price_dropped else 0,
        "sale_tag": "Price Drop" if price_dropped else ("Price Change" if price_changed else "Live Crawl"),
        "source": "live_scraper"
    }])

    return {
        "asin": asin,
        "success": True,
        "price_changed": price_changed,
        "price_dropped": price_dropped,
        "previous_price": prev_price,
        "new_price": final_price,
        "change_info": change_info,
        "drop_info": change_info,
        "message": f"Updated ASIN {asin} (Price: {final_price})",
        "data": updated_product
    }

def scrape_all_asins(group: Optional[str] = None) -> Dict[str, Any]:
    """
    Scrapes all tracked products for a specific group or full portfolio.
    Detects price changes, logs verified changes, and triggers Excel auto-regeneration.
    Memory optimized for Render Free Tier (256MB RAM).
    """
    from app.excel_exporter import export_excel_by_group
    from app.history_engine import seed_database_if_empty

    products = get_products_by_group(group)
    if not products:
        seed_database_if_empty()
        products = get_products_by_group(group)

    results = []
    any_price_changed = False
    price_changes_found = []

    from concurrent.futures import ThreadPoolExecutor

    def _scrape_one(p):
        a = p["asin"]
        logger.info(f"Crawling ASIN: {a} (Group: {p.get('product_group')})...")
        time.sleep(0.15)  # Polite throttle to smooth CPU/RAM spikes
        return scrape_asin_details(a, group=p.get("product_group"), category=p.get("category"))

    with ThreadPoolExecutor(max_workers=SCRAPER_MAX_WORKERS) as executor:
        results = list(executor.map(_scrape_one, products))

    # Free memory after full batch
    gc.collect()

    for res in results:
        if res.get("price_changed"):
            any_price_changed = True
        if res.get("change_info"):
            price_changes_found.append(res.get("change_info"))

    # Dynamic Trigger: Sequential Excel export
    try:
        target_grp = group or GROUP_ALL
        export_excel_by_group(target_grp)
        gc.collect()
        logger.info(f"Dynamic Excel export auto-regenerated for group '{target_grp}'.")
    except Exception as e:
        logger.error(f"Failed to auto-export Excel: {e}")

    return {
        "total": len(products),
        "group": group or "all",
        "any_price_changed": any_price_changed,
        "price_changes_count": len(price_changes_found),
        "price_changes": price_changes_found,
        "results": results,
        "completed_at": now_ist_str()
    }
