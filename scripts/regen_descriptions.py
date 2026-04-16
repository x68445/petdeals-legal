#!/usr/bin/env python3
"""Regenerate product descriptions with price-tier-appropriate tone."""

import json
import re
import sys
import time

sys.path.insert(0, "/home/ubuntu/petdeals_bot")
from modules.gemini_copy import client

DATA_PATH = "/home/ubuntu/petdeals_bot/data/products.json"

TIER_PROMPTS = {
    "budget": (
        "아래 상품 이름을 보고 가성비/친근한 톤의 한 줄 홍보 문구를 만들어줘.\n"
        "규칙:\n"
        "- 각 문구는 20자 이내, 100% 한국어\n"
        "- 이모지 1개 허용 (선택)\n"
        "- 톤: 캐주얼, 친근, 가성비 강조\n"
        "- 예: '가성비 끝판왕!' '이 가격에 이 품질?' '하나쯤은 있어야 할 필수템'\n"
        "- 반드시 번호를 유지해서 '1. 문구' 형식으로 출력\n"
        "- 설명 없이 문구만 출력\n\n"
    ),
    "mid": (
        "아래 상품 이름을 보고 세련되고 도움되는 톤의 한 줄 홍보 문구를 만들어줘.\n"
        "규칙:\n"
        "- 각 문구는 20자 이내, 100% 한국어\n"
        "- 이모지 1개 허용 (선택)\n"
        "- 톤: 세련, 신뢰, 실용적\n"
        "- 예: '일상을 편안하게' '매일 쓰는 프리미엄' '현명한 선택'\n"
        "- 반드시 번호를 유지해서 '1. 문구' 형식으로 출력\n"
        "- 설명 없이 문구만 출력\n\n"
    ),
    "premium": (
        "아래 상품 이름을 보고 고급스럽고 신뢰감 있는 톤의 한 줄 홍보 문구를 만들어줘.\n"
        "규칙:\n"
        "- 각 문구는 20자 이내, 100% 한국어\n"
        "- 이모지 1개 허용 (선택)\n"
        "- 톤: 프리미엄, 전문가, 투자 가치\n"
        "- 예: '전문가가 인정한 품질' '확실한 투자 가치' '최상급 퀄리티'\n"
        "- 반드시 번호를 유지해서 '1. 문구' 형식으로 출력\n"
        "- 설명 없이 문구만 출력\n\n"
    ),
}


def get_tier(price_band: str) -> str:
    if price_band in ("price_1k", "price_5k"):
        return "budget"
    if price_band in ("price_10k", "price_30k"):
        return "mid"
    return "premium"


def batch_generate(products: list, tier: str, batch_size: int = 10) -> list:
    prompt_prefix = TIER_PROMPTS[tier]
    results = [""] * len(products)

    for start in range(0, len(products), batch_size):
        batch = products[start:start + batch_size]
        numbered = "\n".join(
            f"{i+1}. {p.get('name_ko', p.get('product_title', ''))}"
            for i, p in enumerate(batch)
        )
        prompt = prompt_prefix + numbered

        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt
            )
            for line in resp.text.strip().splitlines():
                line = line.strip()
                m = re.match(r'^(\d+)[.\)]\s*(.+)$', line)
                if m:
                    idx = int(m.group(1)) - 1
                    if 0 <= idx < len(batch):
                        results[start + idx] = m.group(2).strip().strip('"').strip("'")[:25]
            ok = sum(1 for r in results[start:start+len(batch)] if r)
            print(f"  [{tier}] batch {start}-{start+len(batch)-1}: {ok}/{len(batch)} OK")
        except Exception as e:
            print(f"  [{tier}] batch {start} FAILED: {e}")

        if start + batch_size < len(products):
            time.sleep(3)

    return results


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        products = json.load(f)

    # Group by tier
    tier_groups = {"budget": [], "mid": [], "premium": []}
    tier_indices = {"budget": [], "mid": [], "premium": []}
    for i, p in enumerate(products):
        tier = get_tier(p.get("price_band", "price_1k"))
        tier_groups[tier].append(p)
        tier_indices[tier].append(i)

    print(f"Total: {len(products)} products")
    for tier, items in tier_groups.items():
        print(f"  {tier}: {len(items)}")

    updated = 0
    for tier in ("budget", "mid", "premium"):
        if not tier_groups[tier]:
            continue
        print(f"\nGenerating {tier} descriptions...")
        descs = batch_generate(tier_groups[tier], tier)
        for j, desc in enumerate(descs):
            if desc:
                idx = tier_indices[tier][j]
                products[idx]["name_desc"] = desc
                updated += 1

    print(f"\nUpdated {updated}/{len(products)} descriptions")

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    print(f"Saved {DATA_PATH}")


if __name__ == "__main__":
    main()
