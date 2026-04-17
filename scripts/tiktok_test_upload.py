#!/usr/bin/env python3
"""
Test TikTok video upload.
Usage: python3 scripts/tiktok_test_upload.py [video_path]
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, "/home/ubuntu/petdeals_bot")

from modules.tiktok_uploader import upload_video, get_access_token, query_creator_info


def find_sample_video() -> str:
    """Find a video file in output/videos/ for testing."""
    video_dir = Path("/home/ubuntu/petdeals_bot/output/videos")
    if video_dir.exists():
        for ext in ("*.mp4", "*.mov"):
            videos = sorted(video_dir.glob(ext), key=lambda p: p.stat().st_mtime, reverse=True)
            if videos:
                return str(videos[0])
    return ""


def main():
    video_path = sys.argv[1] if len(sys.argv) > 1 else find_sample_video()
    if not video_path or not Path(video_path).exists():
        print("No video found. Provide a path: python3 scripts/tiktok_test_upload.py <video>")
        sys.exit(1)

    size_mb = Path(video_path).stat().st_size / (1024 * 1024)
    print(f"Video: {video_path} ({size_mb:.1f} MB)")

    # Verify token works
    print("\nChecking access token...")
    try:
        token = get_access_token()
        print(f"Token OK: {token[:20]}...")
    except Exception as e:
        print(f"Token error: {e}")
        print("Run 'python3 scripts/tiktok_setup.py' first.")
        sys.exit(1)

    # Check creator info
    print("\nQuerying creator info...")
    try:
        info = query_creator_info()
        print(json.dumps(info, indent=2))
    except Exception as e:
        print(f"Creator info failed: {e}")

    # Upload
    caption = "냥댕라이프 test upload #shorts #petproducts"
    print(f"\nUploading with caption: {caption}")
    try:
        result = upload_video(video_path, caption)
        print(f"\nResult:\n{json.dumps(result, indent=2)}")
        print("\nUpload test complete!")
    except Exception as e:
        print(f"\nUpload failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
