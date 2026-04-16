# PetDeals Bot -- 3단계 개선 핸드오프 문서

최종 업데이트: 2026-04-16

## Stage 1: Deals Page Core Fixes

### 중복 제거
- `link_page_generator.py` > `_deduplicate_similar()`: name_ko 앞 5자 클러스터링, 클러스터당 최대 3개 유지
- 정렬 기준: evaluate_rate (높은순) > lastest_volume (높은순)
- 결과: 234개 -> 170개 (22개 저가, 3개 중복, 39개 품절 제거)

### 원래가격 취소선
- `_render_deal_card()`: discount에서 원래가 계산, `<span class="deal-orig-price">` 취소선 표시
- 예: ~~₩34,979~~ ₩11,893 (66% 할인)

### 날짜 자동화
- deals.html `<span id="update-date">` + KST JavaScript 동적 렌더링
- 서버 재생성 없이도 항상 오늘 날짜 표시

### 썸네일 통일
- 모든 `.thumb`, `.thumb img`에 `aspect-ratio:1/1; object-fit:cover` 적용

### 품절 제거
- `update_deals_site()`: volume=0 + 평점 없는 상품 자동 필터링

---

## Stage 2: UX & Mobile Optimization

### 가격대별 설명 톤 차별화
- `scripts/regen_descriptions.py`: Gemini API로 3단계 톤 분리
  - budget (price_1k/5k): 캐주얼, 가성비 강조
  - mid (price_10k/30k): 세련, 실용적
  - premium (price_100k): 프리미엄, 전문가 신뢰

### 검색바
- deals.html sticky 검색 입력: `#search-input`
- 클라이언트사이드 JS, `window.__PRODUCTS` JSON 임베드 (170개 상품)
- name_ko + name_desc 실시간 필터링

### 필터
- 가격: 전체/천원대/만원대/십만원+
- 카테고리: 8종 (고양이/강아지/캠핑/전자/주방/패션/자동차/스포츠)
- 할인율: 전체/30%+/50%+/70%+
- AND 조합 로직

### 모바일 최적화
- `html { scroll-behavior:smooth }`
- `.fbtn` 최소 36px 높이, 44px 너비 터치 타겟
- 필터 그룹 수평 스크롤 (overflow-x:auto)
- 검색 결과 2열 그리드 (모바일), 3열 (640px+)

---

## Stage 3: Revenue Optimization

### 커미션 기반 정렬
- 카테고리 페이지 정렬: commission_rate DESC > discount DESC > price ASC
- commission > 8% 상품에 "💎 추천" 배지 (`rec-badge`)
- 현재 상품 분포: 7% x221, 9% x11, 3% x2

### CTA 강화
- 카운트다운 배너: "🔥 오늘만! 자정까지 특가" + KST 자정까지 타이머
- 상품 카드: "👆 클릭하고 알리에서 확인!" 마이크로카피
- 페이지 하단: "💌 매일 새 특가 알림 받기 -> 유튜브 구독" CTA 버튼

### YouTube 설명 템플릿
- `gemini_copy.py` > `build_full_description()` 전면 개편
- 강력 CTA + 체크마크 목록 + 어필리에이트 고지 포함

### SEO 제목 생성
- `generate_seo_title()`: 연도(2026), "추천"/"BEST"/"TOP" 키워드 추가
- 55자 이내 (모바일 최적화)

### 썸네일 브랜딩
- `thumbnail_generator.py`: 금색(#FFD700) + 다크(#1a1a1a) 색상 체계
- 우측 상단 "🐾 PawPawMeow" 로고
- 60px+ 한국어 텍스트, "오늘의 특가" 라벨

---

## 수동 작업 필요

**YouTube Studio 채널 프로필 링크 설정** -- `docs/SETUP_TODO.md` 참고

---

## 파일 변경 목록

| 파일 | 변경 내용 |
|------|-----------|
| `modules/link_page_generator.py` | 중복 제거, 원래가격, 날짜 JS, 검색/필터, CTA, 커미션 정렬 |
| `modules/gemini_copy.py` | YouTube 설명 템플릿, SEO 제목 |
| `modules/thumbnail_generator.py` | 브랜딩 색상, 로고, 레이아웃 |
| `data/products.json` | 가격대별 설명 톤 재생성 |
| `scripts/regen_descriptions.py` | 설명 재생성 스크립트 (신규) |
| `docs/SETUP_TODO.md` | YouTube 수동 설정 안내 (신규) |
| `docs/handoff.md` | 이 문서 (신규) |
