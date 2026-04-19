#!/usr/bin/env python3
"""
AliExpress Product Scraper
Collects top pet products using Affiliate API
"""

import os
import json
import hashlib
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv("/home/ubuntu/petdeals_bot/config/.env")

BASE_DIR = "/home/ubuntu/petdeals_bot"
DATA_PATH = f"{BASE_DIR}/data/products.json"

# Price range: skip under $5 (low commission) and over $500 (low conversion)
MIN_PRICE_USD = 5
MAX_PRICE_USD = 500

SEARCH_KEYWORDS = [
    # 고양이용품 (cat)
    "cat toy interactive", "cat toy feather wand", "cat litter box",
    "cat litter mat", "cat scratching post", "cat tower tree",
    "cat collar bell", "cat water fountain", "cat carrier bag",
    "cat grooming brush", "cat kicker toy",

    # 강아지용품 (dog)
    "dog toy chew rubber", "dog toy rope", "dog treat training",
    "dog harness vest", "dog leash retractable", "dog collar LED",
    "dog clothes winter", "dog raincoat", "dog ball launcher",
    "dog carrier backpack", "dog squeaky toy",

    # 공통 펫용품 (pet_common)
    "automatic pet feeder", "pet water dispenser",
    "pet nail clipper", "pet grooming brush",
    "pet bed cushion", "pet blanket warm",
    "pet bowl stainless steel", "pet carrier travel bag",

    # 펫 생활용품 (pet_home)
    "pet hair remover roller", "pet waste bag dispenser",
    "pet gate barrier", "pet stairs ramp",
    "pet car seat cover", "pet camera monitor",

    # 펫 장난감 (pet_toys)
    "pet laser pointer", "pet puzzle toy treat",
    "pet tunnel play", "pet treat ball dispenser",

    # 20% general trending (kept for backward compat → mapped to new categories)
    "wireless earbuds bluetooth", "LED strip lights room",
    "portable charger power bank", "car phone mount magnetic",
    "LED desk lamp", "humidifier mini portable",
    "kitchen organizer shelf", "yoga mat thick",

    # 캠핑용품 (camping)
    "camping tent waterproof", "camping chair folding",
    "camping lantern LED", "camping cookware set",
    "camping sleeping bag", "camping table portable",
    "camping hammock outdoor",

    # 전자기기 (electronics)
    "wireless earbuds", "smartwatch fitness tracker",
    "LED strip lights", "bluetooth speaker portable",
    "wireless charger pad", "USB hub adapter",

    # 주방용품 (kitchen)
    "air fryer mini", "tumbler insulated",
    "kitchen storage rack", "knife sharpener",
    "silicone cooking utensils", "vacuum food container",

    # 패션 (fashion)
    "crossbody bag women", "sunglasses polarized",
    "bucket hat unisex", "minimalist wallet",
    "canvas tote bag",

    # 자동차용품 (car)
    "car charger fast", "car air freshener",
    "car phone holder magnetic", "car vacuum cleaner",
    "car seat organizer",

    # 스포츠/건강 (sports)
    "yoga mat non slip", "adjustable dumbbells",
    "massage gun deep", "resistance bands set",
    "foam roller muscle", "jump rope speed",
]

def get_seasonal_keywords() -> list:
    """Return trending keywords for the current month."""
    from datetime import datetime
    month = datetime.now().month
    seasonal = {
        1:  ["winter jacket", "hand warmer electric", "heated blanket", "snow boots"],
        2:  ["valentines gift", "couple items", "heart shaped"],
        3:  ["spring cleaning", "air purifier", "gardening tools"],
        4:  ["rain jacket", "umbrella compact", "spring fashion"],
        5:  ["summer hat UV", "portable fan USB", "sunscreen"],
        6:  ["cooling mat", "beach towel", "swim accessories"],
        7:  ["camping fan", "ice maker", "outdoor cooler"],
        8:  ["back to school", "laptop stand", "desk organizer"],
        9:  ["thermos bottle", "scarf autumn", "hiking gear"],
        10: ["halloween pet costume", "fall camping", "warm gloves"],
        11: ["singles day deals", "winter preparation", "gift set"],
        12: ["christmas gift", "new year planner", "winter warm"],
    }
    return seasonal.get(month, [])


REGIONAL_DOMAINS = {
    "ko": "ko.aliexpress.com",
    "en": "www.aliexpress.com",
    "zh": "www.aliexpress.com",   # zh.aliexpress.com does not exist; www redirects per user IP
}


_CATEGORY_TRACE_SUFFIX = {
    "cat": "_pet", "dog": "_pet", "pet_common": "_pet",
    "pet_home": "_pet", "pet_toys": "_pet",
    "camping": "_camp", "electronics": "_tech",
    "kitchen": "_kitchen", "fashion": "_fashion",
    "car": "_car", "sports": "_sports",
    "etc": "",
}


def build_affiliate_link(product_id: str, lang: str = "ko",
                         category_key: str = "") -> str:
    """Build a reliable, non-expiring affiliate link from a product ID.

    Uses the tracking_id from env so commission is tracked.
    Category suffix enables per-category revenue tracking.
    Falls back to plain product URL if no credentials.
    """
    tracking_id = os.getenv("ALI_TRACKING_ID", "")
    if tracking_id and category_key:
        suffix = _CATEGORY_TRACE_SUFFIX.get(category_key, "")
        tracking_id = f"{tracking_id}{suffix}"
    domain = REGIONAL_DOMAINS.get(lang, "www.aliexpress.com")
    base = f"https://{domain}/item/{product_id}.html"
    if tracking_id:
        return f"{base}?aff_platform=api-new-link-generate&aff_trace_key={tracking_id}"
    return base


def validate_affiliate_link(url: str, timeout: int = 8) -> bool:
    """Return True if the URL resolves to a real AliExpress product page (2xx/3xx).

    On any network error returns True (benefit of the doubt -- don't drop a product
    due to a transient connectivity issue).
    """
    if not url or len(url) < 15:
        return False
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout,
                          headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code in (200, 301, 302, 303, 307, 308):
            return True
        if r.status_code == 404:
            return False
        return True  # 5xx, 429 etc -- assume product exists, don't drop
    except Exception:
        return True  # network error -- keep the product


class AliScraper:
    def __init__(self):
        self.app_key = os.getenv("ALI_APP_KEY")
        self.app_secret = os.getenv("ALI_APP_SECRET")
        self.tracking_id = os.getenv("ALI_TRACKING_ID")
        self.base_url = "https://api-sg.aliexpress.com/sync"

    def _sign_request(self, params: dict) -> str:
        """Generate MD5 API signature."""
        sorted_params = sorted(params.items())
        sign_str = self.app_secret
        for k, v in sorted_params:
            sign_str += f"{k}{v}"
        sign_str += self.app_secret
        return hashlib.md5(sign_str.encode()).hexdigest().upper()

    def _post(self, params: dict) -> dict:
        """Send signed GET request with retry."""
        params["sign"] = self._sign_request(params)
        for attempt in range(3):
            try:
                r = requests.get(self.base_url, params=params, timeout=30)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == 2:
                    print(f"[ALI] Request failed after 3 attempts: {e}")
                    return {}
                time.sleep(2 ** attempt)
        return {}

    def search_products(self, keywords: str, limit: int = 10,
                        min_price_usd: float | None = None,
                        max_price_usd: float | None = None,
                        sort: str = "SALE_PRICE_ASC") -> list:
        """Search products by keyword with optional USD price range + sort."""
        params = {
            "app_key": self.app_key,
            "method": "aliexpress.affiliate.product.query",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sign_method": "md5",
            "keywords": keywords,
            "target_currency": "KRW",
            "target_language": "EN",
            "tracking_id": self.tracking_id,
            "page_size": str(limit),
            "sort": sort,
        }
        if min_price_usd is not None:
            params["min_sale_price"] = f"{min_price_usd:.2f}"
        if max_price_usd is not None:
            params["max_sale_price"] = f"{max_price_usd:.2f}"
        data = self._post(params)
        resp = data.get("aliexpress_affiliate_product_query_response", {})
        return resp.get("resp_result", {}).get("result", {}).get("products", {}).get("product", [])

    def get_hot_products(self, limit: int = 3) -> list:
        """Get hot-selling pet products."""
        params = {
            "app_key": self.app_key,
            "method": "aliexpress.affiliate.hotproduct.query",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sign_method": "md5",
            "target_currency": "KRW",
            "tracking_id": self.tracking_id,
            "page_size": str(limit),
        }
        data = self._post(params)
        resp = data.get("aliexpress_affiliate_hotproduct_query_response", {})
        return resp.get("resp_result", {}).get("result", {}).get("products", {}).get("product", [])

    def get_affiliate_link(self, product_url: str) -> str:
        """Generate affiliate link for a given URL. Returns original URL on failure."""
        params = {
            "app_key": self.app_key,
            "method": "aliexpress.affiliate.link.generate",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sign_method": "md5",
            "promotion_link_type": "0",
            "source_values": product_url,
            "tracking_id": self.tracking_id,
        }
        data = self._post(params)
        resp = data.get("aliexpress_affiliate_link_generate_response", {})
        links = resp.get("resp_result", {}).get("result", {}).get("promotion_links", {}).get("promotion_link", [])
        if links:
            return links[0].get("promotion_link", product_url)
        return product_url

    def get_regional_affiliate_links(self, product_id: int, fallback_link: str = "") -> dict:
        """
        Build region-specific affiliate links.

        Strategy:
        - Generate ONE affiliate link, follow redirect to get params with aff_fcid/sk.
        - KO: use ko.aliexpress.com with full params (works as-is).
        - EN/ZH: use www.aliexpress.com with ONLY essential tracking params
          (strip gatewayAdapt=glo2kor which forces Korean redirect and causes 404 on zh).
          Users outside Korea clicking www links land on their own regional AliExpress.

        Returns: {"ko": url, "en": url, "zh": url}
        """
        import requests as _req
        from urllib.parse import urlparse, parse_qs, urlencode

        # Step 1: generate one tracked short link
        source_url = f"https://www.aliexpress.com/item/{product_id}.html"
        aff_link = self.get_affiliate_link(source_url)
        if aff_link == source_url:
            aff_link = fallback_link or source_url

        # Step 2: follow redirect to get full URL with affiliate params
        try:
            resp = _req.get(aff_link, allow_redirects=True, timeout=15)
            final_url = resp.url
        except Exception as e:
            print(f"[ALI] redirect resolve failed: {e}")
            final_url = f"https://ko.aliexpress.com/item/{product_id}.html"

        # Step 3: extract commission params (strip region-forcing params)
        parsed = urlparse(final_url)
        all_params = parse_qs(parsed.query)
        # These are the only params needed for affiliate commission tracking
        tracking_params = {
            k: all_params[k][0]
            for k in ["aff_fcid", "sk", "aff_platform", "aff_trace_key"]
            if k in all_params
        }
        tracking_qs = urlencode(tracking_params)

        # Step 4: build per-region URLs
        links = {}
        for lang, domain in REGIONAL_DOMAINS.items():
            if lang == "ko":
                # Korean: keep original final_url (already correct ko.aliexpress.com)
                links["ko"] = final_url
            else:
                # EN/ZH: www.aliexpress.com + only tracking params (no gatewayAdapt)
                links[lang] = f"https://{domain}/item/{product_id}.html?{tracking_qs}"

            print(f"[ALI] regional [{lang}]: {links[lang][:75]}")

        return links

    def _normalize(self, product: dict) -> dict:
        """Map raw API fields to standard keys used across the codebase."""
        sale = safe_number(product.get("target_sale_price") or 0)
        app_sale = safe_number(product.get("target_app_sale_price") or 0)
        orig = safe_number(product.get("target_original_price") or 0)

        # Use lowest available price (app price can be lower due to app coupons)
        if app_sale > 0 and (app_sale < sale or sale == 0):
            sale = app_sale

        # Discount: prefer API field, fallback to calc from prices
        discount = int(safe_number(product.get("discount", 0) or 0))
        if discount == 0 and orig > 0 and sale < orig:
            discount = int((orig - sale) / orig * 100)
        # Recalculate discount if we used the lower app price
        if orig > 0 and sale > 0 and sale < orig:
            calc_disc = int((orig - sale) / orig * 100)
            if calc_disc > discount:
                discount = calc_disc
        # If original price missing but discount known, back-calculate it
        if orig == 0 and discount > 0 and sale > 0:
            orig = round(sale / (1 - discount / 100), 2)

        # evaluate_rate is "96.4%" -> store as 96.4 (0-100 scale)
        rating = safe_number(product.get("evaluate_rate") or product.get("rating") or 0)

        product["title"] = product.get("product_title", "")
        product["price"] = sale
        product["original_price"] = orig
        product["discount"] = discount
        product["price_updated_at"] = datetime.now().isoformat()
        product["image_url"] = product.get("product_main_image_url", "")
        product["rating"] = rating  # 0-100 scale
        product["video_url"] = product.get("product_video_url", "")
        # Use promotion_link from search results directly if available
        if not product.get("affiliate_link") and product.get("promotion_link"):
            product["affiliate_link"] = product["promotion_link"]
        # Collect all images for slideshow fallback
        images = []
        main_img = product.get("product_main_image_url", "")
        if main_img:
            images.append(main_img)
        small = product.get("product_small_image_urls", {})
        if isinstance(small, dict):
            for img in small.get("string", []):
                if img and img not in images:
                    images.append(img)
        elif isinstance(small, list):
            for img in small:
                if img and img not in images:
                    images.append(img)
        product["product_images"] = images
        return product

    def _has_video(self, product: dict) -> bool:
        """Return True if product has a valid video URL."""
        url = product.get("product_video_url", "") or product.get("video_url", "")
        return bool(url and url.strip())

    def _passes_filters(self, product: dict, relaxed: bool = False) -> bool:
        """Apply filters. relaxed=True: discount >15%, rating >60, no price limit.
        Video is NOT required -- has_video flag added later for sorting."""
        sale = safe_number(product.get("target_sale_price") or 0)

        if not relaxed:
            # Strict: price $5-$500
            if sale < MIN_PRICE_USD or sale > MAX_PRICE_USD:
                return False

        # Discount check (calc from prices if field is 0)
        orig = safe_number(product.get("target_original_price") or 0)
        discount = int(safe_number(product.get("discount", 0) or 0))
        if discount == 0 and orig > 0 and sale < orig:
            discount = int((orig - sale) / orig * 100)

        min_discount = 15 if relaxed else 20
        if discount <= min_discount:
            return False

        # Rating check: evaluate_rate is 0-100 scale
        rating = safe_number(product.get("evaluate_rate") or product.get("rating") or 0)
        min_rating = 60.0 if relaxed else 70.0
        if rating < min_rating:
            return False

        return True

    def save_products(self, products: list) -> int:
        """Append products to data/products.json. Returns count saved."""
        existing = []
        if os.path.exists(DATA_PATH):
            with open(DATA_PATH) as f:
                existing = json.load(f)

        existing_ids = {str(p.get("product_id", "")) for p in existing
                        if p.get("product_id")}

        ts = datetime.now().isoformat()
        added = 0
        for p in products:
            pid = str(p.get("product_id", ""))
            if pid and pid in existing_ids:
                continue
            p = self._normalize(p)
            p["collected_at"] = ts
            p["uploaded"] = False
            existing.append(p)
            if pid:
                existing_ids.add(pid)
            added += 1

        with open(DATA_PATH, "w") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        return added


# ── Product history: prevent duplicate products across days ──────────────────

HISTORY_FILE = f"{BASE_DIR}/data/product_history.json"
MAX_HISTORY = 2000  # ~90 days x 10 products x buffer


def load_product_history() -> dict:
    """Load history. Returns {"ids": set, "names": list, "entries": list}.

    entries: list of {"id": str, "name": str, "ts": ISO timestamp}
    Older format (ids/names only) is auto-migrated.
    """
    if not os.path.exists(HISTORY_FILE):
        return {"ids": set(), "names": [], "entries": []}
    try:
        with open(HISTORY_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return {"ids": set(data), "names": [], "entries": []}
        entries = data.get("entries", [])
        ids = set(data.get("ids", []))
        names = data.get("names", [])
        # Backfill ids/names from entries if empty
        for e in entries:
            if e.get("id"):
                ids.add(e["id"])
            if e.get("name") and e["name"] not in names:
                names.append(e["name"])
        return {"ids": ids, "names": names, "entries": entries}
    except Exception:
        return {"ids": set(), "names": [], "entries": []}


def save_to_history(product_id: str, product_name: str = ""):
    """Append a product to the history file with timestamp."""
    history = load_product_history()
    ts = datetime.now().isoformat()
    if product_id:
        history["ids"].add(str(product_id))
    if product_name and product_name not in history["names"]:
        history["names"].append(product_name)
    history["entries"].append({
        "id": str(product_id) if product_id else "",
        "name": product_name,
        "ts": ts,
    })
    # Trim to MAX_HISTORY
    if len(history["entries"]) > MAX_HISTORY:
        history["entries"] = history["entries"][-MAX_HISTORY:]
    if len(history["ids"]) > MAX_HISTORY:
        ids_sorted = sorted(history["ids"])
        history["ids"] = set(ids_sorted[-MAX_HISTORY:])
        history["names"] = history["names"][-MAX_HISTORY:]
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump({
            "ids": list(history["ids"]),
            "names": history["names"],
            "entries": history["entries"],
        }, f)


def cleanup_old_history(max_age_days: int = 30) -> int:
    """Remove history entries older than max_age_days. Returns count removed."""
    history = load_product_history()
    if not history["entries"]:
        return 0

    cutoff = datetime.now() - __import__("datetime").timedelta(days=max_age_days)
    cutoff_iso = cutoff.isoformat()

    new_entries = [e for e in history["entries"] if e.get("ts", "") >= cutoff_iso]
    removed = len(history["entries"]) - len(new_entries)
    if removed == 0:
        return 0

    # Rebuild ids/names from remaining entries
    new_ids = set()
    new_names = []
    for e in new_entries:
        if e.get("id"):
            new_ids.add(e["id"])
        if e.get("name") and e["name"] not in new_names:
            new_names.append(e["name"])

    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump({
            "ids": list(new_ids),
            "names": new_names,
            "entries": new_entries,
        }, f)

    # Log cleanup
    log_path = os.path.join(BASE_DIR, "logs", "cleanup.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as lf:
        lf.write(f"{datetime.now().isoformat()} | cleanup: removed {removed} entries "
                 f"older than {max_age_days}d, kept {len(new_entries)}\n")

    return removed


def emergency_trim_history(keep_ratio: float = 0.5) -> int:
    """Emergency trim: remove oldest entries to recover from 0-product situation."""
    history = load_product_history()
    total = len(history["entries"])
    if total == 0:
        # No entries -- just clear ids/names (old format)
        old_count = len(history["ids"])
        if old_count == 0:
            return 0
        keep = int(old_count * keep_ratio)
        ids_sorted = sorted(history["ids"])
        new_ids = set(ids_sorted[-keep:]) if keep else set()
        new_names = history["names"][-keep:] if keep else []
        with open(HISTORY_FILE, "w") as f:
            json.dump({"ids": list(new_ids), "names": new_names, "entries": []}, f)
        removed = old_count - len(new_ids)
    else:
        keep = int(total * keep_ratio)
        new_entries = history["entries"][-keep:] if keep else []
        new_ids = set()
        new_names = []
        for e in new_entries:
            if e.get("id"):
                new_ids.add(e["id"])
            if e.get("name") and e["name"] not in new_names:
                new_names.append(e["name"])
        with open(HISTORY_FILE, "w") as f:
            json.dump({
                "ids": list(new_ids),
                "names": new_names,
                "entries": new_entries,
            }, f)
        removed = total - len(new_entries)

    log_path = os.path.join(BASE_DIR, "logs", "cleanup.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as lf:
        lf.write(f"{datetime.now().isoformat()} | EMERGENCY trim: removed {removed} "
                 f"entries (kept {keep_ratio:.0%})\n")
    return removed


def is_duplicate_by_name(product_name: str, history_names: list) -> bool:
    """Return True if a similar product name was already used."""
    name_l = product_name.lower().strip()
    for past in history_names:
        past_l = past.lower().strip()
        if name_l == past_l:
            return True
        # Substring containment on names >15 chars
        shorter, longer = (
            (name_l, past_l) if len(name_l) <= len(past_l) else (past_l, name_l)
        )
        if len(shorter) > 15 and shorter in longer:
            return True
    return False


def safe_number(value, default=0) -> float:
    """Convert any value to float. Handles '51%', '$29.99', '1,234', etc."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = (
            value.replace("%", "").replace("$", "").replace(",", "")
                 .replace("\uffed", "").replace("\u20a9", "").replace("\u20b1", "")
                 .strip()
        )
        try:
            return float(cleaned)
        except Exception:
            return float(default)
    return float(default)


KRW_PER_USD = 1  # prices are now KRW directly from API


def passes_price_filter(product: dict, settings: dict | None = None) -> bool:
    """Return True if product is within configured KRW price range.

    Reads settings['price_filter']['min_price_krw'] (default 1,000)
                                   ['max_price_krw'] (default 100,000)
    """
    pf        = (settings or {}).get("price_filter", {})
    min_krw   = int(pf.get("min_price_krw", 1000))
    max_krw   = int(pf.get("max_price_krw", 100000))

    price_usd = safe_number(product.get("price") or product.get("target_sale_price") or 0)
    price_krw = int(price_usd * KRW_PER_USD)

    return min_krw <= price_krw <= max_krw


def calculate_product_score(product: dict) -> int:
    """
    Score a product 0-100. Higher = better for our channel.
    Uses the field names produced by _enrich_product():
      price / target_sale_price, discount (int), rating (0-100 float),
      has_video (bool), orders/sold/sales (int), reviews/feedback (int).
    """
    score = 0

    # 1. Discount (0-25 pts)
    discount = safe_number(product.get("discount", 0) or 0)
    if discount >= 50:
        score += 25
    elif discount >= 30:
        score += 20
    elif discount >= 20:
        score += 15
    elif discount >= 10:
        score += 8
    else:
        score += 3

    # 2. Rating (0-20 pts) -- 0-100 scale
    rating = safe_number(product.get("rating", 0) or 0)
    if rating >= 90:
        score += 20
    elif rating >= 80:
        score += 16
    elif rating >= 70:
        score += 12
    elif rating >= 60:
        score += 8
    else:
        score += 4

    # 3. Price sweet spot (0-20 pts)
    price = safe_number(product.get("price") or product.get("target_sale_price") or 0)
    if 15 <= price <= 50:
        score += 20
    elif 50 < price <= 100:
        score += 15
    elif 5 <= price < 15:
        score += 10
    elif 100 < price <= 200:
        score += 8
    else:
        score += 3

    # 4. Has video (0-10 pts)
    score += 10 if (product.get("has_video") or product.get("video_url")) else 3

    # 5. Sales / orders (0-15 pts)
    orders = safe_number(
        product.get("orders") or product.get("sales") or product.get("sold") or 0
    )
    if orders >= 1000:
        score += 15
    elif orders >= 500:
        score += 12
    elif orders >= 100:
        score += 10
    elif orders >= 50:
        score += 7
    elif orders >= 10:
        score += 5
    else:
        score += 2

    # 6. Review count (0-10 pts)
    reviews = safe_number(
        product.get("reviews") or product.get("review_count")
        or product.get("feedback") or product.get("evaluate_count") or 0
    )
    if reviews >= 500:
        score += 10
    elif reviews >= 100:
        score += 8
    elif reviews >= 50:
        score += 6
    elif reviews >= 10:
        score += 4
    else:
        score += 1

    return score


def collect_products_balanced(scraper, keywords: list,
                              target_per_band: int = 5,
                              src_cat_map: dict | None = None) -> list:
    """Collect products with balanced distribution across KRW price bands.

    For each price band (1k/5k/10k/30k), searches a sample of keywords with
    USD price-range constraints until target_per_band products are found.
    Stops early per band once the target is reached to limit API calls.
    Returns a combined deduplicated list tagged with _source_category.
    """
    from modules.category_mapper import PRICE_BANDS_USD
    src_cat_map = src_cat_map or {}
    all_results: list = []
    seen_ids: set = set()

    # Representative keywords to use per band (cap at 8 to limit API calls)
    sample_kw = keywords[:8]

    for band in PRICE_BANDS_USD:
        band_key  = band["key"]
        min_usd   = band["min_usd"]
        max_usd   = band["max_usd"]
        collected = 0
        print(f"[BAL] Band {band_key} (${min_usd}-${max_usd}): targeting {target_per_band}")

        for kw in sample_kw:
            if collected >= target_per_band:
                break
            need  = target_per_band - collected
            results = scraper.search_products(
                kw, limit=min(need + 3, 10),
                min_price_usd=min_usd,
                max_price_usd=max_usd,
            )
            time.sleep(0.3)
            for p in results:
                pid = p.get("product_id")
                if pid and pid in seen_ids:
                    continue
                if pid:
                    seen_ids.add(pid)
                src_cat = src_cat_map.get(kw, "")
                if src_cat and not p.get("_source_category"):
                    p["_source_category"] = src_cat
                all_results.append(p)
                collected += 1
                if collected >= target_per_band:
                    break

        print(f"[BAL] Band {band_key}: got {collected}")

    return all_results


def collect_daily_products(exclude_ids: set = None) -> list:
    """Collect products (video preferred, image-slideshow fallback). Save up to daily_uploads."""
    scraper = AliScraper()
    exclude_ids = exclude_ids or set()

    with open(f"{BASE_DIR}/config/settings.json") as f:
        settings = json.load(f)

    all_products = []
    keywords = SEARCH_KEYWORDS + get_seasonal_keywords()
    print(f"[ALI] Searching {len(keywords)} keywords ({len(SEARCH_KEYWORDS)} base + {len(keywords)-len(SEARCH_KEYWORDS)} seasonal)")
    try:
        from modules.category_mapper import KEYWORD_TO_CATEGORY
    except Exception:
        KEYWORD_TO_CATEGORY = {}

    # 80/20 channel focus: pet keywords searched 4x (more results), others 1x
    _PET_PREFIXES = ("cat ", "dog ", "pet ", "automatic pet", "kitten", "puppy")
    for keyword in keywords:
        is_pet = any(keyword.lower().startswith(p) for p in _PET_PREFIXES)
        limit = 20 if is_pet else 5  # 4x weight for pet keywords
        results = scraper.search_products(keyword, limit=limit)
        src_cat = KEYWORD_TO_CATEGORY.get(keyword, "")
        for p in results:
            if src_cat and not p.get("_source_category"):
                p["_source_category"] = src_cat
        all_products.extend(results)
        time.sleep(0.3)

    # Balanced collection pass: top-up under-represented price bands
    balanced = collect_products_balanced(
        scraper, keywords[:8],
        target_per_band=5,
        src_cat_map=KEYWORD_TO_CATEGORY,
    )
    all_products.extend(balanced)
    print(f"[ALI] Balanced pass added {len(balanced)} products")

    # Deduplicate by product_id
    seen = set()
    unique = []
    for p in all_products:
        pid = p.get("product_id")
        if pid and pid not in seen and pid not in exclude_ids:
            seen.add(pid)
            unique.append(p)

    # FIX 3: Tag has_video before filtering (no longer a hard requirement)
    for p in unique:
        p["has_video"] = scraper._has_video(p)

    n_with_video = sum(1 for p in unique if p["has_video"])
    print(f"[ALI] {len(all_products)} raw -> {len(unique)} unique ({n_with_video} with video)")

    # Minimal validity filter: must have name, price > 0, and image or video
    valid = [
        p for p in unique
        if (p.get("product_title") or p.get("name"))
        and safe_number(p.get("target_sale_price") or p.get("price") or 0) > 0
        and (p.get("product_images") or p.get("image_url") or p["has_video"])
    ]
    print(f"[ALI] {len(unique)} unique -> {len(valid)} valid (name+price+media)")

    if not valid:
        print("[ERROR] No valid products found!")
        try:
            from modules.telegram_alert import send_telegram_message
            send_telegram_message("No valid products found (name+price+media check failed)!", level="ERROR")
        except Exception:
            pass

    # Price filter: drop items below min KRW threshold (configurable in settings.json)
    price_passed = [p for p in valid if passes_price_filter(p, settings)]
    price_rejected = len(valid) - len(price_passed)
    if price_rejected:
        print(f"[ALI] Price filter: {len(valid)} -> {len(price_passed)} "
              f"({price_rejected} rejected below KRW threshold)")
    valid = price_passed

    # Score every product (0-100 pts)
    for p in valid:
        p["_score"] = calculate_product_score(p)
    valid.sort(key=lambda p: p["_score"], reverse=True)

    n_video = sum(1 for p in valid if p["has_video"])
    n_image = len(valid) - n_video
    scores = [p["_score"] for p in valid[:10]] if valid else []
    print(f"[ALI] Scored: {n_video} video, {n_image} image-only | top-10 scores: {scores}")

    # Category dedup: max 10 products per AliExpress sub-category (diverse selection).
    # Raised from 2 -> 10 because most pet products share the "Pet Products" L2,
    # so the old cap was the main reason the deals page only showed ~15 items.
    seen_categories = {}
    deduped = []
    for p in valid:
        cat = (p.get("second_level_category_name") or p.get("first_level_category_name") or "unknown").lower()
        if seen_categories.get(cat, 0) < 10:
            seen_categories[cat] = seen_categories.get(cat, 0) + 1
            deduped.append(p)
    print(f"[ALI] {len(valid)} valid -> {len(deduped)} after category dedup (max 10/category)")

    # History filter: skip products already used in past runs
    history = load_product_history()
    fresh = []
    skipped_hist = 0
    for p in deduped:
        pid = str(p.get("product_id", "") or "")
        pname = p.get("product_title", "") or ""
        if pid and pid in history["ids"]:
            skipped_hist += 1
            continue
        if pname and is_duplicate_by_name(pname, history["names"]):
            skipped_hist += 1
            continue
        fresh.append(p)
    if skipped_hist:
        print(f"[ALI] Skipped {skipped_hist} duplicate(s) (already used before)")
    if not fresh and deduped:
        # Auto-recovery: trim oldest 50% of history and retry filter
        print("[ALI] WARNING: all products are duplicates -- auto-trimming history")
        removed = emergency_trim_history(keep_ratio=0.5)
        print(f"[ALI] Emergency trim removed {removed} old entries -- retrying filter")
        history = load_product_history()
        for p in deduped:
            pid = str(p.get("product_id", "") or "")
            pname = p.get("product_title", "") or ""
            if pid and pid in history["ids"]:
                continue
            if pname and is_duplicate_by_name(pname, history["names"]):
                continue
            fresh.append(p)
        if fresh:
            print(f"[ALI] Recovery success: {len(fresh)} products after history trim")
        else:
            print("[ALI] Recovery failed: still 0 products after trim")
    deduped = fresh

    selected = deduped[:settings.get("daily_uploads", 99)]

    for product in selected:
        promo = product.get("promotion_link", "")
        fallback = promo or product.get("product_detail_url", "")
        product_id = str(product.get("product_id") or "")

        # Generate region-specific affiliate links (ko/en/zh domains)
        if product_id:
            regional = scraper.get_regional_affiliate_links(product_id, fallback_link=fallback)
        else:
            regional = {lang: fallback for lang in REGIONAL_DOMAINS}

        # Ensure every regional link has affiliate tracking params.
        # Links missing aff_fcid/sk (e.g. pdp_npi-only URLs) get rebuilt.
        # s.click short links also get rebuilt -- they expire after ~30 days.
        for lang in list(regional.keys()):
            link = regional.get(lang, "")
            needs_rebuild = (
                not link
                or len(link) < 20
                or "s.click.aliexpress" in link
                or ("aff_fcid" not in link and "aff_platform" not in link)
            )
            if needs_rebuild and product_id:
                cat_key = product.get("category_key", "")
                regional[lang] = build_affiliate_link(product_id, lang, cat_key)
                print(f"[ALI] Rebuilt {lang} link for pid={product_id}")

        product["regional_affiliate_links"] = regional

        # Default affiliate_link = KO regional (used when lang is unknown)
        cat_key = product.get("category_key", "")
        aff_ko = regional.get("ko") or fallback or build_affiliate_link(product_id, category_key=cat_key)
        product["affiliate_link"] = aff_ko

        # Validate KO link -- drop 404 products silently (product removed from AliExpress)
        if not validate_affiliate_link(aff_ko):
            print(f"[ALI] 404 link -- skipping pid={product_id} '{product.get('product_title','')[:28]}'")
            product["_skip"] = True
            continue

        print(
            f"[ALI] pid={product_id} | {product.get('product_title','')[:28]} "
            f"| ko={aff_ko[:60]}"
        )

    # Remove products that 404'd
    selected = [p for p in selected if not p.get("_skip")]

    # Batch-translate product titles to Korean (name_ko field)
    try:
        from modules.gemini_copy import batch_translate_names
        needs_ko = [i for i, p in enumerate(selected) if not p.get("name_ko")]
        if needs_ko:
            names = [selected[i].get("product_title") or selected[i].get("title", "") for i in needs_ko]
            translations = batch_translate_names(names)
            for i, ko in zip(needs_ko, translations):
                selected[i]["name_ko"] = ko
            print(f"[ALI] Translated {len(needs_ko)} product names to Korean")
    except Exception as _te:
        print(f"[ALI] Korean translation skipped: {_te}")

    # Batch-generate short Korean description blurbs for deals-page cards
    try:
        from modules.gemini_copy import batch_descriptions
        needs_desc = [i for i, p in enumerate(selected) if not p.get("name_desc")]
        if needs_desc:
            names_for_desc = [selected[i].get("name_ko") or selected[i].get("product_title", "") for i in needs_desc]
            descs = batch_descriptions(names_for_desc)
            for i, d in zip(needs_desc, descs):
                selected[i]["name_desc"] = d
            print(f"[ALI] Generated {sum(1 for d in descs if d)} Korean description blurbs")
    except Exception as _de:
        print(f"[ALI] Description generation skipped: {_de}")

    # Classify each product into a Korean category (category_key field)
    try:
        from modules.category_mapper import classify_product
        for p in selected:
            if not p.get("category_key"):
                p["category_key"] = classify_product(p)
        print(f"[ALI] Category classification done")
    except Exception as _ce:
        print(f"[ALI] Category classification skipped: {_ce}")

    # Tag price band (price_band field)
    try:
        from modules.category_mapper import classify_price_band
        for p in selected:
            if not p.get("price_band"):
                p["price_band"] = classify_price_band(p)
        band_dist = {}
        for p in selected:
            band_dist[p.get("price_band","?")] = band_dist.get(p.get("price_band","?"),0)+1
        print(f"[ALI] Price bands: {band_dist}")
    except Exception as _pe:
        print(f"[ALI] Price band tagging skipped: {_pe}")

    count = scraper.save_products(selected)
    n_vid = sum(1 for p in selected if p.get("has_video"))
    n_img = count - n_vid
    print(f"[ALI] Saved {count} products ({n_vid} video, {n_img} image-only slideshow)")
    return selected


if __name__ == "__main__":
    collect_daily_products()
