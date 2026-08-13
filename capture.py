"""Snapshot tool for the Juneau flood cameras.

Resolves each live stream to a playable address, pulls a single frame
with ffmpeg, and files it under photos/<camera>/<date>/ using Juneau
local time. Every camera gets its own retry loop, so one bad stream
never blocks the others.
"""

import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from yt_dlp import YoutubeDL

JUNEAU = ZoneInfo("America/Juneau")
PHOTO_ROOT = Path(__file__).resolve().parent / "photos"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

ATTEMPTS = 3
RETRY_WAIT_SEC = 30
FFMPEG_TIMEOUT_SEC = 150
MIN_FILE_BYTES = 20_000

CAMERAS = [
    {
        "name": "mendenhall_river_cam",
        "kind": "rtspme",
        "stream_id": "3nNBGQsb",
        "jpeg_quality": 3,
    },
    {
        "name": "all_cameras_grid",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=ZlQLmBNLz-c",
        "jpeg_quality": 1,
    },
    {
        "name": "rotating_single_view",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=sDAtRwK8oNE",
        "jpeg_quality": 2,
    },
    {
        "name": "mendenhall_glacier_cam",
        "kind": "youtube",
        "url": "https://www.youtube.com/watch?v=jJI5w_RVGtQ",
        "jpeg_quality": 2,
        # The explore.org channel uses a promotional still as its
        # thumbnail, so falling back to it would save a wrong image.
        "thumbnail_fallback": False,
    },
    {
        # USGS camera inside Suicide Basin, the source of the flood.
        # A plain hourly jpg, so it works from any machine.
        "name": "usgs_suicide_basin",
        "kind": "image",
        "url": (
            "https://usgs-nims-images.s3.amazonaws.com/overlay/"
            "AK_Glacial_Lake_near_Nugget_LOOKING_UPSTREAM_GLACIER_VIEW/"
            "AK_Glacial_Lake_near_Nugget_LOOKING_UPSTREAM_GLACIER_VIEW_newest.jpg"
        ),
    },
]


def log(message):
    stamp = datetime.now(JUNEAU).strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def resolve_rtspme(stream_id):
    """rtsp.me hands out a short lived token, then its media server
    turns that token into an HLS address tied to our own IP."""
    referer = f"https://rtsp.me/embed/{stream_id}/"
    headers = {"User-Agent": BROWSER_UA, "Referer": referer}

    reply = requests.get(
        f"https://rtsp.me/api/embed/{stream_id}/token/",
        headers=headers,
        timeout=30,
    )
    reply.raise_for_status()
    session = reply.json()
    if session.get("status") != "ok":
        raise RuntimeError(f"rtsp.me answered with status {session.get('status')!r}")

    server = session["url"].rstrip("/")
    reply = requests.get(
        f"{server}/token/{session['token']}", headers=headers, timeout=30
    )
    reply.raise_for_status()
    sources = reply.json()

    address = sources.get("hd") or sources.get("hls") or sources.get("ios")
    if not address:
        raise RuntimeError("rtsp.me reply had no stream address")
    return address, referer


def resolve_youtube(page_url):
    """YouTube refuses stream requests from shared cloud machines
    unless real browser cookies come along. When the YT_COOKIES_FILE
    variable points at a cookies file we use it, otherwise this only
    succeeds from a normal home connection."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestvideo/best",
    }
    cookies = os.environ.get("YT_COOKIES_FILE")
    if cookies and Path(cookies).exists():
        options["cookiefile"] = cookies
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(page_url, download=False)
    address = info.get("url")
    if not address:
        raise RuntimeError("yt-dlp found no stream address")
    return address, None


def youtube_live_thumbnail(video_id, out_path):
    """Worst case fallback. The live thumbnail refreshes often and is
    never blocked, but it tops out at 1280 x 720."""
    address = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    reply = requests.get(address, headers={"User-Agent": BROWSER_UA}, timeout=30)
    reply.raise_for_status()
    if len(reply.content) < MIN_FILE_BYTES:
        raise RuntimeError("thumbnail came back empty or tiny")
    out_path.write_bytes(reply.content)


def grab_frame(address, referer, quality, out_path):
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if referer:
        command += ["-headers", f"Referer: {referer}\r\n"]
    command += [
        "-i",
        address,
        "-frames:v",
        "1",
        "-q:v",
        str(quality),
        str(out_path),
    ]
    subprocess.run(command, check=True, timeout=FFMPEG_TIMEOUT_SEC)

    if not out_path.exists() or out_path.stat().st_size < MIN_FILE_BYTES:
        out_path.unlink(missing_ok=True)
        raise RuntimeError("frame came back empty or truncated")


def latest_saved(camera):
    cam_dir = PHOTO_ROOT / camera["name"]
    if not cam_dir.exists():
        return None
    files = sorted(cam_dir.glob("*/" + camera["name"] + "_*.jpg"))
    return files[-1] if files else None


def already_covered(camera, now):
    """Workflow runs can overlap around the quarter hour marks, so a
    camera gets skipped when its slot already has a photo."""
    day_dir = PHOTO_ROOT / camera["name"] / now.strftime("%Y-%m-%d")
    if not day_dir.exists():
        return False
    slot = (now.hour * 60 + now.minute) // 15
    for existing in day_dir.glob(camera["name"] + "_*.jpg"):
        found = re.search(r"_(\d{2})(\d{2})_[A-Z]", existing.name)
        if found:
            minutes = int(found.group(1)) * 60 + int(found.group(2))
            if minutes // 15 == slot:
                return True
    return False


def capture(camera, last_chance=False):
    now = datetime.now(JUNEAU)
    day_dir = PHOTO_ROOT / camera["name"] / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    filename = "{}_{}.jpg".format(camera["name"], now.strftime("%Y-%m-%d_%H%M_%Z"))
    out_path = day_dir / filename

    if camera["kind"] == "image":
        reply = requests.get(
            camera["url"], headers={"User-Agent": BROWSER_UA}, timeout=60
        )
        reply.raise_for_status()
        if len(reply.content) < MIN_FILE_BYTES:
            raise RuntimeError("image came back empty or tiny")
        previous = latest_saved(camera)
        if previous and previous.read_bytes() == reply.content:
            log(f"{camera['name']}: source has not posted a new frame yet")
            return None
        out_path.write_bytes(reply.content)
        return out_path

    if camera["kind"] == "rtspme":
        address, referer = resolve_rtspme(camera["stream_id"])
        grab_frame(address, referer, camera["jpeg_quality"], out_path)
        return out_path

    try:
        address, referer = resolve_youtube(camera["url"])
        grab_frame(address, referer, camera["jpeg_quality"], out_path)
    except Exception:
        if not last_chance or not camera.get("thumbnail_fallback", True):
            raise
        video_id = re.search(r"[?&]v=([\w-]{11})", camera["url"]).group(1)
        youtube_live_thumbnail(video_id, out_path)
        log(f"{camera['name']}: stream was blocked, kept the live thumbnail instead")
    return out_path


def main():
    saved = 0
    for camera in CAMERAS:
        name = camera["name"]
        if already_covered(camera, datetime.now(JUNEAU)):
            log(f"{name}: this quarter hour already has a photo")
            saved += 1
            continue
        for attempt in range(1, ATTEMPTS + 1):
            try:
                out_path = capture(camera, last_chance=attempt == ATTEMPTS)
            except Exception as problem:
                log(f"{name}: attempt {attempt} of {ATTEMPTS} failed, {problem}")
                if attempt < ATTEMPTS:
                    time.sleep(RETRY_WAIT_SEC)
            else:
                if out_path is not None:
                    size_kb = out_path.stat().st_size // 1024
                    log(f"{name}: saved {out_path.name} ({size_kb} KB)")
                saved += 1
                break
        else:
            log(f"{name}: gave up after {ATTEMPTS} attempts")

    log(f"done, {saved} of {len(CAMERAS)} cameras saved")
    if saved == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
