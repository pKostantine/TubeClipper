"""Preview for streams YouTube is still processing.

Such a stream exists only as five-second pieces (see segments.py), so
there is no address the player can open and seek in.  Instead the player
asks for a *window*: the pieces covering about a minute and a half from a
given time, fetched, joined, and muxed with the matching audio into one
small local file.  The player plays that, maps its position onto the real
timeline with the window's offset, fetches the next window while this one
plays, and fetches a fresh one when the user jumps somewhere else.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading

from . import ffmpegtool


class WindowedPreview:
    """Builds local stretches of a segmented stream for the player."""

    AHEAD = 90.0          # seconds of video per window
    BEHIND = 1.0          # a little before the target, so a seek lands inside
    KEEP = 3              # windows kept on disk (current, next, previous)

    def __init__(self, video, audio=None):
        self.video = video
        self.audio = audio
        self.folder = tempfile.mkdtemp(prefix="tubeclipper-preview-")
        self._count = 0
        self._total = None
        self._lock = threading.Lock()

    def total(self):
        """The real length, read from the stream's last piece."""
        if self._total is None:
            self._total = self.video.duration()
        return self._total

    def _name(self, prefix):
        with self._lock:
            self._count += 1
            number = self._count
        self._tidy(number)
        return os.path.join(self.folder, f"{prefix}{number}.mp4"), number

    def _tidy(self, newest):
        for name in os.listdir(self.folder):
            digits = "".join(ch for ch in name if ch.isdigit())
            if digits and int(digits) <= newest - self.KEEP:
                try:
                    os.remove(os.path.join(self.folder, name))
                except OSError:
                    pass

    def build(self, at, report=None, cancel=None):
        """Fetch the window around ``at``.  Returns ``(path, offset, end)``.

        ``offset`` is the stream time at which the file begins and ``end``
        the time at which it stops.
        """
        video = self.video
        last_index = len(video) - 1
        first = video.index_for(max(0.0, at - self.BEHIND))
        last = video.index_for(at + self.AHEAD)
        offset = video.start(first)
        end = video.start(last + 1) if last < last_index else self.total()

        def video_report(fraction, text):
            if report:
                report(fraction * (0.8 if self.audio else 0.95), text)

        video_path, number = self._name("v")
        video.fetch(first, last, video_path, report=video_report, cancel=cancel)
        if self.audio is None:
            return video_path, offset, end

        audio = self.audio
        a_first = audio.index_for(offset)
        a_last = audio.index_for(max(offset, end - 0.001))

        def audio_report(fraction, text):
            if report:
                report(0.8 + 0.15 * fraction, text)

        audio_path = os.path.join(self.folder, f"a{number}.mp4")
        audio.fetch(a_first, a_last, audio_path, report=audio_report, cancel=cancel)
        lead = audio.start(a_first) - offset

        out = os.path.join(self.folder, f"w{number}.mp4")
        # ffmpeg starts each input at zero; -itsoffset puts the audio back
        # where it was relative to the video, to the millisecond.
        ffmpegtool.run(["-i", video_path, "-itsoffset", f"{lead:.6f}",
                        "-i", audio_path, "-map", "0:v:0", "-map", "1:a:0",
                        "-t", f"{end - offset:.6f}",
                        "-c", "copy", "-movflags", "+faststart", "-y", out],
                       cancel=cancel)
        for path in (video_path, audio_path):
            try:
                os.remove(path)
            except OSError:
                pass
        if report:
            report(1.0, "")
        return out, offset, end

    def close(self):
        shutil.rmtree(self.folder, ignore_errors=True)
