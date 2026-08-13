# Juneau flood cameras

Automatic snapshots from cameras watching the Mendenhall River and
Suicide Basin during the 2026 glacial lake outburst flood in Juneau,
Alaska.

A GitHub Actions job grabs one frame from each camera every 15 minutes
and commits the photos to this repo. Nothing runs on a personal
machine, so the archive keeps growing on its own.

## Cameras

| Folder | Source | What it shows |
| --- | --- | --- |
| `photos/mendenhall_river_cam` | [rtsp.me](https://rtsp.me/embed/3nNBGQsb) | Fixed view of the river, 2880 x 1620 |
| `photos/all_cameras_grid` | [YouTube](https://www.youtube.com/live/ZlQLmBNLz-c) | Grid with all neighborhood cameras, 1080p |
| `photos/rotating_single_view` | [YouTube](https://www.youtube.com/live/sDAtRwK8oNE) | One full screen camera at a time, rotating, 1080p |
| `photos/mendenhall_glacier_cam` | [YouTube](https://www.youtube.com/watch?v=jJI5w_RVGtQ) | Mendenhall Glacier and Mountain Goat Cam from EXPLORE.org, 1080p |
| `photos/usgs_suicide_basin` | [USGS](https://apps.usgs.gov/hivis/camera/AK_Glacial_Lake_near_Nugget_LOOKING_UPSTREAM_GLACIER_VIEW) | Inside Suicide Basin, the source of the flood, posted hourly at 1280 x 720 |
| `photos/usgs_basin_spillway` | [USGS](https://apps.usgs.gov/hivis/camera/AK_Glacial_Lake_SPILLWAY_VIEW_Mendenhall) | The spillway where the basin drains over the glacier, hourly |
| `photos/usgs_spillway_downstream` | [USGS](https://apps.usgs.gov/hivis/camera/AK_Suicide_Basin_Spillway_Downstream_View) | Looking downstream from the spillway, hourly |

The river streams are run by Juneau Flood Solution Advocates, the
glacier cam by EXPLORE.org, and the basin cameras by USGS. The USGS
cameras publish one image an hour, so their folders get one photo per
update instead of four duplicates.

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
others.

GitHub fires cron schedules for small repos far less often than asked,
sometimes only once an hour. To keep a real 15 minute cadence each run
stays alive for almost three hours, shooting on every quarter hour and
pushing as it goes, while queued runs take over the moment a window
ends. A guard skips any quarter hour that already has its photo, so
overlapping runs never double up. Timestamps can still drift a few
minutes around the quarter hour marks.

## YouTube quality on GitHub

YouTube refuses stream requests coming from shared cloud machines like
the ones GitHub Actions runs on. When that happens the two river
cameras fall back to the official live thumbnail, which refreshes every
minute or two but tops out at 1280 x 720. The glacier cam cannot use
that trick because its channel shows a promotional still instead of a
live thumbnail, so it only saves a photo when the stream itself is
reachable. The rtsp.me camera is not affected and always saves at its
full 2880 x 1620.

To get the YouTube cameras at their full 1080p from GitHub, hand the
job a set of browser cookies:

1. Open a private browser window and log in to youtube.com, ideally
   with a spare account rather than your main one
2. Export cookies with an extension such as Get cookies.txt LOCALLY
3. Close the private window without logging out
4. In this repo go to Settings, then Secrets and variables, then
   Actions, and set a secret named `YT_COOKIES` to the whole file

Handle the export like a one way ticket. YouTube treats a cookie set
that shows up from more than one place as stolen and kills it within
minutes, so paste the export straight into the secret without testing
it anywhere first, and never reuse that browser session. After the
first run the job keeps its own living copy of the session between
runs, which is what lets a single export last. If the chain ever
breaks the job simply drops back to thumbnails until a fresh export
replaces the secret, so nothing breaks in the meantime.

To run a capture by hand you need Python 3.11 or newer and ffmpeg:

```
pip install -r requirements.txt
python capture.py
```

## Reaching back into a stream

`backfill.py` walks the history YouTube keeps for a live stream and
saves one frame per hour into the same folders, skipping hours that
already have a photo:

```
python backfill.py all_cameras_grid
```

How far back it reaches is up to YouTube and varies a lot by stream.
The grid stream keeps a few hours, while the glacier and rotating
streams keep only minutes, so there is nothing to walk there.
