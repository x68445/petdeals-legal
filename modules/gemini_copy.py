#!/usr/bin/env python3
"""
Gemini Copywriter v3 - Multi-language + Dynamic variation
Languages: Korean, English, Chinese (Traditional)
"""

import json
import os
import random
from google import genai
from dotenv import load_dotenv

load_dotenv("/home/ubuntu/petdeals_bot/config/.env")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


import re as _re

_HAS_ENGLISH = _re.compile(r'[a-zA-Z]{3,}')

# Common English->Korean word map for quick fallback replacement
_EN_KO_MAP = [
    ("Water Fountain", "정수기"), ("Cat Toy", "고양이 장난감"),
    ("Dog Harness", "강아지 하네스"), ("Pet Bed", "반려동물 침대"),
    ("LED Light", "LED 조명"), ("Portable", "휴대용"),
    ("Wireless", "무선"), ("Bluetooth", "블루투스"),
    ("Camping", "캠핑"), ("Automatic", "자동"),
    ("Premium", "프리미엄"), ("Mini", "미니"),
    ("Outdoor", "아웃도어"), ("Electric", "전동"),
    ("Magnetic", "마그네틱"), ("Silicone", "실리콘"),
    ("Stainless", "스테인리스"), ("Foldable", "접이식"),
    ("Rechargeable", "충전식"), ("Adjustable", "조절 가능"),
]


def _quick_translate(text: str) -> str:
    """Apply word-level English->Korean substitutions (fast, no API)."""
    for eng, kor in _EN_KO_MAP:
        text = text.replace(eng, kor).replace(eng.lower(), kor)
    return text


def safe_number(value, default=0.0) -> float:
    """Convert any value to float. Handles '51%', '$29.99', '1,234' etc."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("%", "").replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except Exception:
            return float(default)
    return float(default)


# ---- SEO prompt builders (discount-aware) -----------------------------------

def get_category_hashtags(product_name: str, category: str) -> str:
    """Return category-specific hashtag string."""
    combined = (product_name + " " + category).lower()
    base = "#shorts #알리익스프레스 #알리직구 #할인"

    if any(w in combined for w in ["cat", "dog", "pet", "고양이", "강아지", "반려", "feeder", "harness", "leash"]):
        return f"{base} #반려동물 #펫딜 #고양이 #강아지"
    elif any(w in combined for w in ["camping", "outdoor", "hiking", "tent", "hammock", "캠핑", "sleeping bag"]):
        return f"{base} #캠핑 #캠핑용품 #아웃도어 #등산"
    elif any(w in combined for w in ["earbuds", "bluetooth", "keyboard", "mouse", "webcam", "usb", "charger", "power bank", "phone"]):
        return f"{base} #가전 #테크 #가성비템 #IT기기"
    elif any(w in combined for w in ["kitchen", "cook", "coffee", "air fryer", "kettle", "vacuum", "ice maker"]):
        return f"{base} #주방용품 #생활용품 #홈카페 #살림"
    elif any(w in combined for w in ["fitness", "yoga", "gym", "exercise", "massage", "resistance", "foam roller"]):
        return f"{base} #운동 #홈트 #피트니스 #건강"
    elif any(w in combined for w in ["car", "dash cam", "tire", "vehicle", "자동차"]):
        return f"{base} #자동차 #차량용품 #카용품"
    elif any(w in combined for w in ["baby", "kids", "child", "toy", "육아"]):
        return f"{base} #육아 #아기용품 #키즈"
    elif any(w in combined for w in ["bag", "wallet", "watch", "sunglasses", "scarf", "fashion", "belt"]):
        return f"{base} #패션 #악세사리 #데일리룩"
    elif any(w in combined for w in ["desk", "notebook", "pen", "monitor", "cable", "office"]):
        return f"{base} #사무용품 #오피스 #문구"
    elif any(w in combined for w in ["led", "light", "lamp", "strip", "humidifier", "plant"]):
        return f"{base} #인테리어 #홈데코 #생활용품"
    else:
        return f"{base} #가성비 #꿀템 #생활용품"


def translate_product_name(name: str) -> str:
    """Translate English product name to Korean via Gemini. Falls back to word-map."""
    if not _HAS_ENGLISH.search(name):
        return name  # Already Korean/non-English
    try:
        prompt = f"이 상품명을 자연스러운 한국어로 번역해줘 (20자 이내):\n{name}\n한국어만 출력해."
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        ko = resp.text.strip().strip('"').strip("'")
        return ko if ko else _quick_translate(name)
    except Exception:
        return _quick_translate(name)


def batch_translate_names(names: list) -> list:
    """Translate a list of English product names to Korean in batches of 10.

    Returns a list of Korean names in the same order.
    On batch failure, falls back to individual translate_product_name() calls.
    """
    import time

    results = [""] * len(names)
    batch_size = 10

    for start in range(0, len(names), batch_size):
        batch = names[start:start + batch_size]
        # Build numbered prompt: "1. Coffee Cup Warmer\n2. Dog Harness\n..."
        numbered = "\n".join(f"{i+1}. {n}" for i, n in enumerate(batch))
        prompt = (
            "아래 영어 상품명들을 각각 자연스러운 한국어로 번역해줘 (각 20자 이내).\n"
            "반드시 번호를 유지해서 '1. 번역결과' 형식으로 출력해.\n"
            "한국어 번역만 출력하고 다른 설명은 쓰지 마.\n\n"
            f"{numbered}"
        )
        try:
            resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            lines = resp.text.strip().splitlines()
            # Parse "1. 번역결과" lines
            parsed = {}
            for line in lines:
                line = line.strip()
                m = _re.match(r'^(\d+)[.\)]\s*(.+)$', line)
                if m:
                    idx = int(m.group(1)) - 1
                    parsed[idx] = m.group(2).strip().strip('"').strip("'")

            # Map back to results; fallback individually for any missing
            for i, name in enumerate(batch):
                global_i = start + i
                if i in parsed and parsed[i]:
                    results[global_i] = parsed[i]
                else:
                    results[global_i] = translate_product_name(name)

        except Exception as e:
            print(f"[GEMINI] 배치 번역 실패 (start={start}): {e} -- 개별 번역으로 fallback")
            for i, name in enumerate(batch):
                results[start + i] = translate_product_name(name)

        if start + batch_size < len(names):
            time.sleep(2)  # rate limit 방지

    return results


def batch_descriptions(names_ko: list) -> list:
    """Generate short Korean marketing blurbs (<=20 chars) for a list of products.

    Used by the deals-page generator to put a 1-line hook under each product title.
    Returns a list of strings in the same order. Empty string on failure.
    """
    import time

    results = [""] * len(names_ko)
    batch_size = 10

    for start in range(0, len(names_ko), batch_size):
        batch = names_ko[start:start + batch_size]
        numbered = "\n".join(f"{i+1}. {n}" for i, n in enumerate(batch))
        prompt = (
            "너는 상품 자체가 되어 주인(사용자)에게 짜증 섞인 잔소리를 한다.\n"
            "규칙:\n"
            "- '나 [상품]인데!' 또는 '내가 [상품]인데!'로 시작\n"
            "- 35~50자, 100% 한국어, 이모지 금지\n"
            "- 짜증 섞인 친근한 반말 + 팩폭 톤\n"
            "- 과학적/실용적 이유 1개 포함 (세균/건강/편의)\n"
            "- '사세요' '구매' '추천' 같은 구매 권유 금지\n"
            "- 반려동물 상품이면 주인을 야단치는 톤\n"
            "- 다른 상품이면 사용자를 야단치는 톤\n"
            "- 반드시 번호를 유지해서 '1. 문구' 형식으로 출력\n"
            "- 설명 없이 문구만 출력\n\n"
            "좋은 예시:\n"
            "- '나 경사형 밥그릇인데! 바닥에 놓고 주니까 냥이 목 꺾여!'\n"
            "- '나 고양이 모래인데! 3일째 안 갈면 세균 공장이라고!'\n"
            "- '나 강아지 하네스인데! 목줄만 하면 기관지 상해!'\n"
            "- '나 자동 급수기인데! 냥이 물 안 마셔서 신장병 걸려!'\n\n"
            f"{numbered}"
        )
        try:
            resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            parsed = {}
            for line in resp.text.strip().splitlines():
                line = line.strip()
                m = _re.match(r'^(\d+)[.\)]\s*(.+)$', line)
                if m:
                    idx = int(m.group(1)) - 1
                    text = m.group(2).strip().strip('"').strip("'")[:55]
                    if text.startswith(("나 ", "내가 ")):
                        parsed[idx] = text
                    else:
                        parsed[idx] = ""
            for i in range(len(batch)):
                results[start + i] = parsed.get(i, "")
        except Exception as e:
            print(f"[GEMINI] 배치 설명 실패 (start={start}): {e}")
            # Leave as empty -- renderer will just skip the description line

        if start + batch_size < len(names_ko):
            time.sleep(2)

    return results


def ensure_korean_title(title: str) -> str:
    """If title has 3+ consecutive English letters (outside #Shorts), re-translate via Gemini."""
    clean = title.replace("#Shorts", "").replace("#shorts", "").strip()
    if not _HAS_ENGLISH.search(clean):
        return title

    try:
        fix_prompt = (
            f"이 제목을 100% 한국어로 바꿔줘. 영어 단어 하나도 없이.\n"
            f"제목: {title}\n"
            f"규칙: 한국어만, 이모지 1개, #Shorts 붙이기\n"
            f"제목만 출력해."
        )
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=fix_prompt)
        fixed = resp.text.strip().strip('"').strip("'")
        if fixed:
            if "#Shorts" not in fixed and "#shorts" not in fixed:
                fixed = fixed + " #Shorts"
            return fixed[:100]
    except Exception:
        pass

    # Fast fallback: word-level replacement
    title = _quick_translate(title)
    if "#Shorts" not in title and "#shorts" not in title:
        title = title + " #Shorts"
    return title


def generate_seo_title(product: dict) -> str:
    """Build a click-worthy Korean title prompt. Category-aware, skips discount when <10%."""
    # Prefer pre-translated name_ko; fall back to raw name
    name = (product.get("name_ko")
            or product.get("title") or product.get("product_title") or product.get("name", ""))
    category = product.get("category", "")
    discount = safe_number(product.get("discount", 0))
    price = safe_number(product.get("price", 0))
    krw = int(price)

    discount_rule = (f"- 할인율 {int(discount)}% 포함"
                     if discount >= 10 else "- 할인 얘기 하지마 (할인 없음)")
    category_line = f"카테고리: {category}" if category else ""

    from datetime import datetime
    year = datetime.now().strftime("%Y")

    prompt = f"""유튜브 쇼츠 제목을 만들어줘.

상품: {name}
{category_line}
{"할인: " + str(int(discount)) + "%" if discount >= 10 else "가격은 알리에서 확인"}

[절대 규칙 -- 이것만 지키면 됨]
- 반드시 100% 한국어로만 작성. 영어 단어 절대 금지.
- 상품명이 영어여도 한국어로 번역: "Water Bottle" → "물병", "Dog Harness" → "강아지 하네스"
- 영어 단어 하나라도 있으면 실패야. 절대 영어 쓰지마.
- 55자 이내 (모바일 표시 최적화)
- 제목에 "알리특가" 단어 포함 (브랜딩)
- "{year}년" 또는 "추천" 또는 "BEST" 중 하나 포함
- 호기심 유발, 상품 카테고리 톤
{discount_rule}
- 이모지 1개만, #Shorts 붙이기

좋은 예시:
- "알리특가 고양이 장난감 TOP5 추천 {year} 😱 #Shorts"
- "알리특가 캠핑 랜턴 추천 이 가격 실화? 🏕️ #Shorts"
- "{year} 알리특가 무선 이어폰 BEST 🎧 #Shorts"
- "알리특가 강아지 물병 {year} 추천 🐶 #Shorts"

제목만 출력해."""

    return prompt


def generate_seo_description(product: dict) -> tuple:
    """Return (hook_prompt, price_line, affiliate_link).

    hook_prompt asks Gemini for ONE short review line only (<=20 chars).
    Full description is assembled by build_full_description().
    """
    name = product.get("title") or product.get("product_title") or product.get("name", "")
    discount = safe_number(product.get("discount", 0))
    price = safe_number(product.get("price", 0))
    original = safe_number(product.get("original_price", 0))
    krw = int(price)
    affiliate = product.get("affiliate_link", "")

    if discount >= 10:
        price_line = f"지금 {int(discount)}% 할인 중! 알리에서 확인하세요"
    else:
        price_line = ""

    name_ko = product.get("name_ko") or name
    hook_prompt = f"""유튜브 쇼츠 영상 설명 첫 줄만 만들어줘.
상품: {name_ko}
100% 한국어로, 한 줄 후기 느낌, 20자 이내. 예: "우리 냥이 음수량 걱정 끝!"
영어 절대 금지. 첫 줄만 출력해."""

    return hook_prompt, price_line, affiliate


DEALS_URL = "https://x68445.github.io/petdeals-legal/deals.html"


PREMIUM_URL = "https://x68445.github.io/petdeals-legal/price_100k.html"
BUDGET_URL = "https://x68445.github.io/petdeals-legal/price_1k.html"


def build_full_description(hook_line: str, price_line: str, affiliate_link: str,
                           product_name: str = "", category: str = "") -> str:
    """Assemble the final YouTube description with specific product + deals hub links."""
    name_line = f"{product_name}" if product_name else ""

    parts = [hook_line.strip()]

    # Specific product link
    if affiliate_link and affiliate_link != "#":
        parts.extend([
            "",
            "🔥 영상 속 이 상품 바로가기!",
        ])
        if name_line:
            parts.append(name_line)
        parts.append(f"👉 {affiliate_link}")

    if price_line:
        parts.append("")
        parts.append(price_line)

    # General deals hub
    parts.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "💎 오늘의 모든 특가 한눈에!",
        f"👉 {DEALS_URL}",
        "",
        "📌 이 영상 상품 + 더 많은 특가",
        "📌 매일 업데이트되는 알리 최저가",
        "📌 펫용품 / 캠핑 / 전자 / 주방 / 패션 / 자동차 / 스포츠",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"💎 프리미엄 상품 → {PREMIUM_URL}",
        f"💰 가성비 상품 → {BUDGET_URL}",
        "",
        "✅ 진짜 싼 상품만 엄선",
        "✅ 매일 새로운 특가 업데이트",
        "✅ 구독하면 놓치지 않아요!",
        "",
        get_category_hashtags(product_name, category),
        "",
        "※ 이 영상은 알리익스프레스 어필리에이트 링크를 포함하고 있으며,",
        "구매 시 일정 커미션을 받을 수 있습니다. 구매자의 추가 비용은 없습니다.",
    ])
    return "\n".join(parts)


def generate_video_metadata(product: dict, gemini_func) -> tuple:
    """Generate title and description. Returns (title, description)."""
    # Ensure name_ko is set
    if not product.get("name_ko"):
        raw = (product.get("title") or product.get("product_title") or product.get("name", ""))
        product["name_ko"] = translate_product_name(raw)
    name_ko = product["name_ko"][:30]

    title_prompt = generate_seo_title(product)
    hook_prompt, price_line, affiliate = generate_seo_description(product)
    discount = safe_number(product.get("discount", 0))
    price = safe_number(product.get("price", 0))
    krw = int(price)

    try:
        title = gemini_func(title_prompt).strip().strip('"').strip("'")
        if len(title) > 100:
            title = title[:97] + "..."
        if "#Shorts" not in title and "#shorts" not in title:
            title = title + " #Shorts"
        title = ensure_korean_title(title)
    except Exception:
        title = (f"알리특가 {name_ko} {int(discount)}% 할인 🔥 #Shorts"
                 if discount >= 10 else f"알리특가 {name_ko} 추천 🛒 #Shorts")

    try:
        hook_line = gemini_func(hook_prompt).strip()
    except Exception:
        hook_line = (f"이거 {int(discount)}% 할인이라고?!" if discount >= 10
                     else f"이 퀄리티 알리에서 가능?!")

    _cat = product.get("category", "")
    description = build_full_description(hook_line, price_line, affiliate, name_ko, _cat)
    return title, description


def call_gemini(prompt: str, model: str = "gemini-2.5-flash") -> str:
    """Simple Gemini text generation helper. Returns response text."""
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text


def generate_seo_metadata(product_info: dict, lang: str, affiliate_link: str = "") -> dict:
    """Generate SEO title + description via Gemini. Returns {"title", "description"} or {}.

    Title: Gemini generates click-worthy Korean title.
    Description: Gemini generates 1-line hook; build_full_description assembles the rest.
    Korean only -- other langs fall back to hook-based title in caller.
    """
    if lang != "ko":
        return {}

    product_info = dict(product_info)
    if affiliate_link:
        product_info["affiliate_link"] = affiliate_link

    # Translate product name to Korean first (cached in product_info["name_ko"])
    raw_name = (product_info.get("title") or product_info.get("product_title")
                or product_info.get("name", ""))
    if not product_info.get("name_ko"):
        product_info["name_ko"] = translate_product_name(raw_name)
    name_ko = product_info["name_ko"][:30]

    title_prompt = generate_seo_title(product_info)
    hook_prompt, price_line, aff = generate_seo_description(product_info)
    if affiliate_link:
        aff = affiliate_link

    discount = safe_number(product_info.get("discount", 0))
    price = safe_number(product_info.get("price", 0))
    krw = int(price)
    _cat = product_info.get("category", "")

    try:
        title_resp = client.models.generate_content(
            model="gemini-2.5-flash", contents=title_prompt
        )
        seo_title = title_resp.text.strip().strip('"').strip("'")
        if len(seo_title) > 100:
            seo_title = seo_title[:97] + "..."
        if "#Shorts" not in seo_title and "#shorts" not in seo_title:
            seo_title = seo_title + " #Shorts"
        # Guarantee Korean
        seo_title = ensure_korean_title(seo_title)

        hook_resp = client.models.generate_content(
            model="gemini-2.5-flash", contents=hook_prompt
        )
        hook_line = hook_resp.text.strip().strip('"')
        seo_description = build_full_description(hook_line, price_line, aff, name_ko, _cat)

        return {"title": seo_title[:100], "description": seo_description[:5000]}
    except Exception as e:
        print(f"[GEMINI SEO] lang={lang}: {e}")
        # Fallback -- always use Korean name_ko
        seo_title = (f"알리특가 {name_ko[:20]} {int(discount)}% 할인 🔥 #Shorts"
                     if discount >= 10 else f"알리특가 {name_ko[:20]} 추천 🛒 #Shorts")
        hook_line = (f"이거 {int(discount)}% 할인이라고?!" if discount >= 10
                     else f"이 퀄리티 알리에서 가능?!")
        seo_description = build_full_description(hook_line, price_line, aff, name_ko, _cat)
        return {"title": seo_title, "description": seo_description[:5000]}


# ---- Hook/CTA pool (fallbacks + prompt seed) --------------------------------

HOOK_STYLES = {
    "ko": [
        {"style": "question",  "example": "이거 진짜 반값?"},
        {"style": "shock",     "example": "헐 이 할인율 실화..."},
        {"style": "casual",    "example": "야 이거 봐봐"},
        {"style": "fomo",      "example": "이거 품절 전에 봐"},
        {"style": "story",     "example": "우리 강아지가 미쳤음"},
    ],
    "en": [
        {"style": "question",  "example": "Is this really $3?"},
        {"style": "shock",     "example": "No way this is that cheap..."},
        {"style": "casual",    "example": "Yo check this out"},
        {"style": "fomo",      "example": "Before it sells out"},
        {"style": "story",     "example": "My dog went absolutely crazy"},
    ],
    "zh": [
        {"style": "question",  "example": "這個真的只要100元?"},
        {"style": "shock",     "example": "天啊這個價格..."},
        {"style": "casual",    "example": "你們快看"},
        {"style": "fomo",      "example": "快斷貨了"},
        {"style": "story",     "example": "我的狗狗愛上它了"},
    ],
}

CTA_POOL = {
    "ko": ["프로필 링크 확인!", "👇 프로필 바로가기", "프로필에서 구매", "프로필 링크 있어", "프로필 가기"],
    "en": ["Link in comments", "Check my profile", "👇 Link below", "Comment if interested", "Link in bio"],
    "zh": ["留言有連結", "查看個人主頁", "👇 連結在下面", "有興趣留言", "點擊留言連結"],
}

TONES = ["casual", "excited", "surprised", "chill"]


def _build_prompt(product_info: dict, lang: str) -> str:
    """Build Gemini prompt for given language. Picks random style+tone."""
    hooks = HOOK_STYLES[lang]
    random.shuffle(hooks)
    hook_examples = " / ".join(f'"{h["example"]}"' for h in hooks[:3])
    tone = random.choice(TONES)
    cta_examples = " / ".join(f'"{c}"' for c in CTA_POOL[lang])

    price = product_info.get("price", 0)
    orig = product_info.get("original_price", 0)
    discount = product_info.get("discount", 0)
    title = product_info.get("title", "")
    category = product_info.get("category", "pet supplies")

    if lang == "ko":
        lang_name = "Korean"
    elif lang == "en":
        lang_name = "English"
    else:
        lang_name = "Traditional Chinese (Taiwan)"

    disc_str = f"{int(discount)}% off" if discount >= 10 else "great value"

    return f"""You are a viral short-video copywriter specializing in pet product affiliate content.

Product: {title}
Category: {category}
Discount: {disc_str}
NOTE: Do NOT mention specific prices or currency amounts. Focus on the discount percentage and product benefits.
Target language: {lang_name}
Required tone: {tone}

Rules:
- NEVER use the same hook pattern twice (current style pool: {hook_examples})
- Vary sentence structure, length, and emoji usage each generation
- Hook must feel DIFFERENT and FRESH -- not a template
- No ad-speak ("amazing deal!", "don't miss out")
- Keep it natural, like a real person talking

Hook variations allowed:
{chr(10).join(f'  - {h["style"]}: e.g. "{h["example"]}"' for h in hooks)}

CTA options (pick one): {cta_examples}

Output ONLY this JSON (no other text):
{{
    "hook": "unique hook in {lang_name}",
    "cta": "cta in {lang_name}",
    "description": "2-line description\\nLine 2 points to link in description",
    "hashtags": ["tag1", "tag2", "tag3", "tag4"],
    "tts_script": "natural spoken version of hook + cta (no emojis)"
}}"""


def generate_video_copy(product_info: dict, lang: str = "ko") -> dict:
    """
    Generate video copy for one language.

    Returns:
        hook, cta, description, hashtags, tts_script
    """
    price = product_info.get("price", 0)
    orig = product_info.get("original_price", 0)

    # Fallback values per language
    disc = int(product_info.get("discount", 0) or 0)
    disc_ko = f"{disc}% 할인" if disc >= 10 else "알리 특가"
    disc_en = f"{disc}% off" if disc >= 10 else "great deal"
    disc_zh = f"{disc}% 折扣" if disc >= 10 else "超值優惠"
    title_str = product_info.get("title", "")

    fallbacks = {
        "ko": {
            "hook": f"이거 {disc_ko}이라고?!",
            "cta": random.choice(CTA_POOL["ko"]),
            "description": f"{title_str} {disc_ko}\n프로필 링크 확인!",
            "hashtags": ["#펫용품", "#강아지", "#고양이", "#알리익스프레스"],
            "tts_script": f"이거 {disc_ko}이에요. 댓글에 링크 있어요.",
        },
        "en": {
            "hook": f"This is {disc_en}!",
            "cta": random.choice(CTA_POOL["en"]),
            "description": f"{title_str} {disc_en}\nLink in comments",
            "hashtags": ["#petproducts", "#dogs", "#cats", "#aliexpress"],
            "tts_script": f"This is {disc_en}. Link in the comments.",
        },
        "zh": {
            "hook": f"{disc_zh}!",
            "cta": random.choice(CTA_POOL["zh"]),
            "description": f"{title_str} {disc_zh}\n留言有連結",
            "hashtags": ["#寵物用品", "#狗狗", "#貓咪", "#淘寶"],
            "tts_script": f"這個{disc_zh}。留言有連結。",
        },
    }

    prompt = _build_prompt(product_info, lang)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = response.text.strip()

        # Strip markdown code fences if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)
        # Ensure tts_script exists
        if "tts_script" not in result:
            result["tts_script"] = f"{result.get('hook', '')} {result.get('cta', '')}"
        return result

    except Exception as e:
        print(f"[GEMINI ERROR] lang={lang}: {e}")
        return fallbacks.get(lang, fallbacks["ko"])


def generate_all_languages(product_info: dict) -> dict:
    """
    Generate copy for Korean only (Korean-only strategy).

    Returns:
        {"ko": {...}}
    """
    result = {}
    result["ko"] = generate_video_copy(product_info, "ko")
    print(f"[GEMINI] ko copy generated: {result['ko'].get('hook', '')[:40]}")
    # EN and ZH disabled -- Korean-only strategy
    # result["en"] = generate_video_copy(product_info, "en")
    # result["zh"] = generate_video_copy(product_info, "zh")
    return result


# ---- YouTube metadata helpers -----------------------------------------------

def build_youtube_metadata(copy: dict, product: dict, lang: str, affiliate_link: str = "") -> dict:
    """Build YouTube title/description/tags per language.

    Uses SEO title from Gemini + build_full_description for body.
    Affiliate link is embedded inside description via build_full_description.
    """
    price = safe_number(product.get("price", 0))

    if lang == "ko":
        price_str = f"₩{int(price):,}"
        tags = ["#shorts", "#알리익스프레스", "#반려동물", "#고양이", "#강아지", "#펫딜", "#알리직구", "#할인"]
    elif lang == "en":
        price_str = f"${price:.2f}"
        tags = ["#shorts", "#petproducts", "#dogs", "#cats", "#aliexpress"]
    else:  # zh
        price_str = f"NT${int(price * 31):,}"
        tags = ["#shorts", "#寵物用品", "#狗狗", "#貓咪", "#淘寶"]

    # SEO metadata includes link inside description -- no separate link_line needed
    seo = generate_seo_metadata(product, lang, affiliate_link)
    if seo.get("title"):
        title = seo["title"]
        description = seo.get("description", "")
    else:
        # Fallback: hook-based title + build_full_description
        title = f"{copy['hook']} #Shorts"
        discount = safe_number(product.get("discount", 0))
        orig = safe_number(product.get("original_price", 0))
        krw = int(price)
        if discount >= 10 and orig > price > 0:
            price_line = f"원래 ₩{int(orig):,} -> 지금 ₩{krw:,} ({int(discount)}% 할인!)"
        elif price > 0:
            price_line = f"가격: ₩{krw:,}"
        else:
            price_line = ""
        hook_line = copy.get("hook", "")
        _name = product.get("title") or product.get("product_title") or ""
        _cat = product.get("category", "")
        description = build_full_description(hook_line, price_line, affiliate_link, _name, _cat)

    return {
        "title": title[:100],
        "description": description[:5000],
        "tags": tags,
        "price_str": price_str,
    }


if __name__ == "__main__":
    test_product = {
        "title": "Interactive Cat Toy Ball",
        "price": 2.50,
        "original_price": 25.00,
        "discount": 90,
        "category": "cat toys",
    }
    copies = generate_all_languages(test_product)
    for lang, copy in copies.items():
        print(f"\n[{lang.upper()}]")
        print(f"  hook: {copy['hook']}")
        print(f"  cta:  {copy['cta']}")
        print(f"  tts:  {copy['tts_script']}")
