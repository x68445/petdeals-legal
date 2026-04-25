# 냥댕라이프 (NyangDaengLife) - 프로젝트 가이드

## 개요
- **채널**: @NyangDaengLife (YouTube)
- **수익**: AliExpress 제휴 (tracking ID: pawmeow)
- **딜페이지**: https://x68445.github.io/petdeals-legal/deals.html
- **운영**: 솔로, ₩0/월
- **시작일**: 2026-04-19
- **운영자 호칭**: 진이님 (한국어)

## 시스템 구조

### 영상 자동 생성
- **롱폼** (2분, TOP 8): compilation_v2.py + compilation_runner.py
- **쇼츠** (60초, TOP 3): shorts_generator.py + shorts_runner.py
- 카테고리 집중 포맷 (요일별 서브카테고리)
- 5가지 조회수 부스터 (쇼크 인트로, 반전 구성, 댓글 유도, SEO 제목, 효과음)

### 자동화/안전장치
- **safety_checker.py**: 7항목 프리체크 (롱폼+쇼츠)
- **auto_publisher.py**: 큐 + unlisted 업로드 + 검토 대기
- **review_queue.py**: pending_review.json 큐 관리
- **telegram_review_bot.py**: /approve, /reject 명령 처리
- **expire_pending.py**: 6시간 만료 자동 삭제
- **emergency_unpublish.py**: 응급 비공개

### 데이터
- **상품 풀**: 577개 (강아지 185, 고양이 302, 범용 110)
- **100% 펫 상품** (is_pet_product 필터, "carpet" 오탐 수정됨)
- **100% s.click 제휴 링크** (promotion_link 필드 사용)
- **키워드**: 114개 (펫 특정)
- **운영 가능**: 65일치

### 중복 방지
- 21일 내 같은 상품 재사용 X
- 같은 날 쇼츠 vs 롱폼 상품 중복 X (양방향)
- compilation_product_history.json (video_type 구분)

## Cron 스케줄 (서버 UTC, KST=UTC+9)

```
0 3 * * *  → KST 12:00 쇼츠 자동 발행 (--mode=auto)
0 9 * * *  → KST 18:00 롱폼 영상 생성
0 10 * * * → KST 19:00 롱폼 자동 발행
0 13 * * * → KST 22:00 일일 리포트
0 * * * *  → 매시간 검토 큐 만료 처리
```

## 발행 흐름 (검토 시스템)

```
1. 자동 영상 생성 (cron)
2. unlisted YouTube 업로드
3. pending_review.json 큐에 추가
4. 텔레그램 알림: "🔍 검토 필요"
5. 진이님 명령:
   - /approve {video_id} → public 전환
   - /reject {video_id} → 삭제
6. 6시간 무응답 → 자동 삭제
```

## 발견하고 수정한 치명적 버그 (이력)

1. **이미지 캐시 버그** (Day 5)
   - media_downloader.py 인덱스 기반 파일명
   - 어제 이미지 재사용 → 자막-이미지 불일치
   - 해결: 매 영상 생성 시 미디어 폴더 클리어

2. **카테고리 필터 실패** (Day 5)
   - "고양이 영상에 강아지 6개"
   - compilation_v2.py가 category_key 무시
   - 해결: _classify_animal() + 반대 카테고리 절대 배제

3. **제휴 링크 0%** (Day 5)
   - link_page_generator.py 가 affiliate_link(가짜) 사용
   - promotion_link(s.click 진짜) 미사용
   - 해결: deals_page_v2.py + link_page_generator.py promotion_link 우선

4. **"carpet" 오탐** (Day 6)
   - "pet" in text 매칭으로 carpet, puppet 등 통과
   - 해결: 공백 포함 매칭 + fashion/car/sports/electronics 차단

5. **같은 날 쇼츠-롱폼 중복** (Day 6)
   - 시뮬레이션 8/3 중 3개 겹침 (100%)
   - 해결: get_todays_used_product_ids() 양방향 적용

6. **자막 □□□ 깨짐** (Day 6)
   - ffmpeg drawtext 한글 3+자 글리프 미스매핑
   - 해결: PIL로 한글 PNG 사전 렌더 + overlay 합성

## 핵심 파일 위치

```
/home/ubuntu/petdeals_bot/
├── modules/
│   ├── compilation_v2.py          # 롱폼 상품 선정 (건드리지 말 것)
│   ├── compilation_runner.py      # 롱폼 실행
│   ├── compilation_video.py       # 롱폼 영상 빌드
│   ├── compilation_tts.py         # TTS
│   ├── shorts_generator.py        # 쇼츠 생성
│   ├── shorts_runner.py           # 쇼츠 실행
│   ├── safety_checker.py          # 프리체크 7항목
│   ├── auto_publisher.py          # 자동 발행
│   ├── review_queue.py            # 검토 큐
│   ├── telegram_review_bot.py     # 텔레그램 봇 (/approve, /reject)
│   ├── expire_pending.py          # 큐 만료 처리
│   ├── youtube_uploader.py        # YouTube API
│   ├── thumbnail_generator.py     # 썸네일 생성
│   ├── product_classifier.py      # 펫 상품 분류 + 서브카테고리
│   ├── deals_page_v2.py           # 딜페이지 생성
│   ├── ali_scraper.py             # 알리 상품 수집
│   ├── bgm_manager.py             # BGM 관리
│   ├── link_tracker.py            # UTM 추적
│   ├── auto_content/              # AI 쇼츠 (PAUSED, 건드리지 말 것)
│   └── ...
├── data/
│   ├── products/                  # 수집된 상품 JSON
│   ├── compilation_product_history.json  # 21일 중복 이력
│   ├── pending_review.json        # 검토 대기 큐
│   ├── bgm/youtube_official/      # 안전 BGM (현재 비어있음)
│   └── sfx/                       # 효과음 (siren, ding, fanfare 등)
├── output/
│   ├── compilation/               # 롱폼 영상
│   ├── shorts/                    # 쇼츠 영상
│   └── thumbnails/                # 썸네일
└── logs/
    ├── compilation_*.log
    ├── shorts_auto.log
    └── expire_pending.log
```

## 절대 건드리지 말 것

1. **modules/auto_content/*** - AI 쇼츠 시스템 (PAUSED 상태)
2. **modules/compilation_*.py** 핵심 로직 (이미 안정화됨)
3. **modules/scheduler.py** (있다면)
4. **cron 기존 엔트리** (/tmp/crontab_backup_*.txt 백업 있음)

## 운영자 (진이님) 정책

- ✅ 비용 ₩0 유지 (ElevenLabs 등 유료 서비스 X, EdgeTTS 사용)
- ✅ 직접 촬영/녹음 X (완전 자동화)
- ✅ AI 영상 생성 X (Pika/Runway 등)
- ✅ 저작권 안전 (Pixabay BGM 위험, YouTube Audio Library 권장)
- ❌ 정중한 톤 / 길게 설명 / 컨디션 걱정 멘트 싫어함
- ✅ 명령형 짧은 답변 선호
- ✅ ask_user_input_v0 도구로 의사결정 묻기 (모바일 사용)
- ✅ 페르소나: Alex Chen (한국어, 직설적, 데이터 중심)

## 발행된 영상 이력

- https://youtu.be/rP3s1kleFQY (4/22, 첫 공식 롱폼)
- https://youtu.be/-2ocD9vH4Ko (4/24, 카테고리 섞임 버그 영상)
- https://youtu.be/OQFP1SjSt5E (4/24, 첫 쇼츠 unlisted)

## PENDING (남은 작업)

1. **YouTube Audio Library BGM 다운로드** (진이님 PC 작업)
   - 위치: data/bgm/youtube_official/
   - 10~20곡 필요
   - 현재 비어있어 BGM 없이 발행 중

2. **About 채널 설명** (검색 노출용)

3. **Tier 2 추가 포맷** (포맷 F 초보자 가이드, 포맷 A 주간 BEST)

4. **타임존 전면 마이그레이션** (datetime.now() 63곳 → KST)

5. **업로드 재시도 제한** (youtube_uploader.py MAX_RETRIES=3)

## 작동 모드

- **--mode=auto**: public 발행 (cron이 사용)
- **--mode=test** 또는 **--privacy=unlisted**: 테스트 (검토 대기)
- 검토 시스템 추가 후 기본값 unlisted, /approve 명령으로 public 전환

## 환경

- 서버: Oracle Cloud Ubuntu, /home/ubuntu/petdeals_bot/
- Python 3, ffmpeg 6.1.1 (한글 drawtext 버그 있음 → PIL overlay 우회)
- systemd 서비스: petdeals-scheduler, petdeals-review-bot
- 텔레그램 봇 (검토 명령 수신)

## 협업 구조

진이님(중계자) ↔ Claude(전략/프롬프트 작성) ↔ Claude Code(서버 실행)

Claude는 서버 직접 접근 불가. 진이님이 결과 복사해서 공유.
