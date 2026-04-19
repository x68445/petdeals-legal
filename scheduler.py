#!/usr/bin/env python3
"""
PetDeals Continuous Pipeline
Runs 24/7. Generates and uploads whenever possible.
Quota exceeded? -> wait 30min -> retry.
New day? -> fetch fresh products -> continue.
"""

import json
import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = "/home/ubuntu/petdeals_bot"
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

Path(f"{BASE_DIR}/logs").mkdir(exist_ok=True)
Path(f"{BASE_DIR}/data").mkdir(exist_ok=True)

TZ = ZoneInfo("Asia/Seoul")

PRODUCTS_CACHE = f"{BASE_DIR}/data/today_products.json"
STATE_FILE     = f"{BASE_DIR}/data/pipeline_state.json"
VEO_USAGE_FILE = f"{BASE_DIR}/data/veo_usage.json"

QUOTA_COOLDOWN = 1800   # 30 min between quota retries
UPLOAD_DELAY   = 30     # seconds between successful uploads
DAILY_UPLOAD_CAP   = 18 # stop generating & uploading after this many
MAX_QUOTA_RETRIES  = 3  # give up after N consecutive quota retries
ERROR_DELAY    = 60     # seconds after unexpected error
MAX_CRASH_RETRIES  = 5  # stop pipeline after N consecutive unexpected crashes
NO_PRODUCT_RETRY = 3600 # seconds to wait if no products found


def _safe_num(v, default=0.0) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace("%", "").replace("$", "").replace(",", "").strip())
        except Exception:
            return float(default)
    return float(default)


def is_valid_product(product: dict) -> tuple:
    """Check if product has enough data to make a good video."""
    price = _safe_num(product.get("price", 0))
    original = _safe_num(product.get("original_price", 0))
    discount = _safe_num(product.get("discount", 0))

    if price <= 0:
        return False, "No price"

    if original <= 0 or original <= price:
        # Try to infer original from discount
        if discount > 0 and price > 0:
            product["original_price"] = round(price / (1 - discount / 100), 2)
            original = product["original_price"]
        else:
            return False, "No original price"

    if discount < 5:
        # Recalculate from prices
        if original > 0 and price > 0:
            discount = round((1 - price / original) * 100)
            product["discount"] = discount
        if discount < 5:
            return False, f"Discount too low ({int(discount)}%)"

    return True, "OK"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("petdeals")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.handlers.TimedRotatingFileHandler(
        f"{BASE_DIR}/logs/pipeline.log",
        when="midnight", interval=1, backupCount=30, encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


log = _setup_logging()


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def _kst_today() -> str:
    """Return today's date string in KST timezone."""
    return str(datetime.now(TZ).date())


def _new_day_state() -> dict:
    return {
        "date": _kst_today(),
        "products_fetched": False,
        "product_index": 0,
        "generated": 0,
        "uploaded": 0,
        "quota_exceeded": False,
        "last_quota_fail": None,
        "quota_retries": 0,
        "consecutive_failures": 0,
        "_pending_video": None,
    }


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        today = _kst_today()
        if state.get("date") != today:
            new_state = _new_day_state()
            # Check if today_products.json cache exists and is usable
            if Path(PRODUCTS_CACHE).exists():
                try:
                    with open(PRODUCTS_CACHE) as f:
                        cached = json.load(f)
                    if cached:
                        new_state["products_fetched"] = True
                        # Restore product_index by checking how many are in history
                        try:
                            from modules.ali_scraper import load_product_history
                            hist = load_product_history()
                            hist_ids = hist.get("ids", set())
                            done = 0
                            for p in cached:
                                pid = str(p.get("product_id", ""))
                                if pid and pid in hist_ids:
                                    done += 1
                                else:
                                    break
                            new_state["product_index"] = done
                        except Exception:
                            new_state["product_index"] = 0
                        log.info(f"[Pipeline] New day {today} -- reusing "
                                 f"{len(cached)} cached products "
                                 f"(resuming from index {new_state['product_index']})")
                except Exception:
                    pass
            return new_state
        # Ensure fields exist
        state.setdefault("consecutive_failures", 0)
        state.setdefault("quota_retries", 0)
        state.setdefault("_pending_video", None)
        return state
    except Exception:
        return _new_day_state()


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Veo scene counter
# ---------------------------------------------------------------------------

def _veo_scenes_today() -> int:
    try:
        if not Path(VEO_USAGE_FILE).exists():
            return 0
        log_data = json.loads(Path(VEO_USAGE_FILE).read_text())
        today = _kst_today()
        entry = next((e for e in log_data if e.get("date") == today), None)
        return entry.get("scenes_generated", 0) if entry else 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _cleanup_old_videos(days: int = 7):
    """Delete mp4 files older than N days from output/videos/."""
    import time as _t
    video_dir = Path(f"{BASE_DIR}/output/videos")
    if not video_dir.exists():
        return
    cutoff = _t.time() - (days * 86400)
    freed = 0
    deleted = 0
    for v in video_dir.rglob("*.mp4"):
        try:
            if v.stat().st_mtime < cutoff:
                freed += v.stat().st_size
                v.unlink()
                deleted += 1
        except OSError:
            pass
    if deleted:
        log.info(f"[Cleanup] Deleted {deleted} old videos, freed {freed/1024/1024:.1f}MB")


# ---------------------------------------------------------------------------
# Core helpers (thin wrappers around existing modules)
# ---------------------------------------------------------------------------

def _generate(product: dict, state: dict) -> dict:
    """Generate KO video for one product. Returns video_results dict or {}."""
    from modules.video_generator import generate_videos_for_product
    with open(f"{BASE_DIR}/config/settings.json") as f:
        settings = json.load(f)

    # Disable hybrid if Veo daily limit hit
    max_veo = settings.get("max_veo_scenes_per_day", 12)
    if _veo_scenes_today() >= max_veo:
        log.info("[Pipeline] Veo daily limit reached -- hybrid disabled for this product")
        try:
            import modules.video_generator as _vg
            _vg._HYBRID_DISABLED_RUNTIME = True
        except Exception:
            pass

    return generate_videos_for_product(product, langs=["ko"]) or {}


def _upload(video_results: dict) -> tuple[str | None, bool]:
    """Upload KO video. Returns (video_id, quota_exceeded)."""
    from modules.youtube_uploader import upload_to_youtube
    content = video_results.get("ko")
    if not content:
        return None, False
    try:
        vid_id = upload_to_youtube(content, lang="ko")
        return vid_id, False
    except Exception as e:
        err = str(e)
        if "uploadLimitExceeded" in err or "quotaExceeded" in err or "quota" in err.lower():
            return None, True
        raise


def _notify(msg: str, level: str = "INFO"):
    try:
        from modules.telegram_alert import send_alert
        send_alert(msg, level)
    except Exception as _e:
        log.warning(f"Telegram alert failed (non-fatal): {_e}")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def continuous_pipeline():
    log.info("=" * 60)
    log.info("PetDeals Continuous Pipeline starting")
    log.info("=" * 60)
    _notify("🔄 파이프라인 시작", "INFO")

    while True:
        try:
            state = load_state()

            # ── MIDNIGHT CLEANUP (once per day) ─────────────────────────
            if not state.get("_cleanup_done"):
                try:
                    from modules.ali_scraper import cleanup_old_history
                    removed = cleanup_old_history(max_age_days=30)
                    if removed:
                        log.info(f"[Pipeline] History cleanup: removed {removed} "
                                 f"entries older than 30 days")
                except Exception as _ce:
                    log.warning(f"[Pipeline] History cleanup failed: {_ce}")
                _cleanup_old_videos(days=7)
                state["_cleanup_done"] = True
                save_state(state)

            # ── DAILY DEALS TELEGRAM (9AM KST, once per day) ──────────────
            if not state.get("_deals_posted"):
                now_kst = datetime.now(TZ)
                if now_kst.hour >= 9:
                    try:
                        from modules.telegram_alert import send_daily_deals_summary
                        send_daily_deals_summary()
                        log.info("[Pipeline] Daily deals summary sent to Telegram")
                    except Exception as _td:
                        log.warning(f"[Pipeline] Daily deals post failed: {_td}")
                    state["_deals_posted"] = True
                    save_state(state)

            # ── NEW DAY: fetch products ─────────────────────────────────────
            if not state["products_fetched"]:
                log.info(f"[Pipeline] New day {state['date']} -- fetching products...")
                _notify("🔄 파이프라인 시작", "INFO")

                from modules.ali_scraper import collect_daily_products
                products = collect_daily_products()

                if not products:
                    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
                    save_state(state)
                    fails = state["consecutive_failures"]
                    log.warning(f"[Pipeline] No products found. "
                                f"Consecutive failures: {fails}. Retrying in 1h...")

                    if fails >= 5:
                        _notify(
                            f"⚠️ 파이프라인 연속 {fails}회 실패 - 점검 필요\n"
                            f"원인: 상품 수집 0개 (history 포화 가능성)",
                            "ERROR",
                        )
                    else:
                        _notify("🚨 상품 없음 -- 1시간 후 재시도", "WARNING")

                    time.sleep(NO_PRODUCT_RETRY)
                    continue

                with open(PRODUCTS_CACHE, "w") as f:
                    json.dump(products, f, indent=2, default=str, ensure_ascii=False)

                state["products_fetched"] = True
                state["product_index"] = 0
                state["consecutive_failures"] = 0
                state["_crash_count"] = 0
                save_state(state)

                log.info(f"[Pipeline] {len(products)} products fetched and cached")
                _notify(f"📦 상품 {len(products)}개 수집 완료", "INFO")

            # ── LOAD CACHE ─────────────────────────────────────────────────
            try:
                with open(PRODUCTS_CACHE) as f:
                    products = json.load(f)
            except Exception:
                log.warning("[Pipeline] Product cache missing -- re-fetching")
                state["products_fetched"] = False
                save_state(state)
                continue

            # ── RULE A: DAILY UPLOAD CAP ───────────────────────────────────
            if state["uploaded"] >= DAILY_UPLOAD_CAP:
                log.info(f"[DAILY CAP] {state['uploaded']}/{DAILY_UPLOAD_CAP} "
                         f"uploaded. Stopping for today. "
                         f"Next cycle: tomorrow 00:00 KST")
                _notify(
                    f"🛑 일일 업로드 완료 ({state['uploaded']}/{DAILY_UPLOAD_CAP}개)\n"
                    f"생성: {state['generated']}개\n"
                    f"내일 00:00 재시작",
                    "SUCCESS",
                )
                now = datetime.now(TZ)
                from datetime import timedelta
                midnight = now.replace(hour=0, minute=0, second=0,
                                       microsecond=0) + timedelta(days=1)
                wait = (midnight - now).total_seconds()
                log.info(f"[Pipeline] Sleeping {wait/3600:.1f}h until midnight KST")
                time.sleep(max(wait, 60))
                continue

            # ── ALL DONE FOR TODAY ──────────────────────────────────────────
            if state["product_index"] >= len(products):
                log.info(f"[Pipeline] All {len(products)} products done today."
                         f" Generated={state['generated']} Uploaded={state['uploaded']}")

                # Send daily summary
                try:
                    from modules.telegram_alert import send_daily_summary
                    send_daily_summary(state["generated"], state["uploaded"], [])
                except Exception:
                    pass

                # Daily analytics report
                try:
                    from modules.analytics_tracker import send_analytics_summary
                    send_analytics_summary()
                except Exception as _ae:
                    log.warning(f"[Pipeline] Analytics failed (non-fatal): {_ae}")

                # Weekly re-upload check (Sundays)
                try:
                    from modules.reupload_manager import get_reupload_candidates, is_sunday
                    if is_sunday():
                        candidates = get_reupload_candidates()
                        if candidates:
                            _notify(
                                f"♻️ 재업로드 후보 {len(candidates)}개:\n"
                                + "\n".join(f"  - {v['title'][:40]} ({v['views']:,}회)"
                                            for v in candidates),
                                "INFO",
                            )
                except Exception as _re:
                    log.warning(f"[Pipeline] Reupload check failed (non-fatal): {_re}")

                _notify(
                    f"📊 오늘 완료!\n"
                    f"생성: {state['generated']}개\n"
                    f"업로드: {state['uploaded']}개\n"
                    f"내일 09:00 재시작",
                    "SUCCESS",
                )

                # Sleep until midnight KST, then new day will trigger
                now = datetime.now(TZ)
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                from datetime import timedelta
                midnight += timedelta(days=1)
                wait = (midnight - now).total_seconds()
                log.info(f"[Pipeline] Sleeping {wait/3600:.1f}h until midnight KST")
                time.sleep(max(wait, 60))
                continue

            # ── RULE B: QUOTA COOLDOWN + RETRY LIMIT ──────────────────────
            if state["quota_exceeded"] and state.get("last_quota_fail"):
                # Check if retries exhausted
                retries = state.get("quota_retries", 0)
                if retries >= MAX_QUOTA_RETRIES:
                    log.warning(
                        f"[QUOTA GIVE UP] {MAX_QUOTA_RETRIES} retries exhausted. "
                        f"Uploaded {state['uploaded']} today. Stopping.")
                    _notify(
                        f"⛔ 쿼터 재시도 {MAX_QUOTA_RETRIES}회 실패\n"
                        f"오늘 {state['uploaded']}개 업로드. 내일 재시작",
                        "WARNING",
                    )
                    state["_pending_video"] = None
                    save_state(state)
                    now = datetime.now(TZ)
                    from datetime import timedelta
                    midnight = now.replace(hour=0, minute=0, second=0,
                                           microsecond=0) + timedelta(days=1)
                    wait = (midnight - now).total_seconds()
                    log.info(f"[Pipeline] Sleeping {wait/3600:.1f}h until midnight KST")
                    time.sleep(max(wait, 60))
                    continue

                last_fail = datetime.fromisoformat(state["last_quota_fail"])
                # Make last_fail timezone-aware if needed
                if last_fail.tzinfo is None:
                    last_fail = last_fail.replace(tzinfo=TZ)
                elapsed = (datetime.now(TZ) - last_fail).total_seconds()
                remaining = int(QUOTA_COOLDOWN - elapsed)

                if remaining > 0:
                    log.info(f"[Pipeline] Quota cooldown -- {remaining}s remaining "
                             f"(retry {retries + 1}/{MAX_QUOTA_RETRIES})")
                    time.sleep(min(remaining, 60))  # check every 60s max
                    continue

                # Cooldown over -- reset quota flag, bump retry counter
                state["quota_exceeded"] = False
                state["quota_retries"] = retries + 1
                save_state(state)
                log.info(f"[QUOTA RETRY] Attempt {retries + 1}/{MAX_QUOTA_RETRIES} "
                         f"-- retrying upload without regenerating video")

            # ── PROCESS NEXT PRODUCT ────────────────────────────────────────
            idx = state["product_index"]
            product = products[idx]
            title = (product.get("product_title") or product.get("name", ""))[:40]
            log.info(f"[Pipeline] [{idx+1}/{len(products)}] {title}")

            # Skip if already uploaded (dedup guard on restart)
            pid = str(product.get("product_id", product.get("id", "")))
            if pid:
                try:
                    from modules.ali_scraper import load_product_history
                    hist = load_product_history()
                    if pid in hist.get("ids", set()):
                        log.info(f"[Pipeline] [{idx+1}] Skip: already in history -- {title}")
                        state["product_index"] += 1
                        save_state(state)
                        continue
                except Exception:
                    pass

            # Validate product data quality
            valid, reason = is_valid_product(product)
            if not valid:
                log.info(f"[Pipeline] [{idx+1}] Skip: {reason} -- {title}")
                state["product_index"] += 1
                save_state(state)
                continue

            # ── RULE C: REUSE PENDING VIDEO ON QUOTA RETRY ───────────────
            pending = state.get("_pending_video")
            if pending:
                # Quota retry -- skip generation, reuse saved video
                video_results = pending
                log.info(f"[Pipeline] [{idx+1}] Reusing pending video (quota retry)")
            else:
                # A: Generate new video
                try:
                    video_results = _generate(product, state)
                except Exception as e:
                    log.error(f"[Pipeline] [{idx+1}] Generation error: {e}",
                              exc_info=True)
                    _notify(f"🚨 오류 발생: {str(e)[:80]}", "ERROR")
                    state["product_index"] += 1
                    save_state(state)
                    time.sleep(ERROR_DELAY)
                    continue

                if not video_results:
                    log.warning(f"[Pipeline] [{idx+1}] Generation returned "
                                f"empty -- skipping")
                    state["product_index"] += 1
                    save_state(state)
                    continue

                state["generated"] += 1

            ko = video_results.get("ko", {})
            log.info(f"[Pipeline] [{idx+1}] Video ready: "
                     f"{ko.get('video_path','?')}")

            # B: Upload
            try:
                vid_id, quota_exceeded = _upload(video_results)
            except Exception as e:
                log.error(f"[Pipeline] [{idx+1}] Upload error: {e}")
                _notify(f"🚨 오류 발생: {str(e)[:80]}", "ERROR")
                state["_pending_video"] = None
                state["product_index"] += 1
                save_state(state)
                continue

            if quota_exceeded:
                # Save video for retry -- do NOT regenerate
                state["quota_exceeded"] = True
                state["last_quota_fail"] = datetime.now(TZ).isoformat()
                state["_pending_video"] = video_results
                save_state(state)
                log.warning(f"[Pipeline] QUOTA EXCEEDED after "
                            f"{state['uploaded']} uploads. Waiting 30min...")
                _notify(
                    f"⏳ 쿼터 초과 (오늘 {state['uploaded']}개 업로드)\n"
                    f"재시도 {state.get('quota_retries', 0) + 1}/"
                    f"{MAX_QUOTA_RETRIES} 예정",
                    "WARNING",
                )
                # Do NOT advance product_index -- retry after cooldown
                continue

            # Upload succeeded or non-quota None
            state["_pending_video"] = None
            state["quota_retries"] = 0  # reset on success
            state["_crash_count"] = 0

            if vid_id:
                state["uploaded"] += 1
                state["product_index"] += 1
                save_state(state)

                try:
                    from modules.ali_scraper import save_to_history
                    save_to_history(
                        product.get("product_id", product.get("id", "")),
                        product.get("product_title", product.get("name", "")),
                    )
                except Exception:
                    pass

                url = f"https://youtube.com/shorts/{vid_id}"
                log.info(f"[Pipeline] [{idx+1}] Uploaded! "
                         f"({state['uploaded']} today) {url}")
                _notify(f"📤 #{state['uploaded']} 업로드 완료\n{url}", "SUCCESS")
                time.sleep(UPLOAD_DELAY)
            else:
                # Upload returned None (non-quota failure)
                log.warning(f"[Pipeline] [{idx+1}] Upload returned None "
                            f"-- skipping")
                state["product_index"] += 1
                save_state(state)

        except KeyboardInterrupt:
            log.info("[Pipeline] KeyboardInterrupt -- shutting down")
            _notify("🔄 파이프라인 중지됨", "WARNING")
            break
        except Exception as e:
            log.error(f"[Pipeline] Unexpected error: {e}", exc_info=True)
            crash_count = state.get("_crash_count", 0) + 1
            state["_crash_count"] = crash_count
            save_state(state)

            if crash_count >= MAX_CRASH_RETRIES:
                _notify(
                    f"⛔ 연속 크래시 {crash_count}회 -- 파이프라인 중지\n"
                    f"마지막 오류: {str(e)[:100]}",
                    "ERROR",
                )
                log.error(f"[Pipeline] {crash_count} consecutive crashes -- "
                          f"stopping until next day")
                now = datetime.now(TZ)
                from datetime import timedelta
                midnight = now.replace(hour=0, minute=0, second=0,
                                       microsecond=0) + timedelta(days=1)
                wait = (midnight - now).total_seconds()
                time.sleep(max(wait, 60))
                continue

            delay = ERROR_DELAY * min(crash_count * 2, 10)
            _notify(f"🚨 크래시 {crash_count}/{MAX_CRASH_RETRIES}: "
                    f"{str(e)[:80]}\n{delay}초 후 재시도", "ERROR")
            time.sleep(delay)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    continuous_pipeline()
