"""
jobs.py -- the export queue, and the background thread that drains it.

Two kinds of work happen off the interface thread.  One-shot lookups (read
a link, fetch a filmstrip) go to a thread pool and report back once.
Exports go through a single serial queue instead, because they are the
opposite: long, ordered, individually cancellable, and pointless to run
four at a time -- two ffmpeg encodes on the same machine finish in about
the time two sequential ones would, and the progress bars stop meaning
anything.
"""

from __future__ import annotations

import inspect
import queue
import traceback
from dataclasses import dataclass, field

from PySide6 import QtCore

from . import engine
from .ffmpegtool import Cancelled

PENDING, RUNNING, DONE, FAILED, CANCELLED = "pending", "running", "done", "failed", "cancelled"


@dataclass
class Job:
    """One queued unit of work."""
    ident: int = 0
    kind: str = "export"                 # "export" | "download"
    label: str = ""
    spec: object = None                  # ExportSpec, or a dict for downloads
    status: str = PENDING
    progress: float = 0.0
    message: str = ""
    out_path: str = ""
    note: str = ""


# --------------------------------------------------------------------------
# one-shot background tasks
# --------------------------------------------------------------------------

class TaskSignals(QtCore.QObject):
    done = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    progress = QtCore.Signal(float, str)


class Task(QtCore.QRunnable):
    """Run ``fn`` on the thread pool and emit the result.

    ``fn`` may take a ``report`` keyword, which it can call with
    ``(fraction, text)`` to drive a progress bar.
    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.signals = TaskSignals()
        self._fn, self._args, self._kwargs = fn, args, kwargs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def cancelled(self):
        return self._cancelled

    @QtCore.Slot()
    def run(self):
        try:
            if _takes_report(self._fn):
                self._kwargs["report"] = \
                    lambda f, t="": self.signals.progress.emit(f or 0.0, t)
            result = self._fn(*self._args, **self._kwargs)
        except Cancelled:
            return
        except Exception as exc:
            self.signals.failed.emit(_message(exc))
            return
        if not self._cancelled:
            self.signals.done.emit(result)


def _takes_report(fn):
    """True when ``fn`` accepts a ``report`` keyword, so we can pass one."""
    try:
        return "report" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _message(exc):
    text = str(exc).strip()
    if not text:
        text = exc.__class__.__name__
    # ffmpeg's stderr can be forty lines; the last few carry the reason.
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) > 6:
        lines = lines[-6:]
    return "\n".join(lines)


def format_traceback():
    return traceback.format_exc()


# --------------------------------------------------------------------------
# the export queue
# --------------------------------------------------------------------------

class Runner(QtCore.QThread):
    """Drains the queue one job at a time until told to stop."""

    started_job = QtCore.Signal(int)
    progressed = QtCore.Signal(int, float, str)
    finished_job = QtCore.Signal(int, str, str)     # ident, path, note
    failed_job = QtCore.Signal(int, str)
    cancelled_job = QtCore.Signal(int)
    became_idle = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue = queue.Queue()
        self._stop = False
        self._current = 0
        self._cancel_ids = set()
        self._lock = QtCore.QMutex()

    # -- submission ------------------------------------------------------

    def submit(self, job):
        self._queue.put(job)

    def cancel(self, ident):
        """Cancel a job whether it is running or still waiting."""
        with QtCore.QMutexLocker(self._lock):
            self._cancel_ids.add(ident)

    def cancel_all(self):
        with QtCore.QMutexLocker(self._lock):
            self._cancel_ids.add(-1)          # sentinel: everything

    def _is_cancelled(self, ident):
        with QtCore.QMutexLocker(self._lock):
            return ident in self._cancel_ids or -1 in self._cancel_ids

    def clear_cancel_all(self):
        with QtCore.QMutexLocker(self._lock):
            self._cancel_ids.discard(-1)

    def stop(self):
        self._stop = True
        self.cancel_all()
        self._queue.put(None)

    # -- the loop --------------------------------------------------------

    def run(self):
        while not self._stop:
            try:
                job = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if job is None:
                break
            if self._is_cancelled(job.ident):
                self.cancelled_job.emit(job.ident)
                if self._queue.empty():
                    self.became_idle.emit()
                continue

            self._current = job.ident
            self.started_job.emit(job.ident)
            try:
                self._run_one(job)
            except Cancelled:
                self.cancelled_job.emit(job.ident)
            except Exception as exc:
                self.failed_job.emit(job.ident, _message(exc))
            self._current = 0
            if self._queue.empty():
                self.became_idle.emit()

    def _run_one(self, job):
        ident = job.ident
        cancel = lambda: self._is_cancelled(ident)

        def progress(fraction, text=None):
            self.progressed.emit(ident, float(fraction or 0.0), text or "")

        def status(text):
            self.progressed.emit(ident, -1.0, text)

        if job.kind == "download":
            spec = job.spec
            path = engine.download_whole(
                spec["url"], spec["video_id"], spec.get("height"),
                on_progress=progress, on_status=status, cancel=cancel,
                cookies_from_browser=spec.get("cookies") or None,
                audio_only=bool(spec.get("audio_only")))
            if not path:
                raise RuntimeError("The whole-video download produced no file.")
            for dependent in spec.get("dependents") or []:
                dependent.local_path = path
            self.finished_job.emit(ident, path, "")
            return

        result = engine.export(job.spec, on_progress=progress,
                               on_status=status, cancel=cancel)
        self.finished_job.emit(ident, result.path, result.note)
