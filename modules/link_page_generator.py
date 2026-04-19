#!/usr/bin/env python3
"""
Link Page Generator v3 - Bright modern multi-category site.
Design refresh: Pretendard font, accent colors, wave header, product thumbnails.
Logic identical to v2 -- design-only refactor.

Generates:
  docs/deals.html              -- main page (category grid)
  docs/category_{key}.html     -- one page per non-empty category

URL base: https://x68445.github.io/petdeals-legal/
"""

import os
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE_DIR  = "/home/ubuntu/petdeals_bot"
DOCS_DIR  = f"{BASE_DIR}/docs"
DEALS_URL = "https://x68445.github.io/petdeals-legal/deals.html"
GIT_ROOT  = BASE_DIR

# ── Category accent colors (냥댕라이프 palette) ──────────────────────────
_ACCENT = {
    "pet":         "#ff6b9d",
    "home":        "#ffa502",
    "outdoor":     "#ff7f50",
    "fashion":     "#ff4757",
    "sports":      "#f368e0",
    "electronics": "#ff9ff3",
    "etc":         "#ff6b35",
}

# ── 냥댕라이프 branding constants ─────────────────────────────────────────────
YOUTUBE_URL = "https://www.youtube.com/@NyangDaengLife"
BRAND_NAME  = "냥댕라이프"
BRAND_TAGLINE = "🐾 오늘의 펫 특가"


def _safe_float(val) -> float:
    try:
        return float(str(val).replace("$", "").replace(",", "").replace("%", "") or 0)
    except Exception:
        return 0.0


def _hex_rgb(hex_color: str) -> str:
    """'#ff8c42' -> '255,140,66'  (for CSS rgba() usage)"""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"


def is_new_product(product: dict, now=None) -> bool:
    collected = product.get("collected_at", "")
    if not collected:
        return False
    try:
        ts = datetime.fromisoformat(collected.replace("Z", "+00:00")).replace(tzinfo=None)
        ref = now or datetime.now()
        return (ref - ts).total_seconds() < 86400
    except Exception:
        return False


def compute_top_discount_ids(products: list, n: int = 10) -> set:
    scored = []
    for p in products:
        pid = p.get("id") or p.get("product_id")
        disc = _safe_float(p.get("discount", 0))
        if pid and disc > 0:
            scored.append((disc, pid))
    scored.sort(reverse=True)
    return {pid for _, pid in scored[:n]}


def compute_savings(product: dict) -> int:
    price = _safe_float(product.get("price", 0))
    disc = _safe_float(product.get("discount", 0))
    if price > 0 and 0 < disc < 100:
        krw = int(price) or int(_safe_float(product.get("price_krw", 0)))
        orig = int(krw / (1 - disc / 100)) if krw > 0 else 0
        return max(orig - krw, 0)
    orig_price = _safe_float(product.get("target_original_price", 0))
    if orig_price > 0 and price > 0:
        return max(int(orig_price - price), 0)
    return 0


# ── Shared card CSS (identical across cat / band / special_deals pages) ────────
_NYANG_TOKENS = """
        :root {
          --nyang-pink: #FF8FAB;
          --nyang-pink-soft: #FFD1DC;
          --nyang-orange: #FFB347;
          --nyang-yellow: #FFD166;
          --nyang-accent: #E85A7A;
          --nyang-cream: #FFF9F5;
          --nyang-white: #FFFFFF;
          --nyang-text: #2D2D2D;
          --nyang-text-soft: #6B6B6B;
          --nyang-border: #FFE5DC;
          --nyang-gradient: linear-gradient(135deg, #FF8FAB 0%, #FFB347 50%, #FFD166 100%);
          --nyang-gradient-soft: linear-gradient(135deg, #FFD1DC 0%, #FFE5DC 100%);
          --nyang-gradient-discount: linear-gradient(135deg, #E85A7A 0%, #FF8FAB 100%);
          --nyang-shadow-soft: 0 4px 20px rgba(255,143,171,.15);
          --nyang-shadow-card: 0 8px 28px rgba(45,45,45,.08);
          --nyang-shadow-hover: 0 12px 36px rgba(255,143,171,.25);
          --nyang-radius-sm: 12px;
          --nyang-radius-md: 20px;
          --nyang-radius-lg: 28px;
          --nyang-radius-full: 999px;
          --nyang-transition: 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }
"""

_CARD_BASE_CSS = _NYANG_TOKENS + """
        .deal { position:relative; transition:transform var(--nyang-transition), box-shadow var(--nyang-transition); }
        .deal:hover { transform:translateY(-4px); box-shadow:var(--nyang-shadow-hover); }
        .deal:active { transform:scale(.98); }
        .thumb img { transition:transform 300ms ease-out; }
        .deal:hover .thumb img { transform:scale(1.05); }
        .deal-info { flex:1; min-width:0; }
        .badge-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; }
        .price-row { display:flex; align-items:center; gap:8px; margin-top:8px; flex-wrap:wrap; }
        .badge { background:var(--nyang-gradient-discount); color:white;
            padding:3px 10px; border-radius:var(--nyang-radius-full); font-size:11px; font-weight:700; white-space:nowrap; }
        .deal-cta { font-size:11px; color:var(--nyang-orange); font-weight:600; margin-top:4px; }
        .deal-disclaimer { font-size:10px; color:var(--nyang-text-soft); margin-top:3px; line-height:1.3; }
        .deal-freshness { font-size:10px; color:#bbb; margin-top:2px; }
        .deal-desc {
            font-size:12px; color:var(--nyang-accent); font-weight:600;
            margin-top:4px; line-height:1.3;
            background:var(--nyang-gradient-soft); padding:6px 10px;
            border-radius:var(--nyang-radius-sm); position:relative;
        }
        .deal-desc::before { content:"\\1F4AC"; margin-right:4px; }
        .rec-badge { background:linear-gradient(135deg,var(--nyang-pink),var(--nyang-orange)); color:white;
            padding:3px 9px; border-radius:var(--nyang-radius-full); font-size:10px; font-weight:800; white-space:nowrap; }
        .top-badge { position:absolute; top:8px; left:8px; z-index:2;
            background:linear-gradient(135deg,var(--nyang-yellow),var(--nyang-orange)); color:white;
            padding:3px 9px; border-radius:var(--nyang-radius-full); font-size:10px; font-weight:800;
            box-shadow:0 2px 6px rgba(255,179,71,.3); white-space:nowrap; }
        .new-badge { position:absolute; top:8px; right:8px; z-index:2;
            background:var(--nyang-gradient-discount); color:white;
            padding:3px 9px; border-radius:var(--nyang-radius-full); font-size:10px; font-weight:800;
            animation:newPulse 2s ease-in-out infinite; white-space:nowrap; }
        @keyframes newPulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.03)} }
        .discount-hero { font-size:2.2rem; font-weight:900; text-align:center;
            margin:10px 0 4px; letter-spacing:-0.02em; padding:12px 0;
            background:var(--nyang-gradient-discount); -webkit-background-clip:text;
            -webkit-text-fill-color:transparent; background-clip:text;
            animation:discountPulse 2s ease-in-out infinite; }
        @keyframes discountPulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.03)} }
        .cta-button { display:block; text-align:center; margin-top:10px;
            background:var(--nyang-gradient); color:white;
            padding:10px 0; border-radius:var(--nyang-radius-sm); font-size:13px; font-weight:700;
            text-decoration:none; transition:transform var(--nyang-transition), box-shadow var(--nyang-transition); }
        .cta-button:hover { transform:translateY(-1px); box-shadow:var(--nyang-shadow-soft); }
        .cta-button .cta-arrow { display:inline-block; transition:transform 250ms ease; }
        .deal:hover .cta-button .cta-arrow { transform:translateX(4px); }
"""


# ── Shared <head> block ────────────────────────────────────────────────────────
def _head(title: str, og_title: str, og_desc: str, extra_css: str = "",
          meta_desc: str = "", meta_keywords: str = "") -> str:
    seo_desc = meta_desc or og_desc
    seo_kw = meta_keywords or "알리익스프레스 특가, 펫용품 할인, 고양이 장난감, 강아지 용품, 캠핑용품, 최저가"
    return f"""<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#FF8FAB">
    <meta name="description"        content="{seo_desc}">
    <meta name="keywords"           content="{seo_kw}">
    <meta property="og:type"        content="website">
    <meta property="og:title"       content="{og_title}">
    <meta property="og:description" content="{seo_desc}">
    <meta property="og:image"       content="https://x68445.github.io/petdeals-legal/og-image.png">
    <link rel="canonical" href="https://x68445.github.io/petdeals-legal/deals.html">
    <title>{title}</title>
    <link rel="preconnect" href="https://cdn.jsdelivr.net">
    <link href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css" rel="stylesheet">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{
            font-family: 'Pretendard Variable', Pretendard, -apple-system,
                         BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(180deg, var(--nyang-cream) 0%, #fff 40%);
            color: var(--nyang-text); min-height: 100vh;
        }}
        .container {{ max-width:760px; margin:0 auto; padding:0 16px 40px; }}
        .footer {{
            text-align:center; padding:32px 16px;
            font-size:11px; color:#888; line-height:1.8;
        }}
        .footer a {{ color:#bbb; text-decoration:none; }}
        .footer a:hover {{ text-decoration:underline; }}
        {_YT_CSS}
        {extra_css}
    </style>
</head>"""


_TRACKER_URL = "http://168.107.3.136:5000/api/track"

_TRACKING_JS = f"""
<script>
(function(){{
  var T="{_TRACKER_URL}";
  var P=location.pathname.split("/").pop()||"index";
  try{{fetch(T,{{method:"POST",headers:{{"Content-Type":"application/json"}},
    body:JSON.stringify({{page:P,action:"view"}}),keepalive:true}})}}catch(e){{}}
  document.addEventListener("click",function(e){{
    var a=e.target.closest("a.deal");
    if(!a)return;
    var n=a.querySelector(".deal-name");
    var prod=n?n.textContent.trim():"";
    try{{fetch(T,{{method:"POST",headers:{{"Content-Type":"application/json"}},
      body:JSON.stringify({{page:P,action:"click",product:prod}}),keepalive:true}})}}catch(e){{}}
  }});
}})();
</script>
"""

_DATE_JS = """
<script>
(function(){
  var el=document.getElementById("update-date");
  if(!el)return;
  var now=new Date();
  var kst=new Date(now.getTime()+(9*60*60*1000)-(now.getTimezoneOffset()*60*1000));
  var y=kst.getFullYear();
  var m=String(kst.getMonth()+1).padStart(2,"0");
  var d=String(kst.getDate()).padStart(2,"0");
  el.textContent=y+"\uB144 "+m+"\uC6D4 "+d+"\uC77C";
})();
</script>
"""

_FOOTER = f"""
    <div class="footer">
        🕐 다음 업데이트: 내일 오전<br>
        매일 새로운 우리집 라이프 특가가 업데이트됩니다!<br>
        <a href="{YOUTUBE_URL}" target="_blank" rel="noopener">🎬 유튜브 채널 보러가기</a><br>
        제휴 마케팅 참여 안내 — 구매 시 커미션을 받을 수 있습니다<br>
        <a href="terms.html">이용약관</a> &nbsp;·&nbsp;
        <a href="privacy.html">개인정보처리방침</a>
    </div>
{_TRACKING_JS}"""

# YouTube promo banner shown at the top of every page (inside .container)
_YT_BANNER = f"""
        <a href="{YOUTUBE_URL}" target="_blank" rel="noopener" class="yt-banner">
            <div class="yt-left">
                <span class="yt-icon">🎬</span>
                <div class="yt-text">
                    <div class="yt-title">유튜브에서 제품 리뷰 영상 보기!</div>
                    <div class="yt-sub">@NyangDaengLife · 구독하면 매일 새 특가 알림 🐾</div>
                </div>
            </div>
            <div class="yt-arrow">▶</div>
        </a>
"""

# Shared CSS for the YouTube banner -- appended into every page's extra_css
_YT_CSS = """
        .yt-banner {
            display:flex; align-items:center; justify-content:space-between; gap:12px;
            background: linear-gradient(135deg,#ff0000 0%,#cc0000 60%,#8b0000 100%);
            color:white; text-decoration:none;
            border-radius:20px; padding:16px 20px;
            margin:16px 0 14px;
            box-shadow:0 6px 22px rgba(255,0,0,.25);
            transition:transform .2s ease, box-shadow .2s ease;
        }
        .yt-banner:hover  { transform:translateY(-3px); box-shadow:0 10px 28px rgba(255,0,0,.35); }
        .yt-banner:active { transform:scale(.98); }
        .yt-left   { display:flex; align-items:center; gap:14px; }
        .yt-icon   { font-size:32px; line-height:1; }
        .yt-title  { font-size:15px; font-weight:800; line-height:1.2; }
        .yt-sub    { font-size:12px; opacity:.85; margin-top:3px; }
        .yt-arrow  { font-size:18px; opacity:.85; flex-shrink:0; }
"""


# ── Wave SVG (header bottom divider) ──────────────────────────────────────────
_WAVE_SVG = (
    '<svg class="wave" viewBox="0 0 1440 48" preserveAspectRatio="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<path d="M0,48 L0,28 Q180,4 360,28 Q540,52 720,28 '
    'Q900,4 1080,28 Q1260,52 1440,28 L1440,48 Z" fill="#fff8f0"/>'
    '</svg>'
)

# ── Main page CSS ─────────────────────────────────────────────────────────────
_MAIN_CSS = """
        .mega-hero {
            position:relative;
            padding:60px 20px 90px;
            background:linear-gradient(135deg, #ff6b8a 0%, #ff8fab 25%, #ffb347 55%, #ffd166 100%);
            text-align:center; overflow:hidden;
        }
        .mega-hero::before {
            content:''; position:absolute; inset:0;
            background:radial-gradient(ellipse at 30% 20%, rgba(255,255,255,.25) 0%, transparent 60%),
                       radial-gradient(ellipse at 70% 80%, rgba(255,179,71,.2) 0%, transparent 50%);
            pointer-events:none;
        }
        .paw-decor {
            font-size:2.2rem; letter-spacing:12px; opacity:.8;
            animation:pawFloat 3s ease-in-out infinite;
            text-shadow:0 2px 8px rgba(0,0,0,.1);
        }
        @keyframes pawFloat {
            0%,100% { transform:translateY(0) scale(1); }
            50% { transform:translateY(-10px) scale(1.05); }
        }
        .signboard {
            position:relative; margin:25px auto 20px; padding:35px 30px 25px;
            display:inline-block;
            background:rgba(255,255,255,.08);
            border-radius:24px;
            border:2px solid rgba(255,255,255,.2);
            backdrop-filter:blur(4px);
        }
        .brand-title {
            font-size:clamp(3.5rem,16vw,5.5rem); font-weight:900;
            letter-spacing:-.02em; line-height:1; margin:0;
            background:linear-gradient(180deg,#FFFFFF 0%,#FFF5EB 40%,#FFE0C0 100%);
            -webkit-background-clip:text; -webkit-text-fill-color:transparent;
            background-clip:text;
            animation:brandShine 3s ease-in-out infinite;
            filter:drop-shadow(0 4px 10px rgba(232,90,122,.6));
            text-shadow:none;
        }
        @keyframes brandShine {
            0%,100% { filter:drop-shadow(0 4px 10px rgba(232,90,122,.6)) brightness(1); }
            50% { filter:drop-shadow(0 6px 24px rgba(255,255,255,.9)) brightness(1.15); }
        }
        .brand-divider {
            display:flex; align-items:center; justify-content:center;
            gap:14px; margin:18px auto; max-width:320px;
        }
        .divider-line {
            flex:1; height:3px;
            background:linear-gradient(90deg,transparent,rgba(255,255,255,.9),transparent);
            border-radius:999px;
        }
        .divider-icon { font-size:1.5rem; animation:pawSpin 4s linear infinite; }
        @keyframes pawSpin {
            0%,100% { transform:rotate(-10deg) scale(1); }
            50% { transform:rotate(10deg) scale(1.15); }
        }
        .sub-title {
            font-size:clamp(1.6rem,6vw,2.4rem); font-weight:800; color:white;
            letter-spacing:.25em; margin:0;
            text-shadow:0 2px 10px rgba(232,90,122,.5);
            animation:subGlow 4s ease-in-out infinite;
        }
        @keyframes subGlow {
            0%,100% { text-shadow:0 2px 10px rgba(232,90,122,.5); }
            50% { text-shadow:0 2px 20px rgba(255,255,255,.6), 0 4px 30px rgba(232,90,122,.3); }
        }
        .hero-tagline {
            font-size:1.15rem; color:white; font-weight:700;
            margin:28px 0 8px; text-shadow:0 1px 4px rgba(0,0,0,.2);
            letter-spacing:.02em;
        }
        .hero-meta {
            font-size:.88rem; color:rgba(255,255,255,.9); font-weight:600;
        }
        .sparkle {
            position:absolute; font-size:1.8rem;
            animation:sparkleFloat 3s ease-in-out infinite; pointer-events:none;
        }
        .sparkle-1 { top:8%; left:4%; animation-delay:0s; }
        .sparkle-2 { top:12%; right:8%; animation-delay:.7s; font-size:1.4rem; }
        .sparkle-3 { bottom:22%; left:10%; animation-delay:1.4s; font-size:1.5rem; }
        .sparkle-4 { bottom:12%; right:6%; animation-delay:2s; }
        .sparkle-5 { top:40%; left:2%; animation-delay:0.3s; font-size:1.2rem; }
        .sparkle-6 { top:35%; right:3%; animation-delay:1.8s; font-size:1.3rem; }
        @keyframes sparkleFloat {
            0%,100% { opacity:0; transform:scale(.4) rotate(0deg); }
            20% { opacity:.6; }
            50% { opacity:1; transform:scale(1.3) rotate(180deg); }
            80% { opacity:.6; }
        }
        .wave-bottom {
            position:absolute; bottom:-1px; left:0; right:0; height:45px;
            background:#fff8f0;
            clip-path:polygon(0 60%,25% 30%,50% 60%,75% 30%,100% 60%,100% 100%,0 100%);
        }
        .wave { position:absolute; bottom:-1px; left:0; right:0; width:100%; height:48px; display:block; }
        @media(min-width:640px) {
            .brand-title { font-size:7rem; }
            .mega-hero { padding:80px 20px 110px; }
            .signboard { padding:45px 50px 35px; }
        }

        .cat-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            margin-top: -24px;
            padding: 0 4px;
            align-items: stretch;
        }
        @media(min-width:640px) { .cat-grid { grid-template-columns: repeat(3, minmax(0,1fr)); } }
        @media(min-width:900px) { .cat-grid { grid-template-columns: repeat(4, minmax(0,1fr)); } }

        .cat-card {
            background: var(--nyang-white); border-radius: var(--nyang-radius-md);
            padding: 18px 12px 16px;
            text-align: center;
            box-shadow: var(--nyang-shadow-card);
            text-decoration: none; color: var(--nyang-text);
            display: flex; flex-direction: column;
            align-items: center; justify-content: flex-start; gap: 6px;
            transition: transform var(--nyang-transition), box-shadow var(--nyang-transition);
            border-top: 4px solid transparent;
            min-width: 0;
            height: auto;
            min-height: fit-content;
        }
        .cat-card:hover  { transform: translateY(-4px); box-shadow: var(--nyang-shadow-hover); }
        .cat-card:active { transform: scale(.97); }
        .cat-emoji { font-size:36px; line-height:1; }
        .cat-label {
            font-size: 14px;
            font-weight: 700;
            line-height: 1.4;
            width: 100%;
            max-width: 100%;
            min-font-size: 12px;
            white-space: normal;
            overflow-wrap: break-word;
            word-wrap: break-word;
            word-break: keep-all;
            hyphens: auto;
            text-overflow: clip;
            overflow: visible;
            display: block;
            padding: 0 2px;
        }
        @media(max-width:360px) { .cat-label { font-size:12px; } }
        @media(min-width:480px) { .cat-label { font-size:15px; } }
        .cat-count {
            font-size:12px; font-weight:600;
            padding:4px 10px; border-radius:999px; margin-top:4px;
            white-space: nowrap;
            flex-shrink: 0;
        }

        /* Special deals banner */
        .special-banner {
            background: var(--nyang-gradient);
            border-radius: var(--nyang-radius-md);
            padding: 20px 24px;
            margin-bottom: 16px;
            text-decoration: none;
            display: flex; align-items: center; justify-content: space-between; gap: 12px;
            box-shadow: 0 4px 20px rgba(255,71,87,.25);
            transition: transform .2s ease, box-shadow .2s ease;
        }
        .special-banner:hover  { transform: translateY(-3px); box-shadow: 0 8px 28px rgba(255,71,87,.35); }
        .special-banner:active { transform: scale(.98); }
        .sb-left  { display:flex; align-items:center; gap:14px; }
        .sb-flame { font-size:40px; animation: pulse 1.8s ease-in-out infinite; }
        @keyframes pulse {
            0%,100% { transform: scale(1);    filter: drop-shadow(0 0 4px rgba(255,200,0,.4)); }
            50%      { transform: scale(1.15); filter: drop-shadow(0 0 10px rgba(255,200,0,.7)); }
        }
        .sb-text h2  { font-size:20px; font-weight:800; color:white; line-height:1.2; }
        .sb-text p   { font-size:13px; color:rgba(255,255,255,.85); margin-top:3px; }
        .sb-right { display:flex; align-items:center; gap:10px; flex-shrink:0; }
        .sb-badge {
            background:rgba(255,255,255,.2); color:white;
            padding:5px 12px; border-radius:999px;
            font-size:13px; font-weight:700; white-space:nowrap;
        }
        .sb-arrow { font-size:22px; color:rgba(255,255,255,.8); }

        /* Section headings -- accent bar is inline span, not border */
        .section-heading {
            font-size:1.3rem; font-weight:800; color:var(--nyang-text);
            margin-top:28px; margin-bottom:16px; padding:0;
            display:flex; align-items:center; gap:10px;
        }
        .section-heading::before { content:"🐾"; font-size:1.3rem; }
        .accent-bar {
            display:inline-block; width:60px; height:4px;
            background:var(--nyang-gradient);
            border-radius:var(--nyang-radius-full); flex-shrink:0;
        }

        /* Price band grid (same 2/3/4 col as cat-grid) */
        .band-grid {
            display:grid;
            grid-template-columns: repeat(2,1fr);
            gap:12px;
        }
        @media(min-width:640px) { .band-grid { grid-template-columns:repeat(4,1fr); } }
        .band-card {
            background:var(--nyang-white); border-radius:var(--nyang-radius-md); padding:18px 12px 14px;
            text-align:center; border-top:4px solid transparent;
            text-decoration:none; color:var(--nyang-text);
            box-shadow:var(--nyang-shadow-card);
            display:flex; flex-direction:column; align-items:center; gap:4px;
            transition:transform var(--nyang-transition), box-shadow var(--nyang-transition);
        }
        .band-card:hover  { transform:translateY(-4px); box-shadow:var(--nyang-shadow-hover); }
        .band-card:active { transform:scale(.97); }
        .band-emoji  { font-size:36px; line-height:1; }
        .band-label  { font-size:14px; font-weight:700; margin-top:4px; }
        .band-range  { font-size:11px; color:#888; margin-top:2px; }
        .band-count  {
            font-size:12px; font-weight:600;
            padding:3px 9px; border-radius:999px; margin-top:5px;
        }
        .band-premium {
            background:linear-gradient(160deg,#faf6ef 0%,#f5f0e8 100%) !important;
            border:1px solid #333333 !important;
            box-shadow:0 2px 12px rgba(0,0,0,.08) !important;
        }
        .band-premium .band-label { color:#2a2520; font-weight:800; }
        .band-premium .band-range { color:#8b7355; }
        .band-premium .band-count {
            background:rgba(139,115,85,.12) !important;
            color:#8b7355 !important;
        }
        .band-luxury {
            position:relative; overflow:hidden;
            background:linear-gradient(145deg,#0a0a14 0%,#1a1530 50%,#0a0a14 100%) !important;
            border:1px solid rgba(255,215,0,.55);
            box-shadow:0 0 24px rgba(255,215,0,.25),
                       0 4px 18px rgba(0,0,0,.35) !important;
            color:#FFD700 !important;
        }
        .band-luxury::after {
            content:""; position:absolute; top:0; left:-100%; width:200%; height:100%;
            background:linear-gradient(90deg,transparent 40%,
                       rgba(255,215,0,.18) 50%,transparent 60%);
            animation:band-shimmer 3.5s infinite linear; pointer-events:none;
        }
        @keyframes band-shimmer { 0%{left:-100%} 100%{left:100%} }
        .band-luxury .band-emoji {
            filter:drop-shadow(0 0 14px rgba(255,215,0,.8));
            position:relative; z-index:1;
        }
        .band-luxury .band-label {
            position:relative; z-index:1;
            background:linear-gradient(135deg,#fff1a8,#FFD700);
            -webkit-background-clip:text; background-clip:text; color:transparent;
            font-weight:900; letter-spacing:.02em;
        }
        .band-luxury .band-range {
            position:relative; z-index:1; color:#c9a227;
        }
        .band-luxury .band-count {
            position:relative; z-index:1;
            background:linear-gradient(135deg,#ffecb3,#FFD700) !important;
            color:#0a0a14 !important;
            box-shadow:0 0 12px rgba(255,215,0,.5);
        }
        .band-luxury:hover {
            border-color:rgba(255,215,0,.9);
            box-shadow:0 0 36px rgba(255,215,0,.4),
                       0 10px 28px rgba(0,0,0,.5) !important;
        }
"""

_SEARCH_CSS = """
        html { scroll-behavior:smooth; }
        .search-sticky {
            position:sticky; top:0; z-index:20;
            background:rgba(255,249,245,.97);
            backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
            padding:10px 16px 8px;
            border-bottom:1px solid var(--nyang-border);
            max-width:760px; margin:0 auto;
        }
        .search-wrap {
            position:relative;
        }
        .search-wrap input {
            width:100%; padding:14px 20px 14px 44px;
            border:2px solid var(--nyang-border); border-radius:var(--nyang-radius-full);
            font-size:15px; font-family:inherit;
            background:var(--nyang-white); outline:none;
            transition:border-color var(--nyang-transition), box-shadow var(--nyang-transition);
            min-height:44px;
        }
        .search-wrap input:focus {
            border-color:var(--nyang-pink); background:var(--nyang-white);
            box-shadow:0 0 0 4px rgba(255,143,171,.15);
        }
        .search-wrap::before {
            content:"🐾"; position:absolute; left:16px; top:50%;
            transform:translateY(-50%); font-size:18px;
            pointer-events:none;
        }
        .filter-row {
            display:flex; flex-direction:column; gap:6px;
            margin-top:8px; padding-bottom:2px;
            overflow-x:auto; -webkit-overflow-scrolling:touch;
        }
        .filter-group {
            display:flex; gap:6px; flex-wrap:nowrap;
            overflow-x:auto; -webkit-overflow-scrolling:touch;
            scrollbar-width:none;
        }
        .filter-group::-webkit-scrollbar { display:none; }
        .fbtn {
            flex-shrink:0; padding:10px 18px;
            border:2px solid #e0c4bc; border-radius:var(--nyang-radius-full);
            background:#fff; color:#2D2D2D; font-size:.95rem;
            font-weight:700; cursor:pointer;
            min-height:36px; min-width:44px;
            transition:all var(--nyang-transition); white-space:nowrap;
            font-family:inherit;
            -webkit-text-fill-color:#2D2D2D;
        }
        .fbtn.active {
            background:linear-gradient(135deg, #FF8FAB 0%, #FFB347 50%, #FFD166 100%);
            color:#fff; border-color:transparent;
            font-weight:800; box-shadow:0 4px 20px rgba(255,143,171,.15);
            -webkit-text-fill-color:#fff;
        }
        .fbtn:hover:not(.active) {
            border-color:#FF8FAB; color:#E85A7A;
            -webkit-text-fill-color:#E85A7A;
            transform:translateY(-1px);
        }
        .results-grid {
            display:grid;
            grid-template-columns:1fr;
            gap:10px; margin-top:8px;
        }
        @media(min-width:420px) { .results-grid { grid-template-columns:repeat(2,1fr); } }
        @media(min-width:640px) { .results-grid { grid-template-columns:repeat(3,1fr); } }
        .result-card {
            background:var(--nyang-white); border-radius:var(--nyang-radius-md);
            overflow:hidden; text-decoration:none; color:var(--nyang-text);
            box-shadow:var(--nyang-shadow-card);
            transition:transform var(--nyang-transition), box-shadow var(--nyang-transition);
            display:flex; flex-direction:column;
        }
        .result-card:hover { transform:translateY(-2px); box-shadow:var(--nyang-shadow-hover); }
        .result-card:active { transform:scale(.98); }
        .rc-img {
            width:100%; aspect-ratio:1/1; object-fit:cover;
            background:#f5f5f5; display:block;
        }
        .rc-body { padding:10px 12px 12px; flex:1; display:flex; flex-direction:column; }
        .rc-name {
            font-size:14px; font-weight:800; line-height:1.35; color:var(--nyang-text);
            letter-spacing:-0.01em;
            display:-webkit-box; -webkit-line-clamp:2;
            -webkit-box-orient:vertical; overflow:hidden;
        }
        .rc-desc {
            font-size:11px; color:var(--nyang-accent); margin-top:4px; font-weight:600;
            background:var(--nyang-gradient-soft); padding:4px 8px;
            border-radius:var(--nyang-radius-sm); line-height:1.3;
        }
        .rc-desc::before { content:"\\1F4AC"; margin-right:3px; }
        .rc-price-row { margin-top:auto; padding-top:6px; }
        .rc-orig { font-size:11px; color:#aaa; text-decoration:line-through; }
        .rc-price { font-size:15px; font-weight:800; color:#1a1a1a; }
        .rc-disc {
            display:inline-block; background:var(--nyang-gradient-discount); color:#fff;
            font-size:10px; font-weight:700; padding:2px 6px;
            border-radius:var(--nyang-radius-sm); margin-left:4px;
        }
        #search-results .no-results {
            text-align:center; padding:40px 16px;
            color:var(--nyang-text-soft); font-size:14px;
        }
        .countdown-banner {
            display:flex; align-items:center; justify-content:space-between; gap:16px;
            background:linear-gradient(135deg,#D94466,#E85A7A,#FF6B6B);
            color:#fff; padding:16px 22px;
            font-weight:700; font-size:1.05rem;
            max-width:500px; margin:16px auto;
            border-radius:var(--nyang-radius-md);
            box-shadow:0 4px 20px rgba(232,90,122,.25);
            animation:countdownPulse 2.5s ease-in-out infinite;
        }
        @keyframes countdownPulse {
            0%,100% { box-shadow:0 4px 20px rgba(232,90,122,.25); }
            50% { box-shadow:0 6px 28px rgba(232,90,122,.4); }
        }
        .cb-icon { font-size:24px; animation:fireFlicker 1.5s ease-in-out infinite; }
        @keyframes fireFlicker {
            0%,100% { transform:scale(1); }
            50% { transform:scale(1.15); }
        }
        .cb-text {
            color:#fff; font-weight:700;
            text-shadow:0 1px 4px rgba(0,0,0,.2);
        }
        .cb-timer {
            background:rgba(255,255,255,.3); padding:7px 16px;
            border-radius:var(--nyang-radius-full);
            font-family:'SF Mono',Menlo,monospace;
            font-weight:800; font-size:1.1rem; color:white;
            backdrop-filter:blur(8px); letter-spacing:.05em;
        }
        .yt-subscribe-cta {
            display:block; text-align:center;
            background:linear-gradient(135deg,#ff0000,#cc0000);
            color:white; text-decoration:none;
            padding:16px 20px; border-radius:16px;
            margin:24px 0 8px; font-weight:700; font-size:14px;
            box-shadow:0 4px 16px rgba(255,0,0,.2);
            transition:transform .2s, box-shadow .2s;
        }
        .yt-subscribe-cta:hover { transform:translateY(-2px); box-shadow:0 8px 24px rgba(255,0,0,.3); }
        @media(max-width:640px) {
            .cat-label { font-size:13px !important; min-height:auto; }
            .cat-card { padding:14px 8px 12px; min-height:auto; }
            .band-card { padding:14px 8px 10px; }
            .cat-card, .band-card { min-height:44px; }
        }
"""

_COUNTDOWN_JS = """
<script>
(function(){
  var el=document.getElementById("countdown-timer");
  if(!el)return;
  function tick(){
    var now=new Date();
    var kst=new Date(now.getTime()+(9*60*60*1000)-(now.getTimezoneOffset()*60*1000));
    var midnight=new Date(kst);
    midnight.setHours(24,0,0,0);
    var diff=midnight-kst;
    if(diff<=0){el.textContent="00:00:00";return;}
    var h=Math.floor(diff/3600000);
    var m=Math.floor((diff%3600000)/60000);
    var s=Math.floor((diff%60000)/1000);
    el.textContent=String(h).padStart(2,"0")+":"+String(m).padStart(2,"0")+":"+String(s).padStart(2,"0");
  }
  tick();setInterval(tick,1000);
})();
</script>
"""

_SEARCH_JS = """
<script>
(function(){
  var P=window.__PRODUCTS||[];
  var input=document.getElementById("search-input");
  var results=document.getElementById("search-results");
  var grid=document.getElementById("results-grid");
  var browse=document.getElementById("browse-sections");
  var countEl=document.getElementById("result-count");
  var filters={price:"",cat:"",disc:""};

  // Filter buttons
  document.querySelectorAll(".fbtn").forEach(function(btn){
    btn.addEventListener("click",function(){
      var f=this.dataset.filter, v=this.dataset.val;
      filters[f]=v;
      this.parentNode.querySelectorAll(".fbtn").forEach(function(b){b.classList.remove("active")});
      this.classList.add("active");
      render();
    });
  });

  input.addEventListener("input",function(){ render(); });

  function matchBand(band,f){
    if(!f) return true;
    if(f==="1k") return band==="price_1k"||band==="price_5k";
    if(f==="10k") return band==="price_10k"||band==="price_30k";
    if(f==="100k") return band==="price_100k";
    return true;
  }

  function render(){
    var q=(input.value||"").trim().toLowerCase();
    var hasFilter=q||filters.price||filters.cat||filters.disc;
    if(!hasFilter){
      results.style.display="none";
      browse.style.display="block";
      return;
    }
    results.style.display="block";
    browse.style.display="none";

    var matched=P.filter(function(p){
      if(q && p.n.toLowerCase().indexOf(q)===-1
         && (p.d||"").toLowerCase().indexOf(q)===-1) return false;
      if(filters.price && !matchBand(p.b,filters.price)) return false;
      if(filters.cat && p.c!==filters.cat) return false;
      if(filters.disc){
        var minDisc=parseInt(filters.disc);
        if(p.dc<minDisc) return false;
      }
      return true;
    });

    countEl.textContent="("+matched.length+"개)";
    if(!matched.length){
      grid.innerHTML='<div class="no-results" style="grid-column:1/-1">검색 결과가 없습니다</div>';
      return;
    }

    var html="";
    matched.forEach(function(p){
      var discHeroHtml=p.dc>=10?'<div class="discount-hero" style="font-size:22px;margin:8px 0 4px">'+p.dc+'% OFF</div>':"";
      var descHtml=p.d?'<div class="rc-desc">'+p.d+'</div>':"";
      var imgHtml=p.i?'<img class="rc-img" src="'+p.i+'" loading="lazy" referrerpolicy="no-referrer" alt="" onerror="this.style.display=\\'none\\'">'
        :'<div class="rc-img" style="display:flex;align-items:center;justify-content:center;font-size:32px">📦</div>';
      html+='<a href="'+p.l+'" class="result-card" target="_blank" rel="nofollow sponsored noopener">'
        +imgHtml
        +'<div class="rc-body">'
        +'<div class="rc-name">'+p.n+'</div>'
        +descHtml
        +discHeroHtml
        +'<div class="cta-button" style="margin:8px 10px 10px;font-size:12px;padding:8px 0">'
        +'알리에서 가격 확인하기 <span class="cta-arrow">\u2192</span></div>'
        +'</div></a>';
    });
    grid.innerHTML=html;
  }
})();
</script>
"""


def _main_page_html(today: str, total: int,
                    category_counts: dict, categories: list,
                    special_count: int = 0,
                    band_counts: dict | None = None,
                    all_products: list | None = None) -> str:
    from modules.category_mapper import PRICE_BANDS

    # 🔥 Special deals banner
    banner_html = ""
    if special_count > 0:
        banner_html = f"""
        <a href="special_deals.html" class="special-banner">
            <div class="sb-left">
                <div class="sb-flame">🔥</div>
                <div class="sb-text">
                    <h2>특가할인</h2>
                    <p>50% 이상 할인 상품 모음</p>
                </div>
            </div>
            <div class="sb-right">
                <div class="sb-badge">{special_count}개 상품</div>
                <div class="sb-arrow">›</div>
            </div>
        </a>"""

    # 💰 Price band cards
    band_counts = band_counts or {}
    band_cards_html = ""
    band_ranges = {"price_1k": "10-29% 할인",
                   "price_10k": "30-49% 할인",
                   "price_100k": "50%+ 할인"}
    any_band = False
    for band in PRICE_BANDS:
        key    = band["key"]
        count  = band_counts.get(key, 0)
        if count == 0:
            continue
        any_band = True
        emoji  = band["emoji"]
        label  = band["label"]
        accent = band["accent"]
        rgb    = _hex_rgb(accent)
        rng    = band_ranges.get(key, "")
        tier   = band.get("tier", "light")
        band_cards_html += f"""
        <a href="{key}.html" class="band-card band-{tier}" style="border-top-color:{accent}">
            <div class="band-emoji">{emoji}</div>
            <div class="band-label">{label}</div>
            <div class="band-range">{rng}</div>
            <div class="band-count"
                 style="background:rgba({rgb},.12);color:{accent}">{count}개</div>
        </a>"""

    band_section = ""
    if any_band:
        band_section = f"""
        <div class="section-heading"
             ><span class="accent-bar" style="background:#ff8c42"></span>🔥 할인별</div>
        <div class="band-grid">{band_cards_html}</div>"""

    # 📂 Category cards
    cards_html = ""
    for key, emoji, label in categories:
        count = category_counts.get(key, 0)
        if count == 0:
            continue
        accent = _ACCENT.get(key, "#9e9e9e")
        rgb    = _hex_rgb(accent)
        cards_html += f"""
        <a href="category_{key}.html" class="cat-card"
           style="border-top-color:{accent}">
            <div class="cat-emoji">{emoji}</div>
            <div class="cat-label">{label}</div>
            <div class="cat-count"
                 style="background:rgba({rgb},.12);color:{accent}">{count}개</div>
        </a>"""

    cat_section = f"""
        <div class="section-heading"
             ><span class="accent-bar" style="background:#607d8b"></span>📂 카테고리별</div>
        <div class="cat-grid">{cards_html}</div>"""

    # Build product JSON for search/filter
    import json as _json
    products_json = "[]"
    if all_products:
        slim = []
        for p in all_products:
            name = (p.get("name_ko") or p.get("product_title") or "")[:50]
            if not name:
                continue
            krw = int(_safe_float(p.get("price", 0)))
            disc = int(_safe_float(p.get("discount", 0)))
            orig_krw = 0
            if disc > 0 and krw > 0:
                orig_krw = int(krw / (1 - disc / 100)) if disc < 100 else 0
            elif _safe_float(p.get("target_original_price", 0)) > 0:
                orig_krw = int(_safe_float(p.get("target_original_price", 0)))
            slim.append({
                "n": name,
                "d": (p.get("name_desc") or "")[:25],
                "c": p.get("category_key", "etc"),
                "b": p.get("price_band", "price_1k"),
                "p": krw,
                "o": orig_krw if orig_krw > krw else 0,
                "dc": disc,
                "l": p.get("affiliate_link", "#"),
                "i": p.get("image_url") or p.get("product_main_image_url", ""),
            })
        products_json = _json.dumps(slim, ensure_ascii=False)

    head = _head(
        title=f"🐾 {BRAND_NAME} 오늘의 특가",
        og_title=f"냥댕라이프 - 오늘의 특가",
        og_desc=f"냥댕라이프 - 우리 가족 댕냥이부터 집안 살림까지, 매일 엄선 특가",
        extra_css=_MAIN_CSS + _SEARCH_CSS,
        meta_desc="냥댕라이프 - 우리 가족 댕냥이부터 집안 살림까지, 매일 엄선 특가. 반려동물, 살림, 패션, 전자 할인",
        meta_keywords="냥댕라이프, 반려동물 할인, 고양이 용품, 강아지 용품, 집안 살림, 캠핑, 최저가",
    )
    return f"""<!DOCTYPE html>
<html lang="ko">
{head}
<body>
    <header class="mega-hero">
        <div class="paw-decor">🐾🐾🐾</div>
        <div class="signboard">
            <div class="sparkle sparkle-1">✨</div>
            <div class="sparkle sparkle-2">✨</div>
            <div class="sparkle sparkle-3">⭐</div>
            <div class="sparkle sparkle-4">💫</div>
            <div class="sparkle sparkle-5">🌟</div>
            <div class="sparkle sparkle-6">✨</div>
            <h1 class="brand-title">{BRAND_NAME}</h1>
            <div class="brand-divider">
                <span class="divider-line"></span>
                <span class="divider-icon">🐾</span>
                <span class="divider-line"></span>
            </div>
            <h2 class="sub-title">오늘의 특가</h2>
        </div>
        <p class="hero-tagline">우리집 댕냥이 & 라이프 특가 😸🐕</p>
        <p class="hero-meta"><span id="update-date">{today}</span> 업데이트 · 총 {total}개 상품</p>
        <div class="wave-bottom"></div>
    </header>
    <div class="search-sticky" id="search-sticky">
        <div class="search-wrap">
            <input type="text" id="search-input" placeholder="상품 검색..."
                   autocomplete="off" />
        </div>
        <div class="filter-row" id="filter-row">
            <div class="filter-group">
                <button class="fbtn active" data-filter="price" data-val="">전체</button>
                <button class="fbtn" data-filter="price" data-val="1k">💰가성비</button>
                <button class="fbtn" data-filter="price" data-val="10k">🔥핫딜</button>
                <button class="fbtn" data-filter="price" data-val="100k">💎초특가</button>
            </div>
            <div class="filter-group">
                <button class="fbtn active" data-filter="cat" data-val="">전체</button>
                <button class="fbtn" data-filter="cat" data-val="pet">🐾반려동물</button>
                <button class="fbtn" data-filter="cat" data-val="home">🏠우리집</button>
                <button class="fbtn" data-filter="cat" data-val="outdoor">🚗나들이</button>
                <button class="fbtn" data-filter="cat" data-val="fashion">👕패션</button>
                <button class="fbtn" data-filter="cat" data-val="sports">💪건강</button>
                <button class="fbtn" data-filter="cat" data-val="electronics">💻전자</button>
                <button class="fbtn" data-filter="cat" data-val="etc">🔥추천템</button>
            </div>
        </div>
    </div>
    <div class="countdown-banner" id="countdown-banner">
        <span class="cb-icon">🔥</span>
        <span class="cb-text">오늘만! 자정까지 특가</span>
        <span class="cb-timer" id="countdown-timer">00:00:00</span>
    </div>
    <div class="container">
        <div id="search-results" style="display:none">
            <div class="section-heading">
                <span class="accent-bar"></span>🔍 검색 결과 <span id="result-count" style="font-size:13px;color:#888;font-weight:400"></span>
            </div>
            <div id="results-grid" class="results-grid"></div>
        </div>
        <div id="browse-sections">
            {_YT_BANNER}
            {banner_html}
            {band_section}
            {cat_section}
        </div>
        <a href="{YOUTUBE_URL}" target="_blank" rel="noopener" class="yt-subscribe-cta">
            💌 매일 새 특가 알림 받기 → 유튜브 구독
        </a>
    </div>
    {_FOOTER}
    {_DATE_JS}
    {_COUNTDOWN_JS}
    <script>window.__PRODUCTS={products_json};</script>
    {_SEARCH_JS}
</body>
</html>"""


# ── Category page CSS (accent-aware) ─────────────────────────────────────────
def _cat_css(accent: str) -> str:
    rgb = _hex_rgb(accent)
    return f"""
        :root {{ --accent:{accent}; --accent-rgb:{rgb}; }}

        .top-bar {{
            position:sticky; top:0; z-index:10;
            background:rgba(255,255,255,.95);
            backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
            padding:12px 16px; border-bottom:1px solid #f0f0f0;
        }}
        .top-bar a {{
            color:var(--accent); font-size:14px; font-weight:500;
            text-decoration:none;
        }}
        .top-bar a:hover {{ text-decoration:underline; }}

        .cat-hero {{
            background: rgba(var(--accent-rgb),.07);
            padding:32px 24px 28px; text-align:center;
        }}
        .hero-emoji {{ font-size:56px; line-height:1; }}
        .cat-hero h1 {{ font-size:24px; font-weight:800; margin-top:10px; }}
        .prod-count {{
            display:inline-block; margin-top:8px; font-size:13px;
            font-weight:600; color:var(--accent);
            background:rgba(var(--accent-rgb),.10);
            padding:4px 14px; border-radius:999px;
        }}

        .deals {{ padding-top:16px; }}
        .deal {{
            display:flex; align-items:center; gap:14px;
            background:white; border-radius:16px; padding:14px;
            margin-bottom:12px; text-decoration:none; color:#1a1a1a;
            box-shadow:0 2px 8px rgba(0,0,0,.04);
            border-left:4px solid var(--accent);
            transition:transform .2s ease, box-shadow .2s ease;
        }}
        .deal:hover  {{ transform:translateY(-2px); box-shadow:0 6px 20px rgba(0,0,0,.08); }}

        .thumb {{
            width:72px; height:72px; border-radius:12px; flex-shrink:0;
            overflow:hidden;
            background:rgba(var(--accent-rgb),.12);
            display:flex; align-items:center; justify-content:center;
            font-size:28px;
            aspect-ratio:1/1;
        }}
        .thumb img {{ width:72px; height:72px; object-fit:cover; display:block; flex-shrink:0; aspect-ratio:1/1; }}

        .deal-name {{
            font-size:15px; font-weight:600; line-height:1.4;
            display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
            overflow:hidden;
        }}
        .deal-desc {{
            font-size:12px; color:var(--nyang-accent); font-weight:600;
            margin-top:4px; line-height:1.3;
            background:var(--nyang-gradient-soft); padding:6px 10px;
            border-radius:var(--nyang-radius-sm);
        }}
        .deal-desc::before {{ content:"\\1F4AC"; margin-right:4px; }}
        .discount-hero {{ font-size:2.2rem; font-weight:900; text-align:center; margin:10px 0 4px;
            letter-spacing:-0.02em; padding:12px 0;
            background:var(--nyang-gradient-discount);
            -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
            animation:discountPulse 2s ease-in-out infinite; }}
        .deal-arrow {{ font-size:20px; color:var(--accent); opacity:.4; flex-shrink:0; }}
""" + _CARD_BASE_CSS


def _redirect_html(target_filename: str, base_url: str) -> str:
    target_url = f"{base_url}/{target_filename}"
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>이동 중... - {BRAND_NAME}</title>
<meta http-equiv="refresh" content="0; url={target_filename}">
<link rel="canonical" href="{target_url}">
<script>window.location.replace("{target_filename}");</script>
</head>
<body>
<p>페이지가 이동되었습니다. <a href="{target_filename}">여기를 클릭</a>하세요.</p>
</body>
</html>"""


def _category_page_html(key: str, emoji: str, label: str,
                         products: list, today: str) -> str:
    accent = _ACCENT.get(key, "#9e9e9e")

    sorted_prods = sorted(
        products,
        key=lambda p: (-_safe_float(p.get("commission_rate", "0")),
                       -_safe_float(p.get("discount", 0)),
                        _safe_float(p.get("price", 0)))
    )

    top_ids = compute_top_discount_ids(sorted_prods)
    now = datetime.now()
    cards_html = ""
    for idx, p in enumerate(sorted_prods):
        cards_html += _render_deal_card(
            p, idx, fallback_emoji=emoji,
            top_discount_ids=top_ids,
            is_new=is_new_product(p, now),
        )

    head = _head(
        title=f"{emoji} {label} - {BRAND_NAME}",
        og_title=f"{emoji} {label} 특가 모음 | {BRAND_NAME}",
        og_desc=f"{label} 카테고리 특가 {len(sorted_prods)}개! 알리익스프레스 최저가.",
        extra_css=_cat_css(accent),
    )
    return f"""<!DOCTYPE html>
<html lang="ko">
{head}
<body>
    <div class="top-bar">
        <a href="deals.html">← 전체 카테고리</a>
    </div>
    <div class="cat-hero">
        <div class="hero-emoji">{emoji}</div>
        <h1>{label}</h1>
        <div class="prod-count">{len(sorted_prods)}개 상품</div>
    </div>
    <div class="container">
        {_YT_BANNER}
        <div class="deals">{cards_html}</div>
        <a href="{YOUTUBE_URL}" target="_blank" rel="noopener"
           style="display:block;text-align:center;background:linear-gradient(135deg,#ff0000,#cc0000);color:white;text-decoration:none;padding:16px 20px;border-radius:16px;margin:24px 0 8px;font-weight:700;font-size:14px">
            💌 매일 새 특가 알림 받기 → 유튜브 구독
        </a>
    </div>
    {_FOOTER}
</body>
</html>"""


def _render_deal_card(p: dict, idx: int,
                      fallback_emoji: str = "📦",
                      border_accent: str | None = None,
                      thumb_bg_rgb: str | None = None,
                      arrow_color: str | None = None,
                      extra_badge_html: str = "",
                      top_discount_ids: set | None = None,
                      is_new: bool = False) -> str:
    """Render one <a class='deal'> card with badges and CTA."""
    name  = (p.get("name_ko") or p.get("product_title") or p.get("name", ""))[:50]
    desc  = (p.get("name_desc") or "").strip()
    price = _safe_float(p.get("price", 0))
    disc  = _safe_float(p.get("discount", 0))
    krw   = int(price) or int(_safe_float(p.get("price_krw", 0)))
    link  = p.get("affiliate_link", "#")
    img   = p.get("image_url") or p.get("product_main_image_url", "")
    if not name or not link or link == "#":
        return ""

    thumb_inner = (
        f'<img src="{img}" alt="" loading="lazy" referrerpolicy="no-referrer"'
        f' onerror="this.outerHTML=\'<span>{fallback_emoji}</span>\'">'
        if img else fallback_emoji
    )
    # Discount hero (no price display -- users check on AliExpress)
    if disc >= 10:
        discount_hero_html = f'<div class="discount-hero">{int(disc)}% OFF</div>'
    else:
        discount_hero_html = ""

    commission = _safe_float(p.get("commission_rate", "0"))
    badges = []
    if commission > 8:
        badges.append('<span class="rec-badge">💎 추천</span>')
    if extra_badge_html:
        badges.append(extra_badge_html)
    badge_row = (f'<div class="badge-row">{"".join(badges)}</div>'
                 if badges else "")
    desc_html = f'<div class="deal-desc">{desc}</div>' if desc else ""
    disclaimer_html = '<div class="deal-disclaimer">👉 알리에서 실시간 가격 확인</div>'

    _top_ids = top_discount_ids or set()
    pid = p.get("id") or p.get("product_id")
    show_top = pid and pid in _top_ids
    show_new = is_new
    top_badge_html = '<span class="top-badge">🏆 할인률 TOP10</span>' if show_top else ""
    new_badge_html = '<span class="new-badge">✨ NEW</span>' if show_new else ""
    cta_btn_html = '<div class="cta-button">알리에서 가격 확인하기 <span class="cta-arrow">→</span></div>'

    # Freshness indicator
    freshness_html = ""
    updated_at = p.get("price_updated_at") or p.get("collected_at", "")
    if updated_at:
        try:
            from datetime import datetime as _dt
            ts = _dt.fromisoformat(updated_at.replace("Z", "+00:00"))
            hours_ago = int((_dt.now() - ts.replace(tzinfo=None)).total_seconds() / 3600)
            if hours_ago < 1:
                freshness_html = '<div class="deal-freshness">방금 업데이트</div>'
            elif hours_ago < 24:
                freshness_html = f'<div class="deal-freshness">{hours_ago}시간 전 업데이트</div>'
            else:
                days = hours_ago // 24
                freshness_html = f'<div class="deal-freshness">{days}일 전 업데이트</div>'
        except Exception:
            pass

    style_bits = []
    if border_accent:
        style_bits.append(f"border-left-color:{border_accent}")
    deal_style = f' style="{";".join(style_bits)}"' if style_bits else ""

    thumb_style = f' style="background:rgba({thumb_bg_rgb},.12)"' if thumb_bg_rgb else ""
    arrow_style = f' style="color:{arrow_color}"' if arrow_color else ""

    return f"""
        <a href="{link}" class="deal" target="_blank" rel="nofollow sponsored noopener"{deal_style}>
            {top_badge_html}
            {new_badge_html}
            <div class="thumb"{thumb_style}>{thumb_inner}</div>
            <div class="deal-info">
                <div class="deal-name">{name}</div>
                {desc_html}
                {badge_row}
                {discount_hero_html}
                {disclaimer_html}
                {freshness_html}
                {cta_btn_html}
            </div>
            <div class="deal-arrow"{arrow_style}>›</div>
        </a>"""


# ── Price Band page ──────────────────────────────────────────────────────────
def _price_band_page_html(band: dict, grouped_by_cat: dict,
                           total: int, today: str, categories: list) -> str:
    """Generate price_*.html -- products in a band, grouped by category."""
    accent  = band["accent"]
    rgb     = _hex_rgb(accent)
    emoji   = band["emoji"]
    label   = band["label"]
    tier    = band.get("tier", "light")
    cat_meta = {key: (e, lbl) for key, e, lbl in categories}

    # Tier-aware badge injection
    if tier == "luxury":
        force_badge = '<span class="vip-badge">👑 프리미엄</span>'
    elif tier == "premium":
        force_badge = '<span class="rec-badge">✨ 추천</span>'
    else:
        force_badge = ""

    now = datetime.now()
    sections_html = ""
    for cat_key, prods in grouped_by_cat.items():
        ce, cl = cat_meta.get(cat_key, ("📦", cat_key))
        cat_accent = _ACCENT.get(cat_key, "#9e9e9e")
        cat_rgb    = _hex_rgb(cat_accent)

        top_ids = compute_top_discount_ids(prods)
        cards_html = ""
        for idx, p in enumerate(prods):
            cards_html += _render_deal_card(
                p, idx, fallback_emoji=ce,
                border_accent=cat_accent, thumb_bg_rgb=cat_rgb,
                arrow_color=cat_accent,
                extra_badge_html=force_badge,
                top_discount_ids=top_ids,
                is_new=is_new_product(p, now),
            )

        sections_html += f"""
        <div class="section">
            <div class="section-header" style="border-left-color:{cat_accent}">
                <span class="sec-emoji">{ce}</span>
                <span class="sec-label">{cl}</span>
                <span class="sec-badge"
                      style="background:rgba({cat_rgb},.12);color:{cat_accent}">{len(prods)}개</span>
            </div>
            {cards_html}
        </div>"""

    band_ranges = {"price_1k": "10-29% 할인",
                   "price_10k": "30-49% 할인",
                   "price_100k": "50%+ 할인"}
    rng = band_ranges.get(band["key"], "")

    extra_css = _band_tier_css(tier, accent, rgb)

    head = _head(
        title=f"{emoji} {label} - {BRAND_NAME}",
        og_title=f"{emoji} {label} ({rng}) | {BRAND_NAME}",
        og_desc=f"{label} 펫 특가 {total}개! 알리익스프레스 {rng} 상품 모음.",
        extra_css=extra_css,
    )

    vip_banner = ""
    subtitle = ""
    if tier == "luxury":
        vip_banner = """
        <div class="vip-banner">
            <div class="vip-shimmer"></div>
            <div class="vip-content">
                <div class="vip-crown">💎</div>
                <div class="vip-text">
                    <div class="vip-title">VIP 특가</div>
                    <div class="vip-sub">최고급 엄선 상품</div>
                </div>
            </div>
        </div>"""
        subtitle = '<div class="hero-sub">🏆 최고급 엄선 상품</div>'
    elif tier == "premium":
        subtitle = '<div class="hero-sub">✨ 프리미엄 선별</div>'

    return f"""<!DOCTYPE html>
<html lang="ko">
{head}
<body class="tier-{tier}">
    <div class="top-bar"><a href="deals.html">← 전체 카테고리</a></div>
    <div class="band-hero">
        <div class="hero-emoji">{emoji}</div>
        <h1>{label}</h1>
        {subtitle}
        <div class="range">{rng}</div>
        <div class="prod-count">{total}개 상품 · {today} 기준</div>
    </div>
    <div class="container">
        {vip_banner}
        {_YT_BANNER}
        {sections_html}
    </div>
    {_FOOTER}
</body>
</html>"""


# ── Tier-aware CSS for price band pages ──────────────────────────────────────
_SHARED_BAND_CSS = """
        .top-bar a:hover { text-decoration:underline; }
        .band-hero { padding:40px 24px 32px; text-align:center; }
        .hero-emoji { font-size:64px; line-height:1; }
        .band-hero h1 { font-size:28px; font-weight:900; margin-top:12px; letter-spacing:-.01em; }
        .hero-sub { font-size:13px; font-weight:700; margin-top:6px; opacity:.85; }
        .band-hero .range { font-size:13px; margin-top:6px; opacity:.65; }
        .prod-count { display:inline-block; margin-top:10px; font-size:13px; font-weight:700;
            padding:5px 16px; border-radius:999px; }
        .section { margin-bottom:32px; }
        .section-header { display:flex; align-items:center; gap:10px;
            padding:10px 0 10px 12px; border-left:4px solid currentColor; margin-bottom:12px; }
        .sec-emoji { font-size:22px; } .sec-label { font-size:16px; font-weight:800; flex:1; }
        .sec-badge { font-size:12px; font-weight:700; padding:3px 10px; border-radius:999px; }
        .deal { display:flex; align-items:center; gap:14px; padding:16px; margin-bottom:12px;
            text-decoration:none; border-radius:18px;
            transition:transform .2s ease, box-shadow .2s ease, border-color .2s ease; }
        .thumb { flex-shrink:0; overflow:hidden; display:flex;
            align-items:center; justify-content:center; font-size:28px; aspect-ratio:1/1; }
        .thumb img { width:100%; height:100%; object-fit:cover; display:block; aspect-ratio:1/1; }
        .deal-name { font-weight:700; line-height:1.4;
            display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
        .deal-desc { font-size:12px; font-weight:600; margin-top:4px; line-height:1.3; }
        .deal-arrow { font-size:20px; opacity:.5; flex-shrink:0; }
""" + _CARD_BASE_CSS


def _band_tier_css(tier: str, accent: str, rgb: str) -> str:
    base = f""":root {{ --accent:{accent}; --accent-rgb:{rgb}; }}
        .top-bar {{ position:sticky; top:0; z-index:10;
            padding:12px 16px; }}
        .top-bar a {{ font-size:14px; font-weight:600; text-decoration:none; }}
""" + _SHARED_BAND_CSS

    if tier == "light":
        return base + """
        body.tier-light { background:#ffffff; color:#333; }
        .tier-light .top-bar { background:#ffffff;
            border-bottom:1px solid #eee; }
        .tier-light .top-bar a { color:#888; }
        .tier-light .band-hero {
            background:#fafafa;
            border-bottom:1px solid #f0f0f0;
            padding:32px 24px 24px; }
        .tier-light .hero-emoji { font-size:44px; }
        .tier-light .band-hero h1 { color:#333; font-size:22px; font-weight:700;
            letter-spacing:0; }
        .tier-light .hero-sub { color:#999; font-weight:400; font-size:12px; }
        .tier-light .range { color:#aaa; font-size:12px; }
        .tier-light .prod-count { color:#888;
            background:#f0f0f0; font-weight:500; font-size:12px; }
        .tier-light .section-header { border-left-color:#ddd !important; }
        .tier-light .sec-label { color:#444; font-weight:600; font-size:15px; }
        .tier-light .sec-badge {
            background:#f5f5f5 !important;
            color:#888 !important; }
        .tier-light .deal {
            background:#ffffff;
            border:1px solid #e8e8e8;
            border-radius:8px;
            box-shadow:none;
            padding:12px; }
        .tier-light .deal:hover {
            border-color:#d0d0d0;
            box-shadow:0 1px 4px rgba(0,0,0,.04); }
        .tier-light .thumb { width:64px; height:64px; border-radius:6px;
            background:#f8f8f8; }
        .tier-light .thumb img { width:64px; height:64px; }
        .tier-light .deal-name { font-size:13px; color:#333; font-weight:600; }
        .tier-light .deal-desc { display:none; }
        .tier-light .badge-row { display:none; }
        .tier-light .badge { display:none; }
        .tier-light .discount-hero { font-size:20px; -webkit-text-fill-color:#333; }
        .tier-light .deal-arrow { color:#ccc; font-size:16px; }
"""


    if tier == "premium":
        return base + """
        body.tier-premium {
            background:#fdfcfa;
            color:#2a2520; }
        .tier-premium .top-bar {
            background:rgba(253,252,250,.97);
            backdrop-filter:blur(10px);
            border-bottom:1px solid #e8e2d8; }
        .tier-premium .top-bar a { color:#5a4a32; font-weight:600; }
        .tier-premium .band-hero {
            background:linear-gradient(180deg,#f5f0e8 0%,#fdfcfa 100%);
            border-bottom:1px solid #e8e2d8;
            padding:44px 24px 36px; }
        .tier-premium .hero-emoji { font-size:52px; }
        .tier-premium .band-hero h1 {
            font-family: Georgia, 'Times New Roman', 'Nanum Myeongjo', serif;
            color:#2a2520;
            font-size:26px; font-weight:700;
            letter-spacing:.02em;
            margin-top:12px; }
        .tier-premium .hero-sub {
            color:#a08968;
            font-size:11px; font-weight:500;
            letter-spacing:.15em;
            margin-top:10px; }
        .tier-premium .range { color:#b0a08a; font-size:12px;
            letter-spacing:.03em; margin-top:6px; }
        .tier-premium .prod-count {
            color:#5a4a32;
            background:rgba(139,115,85,.08);
            border:1px solid rgba(139,115,85,.15);
            font-weight:500;
            letter-spacing:.02em; }
        .tier-premium .section-header {
            border-left-color:#d4c5a9 !important;
            padding-bottom:12px;
            margin-bottom:14px; }
        .tier-premium .sec-emoji { font-size:20px; }
        .tier-premium .sec-label {
            color:#2a2520;
            font-family: Georgia, 'Times New Roman', serif;
            font-weight:600; font-size:15px;
            letter-spacing:.01em; }
        .tier-premium .sec-badge {
            background:rgba(139,115,85,.08) !important;
            color:#a08968 !important; }
        .tier-premium .deal {
            background:#ffffff;
            border:1px solid #d8d0c4;
            border-radius:6px;
            box-shadow:0 1px 4px rgba(42,37,32,.04);
            padding:16px;
            gap:14px; }
        .tier-premium .deal:hover {
            transform:translateY(-1px);
            box-shadow:0 2px 8px rgba(42,37,32,.08);
            border-color:#c0b8aa; }
        .tier-premium .thumb {
            width:84px; height:84px; border-radius:4px;
            background:#f8f5f0;
            border:1px solid #e8e2d8; }
        .tier-premium .thumb img { width:84px; height:84px; }
        .tier-premium .deal-name {
            font-size:14px;
            color:#2a2520;
            font-weight:600;
            font-family: Georgia, 'Times New Roman', serif;
            line-height:1.45; }
        .tier-premium .deal-desc { color:#a08968; font-weight:400; font-size:11px; }
        .tier-premium .discount-hero {
            font-size:24px;
            -webkit-text-fill-color:#2a2520;
            font-family: Georgia, 'Times New Roman', serif; }
        .tier-premium .deal-arrow { color:#c0b8aa; }
        .tier-premium .badge {
            background:transparent !important;
            color:#a08968 !important;
            border:1px solid #d4c5a9;
            font-weight:600;
            letter-spacing:.03em;
            padding:2px 8px !important;
            border-radius:3px !important;
            font-size:10px !important; }
        .tier-premium .rec-badge {
            background:rgba(212,197,169,.15);
            color:#8b7355;
            border:1px solid #d4c5a9;
            padding:2px 9px;
            border-radius:3px;
            font-size:10px;
            font-weight:600;
            letter-spacing:.08em;
            white-space:nowrap; }
"""


    # luxury
    return base + """
        body.tier-luxury { background:radial-gradient(ellipse at top,#1a1530 0%,#0a0a14 60%,#000 100%);
            background-attachment:fixed; color:#f5e8c7; }
        .tier-luxury .top-bar { background:rgba(10,10,20,.85);
            backdrop-filter:blur(14px);
            border-bottom:1px solid rgba(255,215,0,.25); }
        .tier-luxury .top-bar a { color:#FFD700; }
        .tier-luxury .band-hero {
            position:relative; overflow:hidden;
            background:linear-gradient(135deg,#0a0a14 0%,#1a1530 50%,#0a0a14 100%);
            border-bottom:1px solid rgba(255,215,0,.3); }
        .tier-luxury .band-hero::before {
            content:""; position:absolute; top:0; left:-100%; width:200%; height:100%;
            background:linear-gradient(90deg,transparent 0%,
                       rgba(255,215,0,.12) 45%,rgba(255,215,0,.25) 50%,
                       rgba(255,215,0,.12) 55%,transparent 100%);
            animation:shimmer 4.5s infinite linear; pointer-events:none; }
        @keyframes shimmer { 0%{left:-100%} 100%{left:100%} }
        .tier-luxury .hero-emoji { filter:drop-shadow(0 0 18px rgba(255,215,0,.6)); }
        .tier-luxury .band-hero h1 {
            background:linear-gradient(135deg,#fff1a8 0%,#FFD700 40%,#ffecb3 70%,#c9a227 100%);
            -webkit-background-clip:text; background-clip:text; color:transparent;
            font-size:32px; font-weight:900; letter-spacing:.02em;
            text-shadow:0 0 30px rgba(255,215,0,.25); }
        .tier-luxury .hero-sub { color:#FFD700; letter-spacing:.1em;
            text-transform:uppercase; font-size:12px;
            text-shadow:0 0 12px rgba(255,215,0,.4); }
        .tier-luxury .range { color:#c9a227; }
        .tier-luxury .prod-count {
            color:#0a0a14; background:linear-gradient(135deg,#ffecb3,#FFD700);
            box-shadow:0 0 20px rgba(255,215,0,.4); }
        .tier-luxury .vip-banner {
            position:relative; overflow:hidden;
            background:linear-gradient(135deg,#1a1530 0%,#2d1b4e 50%,#1a1530 100%);
            border:1px solid rgba(255,215,0,.5); border-radius:20px;
            padding:20px 22px; margin:20px 0 24px;
            box-shadow:0 0 30px rgba(255,215,0,.15),
                       inset 0 1px 0 rgba(255,215,0,.3); }
        .tier-luxury .vip-shimmer {
            position:absolute; top:0; left:-100%; width:200%; height:100%;
            background:linear-gradient(90deg,transparent 40%,
                       rgba(255,215,0,.15) 50%,transparent 60%);
            animation:shimmer 3.5s infinite linear; }
        .tier-luxury .vip-content {
            position:relative; display:flex; align-items:center; gap:16px; }
        .tier-luxury .vip-crown { font-size:38px;
            filter:drop-shadow(0 0 15px rgba(255,215,0,.7)); }
        .tier-luxury .vip-title {
            font-size:20px; font-weight:900;
            background:linear-gradient(135deg,#fff1a8,#FFD700);
            -webkit-background-clip:text; background-clip:text; color:transparent;
            letter-spacing:.05em; }
        .tier-luxury .vip-sub { font-size:12px; color:#ffecb3;
            margin-top:2px; letter-spacing:.08em; }
        .tier-luxury .section-header {
            border-left-color:#FFD700 !important; }
        .tier-luxury .sec-emoji { filter:drop-shadow(0 0 8px rgba(255,215,0,.4)); }
        .tier-luxury .sec-label {
            color:#FFD700; font-weight:900; letter-spacing:.03em;
            text-shadow:0 0 10px rgba(255,215,0,.3); }
        .tier-luxury .sec-badge {
            background:rgba(255,215,0,.15) !important;
            color:#FFD700 !important;
            border:1px solid rgba(255,215,0,.4); }
        .tier-luxury .deal {
            background:linear-gradient(145deg,#14142a 0%,#0f0f1e 100%);
            border:1px solid rgba(255,215,0,.35);
            border-left:4px solid #FFD700 !important;
            box-shadow:0 0 24px rgba(255,215,0,.10),
                       0 2px 8px rgba(0,0,0,.5),
                       inset 0 1px 0 rgba(255,215,0,.15); }
        .tier-luxury .deal:hover {
            transform:translateY(-3px);
            border-color:rgba(255,215,0,.75);
            box-shadow:0 0 36px rgba(255,215,0,.25),
                       0 8px 24px rgba(0,0,0,.6),
                       inset 0 1px 0 rgba(255,215,0,.25); }
        .tier-luxury .thumb { width:100px; height:100px; border-radius:14px;
            background:linear-gradient(135deg,rgba(255,215,0,.12),rgba(255,215,0,.04));
            border:2px solid rgba(255,215,0,.5);
            box-shadow:0 0 18px rgba(255,215,0,.2),
                       inset 0 0 10px rgba(255,215,0,.08); }
        .tier-luxury .thumb img { width:100px; height:100px; }
        .tier-luxury .deal-name {
            font-size:16px; color:#fff5d1; font-weight:800; }
        .tier-luxury .deal-desc { color:#FFD700; }
        .tier-luxury .discount-hero {
            font-size:30px;
            background:linear-gradient(135deg,#fff1a8,#FFD700);
            -webkit-background-clip:text; background-clip:text;
            -webkit-text-fill-color:transparent; }
        .tier-luxury .deal-arrow { color:#FFD700; opacity:.85; }
        .tier-luxury .vip-badge {
            background:linear-gradient(135deg,#fff1a8,#FFD700,#c9a227);
            color:#0a0a14; padding:3px 10px; border-radius:999px;
            font-size:10px; font-weight:900; white-space:nowrap;
            box-shadow:0 0 12px rgba(255,215,0,.5);
            border:1px solid rgba(255,215,0,.8); }
        .tier-luxury .footer { color:#c9a227; background:transparent; }
        .tier-luxury .footer a { color:#FFD700; }
"""


# ── Special Deals page ───────────────────────────────────────────────────────
def _special_deals_page_html(grouped: dict, total: int, today: str,
                              categories: list) -> str:
    """Generate special_deals.html with products grouped by category.

    grouped: {category_key: [products]} sorted by group size desc.
    """
    # Build category lookup: key -> (emoji, label)
    cat_meta = {key: (emoji, label) for key, emoji, label in categories}

    now = datetime.now()
    sections_html = ""
    for key, prods in grouped.items():
        emoji, label = cat_meta.get(key, ("📦", key))
        accent = _ACCENT.get(key, "#9e9e9e")
        rgb    = _hex_rgb(accent)

        top_ids = compute_top_discount_ids(prods)
        cards_html = ""
        for idx, p in enumerate(prods):
            cards_html += _render_deal_card(
                p, idx, fallback_emoji=emoji,
                border_accent=accent, thumb_bg_rgb=rgb,
                arrow_color=accent,
                top_discount_ids=top_ids,
                is_new=is_new_product(p, now),
            )

        sections_html += f"""
        <div class="section">
            <div class="section-header" style="border-left-color:{accent}">
                <span class="sec-emoji">{emoji}</span>
                <span class="sec-label">{label}</span>
                <span class="sec-badge"
                      style="background:rgba({rgb},.12);color:{accent}">{len(prods)}개</span>
            </div>
            {cards_html}
        </div>"""

    extra_css = """
        :root { --accent: #E85A7A; }

        .top-bar {
            position:sticky; top:0; z-index:10;
            background:rgba(255,249,245,.95);
            backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px);
            padding:12px 16px; border-bottom:1px solid var(--nyang-border);
        }
        .top-bar a { color:var(--nyang-accent); font-size:14px; font-weight:500; text-decoration:none; }
        .top-bar a:hover { text-decoration:underline; }

        .sd-hero {
            background: var(--nyang-gradient-soft);
            padding:32px 24px 28px; text-align:center;
        }
        .sd-hero .hero-flame {
            font-size:56px; line-height:1;
            animation: pulse 1.8s ease-in-out infinite;
        }
        @keyframes pulse {
            0%,100% { transform:scale(1);    filter:drop-shadow(0 0 4px rgba(255,143,171,.4)); }
            50%      { transform:scale(1.15); filter:drop-shadow(0 0 10px rgba(255,143,171,.7)); }
        }
        .sd-hero h1 { font-size:24px; font-weight:800; margin-top:10px; }
        .sd-hero p  { font-size:13px; color:var(--nyang-accent); font-weight:600; margin-top:8px; }

        .section { margin-bottom:28px; }
        .section-header {
            display:flex; align-items:center; gap:8px;
            padding:10px 0 10px 12px;
            border-left:4px solid var(--nyang-pink);
            margin-bottom:10px;
        }
        .sec-emoji { font-size:22px; }
        .sec-label { font-size:16px; font-weight:700; flex:1; }
        .sec-badge {
            font-size:12px; font-weight:600;
            padding:3px 10px; border-radius:var(--nyang-radius-full);
        }

        /* Product cards */
        .deal {
            display:flex; align-items:center; gap:14px;
            background:var(--nyang-white); border-radius:var(--nyang-radius-md); padding:14px;
            margin-bottom:10px; text-decoration:none; color:var(--nyang-text);
            box-shadow:var(--nyang-shadow-card);
            border-left:4px solid var(--nyang-pink);
            transition:transform var(--nyang-transition), box-shadow var(--nyang-transition);
        }
        .deal:hover  { transform:translateY(-2px); box-shadow:var(--nyang-shadow-hover); }
        .thumb {
            width:72px; height:72px; border-radius:var(--nyang-radius-sm); flex-shrink:0;
            overflow:hidden; display:flex; align-items:center;
            justify-content:center; font-size:28px; aspect-ratio:1/1;
        }
        .thumb img { width:72px; height:72px; object-fit:cover; display:block; flex-shrink:0; aspect-ratio:1/1; }
        .deal-name {
            font-size:15px; font-weight:600; line-height:1.4;
            display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
            overflow:hidden;
        }
        .deal-desc {
            font-size:12px; color:var(--nyang-accent); font-weight:600;
            margin-top:4px; line-height:1.3;
            background:var(--nyang-gradient-soft); padding:6px 10px;
            border-radius:var(--nyang-radius-sm);
        }
        .deal-desc::before { content:"\\1F4AC"; margin-right:4px; }
        .deal-arrow { font-size:20px; opacity:.4; flex-shrink:0; }
    """ + _CARD_BASE_CSS

    head = _head(
        title=f"🔥 특가할인 - {BRAND_NAME}",
        og_title=f"🔥 특가할인 | 50% 이상 할인 펫 상품 모음",
        og_desc=f"50% 이상 할인 펫 상품 총 {total}개! 카테고리별 특가 모음.",
        extra_css=extra_css,
    )
    return f"""<!DOCTYPE html>
<html lang="ko">
{head}
<body>
    <div class="top-bar">
        <a href="deals.html">← 전체 카테고리</a>
    </div>
    <div class="sd-hero">
        <div class="hero-flame">🔥</div>
        <h1>특가할인</h1>
        <p>50% 이상 할인 · 총 {total}개 상품 · {today} 기준</p>
    </div>
    <div class="container">
        {_YT_BANNER}
        {sections_html}
    </div>
    {_FOOTER}
</body>
</html>"""


def _deduplicate_similar(products: list, max_per_cluster: int = 3) -> list:
    """Remove similar products, keeping top N per name cluster.

    Clusters by first 5 chars of name_ko. Within each cluster, keeps
    items with highest evaluate_rate, then highest lastest_volume.
    """
    clusters: dict[str, list] = defaultdict(list)
    no_name = []
    for p in products:
        name = (p.get("name_ko") or "").strip()
        if len(name) < 5:
            no_name.append(p)
            continue
        key = name[:5]
        clusters[key].append(p)

    kept = list(no_name)
    total_removed = 0
    for key, items in clusters.items():
        if len(items) <= max_per_cluster:
            kept.extend(items)
            continue
        # Sort: highest rating first, then highest volume
        items.sort(key=lambda p: (
            _safe_float(p.get("evaluate_rate", "0")),
            _safe_float(p.get("lastest_volume", 0)),
        ), reverse=True)
        kept.extend(items[:max_per_cluster])
        removed = len(items) - max_per_cluster
        total_removed += removed
        names_removed = [i.get("name_ko", "?") for i in items[max_per_cluster:]]
        print(f"[Deals] Dedup cluster '{key}': kept {max_per_cluster}, "
              f"removed {removed}: {names_removed}")

    if total_removed:
        print(f"[Deals] Total dedup removed: {total_removed}")
    return kept


# ── Public API (logic identical to v2) ───────────────────────────────────────
def update_deals_site(products: list, push: bool = True) -> bool:
    """Generate deals.html + category_*.html and push to GitHub Pages."""
    from modules.category_mapper import (
        CATEGORIES, classify_product, classify_price_band, PRICE_BANDS
    )

    today = datetime.now().strftime("%Y년 %m월 %d일")
    Path(DOCS_DIR).mkdir(parents=True, exist_ok=True)

    # Dedupe by product_id + drop items under 1,000원
    seen_ids: set = set()
    deduped = []
    dropped_cheap = 0
    for p in products:
        pid = p.get("product_id") or p.get("id", "")
        if pid and pid in seen_ids:
            continue
        price_krw = _safe_float(p.get("price", 0))
        if int(price_krw) < 1000:
            dropped_cheap += 1
            continue
        if pid:
            seen_ids.add(pid)
        deduped.append(p)
    if dropped_cheap:
        print(f"[Deals] Dropped {dropped_cheap} products under 1,000원")

    # Remove similar-name duplicates: keep top 3 per cluster
    deduped = _deduplicate_similar(deduped)

    # Remove likely out-of-stock (no volume + no rating)
    before_oos = len(deduped)
    deduped = [
        p for p in deduped
        if not (_safe_float(p.get("lastest_volume", 1)) == 0
                and not p.get("evaluate_rate"))
    ]
    removed_oos = before_oos - len(deduped)
    if removed_oos:
        print(f"[Deals] Removed {removed_oos} likely out-of-stock products")

    # Always reclassify -- the taxonomy can change between runs and stale
    # category_key / price_band values would drop products into non-existent pages.
    valid_keys = {k for k, _, _ in CATEGORIES}
    valid_band_keys = {b["key"] for b in PRICE_BANDS}
    for p in deduped:
        current = p.get("category_key", "")
        if current not in valid_keys:
            p["category_key"] = classify_product(p)
        if p.get("price_band") not in valid_band_keys:
            p["price_band"] = classify_price_band(p)

    # Rebuild affiliate links with category-specific tracking
    from modules.ali_scraper import build_affiliate_link as _build_aff
    for p in deduped:
        pid = str(p.get("product_id") or "")
        cat = p.get("category_key", "")
        if pid and cat:
            old_link = p.get("affiliate_link", "")
            # Only rebuild if link lacks category suffix or is a plain pawmeow link
            if old_link and "pawmeow_" not in old_link:
                p["affiliate_link"] = _build_aff(pid, "ko", cat)

    # Group by category
    grouped: dict[str, list] = {}
    for p in deduped:
        grouped.setdefault(p.get("category_key", "etc"), []).append(p)

    category_counts = {k: len(v) for k, v in grouped.items()}

    # Special deals
    from modules.category_mapper import (
        group_special_deals_by_category, PRICE_BANDS
    )
    special_grouped = group_special_deals_by_category(deduped, threshold=50.0)
    special_total   = sum(len(v) for v in special_grouped.values())

    # Price bands -- classify each product, group by band then by category
    band_grouped: dict[str, dict[str, list]] = {}  # {band_key: {cat_key: [products]}}
    for p in deduped:
        bk = p.get("price_band") or classify_price_band(p)
        p["price_band"] = bk
        band_grouped.setdefault(bk, {}).setdefault(
            p.get("category_key", "etc"), []
        ).append(p)

    band_counts: dict[str, int] = {
        bk: sum(len(v) for v in by_cat.values())
        for bk, by_cat in band_grouped.items()
    }

    # Write main page
    main_html = _main_page_html(today, len(deduped), category_counts, CATEGORIES,
                                 special_count=special_total, band_counts=band_counts,
                                 all_products=deduped)
    with open(f"{DOCS_DIR}/deals.html", "w", encoding="utf-8") as f:
        f.write(main_html)
    print(f"[Deals] deals.html ({len(main_html):,} bytes, {len(deduped)} products, "
          f"{special_total} special, bands:{band_counts})")

    # Write special_deals.html (skip if empty)
    if special_total > 0:
        sd_html = _special_deals_page_html(special_grouped, special_total, today, CATEGORIES)
        with open(f"{DOCS_DIR}/special_deals.html", "w", encoding="utf-8") as f:
            f.write(sd_html)
        print(f"[Deals] special_deals.html ({len(sd_html):,} bytes, {special_total} products)")
        by_cat = ", ".join(f"{k}:{len(v)}" for k, v in special_grouped.items())
        print(f"[Deals]   breakdown: {by_cat}")
    else:
        stale_sd = Path(f"{DOCS_DIR}/special_deals.html")
        if stale_sd.exists():
            stale_sd.unlink()
            print("[Deals] Removed stale: special_deals.html (no specials today)")

    # Write price band pages
    band_lookup = {b["key"]: b for b in PRICE_BANDS}
    written_bands: set = set()
    for bk, by_cat in band_grouped.items():
        band = band_lookup.get(bk)
        if not band:
            continue
        total_in_band = sum(len(v) for v in by_cat.values())
        pb_html = _price_band_page_html(band, by_cat, total_in_band, today, CATEGORIES)
        with open(f"{DOCS_DIR}/{bk}.html", "w", encoding="utf-8") as f:
            f.write(pb_html)
        print(f"[Deals] {bk}.html ({len(pb_html):,} bytes, {total_in_band} products)")
        written_bands.add(bk)

    # Remove stale price band pages
    for stale in Path(DOCS_DIR).glob("price_*.html"):
        if stale.stem not in written_bands:
            stale.unlink()
            print(f"[Deals] Removed stale: {stale.name}")

    # Write category pages
    written_keys: set = set()
    for key, emoji, label in CATEGORIES:
        prods = grouped.get(key, [])
        if not prods:
            continue
        page_html = _category_page_html(key, emoji, label, prods, today)
        with open(f"{DOCS_DIR}/category_{key}.html", "w", encoding="utf-8") as f:
            f.write(page_html)
        print(f"[Deals] category_{key}.html ({len(page_html):,} bytes, {len(prods)} products)")
        written_keys.add(key)

    # Redirect old category URLs to new merged categories
    _CATEGORY_REDIRECTS = {
        "cat": "pet", "dog": "pet", "pet_common": "pet", "pet_toys": "pet",
        "pet_home": "home", "kitchen": "home",
        "camping": "outdoor", "car": "outdoor",
    }
    base_url = "https://x68445.github.io/petdeals-legal"
    for old_key, new_key in _CATEGORY_REDIRECTS.items():
        if old_key not in written_keys:
            redirect_html = _redirect_html(f"category_{new_key}.html", base_url)
            with open(f"{DOCS_DIR}/category_{old_key}.html", "w", encoding="utf-8") as f:
                f.write(redirect_html)

    # Remove stale category pages (skip redirects)
    redirect_keys = set(_CATEGORY_REDIRECTS.keys())
    for stale in Path(DOCS_DIR).glob("category_*.html"):
        stem_key = stale.stem.replace("category_", "")
        if stem_key not in written_keys and stem_key not in redirect_keys:
            stale.unlink()
            print(f"[Deals] Removed stale: {stale.name}")

    # Generate sitemap.xml (base_url defined above in redirect block)
    today_iso = datetime.now().strftime("%Y-%m-%d")
    sitemap_urls = [f"{base_url}/deals.html"]
    if special_total > 0:
        sitemap_urls.append(f"{base_url}/special_deals.html")
    for bk in written_bands:
        sitemap_urls.append(f"{base_url}/{bk}.html")
    for key in written_keys:
        sitemap_urls.append(f"{base_url}/category_{key}.html")
    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap_xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url in sitemap_urls:
        sitemap_xml += f"  <url><loc>{url}</loc><lastmod>{today_iso}</lastmod><changefreq>daily</changefreq></url>\n"
    sitemap_xml += "</urlset>\n"
    with open(f"{DOCS_DIR}/sitemap.xml", "w") as f:
        f.write(sitemap_xml)
    print(f"[Deals] sitemap.xml ({len(sitemap_urls)} URLs)")

    if push:
        return _git_push("feat: SEO + category tracking + daily deals")
    print("[deploy] push=False, skipping git push")
    return True


def _git_push(commit_msg: str) -> bool:
    if os.environ.get("PETDEALS_NO_PUSH") == "1":
        print("[git_push] Skipped: PETDEALS_NO_PUSH=1 is set")
        return True

    def _run(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=GIT_ROOT)
        return r.returncode == 0, r.stderr.strip()

    _run(["git", "pull", "origin", "main", "--rebase"])
    _run(["git", "add", "docs/"])
    ok, err = _run(["git", "commit", "-m", commit_msg])
    if not ok and "nothing to commit" in err:
        print("[Deals] No changes to push")
        return True
    ok, err = _run(["git", "push", "origin", "main"])
    if ok:
        print(f"[Deals] Pushed -> {DEALS_URL}")
        return True
    print(f"[Deals] Push failed: {err}")
    return False


# Backward-compatible alias
def update_deals_page(products: list, push: bool = True) -> bool:
    """Deprecated alias for update_deals_site(). Kept for pipeline compatibility."""
    return update_deals_site(products, push=push)


if __name__ == "__main__":
    import argparse, json, sys
    sys.path.insert(0, BASE_DIR)
    parser = argparse.ArgumentParser(description="Generate PetDeals HTML pages")
    parser.add_argument("--no-push", action="store_true",
                        help="Generate HTML but don't push to GitHub")
    args = parser.parse_args()
    src = f"{BASE_DIR}/data/products.json"
    with open(src, encoding="utf-8") as f:
        prods = json.load(f)
    print(f"[Deals] Loaded {len(prods)} products from {src}")
    update_deals_site(prods, push=not args.no_push)
