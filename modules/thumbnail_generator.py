#!/usr/bin/env python3
"""
Thumbnail Generator
Extracts best frame (30% into video) + adds price badge overlay.
"""

import json
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = "/home/ubuntu/petdeals_bot"
THUMB_DIR = f"{BASE_DIR}/output/thumbnails"


def _find_font() -> str:
    for fp in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    ]:
        if os.path.exists(fp):
            return fp
    return ""


def _probe_duration(video_path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
            capture_output=True, text=True, timeout=15,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def _extract_frame(video_path: str, output_path: str, ratio: float = 0.3) -> bool:
    """Extract a single frame at `ratio` of total duration."""
    duration = _probe_duration(video_path)
    if duration <= 0:
        return False
    ts = max(duration * ratio, 0.5)
    r = subprocess.run([
        "ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
        "-frames:v", "1", "-q:v", "2", output_path,
    ], capture_output=True, timeout=30)
    return r.returncode == 0 and os.path.exists(output_path)


def generate_thumbnail(product: dict, video_path: str) -> str | None:
    """Generate eye-catching 1080x1920 thumbnail with price badge.

    Returns path to saved JPEG, or None on failure.
    """
    os.makedirs(THUMB_DIR, exist_ok=True)

    pid = str(product.get("product_id") or product.get("id") or "unknown")[:12]
    thumb_path = os.path.join(THUMB_DIR, f"thumb_{pid}.jpg")
    frame_path = os.path.join(THUMB_DIR, f"frame_{pid}.jpg")

    if not _extract_frame(video_path, frame_path):
        return None

    try:
        img = Image.open(frame_path).convert("RGB")
        img = img.resize((1080, 1920), Image.LANCZOS)
        draw = ImageDraw.Draw(img, "RGBA")

        font_path = _find_font()
        if not font_path:
            os.remove(frame_path)
            return None

        discount = float(str(product.get("discount", 0)).replace("%", "") or 0)
        price = float(str(product.get("price", 0) or product.get("target_sale_price", 0))
                      .replace("$", "").replace(",", "") or 0)
        krw = int(price * 1350)

        # -- Price badge (bottom, dark gold+black) --
        badge_y = 1600
        draw.rounded_rectangle([(30, badge_y), (1050, badge_y + 260)],
                                radius=24, fill=(26, 26, 26, 230))
        # Gold accent line
        draw.rounded_rectangle([(30, badge_y), (1050, badge_y + 6)],
                                radius=0, fill=(255, 215, 0, 255))

        try:
            font_big = ImageFont.truetype(font_path, 80)
            font_med = ImageFont.truetype(font_path, 54)
            font_tag = ImageFont.truetype(font_path, 44)
            font_sm = ImageFont.truetype(font_path, 32)
            font_logo = ImageFont.truetype(font_path, 28)
        except Exception:
            os.remove(frame_path)
            return None

        if discount >= 10:
            draw.text((80, badge_y + 20), f"{int(discount)}% 할인!",
                      fill=(255, 215, 0), font=font_big)
        else:
            draw.text((80, badge_y + 20), "알리특가!",
                      fill=(255, 215, 0), font=font_big)
        draw.text((80, badge_y + 120), f"₩{krw:,}",
                  fill="white", font=font_med)
        draw.text((80, badge_y + 190), "오늘의 특가",
                  fill=(255, 215, 0, 180), font=font_sm)

        # -- "알리특가" badge (top-left, gold+black) --
        draw.rounded_rectangle([(30, 50), (330, 130)], radius=15,
                                fill=(26, 26, 26, 230))
        draw.rounded_rectangle([(30, 50), (330, 56)], radius=0,
                                fill=(255, 215, 0, 255))
        draw.text((55, 68), "알리특가", fill=(255, 215, 0), font=font_tag)

        # -- PawPawMeow logo (top-right) --
        draw.rounded_rectangle([(750, 50), (1050, 110)], radius=12,
                                fill=(26, 26, 26, 200))
        draw.text((770, 62), "🐾 PawPawMeow",
                  fill=(255, 215, 0), font=font_logo)

        img.save(thumb_path, "JPEG", quality=90)
    except Exception as e:
        print(f"[THUMB] Failed: {e}")
        thumb_path = None
    finally:
        try:
            os.remove(frame_path)
        except Exception:
            pass

    return thumb_path
