"""Streams that YouTube serves only as numbered pieces.

A broadcast that has just ended stays like this until YouTube finishes
processing it (``live_status == "post_live"``), which can take hours for a
long stream.  Instead of one file there are a couple of thousand five-second
pieces, each a small self-contained MP4 fragment addressed by ``&sq=N``.

Neither Qt nor ffmpeg can treat the first piece's address as the whole
video: they read a few seconds and then fail with "partial file" or
"Demuxing failed".  ffmpeg's HLS reader can stitch them, but its seeking
lands seconds off and sometimes stalls.  So this module does the stitching
itself: it reads the start time stamped inside each piece (a 16 KB range
request is enough), finds the pieces that cover a stretch of time, fetches
them in parallel and writes them end to end.  The result is an ordinary
fragmented MP4 that ffmpeg and Qt both read without complaint.
"""

from __future__ import annotations

import concurrent.futures
import math
import os
import struct
import threading
import time
import urllib.request

from .ffmpegtool import Cancelled

_HEAD_BYTES = 16 * 1024
_WORKERS = 6


def is_segmented(fmt):
    """True for a yt-dlp format that is only available as pieces."""
    return bool(fmt) and fmt.get("protocol") == "http_dash_segments" \
        and bool(fmt.get("fragments"))


# --------------------------------------------------------------------------
# reading the start time out of a piece
# --------------------------------------------------------------------------

def _boxes(data, start=0, end=None):
    end = len(data) if end is None else end
    i = start
    while i + 8 <= end:
        size, kind = struct.unpack(">I4s", data[i:i + 8])
        header = 8
        if size == 1:
            if i + 16 > end:
                return
            size = struct.unpack(">Q", data[i + 8:i + 16])[0]
            header = 16
        elif size == 0:
            size = end - i
        if size < header:
            return
        yield kind, i + header, min(end, i + size)
        i += size


def _find(data, path, start=0, end=None):
    for kind, body, stop in _boxes(data, start, end):
        if kind == path[0]:
            if len(path) == 1:
                return body, stop
            found = _find(data, path[1:], body, stop)
            if found:
                return found
    return None


def piece_start(data):
    """Seconds at which a piece begins, from its mdhd timescale and tfdt.

    Returns None when the header bytes do not hold both boxes.
    """
    mdhd = _find(data, [b"moov", b"trak", b"mdia", b"mdhd"])
    tfdt = _find(data, [b"moof", b"traf", b"tfdt"])
    if not mdhd or not tfdt:
        return None
    body = mdhd[0]
    if data[body] == 1:
        timescale = struct.unpack(">I", data[body + 20:body + 24])[0]
    else:
        timescale = struct.unpack(">I", data[body + 12:body + 16])[0]
    body = tfdt[0]
    if data[body] == 1:
        decode_time = struct.unpack(">Q", data[body + 4:body + 12])[0]
    else:
        decode_time = struct.unpack(">I", data[body + 4:body + 8])[0]
    if not timescale:
        return None
    return decode_time / timescale


# --------------------------------------------------------------------------
# one segmented stream
# --------------------------------------------------------------------------

class Segmented:
    """The pieces of one format, and where each one starts."""

    def __init__(self, fmt):
        base = fmt.get("fragment_base_url") or ""
        self.urls = [f.get("url") or (base + (f.get("path") or ""))
                     for f in fmt["fragments"]]
        self.headers = dict(fmt.get("http_headers") or {})
        self.step = float(fmt.get("target_duration") or 5.0)
        self.format_id = str(fmt.get("format_id") or "")
        self.head_time = None          # seconds YouTube says it has, if known
        self._starts = {}
        self._lock = threading.Lock()

    def __len__(self):
        return len(self.urls)

    # -- network --------------------------------------------------------

    def _get(self, index, head_only=False, timeout=30):
        headers = dict(self.headers)
        if head_only:
            headers["Range"] = f"bytes=0-{_HEAD_BYTES - 1}"
        last = None
        for attempt in range(4):
            try:
                request = urllib.request.Request(self.urls[index], headers=headers)
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    millis = response.headers.get("X-Head-Time-Millis")
                    if millis and millis.isdigit():
                        self.head_time = int(millis) / 1000.0
                    return response.read()
            except Exception as exc:          # network hiccups are common
                last = exc
                time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"Could not fetch part {index} of the stream: {last}")

    # -- timing ---------------------------------------------------------

    def start(self, index):
        """Seconds at which piece ``index`` begins."""
        index = max(0, min(len(self) - 1, int(index)))
        with self._lock:
            if index in self._starts:
                return self._starts[index]
        value = piece_start(self._get(index, head_only=True))
        if value is None:
            value = piece_start(self._get(index))
        if value is None:
            raise RuntimeError(f"Part {index} of the stream has no timestamp.")
        with self._lock:
            self._starts[index] = value
        return value

    def duration(self):
        """Length of the whole stream, as far as it can be known cheaply."""
        # YouTube's "head" time includes a piece it is still writing, which
        # cannot be fetched; the last listed piece plus one step is what can.
        last = self.start(len(self) - 1) + self.step
        if self.head_time and self.head_time < last:
            return self.head_time
        return last

    def index_for(self, seconds):
        """The piece that contains ``seconds``.

        Pieces are almost all ``step`` long, so a guess from the average is
        usually right first time; the loop corrects for the short pieces at
        the start of a broadcast and for any gaps where it dropped.
        """
        n = len(self)
        if n == 0:
            raise RuntimeError("The stream has no parts.")
        seconds = max(0.0, float(seconds))
        k = min(n - 1, int(seconds / self.step))
        for _ in range(40):
            here = self.start(k)
            if here > seconds and k > 0:
                k = max(0, k - max(1, math.ceil((here - seconds) / self.step)))
                continue
            if k + 1 < n:
                following = self.start(k + 1)
                if following <= seconds:
                    k = min(n - 1, k + max(1, int((seconds - following) / self.step) + 1))
                    continue
            return k
        return k

    # -- fetching -------------------------------------------------------

    def fetch(self, first, last, path, report=None, cancel=None):
        """Write pieces ``first``..``last`` end to end into ``path``."""
        first = max(0, first)
        last = min(len(self) - 1, last)
        indices = list(range(first, last + 1))
        total = len(indices)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        partial = path + ".part"
        done = 0
        pending = {}
        next_to_write = first
        with open(partial, "wb") as out, \
                concurrent.futures.ThreadPoolExecutor(_WORKERS) as pool:
            futures = {}
            queue = iter(indices)

            def submit():
                index = next(queue, None)
                if index is not None:
                    futures[pool.submit(self._get, index)] = index

            for _ in range(_WORKERS * 2):
                submit()
            while futures:
                if cancel is not None and cancel():
                    for f in futures:
                        f.cancel()
                    raise Cancelled()
                finished, _ = concurrent.futures.wait(
                    futures, timeout=0.25,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                for future in finished:
                    index = futures.pop(future)
                    pending[index] = future.result()
                    submit()
                while next_to_write in pending:
                    out.write(pending.pop(next_to_write))
                    next_to_write += 1
                    done += 1
                    if report is not None:
                        report(done / total, f"Part {done} of {total}")
        os.replace(partial, path)
        return path

    def fetch_span(self, start, end, path, report=None, cancel=None):
        """Fetch what covers ``start``..``end`` seconds.

        Returns ``(path, offset)``: the local file and the stream time at
        which it begins, so a seek of ``start - offset`` lands on ``start``.
        """
        first = self.index_for(start)
        last = self.index_for(max(start, end - 0.001))
        self.fetch(first, last, path, report=report, cancel=cancel)
        return path, self.start(first)


_cache = {}
_cache_lock = threading.Lock()


def for_format(fmt):
    """One shared :class:`Segmented` per format, so start times are reused."""
    if not is_segmented(fmt):
        return None
    key = (fmt.get("format_id"), (fmt["fragments"][0].get("url")
                                  or fmt["fragments"][0].get("path") or "")[:200])
    with _cache_lock:
        found = _cache.get(key)
        if found is None:
            found = _cache[key] = Segmented(fmt)
        return found
