#!/usr/bin/env python3
"""
Category mapper for 냥댕라이프 multi-category deals site.
Assigns each AliExpress product to one of 7 Korean lifestyle categories.

Priority:
  1. _source_category (keyword group tag set at collection time) -> remapped
  2. AliExpress second_level_category_name mapping
  3. AliExpress first_level_category_name mapping
  4. Keyword match on product_title / name_ko
  5. Default: etc
"""

# ── Display order for the deals site (냥댕라이프) ────────────────
CATEGORIES = [
    ("pet",         "🐾", "반려동물"),
    ("home",        "🏠", "우리집 살림"),
    ("outdoor",     "🚗", "우리 가족 나들이"),
    ("fashion",     "👕", "우리 가족 패션"),
    ("sports",      "💪", "우리 가족 건강"),
    ("electronics", "💻", "전자/디지털"),
    ("etc",         "🔥", "오늘의 추천템"),
]

CATEGORY_KEYS = {key for key, _, _ in CATEGORIES}

# Old _source_category values -> new keys
_SOURCE_REMAP: dict[str, str] = {
    "cat": "pet", "dog": "pet", "pet_common": "pet", "pet_toys": "pet",
    "pet_home": "home", "kitchen": "home",
    "camping": "outdoor", "car": "outdoor",
    "fashion": "fashion", "sports": "sports", "electronics": "electronics",
    "etc": "etc",
}

# ── Search keyword -> category key ─────────────────────────────────────────────
KEYWORD_TO_CATEGORY: dict[str, str] = {
    # Pet (cat + dog + common + toys)
    "cat toy interactive": "pet", "cat toy feather wand": "pet",
    "cat litter box": "pet", "cat litter mat": "pet",
    "cat scratching post": "pet", "cat tower tree": "pet",
    "cat collar bell": "pet", "cat water fountain": "pet",
    "cat carrier bag": "pet", "cat grooming brush": "pet",
    "cat kicker toy": "pet",
    "dog toy chew rubber": "pet", "dog toy rope": "pet",
    "dog treat training": "pet", "dog harness vest": "pet",
    "dog leash retractable": "pet", "dog collar LED": "pet",
    "dog clothes winter": "pet", "dog raincoat": "pet",
    "dog ball launcher": "pet", "dog carrier backpack": "pet",
    "dog squeaky toy": "pet",
    "automatic pet feeder": "pet", "pet water dispenser": "pet",
    "pet nail clipper": "pet", "pet grooming brush": "pet",
    "pet bed cushion": "pet", "pet blanket warm": "pet",
    "pet bowl stainless steel": "pet", "pet carrier travel bag": "pet",
    "pet laser pointer": "pet", "pet puzzle toy treat": "pet",
    "pet tunnel play": "pet", "pet treat ball dispenser": "pet",
    # Home (pet_home + kitchen)
    "pet hair remover roller": "home", "pet waste bag dispenser": "home",
    "pet gate barrier": "home", "pet stairs ramp": "home",
    "pet car seat cover": "home", "pet camera monitor": "home",
    "air fryer mini": "home", "tumbler insulated": "home",
    "kitchen storage rack": "home", "knife sharpener": "home",
    "silicone cooking utensils": "home", "vacuum food container": "home",
    "kitchen organizer shelf": "home",
    # Outdoor (camping + car)
    "camping tent waterproof": "outdoor", "camping chair folding": "outdoor",
    "camping lantern LED": "outdoor", "camping cookware set": "outdoor",
    "camping sleeping bag": "outdoor", "camping table portable": "outdoor",
    "camping hammock outdoor": "outdoor",
    "car charger fast": "outdoor", "car air freshener": "outdoor",
    "car phone holder magnetic": "outdoor", "car vacuum cleaner": "outdoor",
    "car seat organizer": "outdoor", "car phone mount magnetic": "outdoor",
    # Electronics
    "wireless earbuds bluetooth": "electronics", "LED strip lights room": "electronics",
    "portable charger power bank": "electronics", "LED desk lamp": "electronics",
    "humidifier mini portable": "electronics",
    "wireless earbuds": "electronics", "smartwatch fitness tracker": "electronics",
    "LED strip lights": "electronics", "bluetooth speaker portable": "electronics",
    "wireless charger pad": "electronics", "USB hub adapter": "electronics",
    # Fashion
    "crossbody bag women": "fashion", "sunglasses polarized": "fashion",
    "bucket hat unisex": "fashion", "minimalist wallet": "fashion",
    "canvas tote bag": "fashion",
    # Sports
    "yoga mat thick": "sports", "yoga mat non slip": "sports",
    "adjustable dumbbells": "sports", "massage gun deep": "sports",
    "resistance bands set": "sports", "foam roller muscle": "sports",
    "jump rope speed": "sports",
}

# ── AliExpress second_level_category_name -> our key ───────────────────────────
ALIEXPRESS_CATEGORY_MAP: dict[str, str] = {
    "Cat Supplies": "pet",
    "Dog Supplies": "pet",
    "Pet Products": "pet",
}

# AliExpress first_level_category_name -> our key (coarser fallback)
ALIEXPRESS_L1_MAP: dict[str, str] = {}

# ── Title keyword -> category (title/name_ko text match) ───────────────────────
_TITLE_KEYWORD_MAP: list[tuple[list[str], str]] = [
    # Pet (all pet-related keywords merged)
    (["cat", "kitten", "kitty", "catnip", "고양이", "냥이", "캣",
      "litter box", "scratching", "scratcher",
      "dog", "puppy", "canine", "bark", "강아지", "멍멍",
      "harness", "leash", "retractable",
      "laser pointer", "puzzle toy", "tunnel", "squeaky",
      "treat ball", "kicker", "teaser", "chew toy", "rope toy",
      "장난감", "터널", "퍼즐",
      "feeder", "fountain", "pet grooming", "nail clipper", "pet bowl",
      "pet bed", "pet carrier", "pet blanket", "pet dispenser",
      "반려동물", "펫", " pet "], "pet"),
    # Home (pet_home + kitchen)
    (["hair remover", "pet gate", "pet stairs", "pet ramp", "pet camera",
      "waste bag", "poop bag", "litter mat", "pet seat cover",
      "펫 계단", "펫 카메라", "배변봉투",
      "air fryer", "tumbler", "kitchen", "knife sharpener",
      "cooking utensil", "food container", "에어프라이어",
      "텀블러", "주방"], "home"),
    # Outdoor (camping + car)
    (["camping", "tent", "lantern", "sleeping bag", "hammock",
      "outdoor cookware", "캠핑", "텐트", "랜턴",
      "car charger", "car phone", "car mount", "car vacuum",
      "car air freshener", "car seat organizer", "dash cam",
      "차량용", "자동차"], "outdoor"),
    # Sports
    (["yoga mat", "dumbbell", "massage gun", "resistance band",
      "foam roller", "jump rope", "fitness", "요가", "덤벨", "마사지건"], "sports"),
    # Electronics
    (["earbuds", "earphone", "headphone", "smartwatch", "smart watch",
      "bluetooth speaker", "wireless charger", "led strip", "led light",
      "usb hub", "power bank", "이어폰", "스마트워치"], "electronics"),
    # Fashion
    (["crossbody", "tote bag", "wallet", "sunglasses", "bucket hat",
      "backpack fashion", "선글라스", "크로스백", "모자"], "fashion"),
]


def classify_product(product: dict) -> str:
    """Return one of the 7 category keys for the given product dict.

    Priority:
      1. _source_category (remapped from old keys)
      2. Title keyword match
      3. AliExpress second_level_category_name
      4. AliExpress first_level_category_name
      5. "etc"
    """
    # 1. Source keyword group tag (remap old keys)
    src = product.get("_source_category", "")
    remapped = _SOURCE_REMAP.get(src, "")
    if remapped and remapped in CATEGORY_KEYS:
        return remapped

    # 2. Title keyword match
    text = " ".join([
        product.get("product_title", ""),
        product.get("name_ko", ""),
        product.get("title", ""),
    ]).lower()
    for keywords, cat in _TITLE_KEYWORD_MAP:
        if any(kw.lower() in text for kw in keywords):
            return cat

    # 3. AliExpress second-level category
    l2 = product.get("second_level_category_name", "")
    if l2 in ALIEXPRESS_CATEGORY_MAP:
        return ALIEXPRESS_CATEGORY_MAP[l2]

    # 4. AliExpress first-level category
    l1 = product.get("first_level_category_name", "")
    if l1 in ALIEXPRESS_L1_MAP:
        return ALIEXPRESS_L1_MAP[l1]

    return "etc"


# ── Discount tiers (URLs kept as price_*.html for SEO) ───────────────────────

PRICE_BANDS = [
    {"key": "price_1k",   "emoji": "💰", "label": "가성비 특가", "min_disc": 10, "max_disc": 29, "accent": "#26c281", "tier": "light"},
    {"key": "price_10k",  "emoji": "🔥", "label": "핫딜",       "min_disc": 30, "max_disc": 49, "accent": "#c9a227", "tier": "premium"},
    {"key": "price_100k", "emoji": "💎", "label": "초특가",     "min_disc": 50, "max_disc": 999, "accent": "#ffd700", "tier": "luxury"},
]

PRICE_BANDS_USD = PRICE_BANDS


def classify_price_band(product: dict) -> str:
    """Return discount tier key. Items with <10% discount return empty string."""
    disc = float(product.get("discount", 0) or 0)
    if disc < 10:
        return ""
    for band in PRICE_BANDS:
        if band["min_disc"] <= disc <= band["max_disc"]:
            return band["key"]
    return "price_100k"


# ── Special deals helpers ─────────────────────────────────────────────────────

def is_special_deal(product: dict, threshold: float = 50.0) -> bool:
    """Return True if product discount_rate >= threshold."""
    disc = float(product.get("discount") or 0)
    if disc == 0:
        price = float(product.get("price") or product.get("target_sale_price") or 0)
        orig  = float(product.get("original_price") or product.get("target_original_price") or 0)
        if orig > price > 0:
            disc = (orig - price) / orig * 100
    return disc >= threshold


def group_special_deals_by_category(products: list,
                                     threshold: float = 50.0) -> dict:
    """Return {category_key: [products]} for all special-deal products.

    - Dedupes by product_id (first occurrence wins).
    - Sorts each group: discount desc, price asc.
    - Returns dict sorted by group size desc (most deals first).
    """
    seen: set = set()
    grouped: dict = {}
    for p in products:
        if not is_special_deal(p, threshold):
            continue
        pid = p.get("product_id") or p.get("id", "")
        if pid and pid in seen:
            continue
        if pid:
            seen.add(pid)
        key = p.get("category_key") or classify_product(p)
        grouped.setdefault(key, []).append(p)

    for key in grouped:
        grouped[key].sort(
            key=lambda p: (-float(p.get("discount") or 0),
                            float(p.get("price") or 0))
        )

    return dict(sorted(grouped.items(), key=lambda kv: -len(kv[1])))
