"""
formats.py -- the export menu, and the ffmpeg arguments behind each entry.

Two things are worth saying about the shape of this file.

The presets are data, not a chain of ``if`` statements, because the list is
the thing most likely to grow and the encoder flags are the thing most
likely to be got subtly wrong.  Keeping them side by side means a new entry
is one tuple rather than an edit in four places.

And every preset knows which source codecs its container can carry
untouched.  That is what makes the fast/exact choice honest: fast mode
copies only when copying actually produces a file that opens, and says so
in the job's status line when it could not.

No Qt in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Quality:
    """The user's quality choices, in one object.

    ``height`` caps the stream picked off YouTube; ``crf`` and ``abr``
    only matter when something is actually being encoded.
    """
    height: int | None = None       # None means "best available"
    crf: int | None = None          # None means the preset's default
    abr: int = 192                  # kbit/s, lossy audio
    fps: int | None = None          # GIF only
    width: int | None = None        # GIF only


@dataclass
class Preset:
    key: str
    label: str
    ext: str
    kind: str                        # "video" | "audio" | "gif"
    video: object = None             # callable(Quality) -> list[str]
    audio: object = None
    container: list = field(default_factory=list)
    copy_video: tuple = ()           # source vcodec prefixes copyable as-is
    copy_audio: tuple = ()
    note: str = ""

    @property
    def has_video(self):
        return self.kind in ("video", "gif")

    @property
    def has_audio(self):
        return self.kind in ("video", "audio")

    def can_copy_video(self, vcodec):
        return (vcodec or "").lower().startswith(self.copy_video)

    def can_copy_audio(self, acodec):
        return (acodec or "").lower().startswith(self.copy_audio)


# --------------------------------------------------------------------------
# encoder argument builders
# --------------------------------------------------------------------------

def _h264(q):
    # veryfast rather than medium: this is a clipping tool, and the file
    # size difference on a two-minute clip is not worth doubling the wait.
    return ["-c:v", "libx264", "-preset", "veryfast",
            "-crf", str(q.crf if q.crf is not None else 18),
            "-pix_fmt", "yuv420p"]


def _h265(q):
    # hvc1 rather than the default hev1 tag, because QuickTime and every
    # Apple device refuse to open the latter.
    return ["-c:v", "libx265", "-preset", "medium",
            "-crf", str(q.crf if q.crf is not None else 24),
            "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]


def _vp9(q):
    return ["-c:v", "libvpx-vp9", "-b:v", "0",
            "-crf", str(q.crf if q.crf is not None else 31),
            "-row-mt", "1", "-pix_fmt", "yuv420p"]


def _prores(q):
    # Profile 3 is 422 HQ -- the one an NLE actually wants handed to it.
    return ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"]


def _aac(q):
    return ["-c:a", "aac", "-b:a", f"{q.abr}k"]


def _mp3(q):
    return ["-c:a", "libmp3lame", "-b:a", f"{q.abr}k"]


def _opus(q):
    return ["-c:a", "libopus", "-b:a", f"{q.abr}k"]


def _vorbis(q):
    return ["-c:a", "libvorbis", "-b:a", f"{q.abr}k"]


def _pcm16(q):
    return ["-c:a", "pcm_s16le"]


def _pcm24(q):
    return ["-c:a", "pcm_s24le"]


def _flac(q):
    return ["-c:a", "flac", "-compression_level", "5"]


FASTSTART = ["-movflags", "+faststart"]


# --------------------------------------------------------------------------
# the menu
# --------------------------------------------------------------------------

PRESETS = [
    Preset("mp4", "MP4 — H.264 / AAC", ".mp4", "video",
           video=_h264, audio=_aac, container=FASTSTART,
           copy_video=("avc1", "h264"), copy_audio=("mp4a", "aac"),
           note="Opens everywhere. The safe default."),
    Preset("mov", "MOV — H.264 / AAC", ".mov", "video",
           video=_h264, audio=_aac, container=FASTSTART,
           copy_video=("avc1", "h264"), copy_audio=("mp4a", "aac"),
           note="Same streams as MP4 in a QuickTime container."),
    Preset("mkv", "MKV — H.264 / AAC", ".mkv", "video",
           video=_h264, audio=_aac,
           copy_video=("avc1", "h264", "vp9", "vp09", "av01", "hev", "hvc"),
           copy_audio=("mp4a", "aac", "opus", "vorbis", "mp3"),
           note="Carries any codec, so fast mode almost never re-encodes."),
    Preset("mp4_hevc", "MP4 — H.265 / AAC", ".mp4", "video",
           video=_h265, audio=_aac, container=FASTSTART,
           copy_video=("hev", "hvc"), copy_audio=("mp4a", "aac"),
           note="Half the size of H.264, slower to encode."),
    Preset("webm", "WebM — VP9 / Opus", ".webm", "video",
           video=_vp9, audio=_opus,
           copy_video=("vp9", "vp09", "vp8", "av01"), copy_audio=("opus", "vorbis"),
           note="What YouTube already stores, so fast mode is a pure copy."),
    Preset("prores", "MOV — ProRes 422 HQ / PCM", ".mov", "video",
           video=_prores, audio=_pcm16,
           note="Big files, but the format an editor wants to cut with."),
    Preset("gif", "GIF — animated", ".gif", "gif",
           note="Two passes: a palette built from the clip, then the frames."),

    Preset("wav", "WAV — 16-bit PCM", ".wav", "audio", audio=_pcm16,
           note="Uncompressed. What a DAW wants."),
    Preset("wav24", "WAV — 24-bit PCM", ".wav", "audio", audio=_pcm24),
    Preset("mp3", "MP3", ".mp3", "audio", audio=_mp3,
           copy_audio=("mp3",)),
    Preset("m4a", "M4A — AAC", ".m4a", "audio", audio=_aac, container=FASTSTART,
           copy_audio=("mp4a", "aac"),
           note="YouTube's own audio codec, so fast mode copies it untouched."),
    Preset("flac", "FLAC", ".flac", "audio", audio=_flac,
           note="Lossless, but the source was lossy — this only preserves it."),
    Preset("opus", "Opus", ".opus", "audio", audio=_opus,
           copy_audio=("opus",)),
    Preset("ogg", "OGG — Vorbis", ".ogg", "audio", audio=_vorbis,
           copy_audio=("vorbis",)),
    Preset("aac", "AAC — raw ADTS", ".aac", "audio", audio=_aac,
           copy_audio=("mp4a", "aac")),
]

BY_KEY = {p.key: p for p in PRESETS}

VIDEO_KEYS = [p.key for p in PRESETS if p.kind in ("video", "gif")]
AUDIO_KEYS = [p.key for p in PRESETS if p.kind == "audio"]

#: Offered in the quality box.  "Best available" is None.
HEIGHT_CHOICES = (None, 2160, 1440, 1080, 720, 480, 360)
ABR_CHOICES = (320, 256, 192, 128, 96)


def get(key):
    try:
        return BY_KEY[key]
    except KeyError:
        raise KeyError(f"No such export format: {key!r}")


def output_args(preset, quality, source_vcodec="", source_acodec="", fast=False):
    """The encoder half of an ffmpeg command line.

    Returns ``(args, note)``.  The note is empty when the user got exactly
    what the mode promised, and otherwise says which track had to be
    re-encoded and why -- silence there would mean a "fast" export that
    quietly took four minutes with no explanation.
    """
    args = []
    notes = []

    if preset.has_video:
        if fast and preset.can_copy_video(source_vcodec):
            args += ["-c:v", "copy"]
        else:
            if fast and preset.video is not None:
                notes.append(f"video re-encoded ({source_vcodec or 'source'} "
                             f"cannot be copied into {preset.ext.lstrip('.')})")
            args += preset.video(quality)

    if preset.has_audio:
        if fast and preset.can_copy_audio(source_acodec):
            args += ["-c:a", "copy"]
        else:
            if fast and preset.audio is not None:
                notes.append(f"audio re-encoded ({source_acodec or 'source'} "
                             f"cannot be copied into {preset.ext.lstrip('.')})")
            args += preset.audio(quality)
    if not preset.has_video:
        # Belt and braces: the caller normally maps only the audio stream,
        # but an audio preset must never emit a video track even if a
        # cover-art stream sneaks through.
        args += ["-vn"]

    args += list(preset.container)
    return args, "; ".join(notes)


def describe(preset, quality, fast):
    """One line for the export panel, so the choice is legible before it runs."""
    bits = [preset.label]
    if preset.kind == "video":
        bits.append(f"{quality.height}p" if quality.height else "best available")
    elif preset.kind == "audio" and preset.audio in (_mp3, _aac, _opus, _vorbis):
        bits.append(f"{quality.abr} kbit/s")
    bits.append("keyframe-snapped copy" if fast else "frame-accurate")
    return " · ".join(bits)
