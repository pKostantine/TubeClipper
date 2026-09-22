"""
source.py -- what YouTube will tell us about a link, and where the media is.

yt-dlp does the hard part: working out which of the dozen streams behind a
watch page are real, deciphering the throttling parameter, and handing back
URLs that an ordinary HTTP client can read.  This module is the thin,
opinionated layer on top -- pick a video stream, pick an audio stream, and
say plainly what was chosen, because "best" means different things when the
next step is a re-encode than when it is a stream copy.

Nothing here downloads media.  No Qt either.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Preference order for a stream copy into an MP4 or MOV container.  H.264
# and AAC are the only pair every player and every NLE opens without
# argument, so fast mode asks for them by name even when VP9 would be
# smaller -- a smaller file you have to re-encode to use is not faster.
H264 = ("avc1", "h264")
AAC = ("mp4a", "aac")


class SourceError(RuntimeError):
    """The link could not be read."""


def _ytdlp():
    try:
        import yt_dlp
    except ImportError as exc:                     # pragma: no cover
        raise SourceError(
            "yt-dlp is not installed.  pip install yt-dlp") from exc
    return yt_dlp


@dataclass
class Stream:
    """One chosen media stream, ready to hand to ffmpeg."""
    url: str = ""
    headers: dict = field(default_factory=dict)
    format_id: str = ""
    vcodec: str = "none"
    acodec: str = "none"
    height: int = 0
    fps: float = 0.0
    abr: float = 0.0
    ext: str = ""

    @property
    def has_video(self):
        return bool(self.vcodec) and self.vcodec != "none"

    @property
    def has_audio(self):
        return bool(self.acodec) and self.acodec != "none"


@dataclass
class Selection:
    """The one or two streams an export will read."""
    video: Stream | None = None
    audio: Stream | None = None
    note: str = ""

    @property
    def progressive(self):
        """True when a single stream carries both tracks."""
        return (self.video is not None and self.audio is None
                and self.video.has_audio)


@dataclass
class Source:
    """Everything the window needs to know about a link."""
    url: str = ""
    video_id: str = ""
    title: str = ""
    uploader: str = ""
    duration: float = 0.0
    thumbnail: str = ""
    is_live: bool = False
    was_live: bool = False
    heights: tuple = ()
    fps: float = 0.0
    upload_date: str = ""
    info: dict = field(default_factory=dict, repr=False)

    @property
    def display_duration(self):
        return format_timecode(self.duration)


# --------------------------------------------------------------------------
# reading a link
# --------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+", re.I)


def looks_like_url(text):
    text = (text or "").strip()
    if not text:
        return False
    if _URL_RE.fullmatch(text):
        return True
    # A bare 11-character video id is a link as far as the user is concerned.
    return bool(re.fullmatch(r"[\w-]{11}", text))


def normalise(text):
    """Accept a bare video id or a URL with junk around it."""
    text = (text or "").strip().strip("<>\"'")
    if re.fullmatch(r"[\w-]{11}", text):
        return f"https://www.youtube.com/watch?v={text}"
    return text


def probe(url, cookies_from_browser=None, on_log=None):
    """Read a link's metadata without downloading anything.

    ``cookies_from_browser`` is passed through to yt-dlp for the videos
    that will not talk to a signed-out client -- age-gated ones, mostly,
    and members-only streams.
    """
    yt_dlp = _ytdlp()
    url = normalise(url)

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "extract_flat": False,
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if on_log:
        opts["logger"] = _Logger(on_log)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise SourceError(_readable(exc)) from exc

    if not info:
        raise SourceError("Nothing came back for that link.")
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise SourceError("That link is a playlist with nothing in it.")
        info = entries[0]

    return from_info(info, url)


def from_info(info, url=""):
    heights = sorted({f.get("height") for f in info.get("formats") or []
                      if f.get("height")}, reverse=True)
    fps = 0.0
    for f in info.get("formats") or []:
        if f.get("fps"):
            fps = max(fps, float(f["fps"]))
    return Source(
        url=info.get("webpage_url") or url,
        video_id=info.get("id") or "",
        title=info.get("title") or "(untitled)",
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=float(info.get("duration") or 0.0),
        thumbnail=info.get("thumbnail") or "",
        is_live=bool(info.get("is_live")),
        was_live=bool(info.get("was_live")),
        heights=tuple(heights),
        fps=fps,
        upload_date=info.get("upload_date") or "",
        info=info,
    )


class _Logger:
    def __init__(self, sink):
        self.sink = sink

    def debug(self, msg):
        if not msg.startswith("[debug]"):
            self.sink(msg)

    def info(self, msg):
        self.sink(msg)

    def warning(self, msg):
        self.sink(msg)

    def error(self, msg):
        self.sink(msg)


def _readable(exc):
    """Trim yt-dlp's prefixes off an error before it reaches a dialog."""
    text = str(exc)
    text = re.sub(r"^ERROR:\s*", "", text)
    text = re.sub(r"\[[^\]]+\]\s*[\w-]+:\s*", "", text, count=1)
    return text.strip() or "The link could not be read."


# --------------------------------------------------------------------------
# choosing streams
# --------------------------------------------------------------------------

def _usable(formats):
    return [f for f in (formats or []) if f.get("url")]


def _score_video(f, prefer_h264):
    """Rank a video-only format.  Higher is better."""
    codec = (f.get("vcodec") or "").lower()
    compat = 1 if codec.startswith(H264) else 0
    return (
        compat if prefer_h264 else 0,
        f.get("height") or 0,
        f.get("fps") or 0,
        f.get("tbr") or 0,
    )


def _score_audio(f, prefer_aac):
    codec = (f.get("acodec") or "").lower()
    compat = 1 if codec.startswith(AAC) else 0
    return (
        compat if prefer_aac else 0,
        f.get("abr") or f.get("tbr") or 0,
    )


def _stream(f):
    return Stream(
        url=f.get("url", ""),
        headers=dict(f.get("http_headers") or {}),
        format_id=str(f.get("format_id") or ""),
        vcodec=(f.get("vcodec") or "none"),
        acodec=(f.get("acodec") or "none"),
        height=int(f.get("height") or 0),
        fps=float(f.get("fps") or 0.0),
        abr=float(f.get("abr") or f.get("tbr") or 0.0),
        ext=f.get("ext") or "",
    )


def select(info, max_height=None, audio_only=False, prefer_compatible=False):
    """Pick the streams for an export.

    ``prefer_compatible`` biases towards H.264 and AAC, which is what fast
    mode needs: a VP9 stream cannot be copied into an MP4 that anything
    else will open, so choosing it would silently force the re-encode the
    user asked to avoid.  In exact mode the codec is about to be replaced
    anyway, so resolution wins instead.
    """
    formats = _usable(info.get("formats"))
    if not formats:
        raise SourceError("That video exposed no playable streams.")

    audio_pool = [f for f in formats
                  if (f.get("acodec") or "none") != "none"
                  and (f.get("vcodec") or "none") == "none"]
    video_pool = [f for f in formats
                  if (f.get("vcodec") or "none") != "none"
                  and (f.get("acodec") or "none") == "none"]
    muxed_pool = [f for f in formats
                  if (f.get("vcodec") or "none") != "none"
                  and (f.get("acodec") or "none") != "none"]

    note = ""

    if audio_only:
        pool = audio_pool or muxed_pool
        if not pool:
            raise SourceError("That video exposed no audio stream.")
        best = max(pool, key=lambda f: _score_audio(f, prefer_compatible))
        return Selection(audio=_stream(best), note=note)

    if max_height:
        capped = [f for f in video_pool if (f.get("height") or 0) <= max_height]
        if capped:
            video_pool = capped
        elif video_pool:
            note = "No stream at or below that height; used the smallest there was."
            smallest = min(f.get("height") or 0 for f in video_pool)
            video_pool = [f for f in video_pool
                          if (f.get("height") or 0) == smallest]

    if video_pool and audio_pool:
        video = max(video_pool, key=lambda f: _score_video(f, prefer_compatible))
        audio = max(audio_pool, key=lambda f: _score_audio(f, prefer_compatible))
        return Selection(video=_stream(video), audio=_stream(audio), note=note)

    # Live HLS and a few older uploads only offer muxed streams.
    if muxed_pool:
        pool = muxed_pool
        if max_height:
            capped = [f for f in pool if (f.get("height") or 0) <= max_height]
            pool = capped or pool
        best = max(pool, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
        return Selection(video=_stream(best),
                         note=note or "Only a combined stream was available.")

    raise SourceError("That video exposed no video stream.")


def preview_stream(info, max_height=720):
    """Pick preview media, pairing adaptive video and audio when needed.

    A combined stream remains the simplest and most reliable preview.  Modern
    YouTube uploads often expose only separate adaptive streams, though, so in
    that case return both tracks for the UI to play in sync.  H.264 and AAC are
    preferred because Qt Multimedia supports them consistently on Windows and
    macOS.
    """
    formats = _usable(info.get("formats"))
    muxed = [f for f in formats
             if (f.get("vcodec") or "none") != "none"
             and (f.get("acodec") or "none") != "none"]
    if muxed:
        capped = [f for f in muxed if (f.get("height") or 0) <= max_height]
        if capped:
            pool = capped
        else:
            smallest = min(f.get("height") or 0 for f in muxed)
            pool = [f for f in muxed if (f.get("height") or 0) == smallest]

        def muxed_score(f):
            video_codec = (f.get("vcodec") or "").lower()
            audio_codec = (f.get("acodec") or "").lower()
            compatible = (int(video_codec.startswith(H264))
                          + int(audio_codec.startswith(AAC)))
            return (compatible, f.get("height") or 0, f.get("tbr") or 0)

        best = max(pool, key=muxed_score)
        return Selection(video=_stream(best))

    video_only = [f for f in formats
                  if (f.get("vcodec") or "none") != "none"
                  and (f.get("acodec") or "none") == "none"]
    audio_only = [f for f in formats
                  if (f.get("acodec") or "none") != "none"
                  and (f.get("vcodec") or "none") == "none"]
    if video_only:
        capped = [f for f in video_only if (f.get("height") or 0) <= max_height]
        pool = capped or video_only
        video = max(pool, key=lambda f: _score_video(f, True))
        if audio_only:
            audio = max(audio_only, key=lambda f: _score_audio(f, True))
            return Selection(video=_stream(video), audio=_stream(audio))
        return Selection(
            video=_stream(video),
            note="Preview is silent because this source has no audio stream.")

    raise SourceError("Nothing playable to preview.")


# --------------------------------------------------------------------------
# time formatting, shared by everything that shows a timecode
# --------------------------------------------------------------------------

def format_timecode(seconds, millis=True):
    """HH:MM:SS.mmm, with the hours dropped when they are zero."""
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        seconds = 0.0
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole = seconds % 60
    if millis:
        body = f"{minutes:02d}:{whole:06.3f}"
    else:
        body = f"{minutes:02d}:{int(whole):02d}"
    if hours:
        return f"{sign}{hours:d}:{body}"
    return f"{sign}{body}"


_TC_RE = re.compile(r"^\s*(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)\s*$")


def parse_timecode(text):
    """Read 90, 1:30, 1:30.5 or 1:02:03.250 as seconds.  None if unreadable."""
    match = _TC_RE.match(text or "")
    if not match:
        return None
    a, b, c = match.groups()
    parts = [p for p in (a, b) if p is not None]
    seconds = float(c)
    if len(parts) == 1:
        seconds += int(parts[0]) * 60
    elif len(parts) == 2:
        seconds += int(parts[0]) * 3600 + int(parts[1]) * 60
    return seconds
