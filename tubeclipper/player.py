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
    elif name == "forward":
        polygon(((11, 14), (11, 50), (32, 32)))
        polygon(((35, 14), (35, 50), (56, 32)))
    else:                                           # pragma: no cover
        raise ValueError(f"Unknown transport icon: {name}")

    painter.end()
    return QtGui.QIcon(canvas)


class PlayerPane(QtWidgets.QWidget):
    """Video surface plus transport, reporting position in seconds."""

    positionChanged = QtCore.Signal(float)
    durationChanged = QtCore.Signal(float)
    playingChanged = QtCore.Signal(bool)
    errored = QtCore.Signal(str)
    markIn = QtCore.Signal(float)
    markOut = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scale = 1.0
        self._seeking = False
        self._split_audio = False
        self._buttons = []
        self._transport_icons = {
            name: _transport_icon(name)
            for name in ("back", "previous", "play", "pause", "next", "forward")
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
        else:                                        # pragma: no cover
            self.video = None
            self.player = None
            self.audio = None
            self.audio_player = None
            self.split_audio = None
            self.placeholder.setText("Qt Multimedia is unavailable:\n" + MEDIA_ERROR)
            surface_layout.addWidget(self.placeholder)

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
        self.btn_back10 = self._button(
            icons["back"], "Back ten seconds", lambda: self.nudge(-10),
            width=60, text="10s")
        self.btn_back1 = self._button(
            icons["back"], "Back one second", lambda: self.nudge(-1),
            width=52, text="1s")
        self.btn_frame_back = self._button(
            icons["previous"], "Back one frame (Left)",
            lambda: self.nudge(-self._frame()))
        self.btn_play = self._button(
            icons["play"], "Play / pause (Space)", self.toggle, 44)
        self.btn_frame_fwd = self._button(
            icons["next"], "Forward one frame (Right)",
            lambda: self.nudge(self._frame()))
        self.btn_fwd1 = self._button(
            icons["forward"], "Forward one second", lambda: self.nudge(1),
            width=52, text="1s", icon_after=True)
        self.btn_fwd10 = self._button(
            icons["forward"], "Forward ten seconds", lambda: self.nudge(10),
            width=60, text="10s", icon_after=True)
        for b in (self.btn_back10, self.btn_back1, self.btn_frame_back,
                  self.btn_play, self.btn_frame_fwd, self.btn_fwd1,
                  self.btn_fwd10):
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
        """Load preview video and an optional separate audio stream."""
        if not HAVE_MEDIA:
            return
        self._fps = fps or 25.0
        self.player.stop()
        self.audio_player.stop()
        self._split_audio = bool(audio_url)
        self.placeholder.hide()
        self.video.show()
        self.player.setSource(QtCore.QUrl(url))
        self.audio_player.setSource(
            QtCore.QUrl(audio_url) if audio_url else QtCore.QUrl())
        self.set_enabled(True)

    def clear(self):
        if not HAVE_MEDIA:
            return
        self.player.stop()
        self.audio_player.stop()
        self.player.setSource(QtCore.QUrl())
        self.audio_player.setSource(QtCore.QUrl())
        self._split_audio = False
        self.video.hide()
        self.placeholder.show()
        self.set_enabled(False)

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

    def seek(self, seconds):
        if not HAVE_MEDIA or self.player is None:
            return
        self._seeking = True
        position = int(max(0.0, seconds) * 1000)
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
        if text:
            self.errored.emit(text)

    def _on_audio_error(self, _error, text=""):
        if self._split_audio and text:
            self.errored.emit(f"Preview audio could not play: {text}")
