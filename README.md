# TubeClipper

TubeClipper turns a YouTube video or past livestream into exactly the clip
you need. Paste a link, preview and scrub the video, set frame-level in and
out points, then export video, audio, or an animated GIF.

The Windows build is the primary target. A macOS PyInstaller configuration is
included and must be built on a Mac.

## Features

- Embedded video preview with play/pause, variable speed, frame stepping,
  ten-second jumps, volume, and keyboard transport controls.
- Zoomable filmstrip timeline with draggable in/out handles and timecode entry.
- Multiple named clips from one source and a serial batch-export queue.
- Exact cuts that re-encode from the requested frame, or fast lossless cuts
  that snap to the previous keyframe when the container supports stream copy.
- Stream only the requested range, or download the complete source once before
  exporting several clips.
- Resolution caps from 360p through 4K and audio bitrate choices.
- Browser-cookie access for age-restricted or signed-in videos.
- A Qt-free engine that can be tested or used from the command line.

## Export formats

Video:

- MP4 (H.264/AAC)
- MOV (H.264/AAC)
- MKV (H.264/AAC)
- MP4 (H.265/AAC)
- WebM (VP9/Opus)
- MOV (ProRes 422 HQ/PCM)
- Animated GIF

Audio:

- WAV, 16-bit or 24-bit PCM
- MP3
- M4A/AAC
- FLAC
- Opus
- OGG/Vorbis
- Raw AAC

## Run from source on Windows

Double-click `run_dev.bat`. The first run creates `.venv`, installs the Python
packages, regenerates the app icons from `logo.png`, and launches TubeClipper.

Or run it manually with Python 3.10 or newer:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe TubeClipper.py
```

If ffmpeg is not on the machine, TubeClipper offers to download a private copy
into the current user's app-data folder. A built Windows release includes
ffmpeg and ffprobe and does not need that download.

## Basic workflow

1. Paste a YouTube URL (or an 11-character video id) and click **Load**.
2. Scrub the player or timeline to the beginning and press **I**.
3. Move to the end and press **O**. Exact timecodes can also be typed below
   the timeline.
4. Click **Add clip** to keep the selection and mark more moments, or export
   the current selection immediately.
5. Choose Video or Audio only, a format, quality, trim mode, and fetch mode.
6. Export the selection or every saved clip. Double-click a completed queue
   row to reveal its output folder.

Fast mode is only a true stream copy when the selected source codec fits the
chosen container. If one stream must be encoded for compatibility, the queue
records that fact instead of silently pretending the job was lossless.

## Keyboard shortcuts

| Key | Action |
|---|---|
| Space | Play / pause |
| I / O | Set in / out at the playhead |
| Ctrl+K | Add the selection as a clip |
| Left / Right | Step one frame |
| Shift+Left / Shift+Right | Step one second |
| J / K / L | Back five seconds / pause / forward five seconds |
| F / Shift+F | Fit the clip / whole source on the timeline |
| Ctrl+E | Export current selection |
| Ctrl+Shift+E | Export every saved clip |
| Ctrl+L | Focus the URL box |
| Ctrl++ / Ctrl+- / Ctrl+0 | Scale / reset the interface |

## Tests

After the development environment exists, run `run_tests.bat` on Windows or
`./run_tests.sh` on macOS/Linux. The suites verify stream selection, ffmpeg
command construction, every format preset, cache separation, filename safety,
timeline/clip behavior, and the main window in Qt's offscreen mode.

The distributable also has an offline media-pipeline self-test:

```bat
TubeClipper-check.exe --selftest
```

It creates a synthetic video, trims and encodes it through the shipped engine,
then probes the result. It does not contact YouTube.

## Build Windows

```bat
build.bat
```

This creates an isolated build environment, installs dependencies, generates
icons, bundles ffmpeg/ffprobe, runs both test suites, freezes the program, and
runs the frozen self-test. The portable result is:

```text
dist\TubeClipper\TubeClipper.exe
```

To create a normal per-user installer, install Inno Setup 6 and run:

```bat
make_installer.bat
```

The result is `dist\TubeClipper-Setup-<version>.exe`. It includes Python,
PySide6, yt-dlp, ffmpeg, and ffprobe and does not require administrator access.

## Build macOS

On a Mac with Python 3.10+ and ffmpeg installed through Homebrew on the build
machine:

```sh
./build.sh
./make_dmg.sh
```

This creates `dist/TubeClipper.app` and
`dist/TubeClipper-<version>-macOS-<architecture>.dmg`. ffmpeg and ffprobe are
bundled inside the app, so the destination Mac does not need Homebrew.

The GitHub Actions workflow in `.github/workflows/macos-release.yml` builds
native Apple Silicon (`arm64`) and Intel (`x86_64`) DMGs. It can be run
manually from the Actions page to download workflow artifacts. Pushing a
version tag builds both installers, creates the matching GitHub Release if
needed, and attaches both DMGs:

```sh
git tag v1.0.0
git push origin v1.0.0
```

The included build is ad-hoc signed, not Apple-notarized, so another Mac may
need the Control-click → Open flow on first launch.

## Command line

With the dependencies installed, TubeClipper can export without opening the
window:

```sh
python TubeClipper.py URL --start 1:20 --end 2:05 --format mp4 --height 1080
python TubeClipper.py URL --start 30 --end 90 --format mp3 --bitrate 192
python TubeClipper.py URL --start 0 --end 10 --format webm --fast --dry-run
```

Use `--cookies-from-browser chrome` (or `edge`, `firefox`, etc.) for a video
that needs a signed-in session, and `--whole` to cache the complete source
before cutting.

## Project layout

```text
TubeClipper.py               GUI/CLI/frozen-build entry point
tubeclipper/source.py        yt-dlp metadata and stream selection
tubeclipper/engine.py        trimming, downloads, caching, thumbnails
tubeclipper/formats.py       export presets and encoder arguments
tubeclipper/ffmpegtool.py    ffmpeg discovery, download, and progress
tubeclipper/player.py        embedded Qt media player
tubeclipper/timeline.py      zoomable filmstrip and range handles
tubeclipper/jobs.py          background tasks and serial export queue
tubeclipper/ui.py            main window and dialogs
tests/                       engine and headless UI tests
tools/                       icons, ffmpeg fetch, and version helpers
installer/                   Inno Setup definition
```

Only download and export media you have permission to use, and follow the
source platform's terms and applicable copyright law.
