"""TubeClipper entry point for source runs and frozen builds."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import shlex
import sys
import tempfile


def _ensure_streams():
    """Windowed PyInstaller builds have no stdout or stderr."""
    import io
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, io.StringIO())


def selftest():
    """Exercise imports, bundled ffmpeg, probing, trimming, and encoding."""
    print("TubeClipper self-test")
    print("-" * 50)
    ok = True
    for name in ("PySide6.QtWidgets", "PySide6.QtMultimedia", "yt_dlp"):
        try:
            module = __import__(name)
            version = getattr(module, "__version__", "ok")
            print(f"  {name:<26} {version}")
        except Exception as exc:
            ok = False
            print(f"  {name:<26} FAILED  {exc}")

    from tubeclipper import engine, ffmpegtool, formats

    if not ffmpegtool.have_ffmpeg():
        ok = False
        print(f"  {'ffmpeg + ffprobe':<26} MISSING")
    else:
        print(f"  {'ffmpeg + ffprobe':<26} ok")
        print(f"    {ffmpegtool.version_string()}")

    if not ok:
        print("-" * 50)
        print("FAIL — a required component is missing.")
        return 1

    try:
        with tempfile.TemporaryDirectory(prefix="tubeclipper-selftest-") as tmp:
            sample = os.path.join(tmp, "sample.mp4")
            ffmpegtool.run([
                "-f", "lavfi", "-i",
                "testsrc2=size=320x180:rate=30:duration=4",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-y", sample,
            ])
            spec = engine.ExportSpec(
                title="Self-test",
                video_id="selftest",
                clip=engine.Clip(0.75, 2.25, "Self-test clip"),
                preset_key="mp4",
                quality=formats.Quality(height=180, crf=28),
                out_dir=tmp,
                local_path=sample,
                require_local=True,
            )
            result = engine.export(spec)
            data = ffmpegtool.probe(result.path)
            duration = float((data.get("format") or {}).get("duration") or 0.0)
            size = os.path.getsize(result.path)
            print(f"  {'local trim + encode':<26} {duration:.3f}s, {size:,} bytes")
            if not (1.25 <= duration <= 1.75 and size > 1000):
                raise RuntimeError("the exported test clip has the wrong duration or size")
    except Exception as exc:
        print(f"  {'media pipeline':<26} FAILED  {exc}")
        print("-" * 50)
        print("FAIL — the media pipeline is not working.")
        return 1

    print("-" * 50)
    print("PASS — this build is working.")
    return 0


def _parser():
    parser = argparse.ArgumentParser(
        description="Trim a YouTube video from the command line, or open the GUI.")
    parser.add_argument("url", nargs="?", help="YouTube URL or video id")
    parser.add_argument("--start", default="0", help="in point (seconds or HH:MM:SS)")
    parser.add_argument("--end", help="out point (seconds or HH:MM:SS)")
    parser.add_argument("--format", default="mp4", dest="preset_key",
                        help="export preset: mp4, mov, mkv, webm, wav, mp3, m4a…")
    parser.add_argument("--height", type=int, help="maximum video height")
    parser.add_argument("--bitrate", type=int, default=192,
                        help="lossy audio bitrate in kbit/s")
    parser.add_argument("--fast", action="store_true",
                        help="copy compatible streams; cut on a keyframe")
    parser.add_argument("--whole", action="store_true",
                        help="download the whole source before cutting")
    parser.add_argument("--cookies-from-browser", dest="cookies", metavar="BROWSER")
    parser.add_argument("--output", default=os.getcwd(), help="output folder")
    parser.add_argument("--name", default="", help="output name without extension")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve streams and print the ffmpeg arguments")
    parser.add_argument("--selftest", action="store_true")
    return parser


def cli(argv):
    from tubeclipper import engine, formats, source

    args = _parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.url:
        from tubeclipper.ui import main
        return main()

    start = source.parse_timecode(args.start)
    end = source.parse_timecode(args.end) if args.end else None
    if start is None or end is None or end <= start:
        _parser().error("--end must be after --start (timecodes such as 1:02:03 work)")
    try:
        preset = formats.get(args.preset_key)
    except KeyError as exc:
        _parser().error(str(exc))

    src = source.probe(args.url, args.cookies)
    spec = engine.ExportSpec(
        url=src.url,
        title=src.title,
        video_id=src.video_id,
        clip=engine.Clip(start, end, args.name),
        preset_key=preset.key,
        quality=formats.Quality(height=args.height, abr=args.bitrate),
        fast=bool(args.fast and preset.kind != "gif"),
        out_dir=args.output,
        out_name=args.name,
        info=src.info,
        cookies_from_browser=args.cookies or "",
    )
    if args.whole:
        spec.local_path = engine.download_whole(
            src.url, src.video_id, args.height,
            on_status=lambda text: print(text, file=sys.stderr),
            cookies_from_browser=args.cookies,
            audio_only=not preset.has_video)
        spec.require_local = True

    if args.dry_run:
        command, note, _video, _audio = engine.build_command(spec)
        print("ffmpeg " + shlex.join(command + ["OUTPUT".lower() + preset.ext]))
        if note:
            print("note:", note)
        return 0

    result = engine.export(
        spec,
        on_status=lambda text: print(text, file=sys.stderr),
        on_progress=lambda fraction, _text: print(
            f"\r{(fraction or 0.0):6.1%}", end="", file=sys.stderr, flush=True),
    )
    print(file=sys.stderr)
    print(result.path)
    if result.note:
        print("note:", result.note, file=sys.stderr)
    return 0


def run():
    multiprocessing.freeze_support()
    _ensure_streams()
    return cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(run())
