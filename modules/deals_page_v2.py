#!/usr/bin/env python3
"""
Interactive Deals Page v2 -- 냥댕라이프
Single-page with client-side search, filter, sort.
Categories: 강아지 / 고양이 / 라이프
"""

import json
from datetime import datetime


def _classify_pet_type(p: dict) -> str:
    cat_key = p.get("category_key", "")
    if cat_key == "dog":
        return "dog"
    if cat_key == "cat":
        return "cat"
    if cat_key in ("pet", "pet_common", "pet_toys", "pet_home"):
        title = (str(p.get("product_title", "")) + " " +
                 str(p.get("name_ko", ""))).lower()
        if any(w in title for w in ["cat ", "kitten", "고양이", "냥", "집사", "캣타워",
                                     "cat toy", "cat litter", "cat scr"]):
            return "cat"
        if any(w in title for w in ["dog ", "puppy", "강아지", "댕", "반려견",
                                     "dog toy", "dog harness", "dog leash"]):
            return "dog"
        return "pet"
    return "life"


def _life_subcat(p: dict) -> str:
    cat_key = p.get("category_key", "")
    remap = {
        "home": "home", "kitchen": "home", "pet_home": "home",
        "outdoor": "outdoor", "camping": "outdoor", "car": "outdoor",
        "fashion": "fashion",
        "sports": "sports",
        "electronics": "electronics",
    }
    return remap.get(cat_key, "etc")


def _pet_subcat(p: dict) -> str:
    title = (str(p.get("product_title", "")) + " " +
             str(p.get("name_ko", "")) + " " +
             str(p.get("_source_category", ""))).lower()
    if any(w in title for w in ["food", "사료", "treat", "간식", "츄르", "chew", "snack"]):
        return "food"
    if any(w in title for w in ["toy", "장난감", "ball", "wand", "feather", "laser",
                                 "puzzle", "tunnel", "kicker", "낚시"]):
        return "toy"
    if any(w in title for w in ["harness", "leash", "collar", "하네스", "목줄", "리드"]):
        return "walk"
    if any(w in title for w in ["groom", "brush", "shampoo", "nail", "샴푸", "빗", "미용"]):
        return "groom"
    if any(w in title for w in ["bed", "cushion", "blanket", "house", "침대", "쿠션",
                                 "tower", "tree", "캣타워", "스크래처", "scratch"]):
        return "house"
    if any(w in title for w in ["feeder", "fountain", "bowl", "급식", "급수", "정수기",
                                 "water", "dispenser"]):
        return "feed"
    if any(w in title for w in ["carrier", "bag", "이동", "캐리어", "가방"]):
        return "travel"
    if any(w in title for w in ["litter", "모래", "화장실", "toilet"]):
        return "litter"
    if any(w in title for w in ["cloth", "옷", "coat", "raincoat", "vest", "costume"]):
        return "clothes"
    return "etc"


def _safe_float(val) -> float:
    try:
        return float(str(val).replace("$", "").replace(",", "").replace("%", "") or 0)
    except Exception:
        return 0.0


def generate_interactive_html(products: list, today: str = "") -> str:
    if not today:
        today = datetime.now().strftime("%Y년 %m월 %d일")

    now = datetime.now()
    items = []
    for p in products:
        name = (p.get("name_ko") or p.get("product_title") or "")[:50]
        link = p.get("affiliate_link", "")
        if not name or not link:
            continue
        img = p.get("image_url") or p.get("product_main_image_url", "")
        disc = int(_safe_float(p.get("discount", 0)))
        price = int(_safe_float(p.get("price", 0)))
        comm = _safe_float(p.get("commission_rate", 0))
        pet_type = _classify_pet_type(p)
        life_sub = _life_subcat(p) if pet_type == "life" else ""
        pet_sub = _pet_subcat(p) if pet_type in ("dog", "cat", "pet") else ""

        is_new = False
        collected = p.get("collected_at", "")
        if collected:
            try:
                ts = datetime.fromisoformat(collected.replace("Z", "+00:00")).replace(tzinfo=None)
                is_new = (now - ts).total_seconds() < 86400
            except Exception:
                pass

        items.append({
            "n": name,
            "i": img,
            "l": link,
            "d": disc,
            "p": price,
            "t": pet_type,
            "s": life_sub,
            "ps": pet_sub,
            "c": round(comm, 1),
            "w": is_new,
        })

    products_json = json.dumps(items, ensure_ascii=False, separators=(",", ":"))

    counts = {"dog": 0, "cat": 0, "pet": 0, "life": 0}
    for it in items:
        t = it["t"]
        if t in counts:
            counts[t] += 1

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<title>냥댕라이프 | 매일 특가</title>
<meta name="description" content="강아지, 고양이 용품 매일 특가. 알리익스프레스 최저가 모음.">
<meta property="og:title" content="냥댕라이프 | 매일 특가">
<meta property="og:description" content="강아지, 고양이 용품 매일 특가 모음">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:'Pretendard Variable',Pretendard,-apple-system,sans-serif;
  background:#f8f8fa;color:#1a1a1a;-webkit-tap-highlight-color:transparent;
  padding-bottom:80px;
}}
.header{{
  background:linear-gradient(135deg,#FF8FAB 0%,#FFB347 50%,#FFD166 100%);
  padding:28px 20px 20px;text-align:center;color:#fff;
  position:relative;overflow:hidden;
}}
.header::after{{
  content:'';position:absolute;bottom:-20px;left:0;right:0;height:40px;
  background:#f8f8fa;border-radius:50% 50% 0 0;
}}
.header h1{{font-size:24px;font-weight:800;letter-spacing:-0.5px}}
.header p{{font-size:13px;margin-top:4px;opacity:0.9}}
.tabs{{
  display:flex;gap:0;background:#fff;margin:0 16px;border-radius:14px;
  box-shadow:0 2px 12px rgba(0,0,0,0.06);padding:4px;position:relative;z-index:2;
  margin-top:-10px;
}}
.tab{{
  flex:1;padding:12px 4px;text-align:center;font-size:13px;font-weight:600;
  border-radius:10px;cursor:pointer;transition:all 0.2s;color:#888;
  border:none;background:none;
}}
.tab.active{{
  background:linear-gradient(135deg,#FF8FAB,#FFB347);color:#fff;
  box-shadow:0 2px 8px rgba(255,143,171,0.3);
}}
.tab .cnt{{font-size:11px;opacity:0.7;display:block;margin-top:2px}}
.sub-tabs{{
  display:none;gap:6px;padding:12px 16px 4px;overflow-x:auto;
  -webkit-overflow-scrolling:touch;justify-content:center;flex-wrap:wrap;
}}
.sub-tabs.show{{display:flex}}
.sub-tab{{
  flex-shrink:0;padding:6px 14px;font-size:12px;font-weight:500;
  border-radius:20px;background:#f0f0f2;color:#666;cursor:pointer;
  border:none;transition:all 0.2s;white-space:nowrap;
}}
.sub-tab.active{{background:#FF8FAB;color:#fff}}
.filters{{padding:12px 16px}}
.search-wrap{{position:relative;margin-bottom:8px}}
.search-wrap input{{
  width:100%;padding:12px 16px 12px 40px;font-size:15px;border:2px solid #eee;
  border-radius:12px;background:#fff;outline:none;transition:border 0.2s;
  font-family:inherit;
}}
.search-wrap input:focus{{border-color:#FF8FAB}}
.search-wrap::before{{
  content:'\\1F50D';position:absolute;left:14px;top:50%;transform:translateY(-50%);
  font-size:16px;pointer-events:none;
}}
.filter-row{{display:flex;gap:6px;overflow-x:auto;padding-bottom:4px}}
.filter-row select{{
  flex-shrink:0;padding:8px 12px;font-size:13px;border:1.5px solid #eee;
  border-radius:10px;background:#fff;color:#444;font-family:inherit;
  appearance:none;-webkit-appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 4.5l3 3 3-3' fill='none' stroke='%23999' stroke-width='1.5'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 8px center;
  padding-right:28px;cursor:pointer;
}}
.stats{{
  padding:4px 20px 8px;font-size:13px;color:#999;
  display:flex;justify-content:space-between;align-items:center;
}}
.grid{{
  display:grid;grid-template-columns:repeat(2,1fr);gap:10px;
  padding:0 16px 20px;
}}
.card{{
  background:#fff;border-radius:14px;overflow:hidden;
  box-shadow:0 2px 10px rgba(0,0,0,0.04);transition:transform 0.2s,box-shadow 0.2s;
  text-decoration:none;color:inherit;display:block;position:relative;
}}
.card:active{{transform:scale(0.98)}}
.card-img{{
  width:100%;aspect-ratio:1;object-fit:cover;background:#f5f5f5;
  display:block;
}}
.card-img-placeholder{{
  width:100%;aspect-ratio:1;background:#f0f0f2;
  display:flex;align-items:center;justify-content:center;font-size:40px;
}}
.card-badge{{
  position:absolute;top:8px;left:8px;
  background:linear-gradient(135deg,#E85A7A,#FF8FAB);
  color:#fff;font-size:12px;font-weight:700;padding:4px 8px;
  border-radius:8px;
}}
.card-new{{
  position:absolute;top:8px;right:8px;
  background:#FFD166;color:#333;font-size:11px;font-weight:600;
  padding:3px 7px;border-radius:6px;
}}
.card-info{{padding:10px 10px 12px}}
.card-name{{
  font-size:13px;font-weight:500;line-height:1.4;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
  overflow:hidden;color:#333;min-height:36px;
}}
.card-cta{{
  display:block;margin-top:8px;padding:8px 0;text-align:center;
  background:linear-gradient(135deg,#FF8FAB,#FFB347);
  color:#fff;font-size:12px;font-weight:600;border-radius:8px;
}}
.card-rec{{
  display:inline-block;margin-top:6px;font-size:11px;
  color:#E85A7A;font-weight:600;
}}
.empty{{
  text-align:center;padding:60px 20px;color:#999;font-size:14px;
}}
.yt-banner{{
  display:block;margin:12px 16px;padding:16px 20px;
  background:linear-gradient(135deg,#ff0000,#cc0000);
  color:#fff;text-decoration:none;border-radius:14px;
  text-align:center;font-weight:700;font-size:14px;
  box-shadow:0 4px 12px rgba(255,0,0,0.2);
}}
.footer{{
  text-align:center;padding:24px 20px;color:#bbb;font-size:12px;
}}
.footer a{{color:#FF8FAB;text-decoration:none}}
.top-btn{{
  position:fixed;bottom:20px;right:20px;width:44px;height:44px;
  border-radius:50%;background:#FF8FAB;color:#fff;border:none;
  font-size:20px;box-shadow:0 4px 12px rgba(255,143,171,0.4);
  cursor:pointer;display:none;z-index:100;
}}
@media(min-width:600px){{
  .grid{{grid-template-columns:repeat(3,1fr);gap:14px;max-width:720px;margin:0 auto;padding:0 20px 20px}}
  .tabs,.filters,.stats{{max-width:720px;margin-left:auto;margin-right:auto}}
}}
@media(min-width:900px){{
  .grid{{grid-template-columns:repeat(4,1fr);max-width:960px}}
  .tabs,.filters,.stats{{max-width:960px}}
}}
</style>
</head>
<body>

<div class="header">
  <h1>냥댕라이프</h1>
  <p>우리집 댕냥이 매일 특가</p>
</div>

<div class="tabs">
  <button class="tab active" data-cat="all">전체<span class="cnt">{len(items)}</span></button>
  <button class="tab" data-cat="dog">🐕 강아지<span class="cnt">{counts['dog']}</span></button>
  <button class="tab" data-cat="cat">🐈 고양이<span class="cnt">{counts['cat']}</span></button>
  <button class="tab" data-cat="life">✨ 라이프<span class="cnt">{counts['life']}</span></button>
</div>

<div class="sub-tabs" id="dogSubs">
  <button class="sub-tab active" data-psub="all">전체</button>
  <button class="sub-tab" data-psub="food">🍖 사료/간식</button>
  <button class="sub-tab" data-psub="toy">🎾 장난감</button>
  <button class="sub-tab" data-psub="walk">🦮 산책</button>
  <button class="sub-tab" data-psub="feed">🥣 급식/급수</button>
  <button class="sub-tab" data-psub="groom">✂️ 미용</button>
  <button class="sub-tab" data-psub="house">🏠 하우스</button>
  <button class="sub-tab" data-psub="clothes">👕 의류</button>
  <button class="sub-tab" data-psub="travel">🧳 이동</button>
</div>

<div class="sub-tabs" id="catSubs">
  <button class="sub-tab active" data-psub="all">전체</button>
  <button class="sub-tab" data-psub="food">🐟 사료/간식</button>
  <button class="sub-tab" data-psub="toy">🪶 장난감</button>
  <button class="sub-tab" data-psub="house">🏠 캣타워/침대</button>
  <button class="sub-tab" data-psub="litter">🚽 모래/화장실</button>
  <button class="sub-tab" data-psub="feed">🥣 급식/급수</button>
  <button class="sub-tab" data-psub="groom">✂️ 미용</button>
  <button class="sub-tab" data-psub="travel">🧳 이동</button>
</div>

<div class="sub-tabs" id="lifeSubs">
  <button class="sub-tab active" data-sub="all">전체</button>
  <button class="sub-tab" data-sub="home">🏠 살림</button>
  <button class="sub-tab" data-sub="outdoor">🚗 나들이</button>
  <button class="sub-tab" data-sub="fashion">👕 패션</button>
  <button class="sub-tab" data-sub="sports">💪 건강</button>
  <button class="sub-tab" data-sub="electronics">💻 전자</button>
  <button class="sub-tab" data-sub="etc">🔥 추천</button>
</div>

<div class="filters">
  <div class="search-wrap">
    <input type="text" id="q" placeholder="상품명 검색..." autocomplete="off">
  </div>
  <div class="filter-row">
    <select id="fDisc">
      <option value="0">🔥 전체 할인</option>
      <option value="30">30% 이상</option>
      <option value="50">50% 이상</option>
      <option value="70">70% 이상</option>
    </select>
    <select id="fSort">
      <option value="rec">추천순</option>
      <option value="disc">할인율순</option>
      <option value="new">최신순</option>
    </select>
  </div>
</div>

<div class="stats">
  <span id="resultCount"></span>
  <span>{today} 업데이트</span>
</div>

<div class="grid" id="grid"></div>
<div class="empty" id="empty" style="display:none">검색 결과가 없어요 😿</div>

<a href="https://www.youtube.com/@NyangDaengLife" target="_blank" rel="noopener" class="yt-banner">
  📺 냥댕라이프 유튜브 구독하기
</a>

<div class="footer">
  <p>냥댕라이프 | <a href="https://www.youtube.com/@NyangDaengLife">YouTube</a></p>
  <p style="margin-top:4px">알리익스프레스 파트너스 제휴 링크 포함</p>
</div>

<button class="top-btn" id="topBtn" onclick="scrollTo({{top:0,behavior:'smooth'}})">↑</button>

<script>
const P={products_json};
let cat='all',sub='all',psub='all',query='',fDisc=0,fSort='rec';

const $=id=>document.getElementById(id);
const grid=$('grid'),empty=$('empty'),rc=$('resultCount');

function hideAllSubs(){{
  ['dogSubs','catSubs','lifeSubs'].forEach(id=>$(id).classList.remove('show'));
  sub='all';psub='all';
  document.querySelectorAll('.sub-tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.sub-tab[data-sub=all],.sub-tab[data-psub=all]').forEach(x=>x.classList.add('active'));
}}
document.querySelectorAll('.tab').forEach(t=>{{
  t.onclick=()=>{{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    cat=t.dataset.cat;
    hideAllSubs();
    if(cat==='dog')$('dogSubs').classList.add('show');
    else if(cat==='cat')$('catSubs').classList.add('show');
    else if(cat==='life')$('lifeSubs').classList.add('show');
    render();
  }};
}});

document.querySelectorAll('.sub-tab').forEach(t=>{{
  t.onclick=()=>{{
    t.closest('.sub-tabs').querySelectorAll('.sub-tab').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    if(t.dataset.sub!==undefined){{sub=t.dataset.sub;psub='all'}}
    if(t.dataset.psub!==undefined){{psub=t.dataset.psub;sub='all'}}
    render();
  }};
}});

$('q').oninput=e=>{{query=e.target.value.toLowerCase();render()}};
$('fDisc').onchange=e=>{{fDisc=parseInt(e.target.value);render()}};
$('fSort').onchange=e=>{{fSort=e.target.value;render()}};

function filter(item){{
  if(cat==='dog'&&item.t!=='dog')return false;
  if(cat==='cat'&&item.t!=='cat')return false;
  if(cat==='life'&&item.t!=='life')return false;
  if(cat==='life'&&sub!=='all'&&item.s!==sub)return false;
  if((cat==='dog'||cat==='cat')&&psub!=='all'&&item.ps!==psub)return false;
  if(query&&!item.n.toLowerCase().includes(query))return false;
  if(fDisc>0&&item.d<fDisc)return false;
  return true;
}}

function sortFn(a,b){{
  if(fSort==='disc')return b.d-a.d;
  if(fSort==='new')return(b.w?1:0)-(a.w?1:0);
  return(b.c-a.c)||((b.d-a.d))||((a.p-b.p));
}}

function cardHTML(item){{
  const img=item.i
    ?`<img class="card-img" src="${{item.i}}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<div class=card-img-placeholder>📦</div>'">`
    :'<div class="card-img-placeholder">📦</div>';
  const badge=item.d>=10?`<div class="card-badge">${{item.d}}% OFF</div>`:'';
  const newB=item.w?'<div class="card-new">NEW</div>':'';
  const rec=item.c>8?'<div class="card-rec">💎 추천</div>':'';
  return`<a href="${{item.l}}" class="card" target="_blank" rel="nofollow sponsored noopener">
    ${{badge}}${{newB}}${{img}}
    <div class="card-info">
      <div class="card-name">${{item.n}}</div>
      ${{rec}}
      <div class="card-cta">가격 확인하기 →</div>
    </div></a>`;
}}

function render(){{
  const filtered=P.filter(filter).sort(sortFn);
  rc.textContent=`${{filtered.length}}개 상품`;
  if(filtered.length===0){{
    grid.innerHTML='';empty.style.display='';return;
  }}
  empty.style.display='none';
  grid.innerHTML=filtered.map(cardHTML).join('');
}}

window.onscroll=()=>{{
  $('topBtn').style.display=window.scrollY>600?'block':'none';
}};

// Hash routing
function applyHash(){{
  const h=location.hash.replace('#','');
  if(['dog','cat','life'].includes(h)){{
    document.querySelector(`.tab[data-cat=${{h}}]`).click();
  }}
}}
window.onhashchange=applyHash;
applyHash();

render();
</script>
</body>
</html>"""
    return html
