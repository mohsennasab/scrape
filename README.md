# Juneau flood cameras

Automatic snapshots from three live streams watching the Mendenhall River
during the 2026 glacial lake outburst flood in Juneau, Alaska.

A GitHub Actions job wakes up every 15 minutes, grabs one frame from each
stream, and commits the photos to this repo. Nothing runs on a personal
machine, so the archive keeps growing on its own.

## Cameras

| Folder | Source | What it shows |
| --- | --- | --- |
| `photos/mendenhall_river_cam` | [rtsp.me](https://rtsp.me/embed/3nNBGQsb) | Fixed view of the river, 2880 x 1620 |
| `photos/all_cameras_grid` | [YouTube](https://www.youtube.com/live/ZlQLmBNLz-c) | Grid with all neighborhood cameras, 1080p |
| `photos/rotating_single_view` | [YouTube](https://www.youtube.com/live/sDAtRwK8oNE) | One full screen camera at a time, rotating, 1080p |

The two YouTube streams are run by Juneau Flood Solution Advocates.

## File naming

```
photos/<camera>/<date>/<camera>_<date>_<time>_<zone>.jpg
```

Times are Juneau local time. A file called
`all_cameras_grid_2026-08-12_1430_AKDT.jpg` was taken at 2:30 pm in Juneau.

## Notes

Frames are saved as high quality JPEGs straight from the stream with no
resizing, so each photo keeps the full resolution of its source. Every
camera has its own retry loop and one stream going down never stops the
other two. GitHub sometimes starts scheduled jobs a few minutes late,
which is why timestamps can drift a little around the quarter hour marks.

## YouTube quality on GitHub

YouTube refuses stream requests coming from shared cloud machines like
the ones GitHub Actions runs on. When that happens the two YouTube
cameras fall back to the official live thumbnail, which refreshes every
minute or two but tops out at 1280 x 720. The rtsp.me camera is not
affected and always saves at its full 2880 x 1620.

To get the YouTube cameras at their full 1080p from GitHub, hand the
job a set of browser cookies:

1. Open a private browser window and log in to youtube.com, ideally
   with a spare account rather than your main one
2. Export cookies with an extension such as Get cookies.txt LOCALLY
3. Close the private window without logging out
4. In this repo go to Settings, then Secrets and variables, then
   Actions, and add a secret named `YT_COOKIES` with the whole file as
   its value

The job picks the secret up on its next run. No other change is needed.
If the cookies ever expire the job simply drops back to thumbnails, so
nothing breaks in the meantime.

To run a capture by hand you need Python 3.11 or newer and ffmpeg:

```
pip install -r requirements.txt
python capture.py
```
