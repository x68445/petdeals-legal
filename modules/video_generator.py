#!/usr/bin/env python3
"""
PetDeals Video Generator v3
Pipeline: AliExpress product video -> trim -> text overlay -> TTS merge -> 9:16 export
"""

import os
import random
import subprocess
import tempfile
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# Pillow 10+ compat
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.LANCZOS


def _safe_num(value, default=0.0) -> float:
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

BASE_DIR = "/home/ubuntu/petdeals_bot"
OUTPUT_DIR = f"{BASE_DIR}/output/videos"
AUDIO_DIR = f"{BASE_DIR}/output/audio"
TEMP_DIR = "/tmp/petdeals_v3"

# Fonts (fallback chain)
FONTS_BOLD = [
    "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    f"{BASE_DIR}/templates/fonts/NanumGothicBold.ttf",
]
FONTS_CJK = [
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKkr-Bold.otf",
]

TARGET_W, TARGET_H = 1080, 1920
MIN_DURATION = 6
MAX_DURATION = 13
MAX_VIDEO_DURATION = 13   # Target 13s for snappy Shorts

# U1: Hook overlay text (shown first HOOK_DURATION seconds)
HOOK_TEXT = {
    "ko": "{discount}% 할인!",
    # "en": "{discount}% OFF!",
    # "zh": "{discount}%折扣!",
}
HOOK_DURATION = 2  # seconds

# U3: CTA end card text (shown last CTA_DURATION seconds)
CTA_TEXT = {
    "ko": {"main": "프로필 링크 확인!", "sub": "팔로우하면 매일 특가!"},
    # "en": {"main": "Link in description!", "sub": "Follow for more deals!"},
    # "zh": {"main": "链接在简介里!", "sub": "关注获取每日优惠!"},
}
CTA_DURATION = 3  # seconds

# FIX 1: Link CTA text banner (replaces QR code)
LINK_CTA_TEXT = {
    "ko": "프로필 링크 확인!",
    # "en": "Link in comments!",
    # "zh": "评论区有链接!",
}
LINK_CTA_MARGIN_BOTTOM = 80  # px from bottom, above price badge

# FIX 5: Video template system
VIDEO_TEMPLATES = ["standard", "comparison", "question"]

TEMPLATE_HOOKS = {
    "standard": {
        "ko": "{discount}% 할인!",
    },
    "comparison": {
        "ko": "{discount}% 할인!",
    },
    "question": {
        "ko": "{discount}% 할인 실화?!",
    },
}

# BGM volume (applied in audio merge)
BGM_VOLUME = 0.15

KRW_RATE = 1  # prices are now KRW directly from API

for d in [OUTPUT_DIR, AUDIO_DIR, TEMP_DIR]:
    Path(d).mkdir(parents=True, exist_ok=True)


# ---- Font loader --------------------------------------------------------

def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    paths = FONTS_CJK + FONTS_BOLD if bold else FONTS_BOLD
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ---- Emoji stripper (PIL fonts don't render emoji) -------------------------

import re as _re
_EMOJI_RE = _re.compile(
    "[\U0001F600-\U0001F64F\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F9FF\U0001FA00-\U0001FAFF"
    "\U00002702-\U000027B0]+",
    flags=_re.UNICODE,
)

def _strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


# ---- FIX 5: Template picker ------------------------------------------------

_TEMPLATE_COUNTER_FILE = f"{BASE_DIR}/output/.template_counter"

def pick_template() -> str:
    """Cycle through standard → comparison → question → standard…"""
    try:
        with open(_TEMPLATE_COUNTER_FILE) as f:
            idx = int(f.read().strip())
    except Exception:
        idx = 0
    template = VIDEO_TEMPLATES[idx % len(VIDEO_TEMPLATES)]
    try:
        Path(_TEMPLATE_COUNTER_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(_TEMPLATE_COUNTER_FILE, "w") as f:
            f.write(str(idx + 1))
    except Exception:
        pass
    return template


# ---- Hook overlay image (template-aware) -----------------------------------

def _build_hook_image(
    discount: int, lang: str,
    price_str: str = "", orig_str: str = "",
    template: str = "standard",
) -> str:
    """Full-canvas transparent PNG for first HOOK_DURATION seconds."""
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    strip_y0 = int(TARGET_H * 0.28)
    strip_y1 = int(TARGET_H * 0.64)
    draw.rectangle([(0, strip_y0), (TARGET_W, strip_y1)], fill=(0, 0, 0, 145))

    font_big = _load_font(100)
    font_med = _load_font(64)

    def _centered_text(text, font, y, color=(255, 255, 255, 255)):
        b = draw.textbbox((0, 0), text, font=font)
        tw, th = b[2] - b[0], b[3] - b[1]
        tx = (TARGET_W - tw) // 2
        for dx, dy in [(-3,-3),(3,-3),(-3,3),(3,3),(0,4),(0,-4)]:
            draw.text((tx+dx, y+dy), text, font=font, fill=(0, 0, 0, 255))
        draw.text((tx, y), text, font=font, fill=color)
        return th

    mid_y = strip_y0 + (strip_y1 - strip_y0) // 2

    if discount >= 10:
        tmpl = TEMPLATE_HOOKS.get(template, TEMPLATE_HOOKS["standard"])
        tmpl_str = tmpl.get(lang, tmpl.get("ko", "{discount}% 할인!"))
        text = _strip_emoji(tmpl_str.format(discount=discount))
        _centered_text(text, font_big, mid_y - 50, color=(255, 215, 0, 255))
    else:
        _centered_text("알리특가!", font_big, mid_y - 50, color=(255, 215, 0, 255))

    path = f"{TEMP_DIR}/hook_{lang}.png"
    img.save(path, "PNG")
    return path


# ---- U3: CTA end card image ------------------------------------------------

def _build_cta_image(lang: str) -> str:
    """Full-canvas PNG: dark overlay + centered CTA text for last 3 seconds."""
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, TARGET_H)], fill=(0, 0, 0, 153))

    cta = CTA_TEXT.get(lang, CTA_TEXT["ko"])
    main_text = _strip_emoji(cta["main"])
    sub_text = _strip_emoji(cta["sub"])

    font_main = _load_font(60)
    font_sub  = _load_font(38)

    mb = draw.textbbox((0, 0), main_text, font=font_main)
    mw, mh = mb[2] - mb[0], mb[3] - mb[1]
    mx = (TARGET_W - mw) // 2
    my = int(TARGET_H * 0.40)

    for dx, dy in [(-2,-2),(2,-2),(-2,2),(2,2)]:
        draw.text((mx+dx, my+dy), main_text, font=font_main, fill=(0, 0, 0, 255))
    draw.text((mx, my), main_text, font=font_main, fill=(255, 255, 255, 255))

    sb = draw.textbbox((0, 0), sub_text, font=font_sub)
    sw = sb[2] - sb[0]
    sx = (TARGET_W - sw) // 2
    sy = my + mh + 30
    draw.text((sx, sy), sub_text, font=font_sub, fill=(210, 210, 210, 230))

    path = f"{TEMP_DIR}/cta_{lang}.png"
    img.save(path, "PNG")
    return path


# ---- FIX 2: Slideshow video from product images ----------------------------

def generate_slideshow_video(product_images: list, output_path: str,
                              duration_per_image: int = 3) -> bool:
    """
    Create a 1080x1920 slideshow video from product images with Ken Burns zoom effect.
    Used as fallback when product has no video URL.
    Returns True on success.
    """
    import requests as _req

    image_paths = []
    for i, img_url in enumerate(product_images[:5]):
        img_path = f"{TEMP_DIR}/slide_img_{i}.jpg"
        try:
            r = _req.get(img_url, timeout=15)
            r.raise_for_status()
            with open(img_path, "wb") as f:
                f.write(r.content)
            if os.path.getsize(img_path) > 1000:
                image_paths.append(img_path)
        except Exception as e:
            print(f"[SLIDESHOW] Image {i} download failed: {e}")

    if not image_paths:
        print("[SLIDESHOW] No images downloaded")
        return False

    n = len(image_paths)
    fps = 30
    frames_per_image = duration_per_image * fps

    filter_parts = []
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
            f"zoompan=z='min(zoom+0.0008,1.08)':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d={frames_per_image}:s=1080x1920:fps={fps}[v{i}]"
        )

    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_complex = ";".join(filter_parts) + f";{concat_inputs}concat=n={n}:v=1:a=0[out]"

    inputs = []
    for img in image_paths:
        inputs.extend(["-loop", "1", "-i", img])

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-t", str(n * duration_per_image),
        "-r", str(fps),
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        size = os.path.getsize(output_path)
        print(f"[SLIDESHOW] {n} images -> {output_path} ({size // 1024}KB)")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[SLIDESHOW] Failed: {e.stderr.decode()[:200]}")
        return False
    finally:
        for p in image_paths:
            try:
                os.unlink(p)
            except Exception:
                pass


# ---- Video download --------------------------------------------------------

def _download_video(url: str, output_path: str) -> bool:
    """Download video from URL. Returns True on success."""
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
        size = os.path.getsize(output_path)
        if size < 10_000:  # < 10KB = likely error
            print(f"[VIDEO] Download too small ({size} bytes): {url}")
            return False
        print(f"[VIDEO] Downloaded {size // 1024}KB: {output_path}")
        return True
    except Exception as e:
        print(f"[VIDEO] Download failed: {e}")
        return False


# ---- Video probing ---------------------------------------------------------

def _probe_duration(path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=15)
        return float(out.strip())
    except Exception:
        return 0.0


# ---- Trim + resize ---------------------------------------------------------

def _trim_and_resize(input_path: str, output_path: str) -> bool:
    """
    Trim to [MIN_DURATION, MAX_DURATION] seconds.
    Resize/crop to 1080x1920 (9:16).
    """
    duration = _probe_duration(input_path)
    if duration <= 0:
        print("[VIDEO] Cannot probe duration")
        return False

    # Clip to target range
    trim_dur = min(max(duration, MIN_DURATION), MAX_DURATION)
    # If source shorter than MIN, pad with loop or just use as-is
    if duration < MIN_DURATION:
        trim_dur = duration

    # ffmpeg: crop to 9:16, scale to 1080x1920
    filter_str = (
        "scale=iw*min(1080/iw\\,1920/ih):ih*min(1080/iw\\,1920/ih),"
        "pad=1080:1920:(1080-iw)/2:(1920-ih)/2:black,"
        "setsar=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-t", str(trim_dur),
        "-vf", filter_str,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[VIDEO] Trim/resize failed: {e.stderr.decode()[:200]}")
        return False


# ---- FIX 1+3: Middle overlay (price badge + link CTA, shown 2s to end-3s) --

def _build_middle_overlay(
    price_str: str, orig_price_str: str, discount: int, lang: str
) -> str:
    """
    Price badge + link CTA text. No QR, no watermark.
    Shown from 2s to (duration - 3s). Max 2 overlays at once.
    """
    img = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    ACCENT     = (255, 68, 68, 255)
    WHITE      = (255, 255, 255, 255)
    GOLD       = (255, 215, 0, 255)
    LIGHT_GRAY = (220, 220, 220, 200)
    PILL_BG    = (0, 0, 0, 178)

    def draw_pill(y_top, y_bot, x_pad=60):
        draw.rounded_rectangle([(x_pad, y_top), (TARGET_W - x_pad, y_bot)],
                                radius=28, fill=PILL_BG)

    font_large  = _load_font(90)
    font_small  = _load_font(38)
    font_banner = _load_font(30)

    y_base = int(TARGET_H * 0.68)

    # ---- Price pill ----
    pill_top = y_base - 20
    pill_bot = y_base + 160
    draw_pill(pill_top, pill_bot)

    disc_text = f"{discount}% OFF" if discount >= 10 else "알리특가"
    disc_bbox = draw.textbbox((0, 0), disc_text, font=font_large)
    dw = disc_bbox[2] - disc_bbox[0]
    dx = (TARGET_W - dw) // 2
    draw.text((dx, y_base), disc_text, font=font_large, fill=GOLD)

    sub_text = "알리에서 확인"
    sub_bbox = draw.textbbox((0, 0), sub_text, font=font_small)
    sx = (TARGET_W - (sub_bbox[2] - sub_bbox[0])) // 2
    draw.text((sx, y_base + 100), sub_text, font=font_small, fill=LIGHT_GRAY)

    # ---- Link CTA banner (below price pill) ----
    cta_text = _strip_emoji(LINK_CTA_TEXT.get(lang, LINK_CTA_TEXT["ko"]))
    cta_y = pill_bot + 18
    cta_pill_bot = cta_y + 64
    draw_pill(cta_y - 8, cta_pill_bot, x_pad=120)

    cb = draw.textbbox((0, 0), cta_text, font=font_banner)
    cx = (TARGET_W - (cb[2] - cb[0])) // 2
    draw.text((cx, cta_y + 10), cta_text, font=font_banner, fill=WHITE)

    path = f"{TEMP_DIR}/middle_{lang}.png"
    img.save(path, "PNG")
    return path


# ---- FIX 4: Source video quality check + enhancement ----------------------

import json as _json

def check_video_quality(video_path: str):
    """
    Returns (ok: bool, reason: str).
    Checks: min resolution 480x480, aspect ratio < 2.0.
    """
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        info = _json.loads(result.stdout)
    except Exception as e:
        return False, f"ffprobe failed: {e}"

    video_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if not video_stream:
        return False, "No video stream"

    w = int(video_stream.get("width", 0))
    h = int(video_stream.get("height", 0))

    if w < 480 or h < 480:
        return False, f"Resolution too low: {w}x{h}"

    if h > 0 and (w / h) > 2.0:
        return False, f"Too wide: {w}x{h} (aspect {w/h:.1f})"

    return True, "OK"


def enhance_source_video(input_path: str, output_path: str) -> bool:
    """
    Enhance source video:
    1. Crop 5% edges (removes border watermarks/text)
    2. Scale to fill 9:16 with blurred background (split filter avoids fan-out error)
    3. Sharpen + contrast/saturation boost
    Falls back to simple resize if enhancement fails.
    """
    # split=2 is required: [cropped] feeds two separate scale filters (bg + fg)
    filter_complex = (
        "[0:v]crop=iw*0.90:ih*0.90:iw*0.05:ih*0.05,split=2[cropped_bg][cropped_fg];"
        "[cropped_bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=20:20[bg];"
        "[cropped_fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        "unsharp=3:3:0.5:3:3:0.5,"
        "eq=contrast=1.05:brightness=0.02:saturation=1.1[vout]"
    )
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stderr)
        return True
    except Exception as e:
        err = str(e)[-300:] if len(str(e)) > 300 else str(e)
        print(f"[VIDEO] Enhancement failed ({err}), falling back to simple resize")
        # Fallback: simple scale + pad, no enhancement
        cmd_simple = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            output_path,
        ]
        try:
            subprocess.run(cmd_simple, check=True, capture_output=True, timeout=180)
            return True
        except Exception as e2:
            print(f"[VIDEO] Simple resize also failed: {e2}")
            return False


# ---- Overlay burn-in via ffmpeg ----------------------------------------

def _burn_overlay(video_path: str, overlay_path: str, output_path: str) -> bool:
    """Composite overlay PNG onto video using ffmpeg overlay filter."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", overlay_path,
        "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
        "-map", "[v]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[VIDEO] Overlay failed: {e.stderr.decode()[:300]}")
        return False


# ---- U1+U3: Timed overlay composite (hook + CTA) ---------------------------

def _apply_timed_overlays(
    video_path: str,
    middle_png: str,
    hook_png: str,
    cta_png: str,
    duration: float,
    output_path: str,
) -> bool:
    """
    FIX 3 overlay timeline (max 2 visible at once):
      [0-2s]        HOOK only
      [2 to end-3s] Price badge + Link CTA (middle)
      [last 3s]     CTA end card only
    """
    cta_start = max(0.0, duration - CTA_DURATION)
    filter_complex = (
        # middle overlay: 2s to cta_start
        f"[0:v][1:v]overlay=0:0:enable='between(t,{HOOK_DURATION},{cta_start:.3f})'[v1];"
        # hook: 0 to HOOK_DURATION
        f"[v1][2:v]overlay=0:0:enable='between(t,0,{HOOK_DURATION})'[v2];"
        # CTA end card: cta_start to end
        f"[v2][3:v]overlay=0:0:enable='gte(t,{cta_start:.3f})'[vout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", middle_png,
        "-i", hook_png,
        "-i", cta_png,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[VIDEO] Timed overlay failed: {e.stderr.decode()[:300]}")
        return False


# ---- Source video pre-processing ----------------------------------------

def trim_boring_intro(input_path: str, output_path: str, skip_secs: float = 2.0) -> str:
    """Skip first N seconds of product video (AliExpress logo/blank frames)."""
    import shutil
    duration = _probe_duration(input_path)
    if duration <= 0 or duration <= skip_secs + 2:
        shutil.copy2(input_path, output_path)
        return output_path
    try:
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(skip_secs), "-i", input_path,
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", output_path,
        ], check=True, capture_output=True, timeout=120)
        return output_path
    except subprocess.CalledProcessError:
        shutil.copy2(input_path, output_path)
        return output_path


def adjust_video_speed(input_path: str, output_path: str) -> str:
    """Speed up long product videos (1.2x at 15s+, 1.3x at 25s+) for better engagement."""
    import shutil
    duration = _probe_duration(input_path)
    if duration <= 0:
        shutil.copy2(input_path, output_path)
        return output_path

    if duration > 25:
        speed = 1.3
    elif duration > 15:
        speed = 1.2
    else:
        shutil.copy2(input_path, output_path)
        return output_path

    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-filter_complex",
            f"[0:v]setpts={1/speed:.4f}*PTS[v];[0:a]atempo={speed}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", output_path,
        ], check=True, capture_output=True, timeout=180)
        print(f"[VIDEO] Speed up {speed}x applied (source was {duration:.1f}s)")
        return output_path
    except subprocess.CalledProcessError:
        # Fallback: video-only speed (no audio stream)
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", input_path,
                "-vf", f"setpts={1/speed:.4f}*PTS",
                "-c:v", "libx264", "-preset", "fast", "-an", output_path,
            ], check=True, capture_output=True, timeout=180)
            return output_path
        except subprocess.CalledProcessError:
            shutil.copy2(input_path, output_path)
            return output_path


# ---- Clean overlay: FFmpeg drawtext (replaces PIL image compositing) --------

def _find_ffmpeg_font() -> str:
    """Return first available CJK font path for FFmpeg drawtext, or ''."""
    for fp in [
        "/usr/share/fonts/truetype/nanum/NanumSquareRoundB.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ]:
        if os.path.exists(fp):
            return fp
    return ""


def clean_text_for_ffmpeg(text: str) -> str:
    """Strip characters that break FFmpeg drawtext and escape % signs."""
    import re
    text = re.sub(r"[<>{}|\\^~`\[\]'\":]", "", text)
    text = text.replace("%", "%%")
    return text[:30]


def build_overlay_filter(product: dict, video_duration: float) -> str:
    """
    Build a 4-layer FFmpeg drawtext filter.
    One element visible at a time. Product stays center-stage.

    Timeline:
      0.3-2s      : discount % or "알리특가" (top-left, if discount>=10)
      2.5-end-4s  : product subtitle (bottom, center)
      6-10s       : price (bottom-center)
      last 4s     : CTA   (bottom-center)
    """
    font_path = _find_ffmpeg_font()
    if not font_path:
        return ""

    discount = int(_safe_num(product.get("discount", 0) or 0))
    price    = _safe_num(product.get("price") or product.get("target_sale_price") or 0)
    krw      = int(price * KRW_RATE)

    end       = float(video_duration)
    cta_start = max(end - 4.0, 3.0)

    disc_text = f"{discount}%% 할인" if discount >= 10 else "알리특가"

    style = (
        f"fontfile={font_path}:"
        f"fontcolor=white:"
        f"borderw=2:bordercolor=black@0.3:"
        f"shadowcolor=black@0.4:shadowx=2:shadowy=2"
    )

    # Product subtitle text (center-bottom, middle section)
    prod_raw = (product.get("name_ko") or product.get("title")
                or product.get("product_title") or "")
    subtitle = clean_text_for_ffmpeg(prod_raw)
    sub_start = 2.5
    sub_end = max(sub_start + 1.0, min(end * 0.55, cta_start - 0.5))

    # Timeline: 0.3-2s discount | 2.5-sub_end subtitle | 3-7s price | last4s CTA
    filters = []
    if discount >= 10:
        filters.append(
            f"drawtext=text='{discount}%% 할인':{style}:"
            f"fontsize=52:x=40:y=70:enable='between(t,0.3,2)'"
        )
    if subtitle and sub_end > sub_start:
        filters.append(
            f"drawtext=text='{subtitle}':{style}:"
            f"fontsize=34:x=(w-text_w)/2:y=h-180:"
            f"enable='between(t,{sub_start:.1f},{sub_end:.1f})'"
        )
    if discount >= 10:
        filters.append(
            f"drawtext=text='{disc_text}':{style}:"
            f"fontsize=42:x=(w-text_w)/2:y=h-120:enable='between(t,3,7)'"
        )
    filters.append(
        f"drawtext=text='프로필 링크 확인':{style}:"
        f"fontsize=40:x=(w-text_w)/2:y=h-100:"
        f"enable='between(t,{cta_start:.1f},{end:.1f})'"
    )
    return ",".join(filters)


def apply_overlays(
    input_video: str,
    output_video: str,
    product: dict,
    duration: float,
) -> str:
    """Apply drawtext overlays. Falls back to copy on failure."""
    import shutil
    vf = build_overlay_filter(product, duration)

    if not vf:
        shutil.copy2(input_video, output_video)
        return output_video

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        output_video,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        print(f"[Overlay] FFmpeg error: {result.stderr[-300:]}")
        shutil.copy2(input_video, output_video)

    return output_video


# ---- Background music: real royalty-free tracks, category-matched style -----

def _pick_bgm_style(product: dict) -> str:
    """Match music style to product category."""
    combined = (product.get("name", "") + " " + product.get("category", "")).lower()
    if any(w in combined for w in ["cat", "dog", "pet", "고양이", "강아지", "cute", "baby", "kids"]):
        return "cute"
    if any(w in combined for w in ["camping", "outdoor", "hiking", "sport", "fitness", "gym", "exercise"]):
        return "energetic"
    if any(w in combined for w in ["tech", "gadget", "wireless", "led", "usb", "bluetooth", "phone"]):
        return "upbeat"
    if any(w in combined for w in ["bed", "pillow", "cushion", "sleep", "relax", "lofi", "chill"]):
        return "chill"
    return random.choice(["upbeat", "fun", "cute", "energetic", "chill"])


def _generate_bgm(duration: float, output_path: str, product: dict = None) -> bool:
    """Export BGM matched to product style. Falls back to pydub if no files."""
    from modules.bgm_generator import export_bgm
    style = _pick_bgm_style(product) if product else None
    return export_bgm(duration, output_path, style=style)


# ---- Audio merge: TTS + BGM + original audio --------------------------------

def _merge_audio(
    video_path: str,
    tts_path: Optional[str],
    bgm_path: Optional[str],
    output_path: str,
) -> bool:
    """Mix video + TTS (0.9) + BGM (pre-faded) into output. Falls back gracefully."""
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path,
        ], stderr=subprocess.DEVNULL, timeout=10)
        has_orig = bool(out.strip())
    except Exception:
        has_orig = False

    tts_ok = bool(tts_path and os.path.exists(tts_path))
    bgm_ok = bool(bgm_path and os.path.exists(bgm_path))

    if not tts_ok and not bgm_ok:
        import shutil
        shutil.copy(video_path, output_path)
        return True

    cmd = ["ffmpeg", "-y", "-i", video_path]
    vol_parts = []
    mix_labels = []

    if has_orig:
        vol_parts.append("[0:a]volume=0.15[ao]")
        mix_labels.append("[ao]")

    next_idx = 1
    if tts_ok:
        cmd += ["-i", tts_path]
        vol_parts.append(f"[{next_idx}:a]volume=0.9[at]")
        mix_labels.append("[at]")
        next_idx += 1

    if bgm_ok:
        cmd += ["-i", bgm_path]
        vol_parts.append(f"[{next_idx}:a]volume=1.0[ab]")
        mix_labels.append("[ab]")

    if len(mix_labels) == 1:
        filter_str = ";".join(vol_parts)
        # extract label name from last vol_parts entry e.g. "[at]"
        final_audio = mix_labels[0]
    else:
        amix = "".join(mix_labels) + f"amix=inputs={len(mix_labels)}:duration=first[amix]"
        filter_str = ";".join(vol_parts) + ";" + amix
        final_audio = "[amix]"

    cmd += [
        "-filter_complex", filter_str,
        "-map", "0:v", "-map", final_audio,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest", output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[VIDEO] Audio merge failed: {e.stderr.decode()[:200]}")
        import shutil
        shutil.copy(video_path, output_path)
        return True  # non-fatal


# ---- TTS merge ---------------------------------------------------------

def _merge_tts(video_path: str, tts_path: str, output_path: str) -> bool:
    """
    Mix TTS audio with existing video audio (TTS louder).
    If no existing audio in video, just set TTS as audio.
    """
    # Check if video has audio stream
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        has_audio = bool(subprocess.check_output(probe_cmd, stderr=subprocess.DEVNULL, timeout=10).strip())
    except Exception:
        has_audio = False

    if has_audio:
        # Mix: TTS at 0.9, original at 0.15
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", tts_path,
            "-filter_complex",
            "[0:a]volume=0.15[orig];[1:a]volume=0.9[tts];[orig][tts]amix=inputs=2:duration=first[a]",
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            output_path,
        ]
    else:
        # No original audio, loop TTS to match video length
        video_dur = _probe_duration(video_path)
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-stream_loop", "-1",
            "-i", tts_path,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-t", str(video_dur),
            output_path,
        ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[VIDEO] TTS merge failed: {e.stderr.decode()[:300]}")
        # Fallback: just copy video
        import shutil
        shutil.copy(video_path, output_path)
        return True  # Don't abort pipeline for TTS merge failure


# ---- Main generator class -----------------------------------------------

class VideoGenerator:
    def __init__(self):
        for d in [OUTPUT_DIR, AUDIO_DIR, TEMP_DIR]:
            Path(d).mkdir(parents=True, exist_ok=True)

    def create_video(
        self,
        product: dict,
        copy: dict,
        lang: str,
        output_filename: str,
    ) -> Optional[dict]:
        """
        Full pipeline for one language:
        1. Download Ali video
        2. Trim + resize to 9:16
        3. Burn text overlay
        4. Generate TTS
        5. Mix TTS into video
        6. Export final

        Returns dict with video_path, thumbnail_path, copy, etc.
        """
        video_url = product.get("video_url") or product.get("product_video_url", "")
        base = f"{TEMP_DIR}/{output_filename}_{lang}"
        raw_path = f"{base}_raw.mp4"
        video_source = "original"

        if video_url:
            # Step 1a: Download product video
            if not _download_video(video_url, raw_path):
                return None
            ok, reason = check_video_quality(raw_path)
            if not ok:
                print(f"[VIDEO] Quality check failed ({reason}): {video_url[:60]}")
                return None
        else:
            # Step 1b: FIX 2 -- slideshow fallback from product images
            images = product.get("product_images", [])
            if product.get("image_url") and product["image_url"] not in images:
                images = [product["image_url"]] + images
            if not images:
                print(f"[VIDEO] No video URL and no images for {product.get('title', '')}")
                return None
            print(f"[VIDEO] No video URL -- generating slideshow from {len(images)} images")
            if not generate_slideshow_video(images, raw_path):
                return None
            video_source = f"slideshow ({min(len(images), 5)} images)"

        print(f"[VIDEO] Video source: {video_source}")

        # Hybrid: AI intro + real product + AI outro (optional, real video only)
        use_hybrid = False
        try:
            import json as _json
            _settings_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
            with open(_settings_path) as _sf:
                _settings = _json.load(_sf)
            _hybrid_cfg = _settings.get("hybrid_video", {})
            if _hybrid_cfg.get("enabled") and video_url:
                from modules.veo_product_scenes import create_hybrid_video
                hybrid_path = f"{base}_hybrid.mp4"
                hybrid_result = create_hybrid_video(
                    product=product,
                    product_video_path=raw_path,
                    output_path=hybrid_path,
                    intro_dur=_hybrid_cfg.get("intro_duration", 4),
                    product_dur=_hybrid_cfg.get("product_duration", 14),
                    outro_dur=_hybrid_cfg.get("outro_duration", 4),
                )
                if hybrid_result and os.path.exists(hybrid_result):
                    trimmed_path = hybrid_result
                    video_source = "hybrid (AI + product)"
                    use_hybrid = True
                    print(f"[VIDEO] Using HYBRID pipeline")
        except Exception as _he:
            print(f"[VIDEO] Hybrid skipped ({_he}), using standard pipeline")

        # Enhance + trim (skip enhance for slideshows or hybrid -- already clean 1080x1920)
        if video_url and not use_hybrid:
            # Pre-process: skip boring intro, then speed-adjust long videos
            pp1 = f"{base}_nointro.mp4"
            pp2 = f"{base}_sped.mp4"
            src = trim_boring_intro(raw_path, pp1)
            src = adjust_video_speed(src, pp2)

            enhanced_path = f"{base}_enhanced.mp4"
            if enhance_source_video(src, enhanced_path):
                trimmed_path = f"{base}_trimmed.mp4"
                if not _trim_and_resize(enhanced_path, trimmed_path):
                    return None
                try:
                    os.unlink(enhanced_path)
                except Exception:
                    pass
            else:
                trimmed_path = f"{base}_trimmed.mp4"
                if not _trim_and_resize(src, trimmed_path):
                    return None
            # Cleanup pre-process temps
            for _p in [pp1, pp2]:
                try:
                    if _p != raw_path and os.path.exists(_p):
                        os.unlink(_p)
                except Exception:
                    pass
        elif not use_hybrid:
            # Slideshow is already 1080x1920 -- just trim duration
            trimmed_path = f"{base}_trimmed.mp4"
            if not _trim_and_resize(raw_path, trimmed_path):
                return None

        # U5: Safety duration cap
        actual_dur = _probe_duration(trimmed_path)
        if actual_dur > MAX_VIDEO_DURATION:
            capped_path = f"{base}_capped.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-i", trimmed_path, "-t", str(MAX_VIDEO_DURATION),
                 "-c", "copy", capped_path],
                capture_output=True, timeout=60,
            )
            if os.path.exists(capped_path):
                os.unlink(trimmed_path)
                trimmed_path = capped_path
                actual_dur = MAX_VIDEO_DURATION

        # Step 3: Clean drawtext overlays (1 element at a time, no PIL images)
        template = pick_template()
        print(f"[VIDEO] Template: {template} [{lang}]")

        composited_path = f"{base}_composited.mp4"
        apply_overlays(trimmed_path, composited_path, product, actual_dur)

        # Step 4: TTS
        from modules.tts_generator import generate_tts, build_tts_script
        tts_script = copy.get("tts_script") or build_tts_script(copy, lang)
        tts_audio = generate_tts(tts_script, lang, output_filename)

        # U7: BGM (real royalty-free track, style matched to product category)
        bgm_path_out = f"{TEMP_DIR}/bgm_{lang}_{output_filename}.aac"
        bgm_generated = _generate_bgm(actual_dur, bgm_path_out, product=product)
        bgm_audio = bgm_path_out if bgm_generated else None

        # Step 5: Merge audio (TTS + BGM + original)
        final_path = f"{OUTPUT_DIR}/{output_filename}_{lang}.mp4"
        _merge_audio(composited_path, tts_audio, bgm_audio, final_path)

        if not os.path.exists(final_path):
            print(f"[VIDEO] Final export missing: {final_path}")
            return None

        # Thumbnail: extract frame at 1s
        # Generate custom thumbnail (price badge overlay)
        try:
            from modules.thumbnail_generator import generate_thumbnail
            thumb_path = generate_thumbnail(product, final_path) or ""
        except Exception as _te:
            print(f"[VIDEO] Thumbnail generator failed ({_te}), using basic frame")
            thumb_path = f"{OUTPUT_DIR}/{output_filename}_{lang}.jpg"
            subprocess.run(
                ["ffmpeg", "-y", "-i", final_path, "-ss", "1", "-vframes", "1", "-q:v", "2", thumb_path],
                capture_output=True, timeout=30,
            )

        # Cleanup temp files
        for f in [raw_path, trimmed_path, composited_path, bgm_path_out]:
            try:
                if f and os.path.exists(f):
                    os.unlink(f)
            except Exception:
                pass

        # Pick region-specific affiliate link for this language
        regional = product.get("regional_affiliate_links", {})
        aff_link = (
            regional.get(lang)
            or product.get("affiliate_link")
            or product.get("promotion_link")
            or product.get("product_detail_url", "")
        )
        title = product.get("title", product.get("product_title", ""))
        price = _safe_num(product.get("price") or product.get("target_sale_price") or 0)
        disc = int(_safe_num(product.get("discount", 0) or 0))
        disc_str = f"{disc}% OFF" if disc >= 10 else ""
        print(f"[VIDEO] Done [{lang}]: {final_path}")
        print(f"[VIDEO] link [{lang}]: {aff_link[:65]}")
        size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
        return {
            "video_path": final_path,
            "thumbnail_path": thumb_path if os.path.exists(thumb_path) else None,
            "copy": copy,
            "lang": lang,
            "affiliate_link": aff_link,
            "title": title,
            "price_str": disc_str,
            "price_krw": 0,
            "price": price,
            "original_price": _safe_num(product.get("original_price", 0) or 0),
            "discount": product.get("discount", 0),
            "category": product.get("category", ""),
        }


def generate_videos_for_product(product: dict, langs: list = None) -> dict:
    """
    Generate videos for specified languages for one product.

    langs: list of language codes to process e.g. ["ko"] or ["ko","en","zh"].
           Defaults to all 3 if None.
    Returns: {"ko": result_dict, ...}
    """
    from modules.gemini_copy import generate_all_languages

    target_langs = langs if langs else ["ko"]

    product_info = {
        "title": product.get("title", product.get("product_title", "Pet Product")),
        "price": _safe_num(product.get("price", product.get("target_sale_price", 0)) or 0),
        "original_price": _safe_num(product.get("original_price", 0) or 0),
        "discount": product.get("discount", 0),
        "category": product.get("category", ""),
    }

    copies = generate_all_languages(product_info)
    generator = VideoGenerator()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {}

    for lang, copy in copies.items():
        if lang not in target_langs:
            continue
        filename = f"deal_{ts}"
        result = generator.create_video(product, copy, lang, filename)
        if result:
            results[lang] = result
            print(f"[PIPELINE] {lang} video ready: {result['video_path']}")
        else:
            print(f"[PIPELINE] {lang} video FAILED")

    return results


if __name__ == "__main__":
    test_product = {
        "title": "Interactive Cat Toy Ball",
        "price": 2.50,
        "original_price": 25.00,
        "discount": 90,
        "video_url": "",  # needs real URL
        "category": "cat toys",
    }
    results = generate_videos_for_product(test_product)
    for lang, r in results.items():
        print(f"{lang}: {r.get('video_path', 'FAILED')}")
