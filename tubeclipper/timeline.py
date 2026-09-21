"""
timeline.py -- the scrub bar: filmstrip, ruler, in/out handles, playhead.

The widget owns two ranges and it is worth keeping them straight.  The
*clip* range is what the user is cutting.  The *view* range is what part
of the video the widget is currently showing, which zoom and pan change
without touching the clip at all.

Zoom is the whole reason this is a custom widget rather than two sliders.
Setting an out point to the frame on a six-hour stream means one pixel is
twenty seconds at full width, and no amount of careful dragging fixes
that.  Scrolling to zoom around the pointer, with the ruler relabelling
itself as the scale changes, makes the same drag land on the frame.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .source import format_timecode

BG = QtGui.QColor("#12141a")
STRIP_BG = QtGui.QColor("#0d0f13")
RULER_BG = QtGui.QColor("#171b22")
BORDER = QtGui.QColor("#262b34")
TICK = QtGui.QColor("#3a4353")
TEXT = QtGui.QColor("#8b95a4")
SEL_FILL = QtGui.QColor(26, 86, 219, 60)
SEL_EDGE = QtGui.QColor("#4a9eff")
HANDLE = QtGui.QColor("#4a9eff")
HANDLE_HOT = QtGui.QColor("#8cc4ff")
PLAYHEAD = QtGui.QColor("#f2f5fa")
CLIP_BAR = QtGui.QColor("#38b26a")
OUTSIDE = QtGui.QColor(6, 7, 10, 130)

#: How close to a handle the pointer has to be, in pixels at 100%.
GRAB = 7


class TimelineView(QtWidgets.QWidget):
    """A zoomable strip with a draggable in/out selection."""

    rangeChanged = QtCore.Signal(float, float)     # in, out -- live, while dragging
    rangeCommitted = QtCore.Signal(float, float)   # on release
    seeked = QtCore.Signal(float)
    viewChanged = QtCore.Signal(float, float)
    thumbsWanted = QtCore.Signal(float, float, int)  # view start, end, count

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setCursor(QtCore.Qt.ArrowCursor)

        self._duration = 0.0
        self._view = (0.0, 0.0)
        self._in = 0.0
        self._out = 0.0
        self._playhead = 0.0
        self._thumbs = []          # [(t, QPixmap)]
        self._clips = []           # [(start, end, name)]
        self._drag = None          # "in" | "out" | "region" | "scrub" | "pan"
        self._drag_anchor = 0.0
        self._hot = None
        self._scale = 1.0
        self._strip_h = 62
        self._ruler_h = 17

    # -- state -----------------------------------------------------------

    def set_scale(self, k):
        self._scale = k
        self.setMinimumHeight(int(round(120 * k)))
        self.update()

    def set_duration(self, seconds):
        self._duration = max(0.0, float(seconds or 0.0))
        self._view = (0.0, self._duration)
        self._in = 0.0
        self._out = min(self._duration, 30.0) if self._duration else 0.0
        self._playhead = 0.0
        self._thumbs = []
        self._clips = []
        self.update()
        self._announce_view()

    def duration(self):
        return self._duration

    def range(self):
        return self._in, self._out

    def set_range(self, start, end, announce=True):
        start = self._clamp(start)
        end = self._clamp(end)
        if end < start:
            start, end = end, start
        self._in, self._out = start, end
        self.update()
        if announce:
            self.rangeChanged.emit(self._in, self._out)

    def set_playhead(self, t):
        t = self._clamp(t)
        if abs(t - self._playhead) < 1e-4:
            return
        self._playhead = t
        self.update()

    def playhead(self):
        return self._playhead

    def set_thumbs(self, thumbs):
        self._thumbs = list(thumbs or [])
        self.update()

    def set_clips(self, clips):
        self._clips = list(clips or [])
        self.update()

    def view(self):
        return self._view

    # -- geometry --------------------------------------------------------

    def _k(self):
        return self._scale

    def _strip_rect(self):
        h = int(round(self._strip_h * self._k()))
        return QtCore.QRect(0, 0, self.width(), h)

    def _ruler_rect(self):
        top = self._strip_rect().bottom() + 1
        return QtCore.QRect(0, top, self.width(),
                            int(round(self._ruler_h * self._k())))

    def _body_rect(self):
        top = self._ruler_rect().bottom() + 1
        return QtCore.QRect(0, top, self.width(), max(1, self.height() - top))

    def x_for(self, t):
        a, b = self._view
        span = max(1e-9, b - a)
        return (t - a) / span * max(1, self.width())

    def t_for(self, x):
        a, b = self._view
        span = max(1e-9, b - a)
        return a + x / max(1, self.width()) * span

    def _clamp(self, t):
        return max(0.0, min(self._duration or 0.0, float(t)))

    # -- zoom and pan ----------------------------------------------------

    def set_view(self, start, end):
        if self._duration <= 0:
            return
        span = max(0.02, min(self._duration, end - start))
        start = max(0.0, min(self._duration - span, start))
        self._view = (start, start + span)
        self.update()
        self._announce_view()

    def zoom(self, factor, around=None):
        a, b = self._view
        span = b - a
        if around is None:
            around = (a + b) / 2.0
        new_span = max(0.02, min(self._duration or span, span / factor))
        left = around - (around - a) * (new_span / span)
        self.set_view(left, left + new_span)

    def fit(self):
        self.set_view(0.0, self._duration)

    def fit_selection(self, pad=0.15):
        if self._out <= self._in:
            return
        span = self._out - self._in
        self.set_view(self._in - span * pad, self._out + span * pad)

    def _announce_view(self):
        a, b = self._view
        self.viewChanged.emit(a, b)
        count = max(4, min(24, self.width() // max(1, int(90 * self._k()))))
        self.thumbsWanted.emit(a, b, int(count))

    # -- painting --------------------------------------------------------

    def paintEvent(self, _event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, False)
        k = self._k()

        p.fillRect(self.rect(), BG)
        strip, ruler, body = self._strip_rect(), self._ruler_rect(), self._body_rect()

        p.fillRect(strip, STRIP_BG)
        self._paint_thumbs(p, strip)
        p.fillRect(ruler, RULER_BG)
        self._paint_ruler(p, ruler, k)

        if self._duration <= 0:
            p.setPen(TEXT)
            f = p.font()
            f.setPointSizeF(max(6.0, 9.0 * k))
            p.setFont(f)
            p.drawText(self.rect(), QtCore.Qt.AlignCenter,
                       "Load a link to see the timeline")
            return

        self._paint_clips(p, body, k)
        self._paint_selection(p, strip, body, k)
        self._paint_playhead(p, strip, body, k)

        p.setPen(BORDER)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def _paint_thumbs(self, p, strip):
        if not self._thumbs:
            return
        p.save()
        p.setClipRect(strip)
        for t, pix in self._thumbs:
            if pix is None or pix.isNull():
                continue
            x = int(self.x_for(t))
            scaled = pix.scaledToHeight(strip.height(),
                                        QtCore.Qt.SmoothTransformation)
            p.drawPixmap(x, strip.top(), scaled)
        p.restore()

    def _paint_ruler(self, p, ruler, k):
        if self._duration <= 0:
            return
        a, b = self._view
        span = b - a
        step = _nice_step(span, max(1, self.width() // int(90 * k)))
        f = p.font()
        f.setPointSizeF(max(6.0, 7.5 * k))
        p.setFont(f)

        t = (int(a / step)) * step
        while t <= b:
            x = int(self.x_for(t))
            p.setPen(TICK)
            p.drawLine(x, ruler.top(), x, ruler.bottom())
            p.setPen(TEXT)
            p.drawText(x + int(3 * k), ruler.bottom() - int(4 * k),
                       format_timecode(t, millis=step < 1.0))
            t += step

    def _paint_clips(self, p, body, k):
        if not self._clips:
            return
        h = max(3, int(4 * k))
        y = body.bottom() - h - int(2 * k)
        for start, end, _name in self._clips:
            x0, x1 = self.x_for(start), self.x_for(end)
            p.fillRect(QtCore.QRectF(x0, y, max(2.0, x1 - x0), h), CLIP_BAR)

    def _paint_selection(self, p, strip, body, k):
        x0 = self.x_for(self._in)
        x1 = self.x_for(self._out)
        full = QtCore.QRectF(0, strip.top(), self.width(),
                             body.bottom() - strip.top())

        # Dim everything outside the clip, so the selection reads at a
        # glance even when both handles are off the left of the view.
        p.fillRect(QtCore.QRectF(full.left(), full.top(),
                                 max(0.0, x0 - full.left()), full.height()), OUTSIDE)
        p.fillRect(QtCore.QRectF(x1, full.top(),
                                 max(0.0, full.right() - x1), full.height()), OUTSIDE)
        p.fillRect(QtCore.QRectF(x0, body.top(), max(1.0, x1 - x0),
                                 body.height()), SEL_FILL)

        pen = QtGui.QPen(SEL_EDGE, max(1.0, 1.0 * k))
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(x0, full.top()), QtCore.QPointF(x0, full.bottom()))
        p.drawLine(QtCore.QPointF(x1, full.top()), QtCore.QPointF(x1, full.bottom()))

        self._paint_handle(p, x0, body, k, "in")
        self._paint_handle(p, x1, body, k, "out")

        # Duration, centred in the selection when it fits.
        label = format_timecode(self._out - self._in)
        f = p.font()
        f.setPointSizeF(max(6.5, 8.5 * k))
        f.setBold(True)
        p.setFont(f)
        width = QtGui.QFontMetrics(f).horizontalAdvance(label) + int(10 * k)
        if x1 - x0 > width:
            p.setPen(QtGui.QColor("#dce4f0"))
            p.drawText(QtCore.QRectF(x0, body.top(), x1 - x0, body.height()),
                       QtCore.Qt.AlignCenter, label)

    def _paint_handle(self, p, x, body, k, which):
        w = max(5.0, 7.0 * k)
        h = body.height() * 0.62
        y = body.top() + (body.height() - h) / 2.0
        colour = HANDLE_HOT if self._hot == which else HANDLE
        rect = QtCore.QRectF(x - w / 2.0, y, w, h)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(colour)
        p.drawRoundedRect(rect, w / 3.0, w / 3.0)
        p.setPen(QtGui.QPen(QtGui.QColor("#0d1017"), max(1.0, 1.0 * k)))
        mid = rect.center()
        p.drawLine(QtCore.QPointF(mid.x(), rect.top() + h * 0.28),
                   QtCore.QPointF(mid.x(), rect.bottom() - h * 0.28))
        p.setBrush(QtCore.Qt.NoBrush)

    def _paint_playhead(self, p, strip, body, k):
        x = self.x_for(self._playhead)
        p.setPen(QtGui.QPen(PLAYHEAD, max(1.0, 1.0 * k)))
        p.drawLine(QtCore.QPointF(x, strip.top()), QtCore.QPointF(x, body.bottom()))
        size = max(3.0, 4.0 * k)
        head = QtGui.QPolygonF([
            QtCore.QPointF(x - size, strip.top()),
            QtCore.QPointF(x + size, strip.top()),
            QtCore.QPointF(x, strip.top() + size * 1.6),
        ])
        p.setBrush(PLAYHEAD)
        p.setPen(QtCore.Qt.NoPen)
        p.drawPolygon(head)
        p.setBrush(QtCore.Qt.NoBrush)

    # -- interaction -----------------------------------------------------

    def _near(self, x, t):
        return abs(x - self.x_for(t)) <= GRAB * self._k()

    def _what_at(self, pos):
        if self._duration <= 0:
            return None
        x = pos.x()
        if self._near(x, self._in):
            return "in"
        if self._near(x, self._out):
            return "out"
        if self._strip_rect().contains(pos) or self._ruler_rect().contains(pos):
            return "scrub"
        if self.x_for(self._in) < x < self.x_for(self._out):
            return "region"
        return "scrub"

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._drag is None:
            hot = self._what_at(pos)
            self._hot = hot if hot in ("in", "out") else None
            self.setCursor(QtCore.Qt.SizeHorCursor if self._hot
                           else QtCore.Qt.ArrowCursor)
            self.update()
            return

        t = self._clamp(self.t_for(pos.x()))
        if self._drag == "in":
            self.set_range(min(t, self._out - 0.02), self._out)
        elif self._drag == "out":
            self.set_range(self._in, max(t, self._in + 0.02))
        elif self._drag == "region":
            delta = t - self._drag_anchor
            span = self._out - self._in
            start = self._clamp(self._in + delta)
            start = min(start, max(0.0, self._duration - span))
            self.set_range(start, start + span)
            self._drag_anchor = t
        elif self._drag == "scrub":
            self.set_playhead(t)
            self.seeked.emit(t)
        elif self._drag == "pan":
            a, b = self._view
            delta = self._drag_anchor - self.t_for(pos.x())
            self.set_view(a + delta, b + delta)

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        if event.button() == QtCore.Qt.MiddleButton:
            self._drag = "pan"
            self._drag_anchor = self.t_for(pos.x())
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            return
        if event.button() != QtCore.Qt.LeftButton:
            return
        what = self._what_at(pos)
        self._drag = what
        self._drag_anchor = self._clamp(self.t_for(pos.x()))
        if what == "scrub":
            self.set_playhead(self._drag_anchor)
            self.seeked.emit(self._drag_anchor)
        self.update()

    def mouseReleaseEvent(self, _event):
        if self._drag in ("in", "out", "region"):
            self.rangeCommitted.emit(self._in, self._out)
        self._drag = None
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()

    def mouseDoubleClickEvent(self, event):
        # Double-click the ruler to zoom out to the whole video; double-click
        # inside the selection to zoom to it.  Both are one gesture away
        # from wherever you are.
        pos = event.position().toPoint()
        if self.x_for(self._in) < pos.x() < self.x_for(self._out):
            self.fit_selection()
        else:
            self.fit()

    def wheelEvent(self, event):
        if self._duration <= 0:
            return
        delta = event.angleDelta().y()
        if not delta:
            return
        if event.modifiers() & QtCore.Qt.ShiftModifier:
            a, b = self._view
            step = (b - a) * 0.15 * (-1 if delta > 0 else 1)
            self.set_view(a + step, b + step)
        else:
            around = self.t_for(event.position().x())
            self.zoom(1.25 if delta > 0 else 1 / 1.25, around)
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._announce_view()


def _nice_step(span, want):
    """A tick interval that lands on times a person would say out loud."""
    if want <= 0:
        want = 1
    raw = span / want
    for step in (0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30,
                 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800):
        if step >= raw:
            return step
    return 21600
