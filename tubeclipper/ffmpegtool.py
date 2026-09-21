"""
ffmpegtool.py -- finding ffmpeg, running it, and reading its progress.

Everything that shells out to ffmpeg goes through here, for three reasons.

One, discovery is genuinely fiddly: a frozen build carries its own copy,
a source checkout usually wants the one on PATH, and a machine with
neither should be able to fetch one without the user going hunting.

Two, ffmpeg's normal output is a status line rewritten with carriage
returns, which is unparseable in any robust way.  ``-progress pipe:1``
emits key=value lines instead, and that is what the progress bars read.

Three, on Windows every subprocess without CREATE_NO_WINDOW flashes a
console.  Doing it once here means no other module has to remember.

No Qt in this module.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

from . import app_data_dir, resource_path


class FFmpegMissing(RuntimeError):
    """ffmpeg could not be found and could not be fetched."""


class Cancelled(RuntimeError):
    """The caller asked for the run to stop."""


# --------------------------------------------------------------------------
# process helpers
# --------------------------------------------------------------------------

def _no_window():
    """Keyword arguments that keep a console from flashing on Windows."""
    if sys.platform.startswith("win"):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": 0x08000000}
    return {}


_FOUND = {}


def _candidates(name):
    """Every place worth looking for ffmpeg/ffprobe, best first."""
    exe = name + (".exe" if sys.platform.startswith("win") else "")

    env = os.environ.get("TUBECLIPPER_FFMPEG")
    if env:
        # Either the directory holding both tools, or ffmpeg itself.
        if os.path.isdir(env):
            yield os.path.join(env, exe)
        else:
            yield os.path.join(os.path.dirname(env), exe)

    yield resource_path("ffmpeg", exe)          # frozen build
    yield os.path.join(app_data_dir(), "ffmpeg", exe)   # fetched at runtime

    found = shutil.which(name)
    if found:
        yield found

    if sys.platform == "darwin":
        yield "/opt/homebrew/bin/" + name
        yield "/usr/local/bin/" + name


def tool_path(name):
    """Absolute path to ``ffmpeg`` or ``ffprobe``, or None.

    Cached, because this is called before every run and a failed
    ``shutil.which`` on a slow PATH is not free.
    """
    if name in _FOUND:
        return _FOUND[name]
    for path in _candidates(name):
        if path and os.path.exists(path):
            _FOUND[name] = path
            return path
    _FOUND[name] = None
    return None


def forget_tools():
    """Drop the cache, after fetching a copy."""
    _FOUND.clear()


def have_ffmpeg():
    return tool_path("ffmpeg") is not None and tool_path("ffprobe") is not None


def version_string():
    path = tool_path("ffmpeg")
    if not path:
        return "not found"
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True,
                             timeout=15, **_no_window()).stdout
        return out.splitlines()[0] if out else "unknown"
    except Exception as exc:                       # pragma: no cover - defensive
        return f"unreadable ({exc})"


# --------------------------------------------------------------------------
# fetching a copy
# --------------------------------------------------------------------------

WIN_BUILDS = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
    "ffmpeg-master-latest-win64-gpl.zip",
)


def install_ffmpeg(on_progress=None, cancel=None):
    """Download a static ffmpeg into the app data directory (Windows).

    Returns the directory it landed in.  On macOS and Linux there is no
    single blessed binary to fetch, and both platforms have a package
    manager one line away, so this raises with that instruction rather
    than shipping something unsigned into the user's home directory.
    """
    if not sys.platform.startswith("win"):
        raise FFmpegMissing(
            "ffmpeg is not installed.\n\n"
            "macOS:  brew install ffmpeg\n"
            "Linux:  sudo apt install ffmpeg")

    import urllib.request

    dest = os.path.join(app_data_dir(), "ffmpeg")
    os.makedirs(dest, exist_ok=True)
    tmp = os.path.join(dest, "_download.zip")

    last = None
    for url in WIN_BUILDS:
        try:
            if on_progress:
                on_progress(0.0, "Downloading ffmpeg…")
            with urllib.request.urlopen(url, timeout=60) as response:
                total = int(response.headers.get("Content-Length") or 0)
                read = 0
                with open(tmp, "wb") as handle:
                    while True:
                        if cancel is not None and cancel():
                            raise Cancelled()
                        chunk = response.read(262144)
                        if not chunk:
                            break
                        handle.write(chunk)
                        read += len(chunk)
                        if on_progress and total:
                            on_progress(read / total,
                                        f"Downloading ffmpeg… "
                                        f"{read // 1048576} of {total // 1048576} MB")
            break
        except Cancelled:
            raise
        except Exception as exc:
            last = exc
            continue
    else:
        raise FFmpegMissing(f"Could not download ffmpeg: {last}")

    if on_progress:
        on_progress(1.0, "Unpacking…")

    # The archives nest the binaries a couple of levels down and differ in
    # how; pull out anything named right, wherever it sits.
    wanted = {"ffmpeg.exe", "ffprobe.exe"}
    with zipfile.ZipFile(tmp) as archive:
        for member in archive.namelist():
            base = os.path.basename(member)
            if base in wanted:
                with archive.open(member) as src, \
                        open(os.path.join(dest, base), "wb") as dst:
                    shutil.copyfileobj(src, dst)
    os.remove(tmp)
    forget_tools()

    if not have_ffmpeg():
        raise FFmpegMissing("The downloaded archive did not contain ffmpeg.")
    return dest


# --------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------

_TIME_RE = re.compile(r"out_time_ms=(-?\d+)")


def run(args, duration=None, on_progress=None, cancel=None, poll=0.1):
    """Run ffmpeg, reporting progress as a fraction of ``duration``.

    ``args`` is everything after the executable.  Returns the tail of
    stderr on success and raises ``RuntimeError`` with it on failure --
    ffmpeg's last twenty lines are almost always the actual complaint,
    and the first hundred are banner and stream dumps nobody reads.
    """
    exe = tool_path("ffmpeg")
    if not exe:
        raise FFmpegMissing("ffmpeg was not found.")

    cmd = [exe, "-hide_banner", "-nostdin", "-loglevel", "error",
           "-progress", "pipe:1", "-nostats", *args]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1, universal_newlines=True,
                            **_no_window())

    # stderr has to be drained on its own thread: a full pipe buffer will
    # deadlock the child while we sit reading stdout.
    import threading
    errors = []

    def drain():
        for line in proc.stderr:
            errors.append(line.rstrip())
            del errors[:-40]

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()

    try:
        for line in proc.stdout:
            if cancel is not None and cancel():
                proc.kill()
                raise Cancelled()
            match = _TIME_RE.search(line)
            if match and on_progress:
                seconds = int(match.group(1)) / 1_000_000.0
                if duration and duration > 0:
                    on_progress(max(0.0, min(1.0, seconds / duration)), None)
                else:
                    on_progress(None, f"{seconds:.1f}s")
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass

    code = proc.wait()
    thread.join(timeout=2)
    tail = "\n".join(errors)
    if code != 0:
        raise RuntimeError(tail or f"ffmpeg exited with status {code}")
    return tail


def probe(target, headers=None, timeout=60):
    """ffprobe a file or URL, returning the parsed JSON.

    Works on remote URLs as well as local files, which is what lets the
    timeline know a stream's real frame rate before anything has been
    downloaded.
    """
    exe = tool_path("ffprobe")
    if not exe:
        raise FFmpegMissing("ffprobe was not found.")
    cmd = [exe, "-hide_banner", "-loglevel", "error"]
    if headers:
        cmd += ["-headers", header_block(headers)]
    cmd += ["-show_format", "-show_streams", "-of", "json", target]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                         **_no_window())
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "ffprobe failed")
    return json.loads(out.stdout)


def header_block(headers):
    """Turn a header dict into the single CRLF-joined string ffmpeg wants.

    ffmpeg takes ``-headers`` as one blob rather than repeated flags, and
    it must end with a newline or the last header is dropped silently.
    """
    if not headers:
        return ""
    lines = [f"{k}: {v}" for k, v in headers.items()
             if k.lower() not in ("range", "accept-encoding")]
    return "\r\n".join(lines) + "\r\n"


def input_args(url, headers=None, seek=None):
    """Input flags for one source, local or remote.

    The reconnect flags matter more than they look: a clip taken an hour
    into a six-hour stream is a long-lived HTTP read, and without them a
    single dropped connection ends the export with a truncated file
    rather than a retry.
    """
    args = []
    remote = url.startswith("http://") or url.startswith("https://")
    if remote:
        if headers:
            args += ["-headers", header_block(headers)]
        args += ["-reconnect", "1", "-reconnect_streamed", "1",
                 "-reconnect_on_network_error", "1", "-reconnect_delay_max", "10"]
    if seek is not None and seek > 0:
        # Before -i, so ffmpeg range-requests its way to the seek point
        # instead of reading and discarding everything up to it.  When the
        # output is re-encoded ffmpeg still decodes forward to the exact
        # timestamp, so this is fast *and* frame-accurate; with -c copy it
        # lands on the nearest earlier keyframe, which is what fast mode
        # is asking for.
        args += ["-ss", f"{seek:.6f}"]
    args += ["-i", url]
    return args
