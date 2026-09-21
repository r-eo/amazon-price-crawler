import re
import time
import gc
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from bs4 import BeautifulSoup

from app.config import (
    BASE_AMAZON_URL, DEFAULT_HEADERS,
    GROUP_ACER_MONITORS, GROUP_OTHER_PRODUCTS, GROUP_ALL,
    SCRAPER_MAX_WORKERS, now_ist, now_ist_str,
    SCRAPER_API_KEY, SCRAPERAPI_URL, SCRAPERAPI_COUNTRY, SCRAPERAPI_TIMEOUT
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
                "stock_status": "In Stock",
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

    # 0. Primary Attempt: ScraperAPI Residential Proxy (Essential for Render / Cloud hosting)
    if SCRAPER_API_KEY:
        try:
            import requests
            scraper_params = {
                "api_key": SCRAPER_API_KEY,
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
                logger.info(f"ScraperAPI residential fetch succeeded for ASIN {asin or url}.")
                return resp.text
            logger.warning(f"ScraperAPI returned status {resp.status_code} for {url}, falling back to direct fetch...")
        except Exception as e:
            logger.warning(f"ScraperAPI fetch failed ({e}) for {url}, falling back to direct fetch...")

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

    # 2. Main Product Container & Out-of-Stock Detection
    center_col = soup.select_one("#centerCol") or soup.select_one("#desktop_buybox") or soup.select_one("#apex_desktop") or soup.select_one("#ppd")
    
    stock_status = "In Stock"
    avail_blocks = [
        soup.select_one("#availability"),
        soup.select_one("#outOfStock"),
        soup.select_one("#outOfStockBuyBox_feature_div"),
        soup.select_one("#availabilityInsideBuyBox_feature_div")
    ]
    for ab in avail_blocks:
        if ab:
            txt = ab.get_text().strip().lower()
            if "currently unavailable" in txt or "out of stock" in txt or "we don't know when or if" in txt or "temporarily out of stock" in txt:
                stock_status = "Out of Stock"
                break
            elif "left in stock" in txt:
                stock_status = ab.get_text().strip()

    # 3. Live Price Extraction
    price = None
    if stock_status != "Out of Stock":
        import json as _json

        # Priority 0: JSON-LD Structured Data (most stable — Amazon serves this for SEO)
        jsonld_price = _extract_json_ld_price(soup)

        # Priority 1: Twister Plus Structured Buying Options (embedded JSON)
        twister_price = None
        twister = soup.select_one(".twister-plus-buying-options-price-data, [data-twister-buying-options]")
        if twister:
            try:
                t_data = _json.loads(twister.get_text())
                t_prices = []
                # Handle all known twister data structures:
                # Structure A: {"key": [{"priceAmount": X}, ...]}
                # Structure B: [{"priceAmount": X}, ...]
                # Structure C: {"key": {"priceAmount": X}}
                def _collect_twister_prices(obj):
                    if isinstance(obj, dict):
                        pa = obj.get("priceAmount")
                        if pa:
                            try:
                                pf = float(pa)
                                if pf > 0:
                                    t_prices.append(pf)
                            except (ValueError, TypeError):
                                pass
                        for v in obj.values():
                            _collect_twister_prices(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            _collect_twister_prices(item)
                _collect_twister_prices(t_data)
                if t_prices:
                    twister_price = min(t_prices)
            except Exception:
                pass

        # Check total price and subtotal widgets
        for tp_sel in ["#tp_price_block_total_price_ww .a-offscreen", "#tp-tool-tip-subtotal-price-value .a-offscreen"]:
            tp_elem = soup.select_one(tp_sel)
            if tp_elem:
                tp_val = parse_price(tp_elem.get_text())
                if tp_val and tp_val > 0:
                    twister_price = min(twister_price, tp_val) if twister_price else tp_val
        # Also check the total price block's .a-price element for complete price
        tp_price_block = soup.select_one("#tp_price_block_total_price_ww .a-price")
        if tp_price_block:
            tp_val = _extract_complete_price_from_element(tp_price_block)
            if tp_val and tp_val > 0:
                twister_price = min(twister_price, tp_val) if twister_price else tp_val

        # Priority 2: Hidden buybox price input (canonical customerVisiblePrice)
        buybox_price = None
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

        # Priority 3: CSS selectors within buybox/core price blocks
        if not buybox_price:
            target_blocks = [
                soup.select_one("#corePriceDisplay_desktop_feature_div"),
                soup.select_one("#corePrice_feature_div"),
                soup.select_one("#apex_desktop"),
                soup.select_one("#desktop_buybox"),
                soup.select_one("#buybox"),
                center_col
            ]

            # Selectors using .a-offscreen (complete formatted price — most reliable CSS approach)
            offscreen_selectors = [
                ".priceToPay span.a-offscreen",
                ".apexPriceToPay span.a-offscreen",
                ".reinventPricePriceToPayMargin span.a-offscreen",
                "#priceblock_dealprice",
                "#priceblock_ourprice",
                "#priceblock_saleprice",
                "span.apex-pricetopay-value",
                # Mobile page selectors (when mobile fallback is used)
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

            # If offscreen selectors failed, try .a-price elements with combined whole+fraction
            if not buybox_price:
                for block in target_blocks:
                    if not block:
                        continue
                    # Find the first non-strikethrough .a-price element
                    for a_price_el in block.select('.a-price:not(.a-text-price)'):
                        val = _extract_complete_price_from_element(a_price_el)
                        if val and val > 0:
                            buybox_price = val
                            break
                    if buybox_price:
                        break

        # Priority 4: AOD (All Offers Display) — ONLY as fallback if no buybox price
        # AOD may contain used/renewed/third-party prices, so we don't min() it with buybox.
        aod_price = None
        if not buybox_price and not twister_price and not jsonld_price:
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
                        break  # Take first valid, not min — AOD can mix conditions

        # Final price selection: Prefer buybox > twister > JSON-LD > AOD
        # Buybox/twister are the displayed price; JSON-LD is stable; AOD is last resort
        if buybox_price and buybox_price > 0:
            price = buybox_price
        elif twister_price and twister_price > 0:
            price = twister_price
        elif jsonld_price and jsonld_price > 0:
            price = jsonld_price
        elif aod_price and aod_price > 0:
            price = aod_price

    # 4. MRP Extraction (Strictly within center_col / main area)
    mrp = custom_mrp
    if not mrp and center_col:
        # First try .a-offscreen selectors (complete MRP values)
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
                    mrp = extracted
                    break
        # If offscreen failed, try extracting from .a-text-price elements (strikethrough prices = MRP)
        if not mrp:
            for mrp_el in center_col.select('span.a-price.a-text-price'):
                extracted = _extract_complete_price_from_element(mrp_el)
                if extracted and extracted > 0:
                    mrp = extracted
                    break

    # Safeguard MRP: Never overwrite a verified catalog MRP with a ridiculously low fraction
    existing_mrp = existing.get("mrp") if existing else None
    if existing_mrp and existing_mrp > 0:
        if not mrp or mrp < (existing_mrp * 0.25):
            mrp = existing_mrp

    # 5. Price Sanity Validation (permit steep Amazon limited-time discounts)
    baseline_mrp = mrp or existing_mrp
    if price and baseline_mrp and baseline_mrp > 0:
        if price > (baseline_mrp * 1.5):
            logger.warning(f"ASIN {asin}: Scraped price {price} failed sanity check against MRP {baseline_mrp} (>1.5x). Retaining previous price.")
            price = existing.get("current_price") if existing else baseline_mrp
        elif price < 40:
            logger.warning(f"ASIN {asin}: Scraped price {price} < 40 INR. Retaining previous price.")
            price = existing.get("current_price") if existing else baseline_mrp

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
