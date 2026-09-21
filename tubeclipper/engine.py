"""
engine.py -- turning a link and two timestamps into a file.

The central decision in this module is that ffmpeg reads YouTube's media
URLs directly rather than yt-dlp downloading them first.  It is worth
spelling out why, because the obvious design is the other one.

Downloading first means fetching the whole video.  For the case this app
exists for -- a two-minute clip out of a six-hour livestream -- that is
several gigabytes and half an hour to produce ninety megabytes.  Pointing
ffmpeg at the stream URL instead lets an HTTP range request skip straight
to the part that matters, so the wait is proportional to the clip rather
than to the video.

That also happens to make the exact/fast distinction fall out of one flag.
``-ss`` placed before ``-i`` seeks by range request to the keyframe at or
before the requested time.  With ``-c copy`` the file starts at that
keyframe -- fast, lossless, and off by up to a group of pictures, which is
exactly what fast mode advertises.  When the output is being encoded,
ffmpeg keeps decoding past that keyframe and starts writing at the exact
timestamp, so the same flag gives a frame-accurate cut for the price of
decoding a few discarded frames.

The whole-video path is still here, because it is the right answer when
several clips come out of one video, or when a stream is slow enough that
being able to re-cut without re-fetching wins.

No Qt in this module.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field

from . import cache_dir, ffmpegtool, formats, source
from .ffmpegtool import Cancelled


@dataclass
class Clip:
    """One in/out pair on the timeline."""
    start: float = 0.0
    end: float = 0.0
    name: str = ""

    @property
    def duration(self):
        return max(0.0, self.end - self.start)

    def valid(self, limit=None):
        if self.duration <= 0.001:
            return False
        if limit and self.start >= limit:
            return False
        return True


@dataclass
class ExportSpec:
    """Everything one export needs to know."""
    url: str = ""
    title: str = ""
    video_id: str = ""
    clip: Clip = field(default_factory=Clip)
    preset_key: str = "mp4"
    quality: formats.Quality = field(default_factory=formats.Quality)
    fast: bool = False
    out_dir: str = ""
    out_name: str = ""            # without extension; filled in if empty
    local_path: str = ""          # a whole-video download to cut from
    require_local: bool = False    # fail rather than silently stream on download failure
    info: dict = field(default_factory=dict, repr=False)
    cookies_from_browser: str = ""

    @property
    def preset(self):
        return formats.get(self.preset_key)


@dataclass
class Result:
    path: str = ""
    note: str = ""
    duration: float = 0.0
    argv: list = field(default_factory=list)


# --------------------------------------------------------------------------
# naming
# --------------------------------------------------------------------------

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL",
             *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def safe_name(text, limit=110):
    """A file name Windows will accept, from a video title.

    Trailing dots and spaces are stripped as well as the illegal
    characters: Windows accepts them in an API call and then cannot open
    the file afterwards, which is a miserable way to lose an export.
    """
    text = _BAD.sub("_", text or "").strip()
    text = re.sub(r"\s+", " ", text).strip(" .")
    if len(text) > limit:
        text = text[:limit].rstrip(" .")
    if text.upper() in _RESERVED:
        text += "_"
    return text or "clip"


def _stamp(seconds):
    total = int(round(seconds))
    h, m, s = total // 3600, (total % 3600) // 60, total % 60
    return f"{h:d}h{m:02d}m{s:02d}s" if h else f"{m:d}m{s:02d}s"


def default_name(spec):
    """``Title 12m30s-14m05s`` -- sortable, readable, and unique per clip."""
    if spec.clip.name:
        base = safe_name(spec.clip.name)
    else:
        base = safe_name(spec.title or spec.video_id or "clip")
    return f"{base} {_stamp(spec.clip.start)}-{_stamp(spec.clip.end)}"


def unique_path(directory, name, ext):
    """Never overwrite: append (2), (3)… the way a browser does."""
    candidate = os.path.join(directory, name + ext)
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{name} ({n}){ext}")
        n += 1
    return candidate


# --------------------------------------------------------------------------
# resolving the inputs
# --------------------------------------------------------------------------

def local_codecs(path):
    """(vcodec, acodec) of a local file, empty strings when absent."""
    try:
        data = ffmpegtool.probe(path)
    except Exception:
        return "", ""
    vcodec = acodec = ""
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video" and not vcodec:
            vcodec = stream.get("codec_name") or ""
        elif stream.get("codec_type") == "audio" and not acodec:
            acodec = stream.get("codec_name") or ""
    return vcodec, acodec


def _info_for(spec):
    if spec.info:
        return spec.info
    src = source.probe(spec.url, spec.cookies_from_browser or None)
    spec.info = src.info
    if not spec.title:
        spec.title = src.title
    if not spec.video_id:
        spec.video_id = src.video_id
    return spec.info


def build_command(spec):
    """The ffmpeg argument list for one export, plus what it will produce.

    Split out from :func:`export` so it can be inspected -- the test suite
    checks the flags without touching the network, and ``--dry-run`` on
    the command line prints them.
    """
    preset = spec.preset
    quality = spec.quality
    clip = spec.clip
    audio_only = not preset.has_video

    args = []
    note = ""

    if spec.require_local and not (spec.local_path and os.path.exists(spec.local_path)):
        raise RuntimeError(
            "The whole-video download did not complete, so this clip was not exported.")

    if spec.local_path and os.path.exists(spec.local_path):
        vcodec, acodec = local_codecs(spec.local_path)
        args += ffmpegtool.input_args(spec.local_path, seek=clip.start)
        if preset.kind == "gif":
            maps = ["-map", "0:v:0"]
        else:
            maps = ["-map", "0:v:0", "-map", "0:a:0?"] if not audio_only else \
                   ["-map", "0:a:0"]
    else:
        info = _info_for(spec)
        selection = source.select(info, max_height=quality.height,
                                  audio_only=audio_only,
                                  prefer_compatible=spec.fast)
        note = selection.note
        if audio_only:
            stream = selection.audio
            vcodec, acodec = "", stream.acodec
            args += ffmpegtool.input_args(stream.url, stream.headers, clip.start)
            maps = ["-map", "0:a:0"]
        elif selection.audio is not None and preset.kind != "gif":
            v, a = selection.video, selection.audio
            vcodec, acodec = v.vcodec, a.acodec
            args += ffmpegtool.input_args(v.url, v.headers, clip.start)
            args += ffmpegtool.input_args(a.url, a.headers, clip.start)
            maps = ["-map", "0:v:0", "-map", "1:a:0"]
        else:
            v = selection.video
            vcodec, acodec = v.vcodec, v.acodec
            args += ffmpegtool.input_args(v.url, v.headers, clip.start)
            maps = ["-map", "0:v:0"] if preset.kind == "gif" else \
                   ["-map", "0:v:0", "-map", "0:a:0?"]

    args += ["-t", f"{clip.duration:.6f}"]
    args += maps

    if preset.kind == "gif":
        return args, note, vcodec, acodec        # the caller runs two passes

    encoder, encode_note = formats.output_args(
        preset, quality, vcodec, acodec, fast=spec.fast)
    args += encoder
    if encode_note:
        note = "; ".join(x for x in (note, encode_note) if x)

    if spec.fast:
        # A copy that begins at a keyframe carries that keyframe's original
        # timestamp; without this the first frames land at a negative time
        # and some players show a blank leader.
        args += ["-avoid_negative_ts", "make_zero"]

    title = spec.clip.name or spec.title
    if title:
        args += ["-metadata", f"title={title}"]

    return args, note, vcodec, acodec


# --------------------------------------------------------------------------
# exporting
# --------------------------------------------------------------------------

def export(spec, on_progress=None, on_status=None, cancel=None):
    """Cut one clip and write it.  Returns a :class:`Result`.

    ``on_progress(fraction, text)`` is called as ffmpeg reports; the
    fraction is against the clip's own length, which is why it is honest
    even on a six-hour source.
    """
    if not ffmpegtool.have_ffmpeg():
        raise ffmpegtool.FFmpegMissing("ffmpeg was not found.")

    preset = spec.preset
    clip = spec.clip
    if not clip.valid():
        raise ValueError("The in point is not before the out point.")

    out_dir = spec.out_dir or os.path.expanduser("~")
    os.makedirs(out_dir, exist_ok=True)
    name = spec.out_name or default_name(spec)
    out_path = unique_path(out_dir, name, preset.ext)

    if on_status:
        on_status("Resolving streams…")
    args, note, vcodec, acodec = build_command(spec)

    if on_status:
        on_status("Encoding…" if not spec.fast else "Copying…")

    try:
        if preset.kind == "gif":
            _gif(args, out_path, spec, on_progress, cancel)
        else:
            ffmpegtool.run(args + ["-y", out_path], duration=clip.duration,
                           on_progress=(lambda f, t: on_progress(f, t)) if on_progress else None,
                           cancel=cancel)
    except Exception:
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except OSError:
            pass
        raise

    return Result(path=out_path, note=note, duration=clip.duration,
                  argv=list(args))


def _gif(args, out_path, spec, on_progress, cancel):
    """Palette pass, then frames.

    A GIF is limited to 256 colours, and ffmpeg's default palette is a
    fixed web-safe one that turns any real footage into mud.  Building the
    palette from this clip's own frames costs one extra decode and is the
    whole difference between a usable GIF and a dithered mess.
    """
    q = spec.quality
    fps = q.fps or 15
    width = q.width or 480
    chain = f"fps={fps},scale={width}:-1:flags=lanczos"

    tmp = tempfile.mkdtemp(prefix="tubeclipper-gif-")
    palette = os.path.join(tmp, "palette.png")
    try:
        # build_command returns inputs followed by -t and stream maps.  A
        # second palette input must come before every output option, and a
        # GIF must not inherit the ordinary video's audio map.
        cut = args.index("-t")
        inputs = args[:cut]
        duration = args[cut:cut + 2]
        ffmpegtool.run(inputs + duration + [
                               "-map", "0:v:0", "-an",
                               "-vf", f"{chain},palettegen=stats_mode=diff",
                               "-y", palette],
                       duration=spec.clip.duration,
                       on_progress=(lambda f, t: on_progress(f * 0.5, "Building palette…"))
                       if on_progress else None,
                       cancel=cancel)
        ffmpegtool.run(inputs + ["-loop", "1", "-i", palette] + duration + [
                               "-filter_complex",
                               f"[0:v]{chain}[x];[x][1:v]paletteuse=dither=bayer[out]",
                               "-map", "[out]", "-an", "-loop", "0",
                               "-y", out_path],
                       duration=spec.clip.duration,
                       on_progress=(lambda f, t: on_progress(0.5 + f * 0.5, "Writing GIF…"))
                       if on_progress else None,
                       cancel=cancel)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# the whole-video path
# --------------------------------------------------------------------------

def cached_download(video_id, height, audio_only=False):
    """Path of an already-downloaded copy, or empty."""
    if not video_id:
        return ""
    media = "audio" if audio_only else "video"
    prefix = f"{video_id}.{media}.{height or 'best'}."
    directory = cache_dir()
    for entry in sorted(os.listdir(directory)):
        if entry.startswith(prefix) and not entry.endswith(".part"):
            return os.path.join(directory, entry)
    return ""


def download_whole(url, video_id, height=None, on_progress=None,
                   on_status=None, cancel=None, cookies_from_browser=None,
                   audio_only=False):
    """Fetch the entire video into the cache, and return its path.

    Worth it when several clips come out of one source: the download
    happens once and every cut after it is a local read.
    """
    existing = cached_download(video_id, height, audio_only=audio_only)
    if existing:
        if on_status:
            on_status("Already downloaded.")
        return existing

    import yt_dlp

    directory = cache_dir()
    media = "audio" if audio_only else "video"
    template = os.path.join(
        directory, f"{video_id}.{media}.{height or 'best'}.%(ext)s")
    if audio_only:
        fmt = "bestaudio/best"
    else:
        fmt = (f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
               if height else "bestvideo+bestaudio/best")

    state = {"path": ""}

    def hook(d):
        if cancel is not None and cancel():
            raise Cancelled()
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            if on_progress and total:
                on_progress(done / total, None)
            if on_status and d.get("_speed_str"):
                on_status(f"Downloading… {d.get('_percent_str', '').strip()} "
                          f"at {d['_speed_str'].strip()}")
        elif d.get("status") == "finished":
            state["path"] = d.get("filename") or ""
            if on_status:
                on_status("Merging…")

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": template,
        "format": fmt,
        "progress_hooks": [hook],
        "ffmpeg_location": os.path.dirname(ffmpegtool.tool_path("ffmpeg") or "") or None,
    }
    if not audio_only:
        opts["merge_output_format"] = "mkv"
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception:
        if cancel is not None and cancel():
            raise Cancelled()
        raise

    found = cached_download(video_id, height, audio_only=audio_only)
    return found or state["path"]


def cache_size():
    """Bytes currently held in the download cache."""
    total = 0
    for entry in os.scandir(cache_dir()):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def clear_cache():
    for entry in os.scandir(cache_dir()):
        try:
            if entry.is_file():
                os.remove(entry.path)
            else:
                shutil.rmtree(entry.path, ignore_errors=True)
        except OSError:
            pass


# --------------------------------------------------------------------------
# thumbnails for the timeline
# --------------------------------------------------------------------------

def grab_frames(url, times, out_dir, headers=None, width=160, cancel=None):
    """One JPEG per timestamp, for the filmstrip under the player.

    Each frame is its own ffmpeg run with ``-ss`` before ``-i``: a single
    run with a select filter would have to decode everything between the
    frames, which on a long video is minutes of work for a strip of
    thumbnails nobody is waiting on.
    """
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for index, t in enumerate(times):
        if cancel is not None and cancel():
            break
        path = os.path.join(out_dir, f"thumb_{index:04d}.jpg")
        if os.path.exists(path):
            made.append((t, path))
            continue
        args = ffmpegtool.input_args(url, headers, seek=max(0.0, t))
        args += ["-frames:v", "1", "-vf", f"scale={width}:-2",
                 "-q:v", "5", "-y", path]
        try:
            ffmpegtool.run(args)
            made.append((t, path))
        except Cancelled:
            break
        except Exception:
            continue
    return made
