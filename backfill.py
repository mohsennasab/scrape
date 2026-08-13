"""Pull hourly frames out of the glacier cam's live stream history.

YouTube keeps the rolling history of an active live stream, numbered
in fixed length segments. This walks that history back as far as it
reaches, grabs the segment closest to each top of the hour, and saves
one frame per hour into the same folders the regular capture uses.
Separate from the 15 minute capture, run it by hand from this folder,
naming the camera to walk (glacier cam when left out):

    python backfill.py all_cameras_grid

With --hourly it stays running, does one pass shortly after every top
of the hour, and pushes anything new to GitHub:

    python backfill.py mendenhall_glacier_cam --hourly

Already saved hours are skipped, so rerunning only fills gaps. How far
back it can reach depends on how much history YouTube keeps for the
stream, which swings between minutes and several hours, another reason
the hourly mode is worth leaving on.
"""

import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from yt_dlp import YoutubeDL

JUNEAU = ZoneInfo("America/Juneau")
PHOTO_ROOT = Path(__file__).resolve().parent / "photos"

STREAMS = {
    "mendenhall_glacier_cam": "https://www.youtube.com/watch?v=jJI5w_RVGtQ",
    "all_cameras_grid": "https://www.youtube.com/watch?v=ZlQLmBNLz-c",
    "rotating_single_view": "https://www.youtube.com/watch?v=sDAtRwK8oNE",
}
_names = [word for word in sys.argv[1:] if not word.startswith("--")]
CAMERA_NAME = _names[0] if _names else "mendenhall_glacier_cam"
VIDEO_URL = STREAMS[CAMERA_NAME]
HOURLY = "--hourly" in sys.argv
JPEG_QUALITY = 2
MAX_HOURS = 14 * 24

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
HEADERS = {"User-Agent": BROWSER_UA}


def log(message):
    stamp = datetime.now(JUNEAU).strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def playlist_address():
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "bestvideo/best",
        "js_runtimes": {"deno": {}, "node": {}},
    }
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(VIDEO_URL, download=False)
    return info["url"]


def read_playlist(address):
    """Returns the newest segment number, the segment length in
    seconds, the wall clock time of the newest segment, and a URL
    template with {sq} standing in for the segment number."""
    text = requests.get(address, headers=HEADERS, timeout=30).text

    first_seq = int(re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", text).group(1))
    durations = [float(d) for d in re.findall(r"#EXTINF:([\d.]+)", text)]
    if not durations:
        raise RuntimeError("playlist had no segments")
    seg_len = sum(durations) / len(durations)
    head_seq = first_seq + len(durations) - 1

    stamps = re.findall(r"#EXT-X-PROGRAM-DATE-TIME:(\S+)", text)
    if stamps:
        head_time = datetime.fromisoformat(stamps[-1].replace("Z", "+00:00"))
        stamped_at = text.count("#EXTINF", 0, text.rfind(stamps[-1]))
        head_time += timedelta(seconds=(len(durations) - 1 - stamped_at) * seg_len)
    else:
        head_time = datetime.now(timezone.utc)

    segment = None
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            segment = urljoin(address, line)
    if not segment or "/sq/" not in segment:
        raise RuntimeError("could not find a numbered segment in the playlist")
    template = re.sub(r"/sq/\d+/", "/sq/{sq}/", segment)

    return head_seq, seg_len, head_time, template


def segment_exists(template, seq):
    reply = requests.get(
        template.format(sq=seq),
        headers={**HEADERS, "Range": "bytes=0-0"},
        timeout=20,
    )
    return reply.status_code < 300


def earliest_segment(template, head_seq):
    if segment_exists(template, 0):
        return 0
    low, high = 0, head_seq
    while high - low > 1:
        middle = (low + high) // 2
        if segment_exists(template, middle):
            high = middle
        else:
            low = middle
    return high


def save_frame(template, seq, out_path):
    reply = requests.get(template.format(sq=seq), headers=HEADERS, timeout=60)
    reply.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as handle:
        handle.write(reply.content)
        seg_path = handle.name
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", seg_path,
                "-frames:v", "1",
                "-q:v", str(JPEG_QUALITY),
                str(out_path),
            ],
            check=True,
            timeout=120,
        )
    finally:
        Path(seg_path).unlink(missing_ok=True)


def push_photos():
    root = Path(__file__).resolve().parent
    steps = [
        ["git", "add", "photos"],
        ["git", "commit", "-m", f"Backfill for {CAMERA_NAME}"],
        ["git", "pull", "--rebase", "--autostash"],
        ["git", "push"],
    ]
    for step in steps:
        done = subprocess.run(step, cwd=root, capture_output=True, text=True)
        if done.returncode != 0:
            if step[1] == "commit":
                return
            log(f"git {step[1]} failed, {done.stderr.strip().splitlines()[-1:]}")
            return
    log("pushed to GitHub")


def main():
    log("resolving the stream")
    address = playlist_address()
    head_seq, seg_len, head_time, template = read_playlist(address)

    log("finding how far back the history reaches")
    start_seq = earliest_segment(template, head_seq)
    start_time = head_time - timedelta(seconds=(head_seq - start_seq) * seg_len)
    log(f"history reaches back to {start_time.astimezone(JUNEAU):%Y-%m-%d %H:%M %Z}")

    first_hour = start_time.replace(minute=0, second=0, microsecond=0)
    if first_hour < start_time:
        first_hour += timedelta(hours=1)
    floor = head_time - timedelta(hours=MAX_HOURS)
    if first_hour < floor:
        first_hour = floor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        log(f"limiting to the last {MAX_HOURS} hours, raise MAX_HOURS for more")

    saved = skipped = failed = 0
    hour = first_hour
    while hour <= head_time:
        local = hour.astimezone(JUNEAU)
        day_dir = PHOTO_ROOT / CAMERA_NAME / local.strftime("%Y-%m-%d")
        out_path = day_dir / "{}_{}.jpg".format(
            CAMERA_NAME, local.strftime("%Y-%m-%d_%H%M_%Z")
        )
        if out_path.exists():
            skipped += 1
        else:
            seq = head_seq - round((head_time - hour).total_seconds() / seg_len)
            seq = max(seq, start_seq)
            day_dir.mkdir(parents=True, exist_ok=True)
            try:
                save_frame(template, seq, out_path)
            except Exception as problem:
                log(f"{local:%Y-%m-%d %H:%M}: failed, {problem}")
                failed += 1
            else:
                log(f"{local:%Y-%m-%d %H:%M}: saved {out_path.name}")
                saved += 1
        hour += timedelta(hours=1)

    log(f"done, {saved} saved, {skipped} already there, {failed} failed")
    if saved == 0 and failed > 0 and not HOURLY:
        sys.exit(1)
    return saved


if __name__ == "__main__":
    if not HOURLY:
        main()
    else:
        while True:
            try:
                if main() > 0:
                    push_photos()
            except Exception as problem:
                log(f"pass failed, {problem}")
            coming = datetime.now(timezone.utc)
            coming = coming.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=1, seconds=90
            )
            log(f"next pass at {coming.astimezone(JUNEAU):%H:%M %Z}")
            time.sleep((coming - datetime.now(timezone.utc)).total_seconds())
