"""
player.py -- the preview pane and its transport.

The player streams straight from YouTube's media URL rather than from a
downloaded copy.  That is what makes finding the moment you want on a
six-hour stream bearable: seeking is an HTTP range request, so jumping to
04:12:30 costs about as much as jumping to 00:00:30, and nothing has to be
fetched before the window becomes useful.

Preview prefers a combined video/audio stream.  When YouTube exposes separate
adaptive tracks instead, a second QMediaPlayer handles the audio and follows
the video player's play, pause, seek, speed, and position changes.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    HAVE_MEDIA = True
    MEDIA_ERROR = ""
except Exception as exc:                            # pragma: no cover
    HAVE_MEDIA = False
    MEDIA_ERROR = str(exc)
    QMediaPlayer = QAudioOutput = QVideoWidget = None

RATES = (0.25, 0.5, 1.0, 1.5, 2.0, 4.0)


def _transport_icon(name):
    """Return a crisp, theme-matched media icon without font glyphs."""
    size = 64
    canvas = QtGui.QPixmap(size, size)
    canvas.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(canvas)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    color = QtGui.QColor("#e3e8f0")
    pen = QtGui.QPen(color, 5, QtCore.Qt.SolidLine,
                     QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(color)

    def polygon(points):
        painter.drawPolygon(QtGui.QPolygonF(
            [QtCore.QPointF(x, y) for x, y in points]))

    if name == "back":
        polygon(((29, 14), (29, 50), (8, 32)))
        polygon(((53, 14), (53, 50), (32, 32)))
    elif name == "previous":
        painter.drawLine(QtCore.QPointF(12, 13), QtCore.QPointF(12, 51))
        polygon(((51, 14), (51, 50), (20, 32)))
    elif name == "play":
        polygon(((18, 12), (18, 52), (52, 32)))
    elif name == "pause":
        painter.drawRoundedRect(QtCore.QRectF(16, 12, 11, 40), 2, 2)
        painter.drawRoundedRect(QtCore.QRectF(37, 12, 11, 40), 2, 2)
    elif name == "next":
        polygon(((13, 14), (13, 50), (44, 32)))
        painter.drawLine(QtCore.QPointF(52, 13), QtCore.QPointF(52, 51))
    elif name == "step_back":
        polygon(((44, 16), (44, 48), (20, 32)))
    elif name == "step_fwd":
        polygon(((20, 16), (20, 48), (44, 32)))
    elif name == "forward":
        polygon(((11, 14), (11, 50), (32, 32)))
        polygon(((35, 14), (35, 50), (56, 32)))
    else:                                           # pragma: no cover
        raise ValueError(f"Unknown transport icon: {name}")

    painter.end()
    return QtGui.QIcon(canvas)


class LoadingOverlay(QtWidgets.QLabel):
    """Caption over the video, with a progress bar when there is a number.

    A percentage that moves is what separates "still working" from "hung";
    a caption on its own cannot do that.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fraction = None

    def fraction(self):
        return self._fraction

    def set_fraction(self, fraction):
        self._fraction = (None if fraction is None
                          else max(0.0, min(1.0, float(fraction))))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._fraction is None:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        width = max(80.0, min(280.0, self.width() * 0.5))
        height = 6.0
        lines = self.text().count("\n") + 1
        top = (self.height() + lines * self.fontMetrics().height()) / 2 + 10
        left = (self.width() - width) / 2
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(255, 255, 255, 40))
        painter.drawRoundedRect(QtCore.QRectF(left, top, width, height), 3, 3)
        painter.setBrush(QtGui.QColor("#4a9eff"))
        painter.drawRoundedRect(
            QtCore.QRectF(left, top, max(height, width * self._fraction), height),
            3, 3)
        painter.end()


class PlayerPane(QtWidgets.QWidget):
    """Video surface plus transport, reporting position in seconds."""

    positionChanged = QtCore.Signal(float)
    durationChanged = QtCore.Signal(float)
    playingChanged = QtCore.Signal(bool)
    readyChanged = QtCore.Signal(bool)
    errored = QtCore.Signal(str)
    markIn = QtCore.Signal(float)
    markOut = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scale = 1.0
        self._seeking = False
        self._split_audio = False
        self._buttons = []
        # Readiness is tracked per stream.  With an adaptive source the
        # audio is a second download, and treating the video's "loaded" as
        # the whole story gives you a few seconds of silent playback.
        self._ready = False
        self._video_ready = False
        self._audio_ready = True
        self._pending_seek = None
        self._busy_text = ""
        self._busy_dots = 0
        # A load runs from 0% to 100% across several stages (reading the
        # link, opening the video, opening the audio).  Real milestones set
        # the floor; between them the bar creeps toward the stage ceiling so
        # a slow network still shows movement, and it never goes backwards.
        self._loading = False
        self._load_ceiling = None
        self._has_media = False
        self._transport_icons = {
            name: _transport_icon(name)
            for name in ("back", "previous", "step_back", "play", "pause",
                         "step_fwd", "next", "forward")
        }

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self.surface = QtWidgets.QFrame()
        self.surface.setStyleSheet("background:#000; border:1px solid #262b34;"
                                   "border-radius:6px;")
        self.surface.setMinimumHeight(180)
        self.surface.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                   QtWidgets.QSizePolicy.Expanding)
        surface_layout = QtWidgets.QVBoxLayout(self.surface)
        surface_layout.setContentsMargins(1, 1, 1, 1)

        self.placeholder = QtWidgets.QLabel("Paste a YouTube link above")
        self.placeholder.setAlignment(QtCore.Qt.AlignCenter)
        self.placeholder.setStyleSheet("color:#5a626e; background:transparent;")

        if HAVE_MEDIA:
            self.video = QVideoWidget()
            self.video.setStyleSheet("background:#000;")
            self.video.setAspectRatioMode(QtCore.Qt.KeepAspectRatio)
            surface_layout.addWidget(self.video)
            self.video.hide()
            surface_layout.addWidget(self.placeholder)

            self.audio = QAudioOutput(self)
            self.audio.setVolume(0.9)
            self.split_audio = QAudioOutput(self)
            self.split_audio.setVolume(0.9)
            self.player = QMediaPlayer(self)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video)
            self.audio_player = QMediaPlayer(self)
            self.audio_player.setAudioOutput(self.split_audio)
            self.player.positionChanged.connect(self._on_position)
            self.player.durationChanged.connect(self._on_duration)
            self.player.playbackStateChanged.connect(self._on_state)
            self.player.errorOccurred.connect(self._on_error)
            self.audio_player.errorOccurred.connect(self._on_audio_error)
            self.player.mediaStatusChanged.connect(self._on_media_status)
            self.player.bufferProgressChanged.connect(self._on_buffer)
            self.audio_player.mediaStatusChanged.connect(self._on_audio_status)
        else:                                        # pragma: no cover
            self.video = None
            self.player = None
            self.audio = None
            self.audio_player = None
            self.split_audio = None
            self.placeholder.setText("Qt Multimedia is unavailable:\n" + MEDIA_ERROR)
            surface_layout.addWidget(self.placeholder)

        # Sits on top of the video rather than in the layout, so the frame
        # underneath keeps its size and the message appears over the
        # picture instead of pushing it around.
        self.overlay = LoadingOverlay(self.surface)
        self.overlay.setAlignment(QtCore.Qt.AlignCenter)
        self.overlay.setWordWrap(True)
        self.overlay.setStyleSheet(
            "background: rgba(10,12,16,190); color:#d5dae2; border-radius:6px;")
        self.overlay.hide()

        # The ellipsis animates, because a caption that never changes during
        # a thirty-second buffer is indistinguishable from a frozen window.
        self._busy_timer = QtCore.QTimer(self)
        self._busy_timer.setInterval(450)
        self._busy_timer.timeout.connect(self._tick_busy)

        outer.addWidget(self.surface, 1)
        outer.addLayout(self._transport())
        self.set_enabled(False)

    # -- construction ----------------------------------------------------

    def _button(self, icon, tip, slot, width=38, text="", icon_after=False):
        b = QtWidgets.QPushButton(text)
        b.setIcon(icon)
        b.setIconSize(QtCore.QSize(18, 18))
        if icon_after:
            b.setLayoutDirection(QtCore.Qt.RightToLeft)
        b.setToolTip(tip)
        b.setAccessibleName(tip.partition(" (")[0])
        b.clicked.connect(slot)
        b.setFixedWidth(width)
        self._buttons.append((b, width))
        return b

    def _transport(self):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)

        icons = self._transport_icons
        self.btn_start = self._button(
            icons["previous"], "Go to the start (Home)", self.go_to_start)
        self.btn_back10 = self._button(
            icons["back"], "Back ten seconds", lambda: self.nudge(-10),
            width=60, text="10s")
        self.btn_back1 = self._button(
            icons["back"], "Back one second", lambda: self.nudge(-1),
            width=52, text="1s")
        self.btn_frame_back = self._button(
            icons["step_back"], "Back one frame (Left)",
            lambda: self.nudge(-self._frame()), width=52, text="1f")
        self.btn_play = self._button(
            icons["play"], "Play / pause (Space)", self.toggle, 44)
        self.btn_frame_fwd = self._button(
            icons["step_fwd"], "Forward one frame (Right)",
            lambda: self.nudge(self._frame()), width=52, text="1f",
            icon_after=True)
        self.btn_fwd1 = self._button(
            icons["forward"], "Forward one second", lambda: self.nudge(1),
            width=52, text="1s", icon_after=True)
        self.btn_fwd10 = self._button(
            icons["forward"], "Forward ten seconds", lambda: self.nudge(10),
            width=60, text="10s", icon_after=True)
        self.btn_end = self._button(
            icons["next"], "Go to the end (End)", self.go_to_end)
        for b in (self.btn_start, self.btn_back10, self.btn_back1,
                  self.btn_frame_back, self.btn_play, self.btn_frame_fwd,
                  self.btn_fwd1, self.btn_fwd10, self.btn_end):
            row.addWidget(b)

        row.addSpacing(8)
        self.readout = QtWidgets.QLabel("0:00.000")
        self.readout.setObjectName("value")
        self.readout.setMinimumWidth(96)
        font = QtGui.QFont("Consolas" if QtGui.QFontDatabase.families().count("Consolas")
                           else "Monospace")
        font.setStyleHint(QtGui.QFont.Monospace)
        self.readout.setFont(font)
        row.addWidget(self.readout)

        # Buffering after the video is up is reported here rather than over
        # the picture: on macOS the video surface is a native layer that
        # paints over any widget placed on top of it.
        self.buffer_label = QtWidgets.QLabel("")
        self.buffer_label.setStyleSheet("color:#8cc4ff;")
        self.buffer_label.hide()
        row.addWidget(self.buffer_label)

        row.addStretch(1)

        self.btn_in = QtWidgets.QPushButton("Set In  (I)")
        self.btn_in.setToolTip("Put the in point at the playhead")
        self.btn_in.clicked.connect(lambda: self.markIn.emit(self.position()))
        self.btn_out = QtWidgets.QPushButton("Set Out  (O)")
        self.btn_out.setToolTip("Put the out point at the playhead")
        self.btn_out.clicked.connect(lambda: self.markOut.emit(self.position()))
        row.addWidget(self.btn_in)
        row.addWidget(self.btn_out)

        row.addSpacing(8)
        self.rate = QtWidgets.QComboBox()
        for r in RATES:
            self.rate.addItem(f"{r:g}×", r)
        self.rate.setCurrentIndex(RATES.index(1.0))
        self.rate.setToolTip("Playback speed")
        self.rate.currentIndexChanged.connect(self._on_rate)
        self.rate.setFixedWidth(66)
        row.addWidget(self.rate)

        self.volume = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(90)
        self.volume.setFixedWidth(90)
        self.volume.setToolTip("Volume")
        self.volume.valueChanged.connect(self._on_volume)
        row.addWidget(self.volume)
        return row

    # -- scaling ---------------------------------------------------------

    def set_scale(self, k):
        self._scale = k
        r = lambda v: int(round(v * k))
        for b, base in self._buttons:
            b.setFixedWidth(r(base))
            b.setIconSize(QtCore.QSize(r(18), r(18)))
        self.readout.setMinimumWidth(r(96))
        self.rate.setFixedWidth(r(66))
        self.volume.setFixedWidth(r(90))
        self.surface.setMinimumHeight(r(180))

    # -- loading ---------------------------------------------------------

    def set_enabled(self, on):
        for widget in (self.btn_back10, self.btn_back1, self.btn_frame_back,
                       self.btn_play, self.btn_frame_fwd, self.btn_fwd1,
                       self.btn_fwd10, self.btn_in, self.btn_out, self.rate):
            widget.setEnabled(bool(on) and HAVE_MEDIA)

    def load(self, url, fps=0.0, audio_url=""):
        """Load preview video and an optional separate audio stream.

        The transport stays disabled until the streams report themselves
        loaded.  Opening a YouTube stream takes a few seconds, and buttons
        that are live but do nothing are what makes an app feel broken.
        """
        if not HAVE_MEDIA:
            return
        self._fps = fps or 25.0
        self.player.stop()
        self.audio_player.stop()
        self._split_audio = bool(audio_url)
        self._video_ready = False
        self._audio_ready = not self._split_audio
        self._pending_seek = None
        self._set_ready(False)
        self._has_media = True
        self._loading = True
        self.progress("Loading video", 0.35, 0.80)
        self.player.setSource(QtCore.QUrl(url))
        self.audio_player.setSource(
            QtCore.QUrl(audio_url) if audio_url else QtCore.QUrl())

    def clear(self):
        if not HAVE_MEDIA:
            return
        self.player.stop()
        self.audio_player.stop()
        self.player.setSource(QtCore.QUrl())
        self.audio_player.setSource(QtCore.QUrl())
        self._split_audio = False
        self._video_ready = False
        self._audio_ready = True
        self._has_media = False
        self._set_ready(False)
        self._loading = False
        self.idle()

    # -- the overlay -----------------------------------------------------

    def begin_load(self, text="Reading the link"):
        """Start a fresh load at 0%."""
        self._loading = True
        self.overlay.set_fraction(0.0)
        self.progress(text, 0.0, 0.05)

    def loading(self):
        return self._loading

    def progress(self, text, fraction, ceiling=None):
        """Show a loading step with a percentage.

        ``fraction`` is how far the load has really got.  ``ceiling`` is
        how far the bar may creep while it waits for the next milestone.
        The number never goes backwards within a load.
        """
        shown = self.overlay.fraction() or 0.0
        value = max(shown, float(fraction))
        self._load_ceiling = max(value, ceiling) if ceiling is not None else None
        self._busy_text = text
        self._busy_dots = 0
        self.overlay.set_fraction(value)
        self._render_busy()
        self._show_overlay()
        self._busy_timer.start()

    def busy(self, text):
        """Show a message over the video and animate it."""
        self._busy_text = text
        self._busy_dots = 0
        self._load_ceiling = None
        self.overlay.set_fraction(None)
        self._render_busy()
        self._show_overlay()
        self._busy_timer.start()

    def message(self, text):
        """Show a message over the video that is not going to change."""
        self._loading = False
        self._busy_timer.stop()
        self._busy_text = ""
        self._load_ceiling = None
        self.overlay.set_fraction(None)
        self.overlay.setText(text)
        self._show_overlay()

    def idle(self):
        self._busy_timer.stop()
        self._busy_text = ""
        self._load_ceiling = None
        self.overlay.set_fraction(None)
        self.overlay.hide()
        self._show_surface()

    def _show_overlay(self):
        # The native video layer would cover the caption, so it steps aside
        # while there is something to say, along with the placeholder text.
        if self.video is not None:
            self.video.hide()
        self.placeholder.hide()
        self._place_overlay()
        self.overlay.show()
        self.overlay.raise_()

    def _show_surface(self):
        if self.video is not None and self._has_media:
            self.placeholder.hide()
            self.video.show()
        else:
            if self.video is not None:
                self.video.hide()
            self.placeholder.show()

    def _set_buffering(self, text):
        if text:
            self.buffer_label.setText(text)
            self.buffer_label.show()
        else:
            self.buffer_label.hide()

    def _render_busy(self):
        fraction = self.overlay.fraction()
        if fraction is None:
            self.overlay.setText(self._busy_text + "." * self._busy_dots
                                 if self._busy_dots else self._busy_text + "…")
        else:
            self.overlay.setText(f"{self._busy_text}  {int(fraction * 100)}%")

    def _tick_busy(self):
        # A tick that arrives after the caption became a fixed message must
        # not overwrite it.
        if not self._busy_text:
            self._busy_timer.stop()
            return
        fraction = self.overlay.fraction()
        if fraction is None:
            self._busy_dots = (self._busy_dots + 1) % 4
        elif self._load_ceiling is not None and fraction < self._load_ceiling:
            self.overlay.set_fraction(
                fraction + (self._load_ceiling - fraction) * 0.045)
        self._render_busy()

    def _place_overlay(self):
        self.overlay.setGeometry(self.surface.rect().adjusted(1, 1, -1, -1))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_overlay()

    def ready(self):
        return self._ready

    def _set_ready(self, ready):
        if ready == self._ready:
            return
        self._ready = ready
        self.set_enabled(ready)
        self.readyChanged.emit(ready)

    def _recompute_ready(self):
        """Ready only when every stream the preview needs has loaded."""
        if self._video_ready and self._audio_ready:
            self._loading = False
            self._set_ready(True)
            self.idle()
            if self._pending_seek is not None:
                seconds, self._pending_seek = self._pending_seek, None
                self.seek(seconds)
        elif self._video_ready and not self._audio_ready:
            self._loading = True
            self.progress("Loading audio", 0.85, 0.98)

    # -- transport -------------------------------------------------------

    def _frame(self):
        return 1.0 / max(1.0, getattr(self, "_fps", 25.0))

    def position(self):
        if not HAVE_MEDIA or self.player is None:
            return 0.0
        return self.player.position() / 1000.0

    def playing(self):
        return (HAVE_MEDIA and self.player is not None
                and self.player.playbackState() == QMediaPlayer.PlayingState)

    def play(self):
        if HAVE_MEDIA and self.player is not None:
            self.player.play()
            if self._split_audio:
                self._sync_audio(force=True)
                self.audio_player.play()

    def pause(self):
        if HAVE_MEDIA and self.player is not None:
            self.player.pause()
            if self._split_audio:
                self.audio_player.pause()

    def toggle(self):
        self.pause() if self.playing() else self.play()

    def nudge(self, seconds):
        # Stepping a frame while playing fights the playback clock, so
        # any manual step pauses first -- which is also what a person
        # expects from a frame-step button.
        if self.playing():
            self.pause()
        self.seek(self.position() + seconds)

    def duration(self):
        if not HAVE_MEDIA or self.player is None:
            return 0.0
        return max(0.0, self.player.duration() / 1000.0)

    def go_to_start(self):
        if self.playing():
            self.pause()
        self.seek(0.0)

    def go_to_end(self):
        if self.playing():
            self.pause()
        end = self.duration()
        if end > 0:
            self.seek(max(0.0, end - self._frame()))

    def seek(self, seconds):
        """Seek, or remember the request until the media can accept it.

        Dragging the timeline during the first few seconds used to do
        nothing at all, silently.  Holding the position and applying it on
        load means the gesture lands where the user put it.
        """
        if not HAVE_MEDIA or self.player is None:
            return
        seconds = max(0.0, seconds)
        if not self._ready:
            self._pending_seek = seconds
            return
        self._seeking = True
        position = int(seconds * 1000)
        self.player.setPosition(position)
        if self._split_audio:
            self.audio_player.setPosition(position)
        self._seeking = False

    def set_volume(self, percent):
        self.volume.setValue(int(percent))

    # -- signals ---------------------------------------------------------

    def _on_position(self, ms):
        if self._split_audio and self.playing():
            self._sync_audio(ms)
        seconds = ms / 1000.0
        from .source import format_timecode
        self.readout.setText(format_timecode(seconds))
        self.positionChanged.emit(seconds)

    def _on_duration(self, ms):
        self.durationChanged.emit(ms / 1000.0)

    def _on_state(self, state):
        playing = state == QMediaPlayer.PlayingState
        if self._split_audio:
            if playing:
                self._sync_audio(force=True)
                self.audio_player.play()
            elif state == QMediaPlayer.PausedState:
                self.audio_player.pause()
            else:
                self.audio_player.stop()
        self.btn_play.setIcon(
            self._transport_icons["pause" if playing else "play"])
        self.playingChanged.emit(playing)

    def _on_rate(self, _index):
        if HAVE_MEDIA and self.player is not None:
            rate = float(self.rate.currentData())
            self.player.setPlaybackRate(rate)
            self.audio_player.setPlaybackRate(rate)

    def _on_volume(self, value):
        if HAVE_MEDIA and self.audio is not None:
            volume = value / 100.0
            self.audio.setVolume(volume)
            self.split_audio.setVolume(volume)

    def _sync_audio(self, video_position=None, force=False):
        """Keep an adaptive audio stream close to the video clock."""
        if not self._split_audio or self.audio_player is None:
            return
        position = (self.player.position() if video_position is None
                    else int(video_position))
        if force or abs(self.audio_player.position() - position) > 500:
            self.audio_player.setPosition(max(0, position))

    def _on_error(self, _error, text=""):
        self._loading = False
        self._video_ready = False
        self._set_ready(False)
        self.message(text or "This video could not be previewed.")
        if text:
            self.errored.emit(text)

    def _on_audio_error(self, _error, text=""):
        if not self._split_audio:
            return
        # The video is still watchable, so this must not block the
        # transport; it is a silent preview, which the window already has
        # wording for.
        self._audio_ready = True
        self._recompute_ready()
        if text:
            self.errored.emit(f"Preview audio could not play: {text}")

    def _on_media_status(self, status):
        """Turn Qt's media status into something the window can show.

        Qt reports loading, buffering and stalling separately, and all
        three look identical from the outside: a black rectangle.  Saying
        which one it is turns a seemingly hung window into a wait with a
        reason.
        """
        S = QMediaPlayer.MediaStatus
        if status == S.LoadingMedia:
            self._video_ready = False
            self._loading = True
            self._set_ready(False)
            self.progress("Loading video", 0.40, 0.80)
        elif status == S.BufferingMedia:
            if self._loading:
                self.progress("Buffering video",
                              0.40 + 0.40 * self.player.bufferProgress(), 0.85)
            else:
                self._set_buffering("Buffering…")
        elif status == S.StalledMedia:
            if self._loading:
                self.progress("Waiting for data",
                              self.overlay.fraction() or 0.0,
                              self._load_ceiling)
            else:
                self._set_buffering("Waiting for data…")
        elif status in (S.LoadedMedia, S.BufferedMedia):
            self._set_buffering("")
            self._video_ready = True
            self._recompute_ready()
        elif status == S.InvalidMedia:
            self._loading = False
            self._video_ready = False
            self._set_ready(False)
            self.message("This video could not be previewed.")
        elif status == S.NoMedia:
            self._loading = False
            self._video_ready = False
            self._set_ready(False)
            self.idle()
        elif status == S.EndOfMedia:
            self._set_buffering("")

    def _on_audio_status(self, status):
        """The second stream, when the source is adaptive."""
        if not self._split_audio:
            return
        S = QMediaPlayer.MediaStatus
        if status in (S.LoadedMedia, S.BufferedMedia):
            self._audio_ready = True
            self._recompute_ready()
        elif status == S.InvalidMedia:
            # Let the video play without it rather than blocking on it.
            self._audio_ready = True
            self._recompute_ready()
        elif status == S.LoadingMedia:
            self._audio_ready = False

    def _on_buffer(self, fraction):
        if self._loading and self._busy_text.startswith(("Buffering", "Waiting")):
            self.progress("Buffering video", 0.40 + 0.40 * fraction, 0.85)
        elif self.buffer_label.isVisible() or not self.buffer_label.isHidden():
            if fraction < 1.0:
                self._set_buffering(f"Buffering {int(fraction * 100)}%")
            else:
                self._set_buffering("")
