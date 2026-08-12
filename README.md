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

To run a capture by hand you need Python 3.11 or newer and ffmpeg:

```
pip install -r requirements.txt
python capture.py
```
