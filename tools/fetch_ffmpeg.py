"""Put ffmpeg.exe and ffprobe.exe in the project for a Windows build."""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tubeclipper import ffmpegtool


def copy_tools(source_dir, destination):
    os.makedirs(destination, exist_ok=True)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        source = os.path.join(source_dir, name)
        if not os.path.exists(source):
            return False
        target = os.path.join(destination, name)
        if os.path.abspath(source) != os.path.abspath(target):
            shutil.copy2(source, target)
    return True


def main():
    if not sys.platform.startswith("win"):
        print("fetch_ffmpeg.py is only used by the Windows build.")
        return 0
    destination = os.path.join(ROOT, "ffmpeg")
    if copy_tools(destination, destination):
        print("  bundled ffmpeg is already present")
        return 0

    ffmpeg = ffmpegtool.tool_path("ffmpeg")
    ffprobe = ffmpegtool.tool_path("ffprobe")
    if ffmpeg and ffprobe and os.path.dirname(ffmpeg) == os.path.dirname(ffprobe):
        if copy_tools(os.path.dirname(ffmpeg), destination):
            print(f"  copied ffmpeg from {os.path.dirname(ffmpeg)}")
            return 0

    directory = ffmpegtool.install_ffmpeg(
        on_progress=lambda fraction, text: print(f"  {text or f'{fraction:.0%}'}"))
    if not copy_tools(directory, destination):
        print("fetch_ffmpeg: the downloaded tools are incomplete", file=sys.stderr)
        return 1
    print(f"  stored ffmpeg in {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
