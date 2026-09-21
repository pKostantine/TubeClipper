"""
ui.py -- TubeClipper's window.

The layout follows what the job actually is: find the moment, mark it,
say what you want out of it.  So the left column is the video and the
timeline at whatever size the window allows, and everything that is a
setting rather than a decision lives in the right column, where it can be
read without being in the way.

Clips are a list rather than a single in/out pair because the expensive
part of this workflow is finding the moments, not cutting them.  Once
you have watched through a stream and marked six things, exporting all
six should be one button, and the queue should carry on while you paste
the next link.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

from PySide6 import QtCore, QtGui, QtWidgets

from . import __version__, engine, ffmpegtool, formats, jobs, source
from .player import HAVE_MEDIA, MEDIA_ERROR, PlayerPane
from .timeline import TimelineView

APP_NAME = "TubeClipper"

#: Ctrl+= / Ctrl+- step through these; Ctrl+0 returns to 1.0.  On macOS Qt
#: maps ControlModifier onto Command, so the same code gives the right key.
SCALE_STEPS = (0.75, 0.85, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0, 2.5)

if sys.platform == "darwin":
    BASE_POINT_SIZE = 13.0
elif sys.platform.startswith("win"):
    BASE_POINT_SIZE = 9.0
else:
    BASE_POINT_SIZE = 10.0

_CHECK_URL = ""


def _check_icon_url():
    from . import resource_path
    path = resource_path("assets", "check.png")
    return path.replace("\\", "/") if os.path.exists(path) else ""


def style_sheet(k=1.0):
    """The whole stylesheet in one place, sized by a single factor."""
    def px(v):
        return max(1, int(round(v * k)))

    global _CHECK_URL
    if not _CHECK_URL:
        _CHECK_URL = _check_icon_url()

    return f"""
QWidget {{ background: #14161a; color: #d5dae2; }}
QGroupBox {{ border: 1px solid #262b34; border-radius: {px(6)}px;
            margin-top: {px(9)}px; padding-top: {px(9)}px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: {px(9)}px;
                   padding: 0 {px(4)}px; color: #8b95a4; font-weight: 600; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #1b1f27; border: 1px solid #2b313b; border-radius: {px(4)}px;
    padding: {px(4)}px {px(6)}px; selection-background-color: #1a56db; }}
QLineEdit:focus, QComboBox:focus {{ border-color: #3d6fd0; }}
QComboBox::drop-down {{ border: 0; width: {px(18)}px; }}
QComboBox QAbstractItemView {{ background: #1b1f27; border: 1px solid #2b313b;
    selection-background-color: #1a56db; }}
QLineEdit:read-only {{ color: #aab3c0; }}
QPushButton {{ background: #232935; border: 1px solid #313945;
              border-radius: {px(5)}px; padding: {px(6)}px {px(13)}px; }}
QPushButton:hover {{ background: #2b3341; }}
QPushButton:pressed {{ background: #1d2129; }}
QPushButton:disabled {{ color: #5a626e; background: #1a1e25;
                       border-color: #23272f; }}
QPushButton#primary {{ background: #1a56db; border-color: #2563eb;
                      color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: #2563eb; }}
QPushButton#primary:disabled {{ background: #23303f; color: #63708a;
                               border-color: #263243; }}
QPushButton:checked {{ background: #1a56db; border-color: #2563eb;
                      color: white; }}
QTableWidget {{ background: #12141a; gridline-color: #222732;
               border: 1px solid #262b34; border-radius: {px(6)}px; }}
QTableWidget::item:selected {{ background: #1a3a75; }}
QHeaderView::section {{ background: #1b1f27; border: 0;
    border-bottom: 1px solid #262b34; padding: {px(5)}px; color: #8b95a4;
    font-weight: 600; }}
QProgressBar {{ background: #1b1f27; border: 1px solid #2b313b;
    border-radius: {px(4)}px; text-align: center; height: {px(16)}px; }}
QProgressBar::chunk {{ background: #1a56db; border-radius: {px(3)}px; }}
QSlider::groove:horizontal {{ height: {px(4)}px; background: #2b313b;
    border-radius: {px(2)}px; }}
QSlider::handle:horizontal {{ background: #c8d0dc; width: {px(12)}px;
    margin: -{px(5)}px 0; border-radius: {px(6)}px; }}
QSlider::sub-page:horizontal {{ background: #1a56db;
    border-radius: {px(2)}px; }}
QCheckBox {{ spacing: {px(8)}px; }}
QCheckBox::indicator {{ width: {px(15)}px; height: {px(15)}px;
    border: 1px solid #3a4353; border-radius: {px(4)}px; background: #1b1f27; }}
QCheckBox::indicator:hover {{ border-color: #4a9eff; }}
QCheckBox::indicator:checked {{ background: #1a56db; border-color: #2563eb;
    image: url("{_CHECK_URL}"); }}
QCheckBox::indicator:checked:hover {{ background: #2563eb; }}
QRadioButton::indicator {{ width: {px(15)}px; height: {px(15)}px; }}
QLabel#value {{ color: #ffffff; font-weight: 600; }}
QLabel#hint {{ color: #7b8494; }}
QLabel#title {{ color: #ffffff; font-weight: 600; }}
QLabel#badge {{ background: #2a1f24; color: #e0555f; border-radius: {px(4)}px;
    padding: {px(1)}px {px(6)}px; font-weight: 600; }}
QSplitter::handle {{ background: #1e222a; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: #14161a; width: {px(12)}px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #333b49; min-height: {px(30)}px;
    border-radius: {px(5)}px; margin: {px(2)}px; }}
QScrollBar::handle:vertical:hover {{ background: #46536a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0;
    background: none; border: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none; }}
QScrollBar:horizontal {{ background: #14161a; height: {px(12)}px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #333b49; min-width: {px(30)}px;
    border-radius: {px(5)}px; margin: {px(2)}px; }}
QScrollBar::handle:horizontal:hover {{ background: #46536a; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0;
    background: none; border: none; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none; }}
QMenuBar {{ background: #14161a; }}
QMenuBar::item {{ padding: {px(4)}px {px(9)}px; }}
QMenuBar::item:selected {{ background: #232935; }}
QMenu {{ background: #1b1f27; border: 1px solid #2b313b;
    padding: {px(4)}px; }}
QMenu::item {{ padding: {px(5)}px {px(26)}px; }}
QMenu::item:selected {{ background: #1a56db; }}
QMenu::separator {{ height: 1px; background: #2b313b;
    margin: {px(4)}px {px(6)}px; }}
QStatusBar {{ background: #14161a; color: #8b95a4; }}
QToolTip {{ background: #1b1f27; color: #d5dae2; border: 1px solid #2b313b;
    padding: {px(4)}px; }}
"""


def _mono():
    font = QtGui.QFont()
    font.setStyleHint(QtGui.QFont.Monospace)
    for family in ("Consolas", "Menlo", "DejaVu Sans Mono", "Monospace"):
        if family in QtGui.QFontDatabase.families():
            font.setFamily(family)
            break
    return font


# --------------------------------------------------------------------------
# small pieces
# --------------------------------------------------------------------------

class TimecodeEdit(QtWidgets.QLineEdit):
    """A field that reads 90, 1:30 or 1:02:03.250 and writes back tidily.

    Typing is not the fast way to set a cut point, but it is the exact
    one, and it is the only way to paste a timestamp out of a chat message
    or a chapter list -- which is where a lot of clips actually start.
    """

    committed = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(_mono())
        self.setAlignment(QtCore.Qt.AlignCenter)
        self._value = 0.0
        self.editingFinished.connect(self._commit)

    def value(self):
        return self._value

    def set_value(self, seconds, announce=False):
        self._value = max(0.0, float(seconds or 0.0))
        self.setText(source.format_timecode(self._value))
        if announce:
            self.committed.emit(self._value)

    def _commit(self):
        parsed = source.parse_timecode(self.text())
        if parsed is None:
            self.setText(source.format_timecode(self._value))
            return
        self._value = max(0.0, parsed)
        self.setText(source.format_timecode(self._value))
        self.committed.emit(self._value)


class SettingsDialog(QtWidgets.QDialog):
    """The handful of things that are neither per-clip nor per-export."""

    BROWSERS = ("", "chrome", "edge", "firefox", "brave", "opera", "vivaldi", "safari")

    def __init__(self, parent, values):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)
        form = QtWidgets.QFormLayout(self)
        form.setSpacing(10)

        self.cookies = QtWidgets.QComboBox()
        self.cookies.addItem("None — signed out", "")
        for name in self.BROWSERS[1:]:
            self.cookies.addItem(name.capitalize(), name)
        index = self.cookies.findData(values.get("cookies", ""))
        self.cookies.setCurrentIndex(max(0, index))
        form.addRow("Sign-in cookies from", self.cookies)
        note = QtWidgets.QLabel(
            "Age-restricted and members-only videos need a signed-in session. "
            "Nothing is copied out of the browser except the cookies for this "
            "one request.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        form.addRow("", note)

        self.crf = QtWidgets.QSpinBox()
        self.crf.setRange(0, 51)
        self.crf.setValue(int(values.get("crf", 18)))
        self.crf.setToolTip("Lower is better quality and a bigger file. "
                            "18 is visually lossless for H.264.")
        form.addRow("Encode quality (CRF)", self.crf)

        self.gif_fps = QtWidgets.QSpinBox()
        self.gif_fps.setRange(5, 30)
        self.gif_fps.setValue(int(values.get("gif_fps", 15)))
        form.addRow("GIF frame rate", self.gif_fps)

        self.gif_width = QtWidgets.QSpinBox()
        self.gif_width.setRange(120, 1280)
        self.gif_width.setSingleStep(40)
        self.gif_width.setValue(int(values.get("gif_width", 480)))
        form.addRow("GIF width (px)", self.gif_width)

        size = engine.cache_size()
        row = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(f"{size / 1048576:.0f} MB held")
        label.setObjectName("hint")
        clear = QtWidgets.QPushButton("Empty cache")
        clear.clicked.connect(lambda: (engine.clear_cache(),
                                       label.setText("0 MB held")))
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(clear)
        form.addRow("Downloaded videos", row)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self):
        return {
            "cookies": self.cookies.currentData(),
            "crf": self.crf.value(),
            "gif_fps": self.gif_fps.value(),
            "gif_width": self.gif_width.value(),
        }


class ShortcutsDialog(QtWidgets.QDialog):
    ROWS = [
        ("Space", "Play / pause"),
        ("I", "Set the in point at the playhead"),
        ("O", "Set the out point at the playhead"),
        ("Ctrl+K", "Add the current selection as a clip"),
        ("Left / Right", "Step one frame"),
        ("Shift+Left / Right", "Step one second"),
        ("J / K / L", "Rewind, pause, forward"),
        ("F", "Zoom the timeline to the selection"),
        ("Shift+F", "Zoom out to the whole video"),
        ("Scroll on timeline", "Zoom around the pointer"),
        ("Shift+scroll", "Pan"),
        ("Middle-drag", "Pan"),
        ("Ctrl+L", "Focus the link box"),
        ("Ctrl+E", "Export the selection"),
        ("Ctrl+Shift+E", "Export every clip"),
        ("Ctrl+= / Ctrl+−", "Scale the interface"),
        ("Ctrl+0", "Reset the interface scale"),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        layout = QtWidgets.QVBoxLayout(self)
        table = QtWidgets.QTableWidget(len(self.ROWS), 2)
        table.setHorizontalHeaderLabels(["Key", "Does"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        for row, (key, what) in enumerate(self.ROWS):
            item = QtWidgets.QTableWidgetItem(key)
            item.setFont(_mono())
            table.setItem(row, 0, item)
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(what))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumSize(460, 480)
        layout.addWidget(table)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


# --------------------------------------------------------------------------
# the window
# --------------------------------------------------------------------------

class MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.settings = QtCore.QSettings("TubeClipper", "TubeClipper")

        self.source = None            # source.Source
        self.clips = []               # engine.Clip
        self.jobs = {}                # ident -> jobs.Job
        self._next_ident = 1
        self._thumb_task = None
        self._probe_task = None
        self._ffmpeg_task = None
        self._preview_stream = None
        self._thumb_dir = ""
        self._local_path = ""         # whole-video download for this source
        self._scalables = []
        self._prefs = {
            "cookies": self.settings.value("cookies", "", str),
            "crf": self.settings.value("crf", 18, int),
            "gif_fps": self.settings.value("gif_fps", 15, int),
            "gif_width": self.settings.value("gif_width", 480, int),
        }

        try:
            self.scale = float(self.settings.value("scale", 1.0))
        except (TypeError, ValueError):
            self.scale = 1.0

        self.pool = QtCore.QThreadPool.globalInstance()
        self.runner = jobs.Runner(self)
        self.runner.started_job.connect(self._job_started)
        self.runner.progressed.connect(self._job_progress)
        self.runner.finished_job.connect(self._job_finished)
        self.runner.failed_job.connect(self._job_failed)
        self.runner.cancelled_job.connect(self._job_cancelled)
        self.runner.became_idle.connect(self.runner.clear_cancel_all)
        self.runner.start()

        self._build()
        self._sync_range_fields()
        self._refresh_clips()
        self._menus()
        self._shortcuts()
        self.apply_scale(self.scale)

        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1380, 900)

        self._thumb_timer = QtCore.QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(320)
        self._thumb_timer.timeout.connect(self._fetch_thumbs)
        self._thumb_request = None

        QtCore.QTimer.singleShot(200, self._check_tools)

    # -- construction ----------------------------------------------------

    def _fix(self, widget, w=None, h=None):
        self._scalables.append((widget, w, h))
        return widget

    def _build(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(12, 10, 12, 8)
        outer.setSpacing(9)

        outer.addLayout(self._link_row())
        outer.addWidget(self._info_strip())

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self._left_column())
        splitter.addWidget(self._right_column())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([840, 500])
        self.splitter = splitter
        outer.addWidget(splitter, 1)

        self.status = self.statusBar()
        self.status.showMessage("Paste a YouTube link to begin.")

    def _link_row(self):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)

        label = QtWidgets.QLabel("Link")
        label.setObjectName("hint")
        row.addWidget(label)

        self.url_edit = QtWidgets.QLineEdit()
        self.url_edit.setPlaceholderText(
            "https://www.youtube.com/watch?v=…   (a bare video id works too)")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self.load_link)
        row.addWidget(self.url_edit, 1)

        self.paste_btn = QtWidgets.QPushButton("Paste")
        self.paste_btn.setToolTip("Paste the clipboard and load it")
        self.paste_btn.clicked.connect(self.paste_and_load)
        row.addWidget(self.paste_btn)

        self.load_btn = QtWidgets.QPushButton("Load")
        self.load_btn.setObjectName("primary")
        self.load_btn.clicked.connect(self.load_link)
        row.addWidget(self.load_btn)
        return row

    def _info_strip(self):
        frame = QtWidgets.QFrame()
        frame.setStyleSheet("QFrame { background:#171b22; border:1px solid #262b34;"
                            "border-radius:6px; }")
        row = QtWidgets.QHBoxLayout(frame)
        row.setContentsMargins(8, 6, 10, 6)
        row.setSpacing(10)

        self.thumb = QtWidgets.QLabel()
        self.thumb.setFixedSize(112, 63)
        self.thumb.setStyleSheet("background:#0d0f13; border-radius:4px;")
        self.thumb.setAlignment(QtCore.Qt.AlignCenter)
        self._fix(self.thumb, 112, 63)
        row.addWidget(self.thumb)

        column = QtWidgets.QVBoxLayout()
        column.setSpacing(2)
        self.title_label = QtWidgets.QLabel("Nothing loaded")
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(False)
        self.title_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        column.addWidget(self.title_label)

        meta = QtWidgets.QHBoxLayout()
        meta.setSpacing(8)
        self.meta_label = QtWidgets.QLabel("")
        self.meta_label.setObjectName("hint")
        meta.addWidget(self.meta_label)
        self.live_badge = QtWidgets.QLabel("LIVE")
        self.live_badge.setObjectName("badge")
        self.live_badge.hide()
        meta.addWidget(self.live_badge)
        meta.addStretch(1)
        column.addLayout(meta)
        row.addLayout(column, 1)
        return frame

    def _left_column(self):
        panel = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        self.player = PlayerPane()
        self.player.positionChanged.connect(self._player_moved)
        self.player.markIn.connect(self.set_in)
        self.player.markOut.connect(self.set_out)
        self.player.errored.connect(self._player_error)
        column.addWidget(self.player, 1)

        self.timeline = TimelineView()
        self.timeline.rangeChanged.connect(self._range_changed)
        self.timeline.seeked.connect(self.player.seek)
        self.timeline.thumbsWanted.connect(self._want_thumbs)
        column.addWidget(self.timeline)

        column.addLayout(self._range_row())
        return panel

    def _range_row(self):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)

        for name, caption in (("in", "In"), ("out", "Out")):
            box = QtWidgets.QVBoxLayout()
            box.setSpacing(2)
            tag = QtWidgets.QLabel(caption)
            tag.setObjectName("hint")
            field = TimecodeEdit()
            self._fix(field, 108)
            field.setFixedWidth(108)
            box.addWidget(tag)
            box.addWidget(field)
            row.addLayout(box)
            setattr(self, f"{name}_edit", field)
        self.in_edit.committed.connect(lambda t: self.set_in(t, seek=False))
        self.out_edit.committed.connect(lambda t: self.set_out(t, seek=False))

        box = QtWidgets.QVBoxLayout()
        box.setSpacing(2)
        tag = QtWidgets.QLabel("Length")
        tag.setObjectName("hint")
        self.dur_label = QtWidgets.QLabel("0:00.000")
        self.dur_label.setObjectName("value")
        self.dur_label.setFont(_mono())
        self.dur_label.setAlignment(QtCore.Qt.AlignCenter)
        self._fix(self.dur_label, 108)
        self.dur_label.setFixedWidth(108)
        box.addWidget(tag)
        box.addWidget(self.dur_label)
        row.addLayout(box)

        row.addSpacing(6)
        zoom_box = QtWidgets.QVBoxLayout()
        zoom_box.setSpacing(2)
        zoom_box.addWidget(QtWidgets.QLabel(""))
        zoom_row = QtWidgets.QHBoxLayout()
        zoom_row.setSpacing(4)
        for text, tip, fn in (
                ("Fit clip", "Zoom the timeline to the selection (F)",
                 lambda: self.timeline.fit_selection()),
                ("Fit all", "Zoom out to the whole video (Shift+F)",
                 lambda: self.timeline.fit())):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            zoom_row.addWidget(b)
        zoom_box.addLayout(zoom_row)
        row.addLayout(zoom_box)

        row.addStretch(1)

        add_box = QtWidgets.QVBoxLayout()
        add_box.setSpacing(2)
        add_box.addWidget(QtWidgets.QLabel(""))
        self.add_clip_btn = QtWidgets.QPushButton("Add clip  (Ctrl+K)")
        self.add_clip_btn.setToolTip("Keep this selection in the clip list")
        self.add_clip_btn.clicked.connect(self.add_clip)
        add_box.addWidget(self.add_clip_btn)
        row.addLayout(add_box)
        return row

    def _right_column(self):
        area = QtWidgets.QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        inner = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(inner)
        column.setContentsMargins(0, 0, 4, 0)
        column.setSpacing(10)
        column.addWidget(self._clips_group())
        column.addWidget(self._export_group())
        column.addWidget(self._queue_group(), 1)
        area.setWidget(inner)
        return area

    def _clips_group(self):
        group = QtWidgets.QGroupBox("Clips")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(7)

        self.clip_table = QtWidgets.QTableWidget(0, 4)
        self.clip_table.setHorizontalHeaderLabels(["Name", "In", "Out", "Length"])
        self.clip_table.verticalHeader().setVisible(False)
        self.clip_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.clip_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        header = self.clip_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)
        self.clip_table.setMinimumHeight(120)
        self._fix(self.clip_table, None, 150)
        self.clip_table.itemChanged.connect(self._clip_renamed)
        self.clip_table.itemSelectionChanged.connect(self._clip_selected)
        self.clip_table.doubleClicked.connect(lambda _i: self.use_selected_clip())
        layout.addWidget(self.clip_table)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        for text, tip, fn in (
                ("Add", "Add the current selection (Ctrl+K)", self.add_clip),
                ("Use", "Put this clip back on the timeline", self.use_selected_clip),
                ("Remove", "Delete the selected clips", self.remove_clips),
                ("Clear", "Empty the list", self.clear_clips)):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)
        return group

    def _export_group(self):
        group = QtWidgets.QGroupBox("Export")
        form = QtWidgets.QVBoxLayout(group)
        form.setSpacing(8)

        kind = QtWidgets.QHBoxLayout()
        kind.setSpacing(14)
        self.kind_video = QtWidgets.QRadioButton("Video")
        self.kind_audio = QtWidgets.QRadioButton("Audio only")
        self.kind_video.setChecked(True)
        self.kind_video.toggled.connect(self._kind_changed)
        self.kind_audio.toggled.connect(self._kind_changed)
        kind.addWidget(self.kind_video)
        kind.addWidget(self.kind_audio)
        kind.addStretch(1)
        form.addLayout(kind)

        grid = QtWidgets.QFormLayout()
        grid.setSpacing(7)
        grid.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.currentIndexChanged.connect(self._format_changed)
        grid.addRow("Format", self.format_combo)

        self.quality_combo = QtWidgets.QComboBox()
        self.quality_combo.currentIndexChanged.connect(self._update_summary)
        grid.addRow("Quality", self.quality_combo)

        mode = QtWidgets.QHBoxLayout()
        mode.setSpacing(14)
        self.mode_exact = QtWidgets.QRadioButton("Exact")
        self.mode_exact.setToolTip(
            "Cuts on the frame you asked for. Re-encodes, so it takes about "
            "as long as the clip is.")
        self.mode_fast = QtWidgets.QRadioButton("Fast")
        self.mode_fast.setToolTip(
            "No re-encode: instant, and bit-for-bit what YouTube stored. "
            "The in point snaps back to the nearest keyframe, which can be "
            "a few seconds early.")
        self.mode_exact.setChecked(True)
        self.mode_exact.toggled.connect(self._update_summary)
        mode.addWidget(self.mode_exact)
        mode.addWidget(self.mode_fast)
        mode.addStretch(1)
        grid.addRow("Trim", mode)

        self.fetch_combo = QtWidgets.QComboBox()
        self.fetch_combo.addItem("Stream just this section", "section")
        self.fetch_combo.addItem("Download the whole video first", "whole")
        self.fetch_combo.setToolTip(
            "Streaming reads only the part you asked for, so a two-minute "
            "clip out of a six-hour stream takes seconds. Downloading is "
            "worth it when several clips come out of one video, or when the "
            "connection keeps dropping.")
        self.fetch_combo.currentIndexChanged.connect(self._update_summary)
        grid.addRow("Fetch", self.fetch_combo)

        form.addLayout(grid)

        out_row = QtWidgets.QHBoxLayout()
        out_row.setSpacing(6)
        self.out_dir_edit = QtWidgets.QLineEdit(self._default_out_dir())
        self.out_dir_edit.setReadOnly(True)
        self.out_dir_edit.setToolTip("Where finished clips are written")
        out_row.addWidget(self.out_dir_edit, 1)
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self.choose_out_dir)
        out_row.addWidget(browse)
        open_btn = QtWidgets.QPushButton("Open")
        open_btn.clicked.connect(self.open_out_dir)
        out_row.addWidget(open_btn)
        form.addLayout(out_row)

        self.summary = QtWidgets.QLabel("")
        self.summary.setObjectName("hint")
        self.summary.setWordWrap(True)
        form.addWidget(self.summary)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(6)
        self.export_btn = QtWidgets.QPushButton("Export selection  (Ctrl+E)")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self.export_selection)
        self.export_all_btn = QtWidgets.QPushButton("Export all clips")
        self.export_all_btn.clicked.connect(self.export_all)
        buttons.addWidget(self.export_btn, 1)
        buttons.addWidget(self.export_all_btn)
        form.addLayout(buttons)

        self._populate_formats()
        return group

    def _queue_group(self):
        group = QtWidgets.QGroupBox("Queue")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(7)

        self.queue_table = QtWidgets.QTableWidget(0, 3)
        self.queue_table.setHorizontalHeaderLabels(["Job", "Status", "Progress"])
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.queue_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        self.queue_table.setColumnWidth(2, 120)
        self.queue_table.setMinimumHeight(150)
        self._fix(self.queue_table, None, 190)
        self.queue_table.doubleClicked.connect(self._reveal_job)
        layout.addWidget(self.queue_table, 1)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        for text, tip, fn in (
                ("Cancel", "Stop the selected job", self.cancel_selected_job),
                ("Cancel all", "Stop everything queued", self.cancel_all_jobs),
                ("Clear finished", "Tidy the list", self.clear_finished)):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        layout.addLayout(row)
        return group

    # -- menus and keys --------------------------------------------------

    def _act(self, menu, text, shortcut, fn):
        """Add a menu item.

        Built by hand rather than with the convenience overload, because
        which of ``addAction``'s six signatures PySide binds depends on the
        version, and a menu that silently loses its shortcuts is a bad way
        to find that out.
        """
        action = QtGui.QAction(text, self)
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False: fn())
        menu.addAction(action)
        return action

    def _menus(self):
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        self._act(file_menu, "&Paste link and load", "Ctrl+Shift+V", self.paste_and_load)
        self._act(file_menu, "Focus the &link box", "Ctrl+L",
                  lambda: (self.url_edit.setFocus(), self.url_edit.selectAll()))
        file_menu.addSeparator()
        self._act(file_menu, "Choose &output folder…", "", self.choose_out_dir)
        self._act(file_menu, "Open output folder", "", self.open_out_dir)
        file_menu.addSeparator()
        self._act(file_menu, "&Settings…", "", self.open_settings)
        file_menu.addSeparator()
        self._act(file_menu, "&Quit", "Ctrl+Q", self.close)

        clip_menu = bar.addMenu("&Clip")
        self._act(clip_menu, "Set &in point", "I", lambda: self.set_in(self.player.position()))
        self._act(clip_menu, "Set &out point", "O", lambda: self.set_out(self.player.position()))
        clip_menu.addSeparator()
        self._act(clip_menu, "&Add clip", "Ctrl+K", self.add_clip)
        self._act(clip_menu, "&Remove selected clips", "Del", self.remove_clips)
        clip_menu.addSeparator()
        self._act(clip_menu, "&Fit timeline to clip", "F",
                  lambda: self.timeline.fit_selection())
        self._act(clip_menu, "Fit timeline to &whole video", "Shift+F",
                  lambda: self.timeline.fit())

        export_menu = bar.addMenu("&Export")
        self._act(export_menu, "Export &selection", "Ctrl+E", self.export_selection)
        self._act(export_menu, "Export &all clips", "Ctrl+Shift+E", self.export_all)
        export_menu.addSeparator()
        self._act(export_menu, "&Cancel everything queued", "", self.cancel_all_jobs)

        view_menu = bar.addMenu("&View")
        self._act(view_menu, "Zoom &in", "Ctrl+=", lambda: self.step_scale(+1))
        self._act(view_menu, "Zoom &out", "Ctrl+-", lambda: self.step_scale(-1))
        self._act(view_menu, "&Reset zoom", "Ctrl+0", lambda: self.apply_scale(1.0))

        help_menu = bar.addMenu("&Help")
        self._act(help_menu, "&Keyboard shortcuts", "", lambda: ShortcutsDialog(self).exec())
        self._act(help_menu, "&ffmpeg status…", "", self.show_ffmpeg_status)
        self._act(help_menu, "&About " + APP_NAME, "", self.show_about)

    def _shortcuts(self):
        def add(sequence, fn):
            action = QtGui.QAction(self)
            action.setShortcut(QtGui.QKeySequence(sequence))
            action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
            action.triggered.connect(fn)
            self.addAction(action)
            return action

        add("Space", self._toggle_play)
        add("J", lambda: self.player.nudge(-5))
        add("K", self.player.pause)
        add("L", lambda: self.player.nudge(5))
        add("Left", lambda: self.player.nudge(-self.player._frame()))
        add("Right", lambda: self.player.nudge(self.player._frame()))
        add("Shift+Left", lambda: self.player.nudge(-1))
        add("Shift+Right", lambda: self.player.nudge(1))

    def _toggle_play(self):
        # Space belongs to the text box while the user is typing in it.
        focus = QtWidgets.QApplication.focusWidget()
        if isinstance(focus, QtWidgets.QLineEdit):
            return
        self.player.toggle()

    # -- scaling ---------------------------------------------------------

    def keyPressEvent(self, event):
        if event.modifiers() & QtCore.Qt.ControlModifier:
            key = event.key()
            if key in (QtCore.Qt.Key_Minus, QtCore.Qt.Key_Underscore):
                self.step_scale(-1)
                event.accept()
                return
            if key in (QtCore.Qt.Key_Plus, QtCore.Qt.Key_Equal):
                self.step_scale(+1)
                event.accept()
                return
            if key == QtCore.Qt.Key_0:
                self.apply_scale(1.0)
                event.accept()
                return
        super().keyPressEvent(event)

    def step_scale(self, direction):
        steps = SCALE_STEPS
        index = min(range(len(steps)), key=lambda i: abs(steps[i] - self.scale))
        index = max(0, min(len(steps) - 1, index + direction))
        self.apply_scale(steps[index])

    def apply_scale(self, k):
        self.scale = float(k)
        app = QtWidgets.QApplication.instance()
        font = app.font()
        font.setPointSizeF(BASE_POINT_SIZE * self.scale)
        app.setFont(font)
        app.setStyleSheet(style_sheet(self.scale))
        for widget, w, h in self._scalables:
            if w:
                widget.setFixedWidth(int(round(w * self.scale)))
            if h:
                widget.setMinimumHeight(int(round(h * self.scale)))
        self.player.set_scale(self.scale)
        self.timeline.set_scale(self.scale)
        self.settings.setValue("scale", self.scale)
        self.status.showMessage(f"Interface at {int(self.scale * 100)}%", 1800)

    # -- loading a link --------------------------------------------------

    def paste_and_load(self):
        text = QtWidgets.QApplication.clipboard().text().strip()
        if text:
            self.url_edit.setText(text)
        self.load_link()

    def load_link(self):
        text = self.url_edit.text().strip()
        if not text:
            self.status.showMessage("Nothing to load.", 3000)
            return
        if not source.looks_like_url(text):
            self._warn("That does not look like a link",
                       "Paste a YouTube URL, or an eleven-character video id.")
            return

        self.load_btn.setEnabled(False)
        self.load_btn.setText("Loading…")
        self.status.showMessage("Reading the link…")

        cookies = self._prefs.get("cookies") or None
        task = jobs.Task(source.probe, text, cookies)
        task.signals.done.connect(self._loaded)
        task.signals.failed.connect(self._load_failed)
        self._probe_task = task
        self.pool.start(task)

    def _loaded(self, src):
        self.load_btn.setEnabled(True)
        self.load_btn.setText("Load")
        self.source = src
        self._local_path = ""
        self._preview_stream = None
        self.clips.clear()
        self._refresh_clips()

        self.title_label.setText(src.title)
        pieces = [p for p in (src.uploader, src.display_duration) if p]
        if src.heights:
            pieces.append(f"up to {src.heights[0]}p")
        if src.fps:
            pieces.append(f"{src.fps:g} fps")
        self.meta_label.setText("  ·  ".join(pieces))
        self.live_badge.setVisible(bool(src.is_live))

        if src.is_live:
            self.status.showMessage(
                "This stream is still live — only the part already broadcast "
                "can be clipped.", 8000)

        self.timeline.set_duration(src.duration)
        self._sync_range_fields()
        self._populate_quality()
        self._update_summary()
        self._load_poster(src.thumbnail)

        try:
            stream, note = source.preview_stream(src.info)
        except Exception as exc:
            self.player.clear()
            self.status.showMessage(f"No preview available: {exc}", 8000)
        else:
            self._preview_stream = stream
            self.player.load(stream.url, src.fps or stream.fps)
            if note:
                self.status.showMessage(note, 8000)
            else:
                self.status.showMessage(
                    f"Loaded. {src.display_duration} — mark a clip and export.",
                    6000)

        self._want_thumbs(*self.timeline.view(), 12)

    def _load_failed(self, message):
        self.load_btn.setEnabled(True)
        self.load_btn.setText("Load")
        self.status.showMessage("Could not read that link.", 5000)
        self._warn("Could not read that link", message)

    def _load_poster(self, url):
        if not url:
            self.thumb.clear()
            return

        def fetch():
            import urllib.request
            with urllib.request.urlopen(url, timeout=20) as response:
                return response.read()

        task = jobs.Task(fetch)
        task.signals.done.connect(self._poster_ready)
        self.pool.start(task)

    def _poster_ready(self, data):
        image = QtGui.QPixmap()
        if image.loadFromData(data):
            self.thumb.setPixmap(image.scaled(
                self.thumb.size(), QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation))

    def _player_error(self, text):
        self.status.showMessage(f"Preview: {text}", 8000)

    # -- range and timeline ---------------------------------------------

    def _player_moved(self, seconds):
        self.timeline.set_playhead(seconds)

    def _range_changed(self, start, end):
        self._sync_range_fields()

    def _sync_range_fields(self):
        start, end = self.timeline.range()
        self.in_edit.set_value(start)
        self.out_edit.set_value(end)
        self.dur_label.setText(source.format_timecode(max(0.0, end - start)))
        ready = self.source is not None and end > start
        self.add_clip_btn.setEnabled(ready)
        self.export_btn.setEnabled(ready)

    def set_in(self, seconds, seek=True):
        if self.source is None:
            return
        _start, end = self.timeline.range()
        value = max(0.0, min(float(seconds), max(0.0, end - 0.001)))
        self.timeline.set_range(value, end)
        if seek:
            self.player.seek(value)

    def set_out(self, seconds, seek=True):
        if self.source is None:
            return
        start, _end = self.timeline.range()
        value = min(self.timeline.duration(),
                    max(float(seconds), start + 0.001))
        self.timeline.set_range(start, value)
        if seek:
            self.player.seek(value)

    # -- filmstrip -------------------------------------------------------

    def _want_thumbs(self, start, end, count):
        if self.source is None or self._preview_stream is None:
            return
        self._thumb_request = (float(start), float(end), int(count),
                               self.source.video_id)
        self._thumb_timer.start()

    def _fetch_thumbs(self):
        request = self._thumb_request
        stream = self._preview_stream
        if not request or stream is None:
            return
        start, end, count, video_id = request
        if end <= start or count <= 0:
            return

        if self._thumb_task is not None:
            self._thumb_task.cancel()

        if not self._thumb_dir:
            self._thumb_dir = tempfile.mkdtemp(prefix="tubeclipper-thumbs-")
        view_key = f"{video_id}-{start:.3f}-{end:.3f}-{count}"
        out_dir = os.path.join(self._thumb_dir,
                               engine.safe_name(view_key, limit=80))
        step = (end - start) / max(1, count)
        times = [start + i * step for i in range(count)]

        task = None

        def make():
            return engine.grab_frames(
                stream.url, times, out_dir, stream.headers,
                cancel=lambda: task.cancelled())

        task = jobs.Task(make)
        task.signals.done.connect(
            lambda made, key=view_key: self._thumbs_ready(key, made))
        self._thumb_task = task
        self.pool.start(task)

    def _thumbs_ready(self, key, made):
        request = self._thumb_request
        if not request:
            return
        current = f"{request[3]}-{request[0]:.3f}-{request[1]:.3f}-{request[2]}"
        if key != current:
            return
        thumbs = []
        for when, path in made:
            pix = QtGui.QPixmap(path)
            if not pix.isNull():
                thumbs.append((when, pix))
        self.timeline.set_thumbs(thumbs)

    # -- clips -----------------------------------------------------------

    def add_clip(self):
        if self.source is None:
            self._warn("No video loaded", "Load a YouTube link first.")
            return
        start, end = self.timeline.range()
        clip = engine.Clip(start, end, f"Clip {len(self.clips) + 1}")
        if not clip.valid(self.source.duration):
            self._warn("Nothing to add", "The in point must be before the out point.")
            return
        self.clips.append(clip)
        self._refresh_clips(select=len(self.clips) - 1)
        self.status.showMessage(
            f"Added {clip.name} ({source.format_timecode(clip.duration)}).", 3000)

    def _refresh_clips(self, select=None):
        table = self.clip_table
        table.blockSignals(True)
        table.setRowCount(len(self.clips))
        for row, clip in enumerate(self.clips):
            name = QtWidgets.QTableWidgetItem(clip.name or f"Clip {row + 1}")
            name.setData(QtCore.Qt.UserRole, row)
            table.setItem(row, 0, name)
            values = (source.format_timecode(clip.start),
                      source.format_timecode(clip.end),
                      source.format_timecode(clip.duration))
            for col, value in enumerate(values, 1):
                item = QtWidgets.QTableWidgetItem(value)
                item.setFont(_mono())
                item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                table.setItem(row, col, item)
        table.blockSignals(False)
        self.timeline.set_clips(
            [(clip.start, clip.end, clip.name) for clip in self.clips])
        self.export_all_btn.setEnabled(bool(self.clips))
        if select is not None and 0 <= select < table.rowCount():
            table.selectRow(select)

    def _clip_renamed(self, item):
        if item.column() != 0:
            return
        row = item.row()
        if not 0 <= row < len(self.clips):
            return
        name = item.text().strip() or f"Clip {row + 1}"
        self.clips[row].name = name
        if item.text() != name:
            item.setText(name)
        self.timeline.set_clips(
            [(clip.start, clip.end, clip.name) for clip in self.clips])

    def _clip_selected(self):
        rows = self.clip_table.selectionModel().selectedRows()
        if rows:
            clip = self.clips[rows[0].row()]
            self.status.showMessage(
                f"{clip.name}: {source.format_timecode(clip.start)} to "
                f"{source.format_timecode(clip.end)}", 2500)

    def use_selected_clip(self):
        rows = self.clip_table.selectionModel().selectedRows()
        if not rows:
            return
        clip = self.clips[rows[0].row()]
        self.timeline.set_range(clip.start, clip.end)
        self.timeline.fit_selection()
        self.player.seek(clip.start)

    def remove_clips(self):
        rows = sorted({i.row() for i in self.clip_table.selectionModel().selectedRows()},
                      reverse=True)
        for row in rows:
            if 0 <= row < len(self.clips):
                del self.clips[row]
        if rows:
            self._refresh_clips()

    def clear_clips(self):
        self.clips.clear()
        self._refresh_clips()

    # -- export choices --------------------------------------------------

    def _populate_formats(self):
        previous = self.format_combo.currentData()
        keys = formats.VIDEO_KEYS if self.kind_video.isChecked() else formats.AUDIO_KEYS
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        for key in keys:
            preset = formats.get(key)
            self.format_combo.addItem(preset.label, key)
        index = self.format_combo.findData(previous)
        if index < 0:
            preferred = "mp4" if self.kind_video.isChecked() else "wav"
            index = self.format_combo.findData(preferred)
        self.format_combo.setCurrentIndex(max(0, index))
        self.format_combo.blockSignals(False)
        self._format_changed()

    def _kind_changed(self, checked):
        if checked:
            self._populate_formats()

    def _format_changed(self, _index=None):
        key = self.format_combo.currentData()
        if not key:
            return
        preset = formats.get(key)
        is_gif = preset.kind == "gif"
        self.mode_fast.setEnabled(not is_gif)
        if is_gif:
            self.mode_exact.setChecked(True)
        self._populate_quality()
        self._update_summary()

    def _populate_quality(self):
        key = self.format_combo.currentData()
        if not key:
            return
        preset = formats.get(key)
        previous = self.quality_combo.currentData()
        self.quality_combo.blockSignals(True)
        self.quality_combo.clear()

        if preset.kind == "video":
            available = set(self.source.heights if self.source else ())
            self.quality_combo.addItem("Best available", None)
            for height in formats.HEIGHT_CHOICES[1:]:
                label = f"Up to {height}p"
                if available and not any(h <= height for h in available):
                    label += " (source may be lower)"
                self.quality_combo.addItem(label, height)
        elif preset.kind == "audio" and preset.key in ("mp3", "m4a", "opus", "ogg", "aac"):
            for abr in formats.ABR_CHOICES:
                self.quality_combo.addItem(f"{abr} kbit/s", abr)
        elif preset.kind == "gif":
            self.quality_combo.addItem(
                f"{self._prefs['gif_width']} px · {self._prefs['gif_fps']} fps", None)
        else:
            self.quality_combo.addItem("Source quality", None)

        index = self.quality_combo.findData(previous)
        if index < 0:
            if preset.kind == "audio":
                index = self.quality_combo.findData(192)
            elif preset.kind == "video":
                index = self.quality_combo.findData(1080)
        self.quality_combo.setCurrentIndex(max(0, index))
        self.quality_combo.blockSignals(False)

    def _quality(self):
        preset = formats.get(self.format_combo.currentData())
        value = self.quality_combo.currentData()
        quality = formats.Quality(crf=int(self._prefs.get("crf", 18)))
        if preset.kind == "video":
            quality.height = value
        elif preset.kind == "audio" and isinstance(value, int):
            quality.abr = value
        elif preset.kind == "gif":
            quality.fps = int(self._prefs.get("gif_fps", 15))
            quality.width = int(self._prefs.get("gif_width", 480))
        return quality

    def _update_summary(self, _value=None):
        key = self.format_combo.currentData()
        if not key:
            return
        preset = formats.get(key)
        fast = self.mode_fast.isChecked() and preset.kind != "gif"
        text = formats.describe(preset, self._quality(), fast)
        if self.fetch_combo.currentData() == "whole":
            text += " · downloads once, then cuts locally"
        if preset.note:
            text += f"\n{preset.note}"
        self.summary.setText(text)

    def _default_out_dir(self):
        saved = self.settings.value("out_dir", "", str)
        if saved:
            return saved
        videos = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.MoviesLocation)
        return videos or os.path.expanduser("~/Videos")

    def choose_out_dir(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose export folder", self.out_dir_edit.text())
        if path:
            self.out_dir_edit.setText(path)
            self.settings.setValue("out_dir", path)

    def open_out_dir(self):
        path = self.out_dir_edit.text().strip()
        if path:
            os.makedirs(path, exist_ok=True)
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    # -- queue -----------------------------------------------------------

    def export_selection(self):
        start, end = self.timeline.range()
        self._queue_exports([engine.Clip(start, end, "")])

    def export_all(self):
        if not self.clips:
            self._warn("No clips to export",
                       "Add selections to the clip list first, or use Export selection.")
            return
        self._queue_exports(list(self.clips))

    def _queue_exports(self, clips):
        if self.source is None:
            self._warn("No video loaded", "Load a YouTube link first.")
            return
        valid = [c for c in clips if c.valid(self.source.duration)]
        if not valid:
            self._warn("Nothing to export", "The in point must be before the out point.")
            return
        if not ffmpegtool.have_ffmpeg():
            self._offer_ffmpeg()
            return

        preset = formats.get(self.format_combo.currentData())
        quality = self._quality()
        fast = self.mode_fast.isChecked() and preset.kind != "gif"
        whole = self.fetch_combo.currentData() == "whole"
        audio_only = not preset.has_video
        local = ""
        if whole:
            local = engine.cached_download(
                self.source.video_id, quality.height, audio_only=audio_only)
            self._local_path = local

        specs = []
        for clip in valid:
            specs.append(engine.ExportSpec(
                url=self.source.url,
                title=self.source.title,
                video_id=self.source.video_id,
                clip=engine.Clip(clip.start, clip.end, clip.name),
                preset_key=preset.key,
                quality=formats.Quality(**vars(quality)),
                fast=fast,
                out_dir=self.out_dir_edit.text().strip(),
                local_path=local,
                require_local=bool(whole and not local),
                info=self.source.info,
                cookies_from_browser=self._prefs.get("cookies", ""),
            ))

        queued = 0
        if whole and not local:
            download = jobs.Job(
                ident=self._take_ident(), kind="download",
                label=f"Download · {self.source.title}",
                spec={
                    "url": self.source.url,
                    "video_id": self.source.video_id,
                    "height": quality.height,
                    "audio_only": audio_only,
                    "cookies": self._prefs.get("cookies", ""),
                    "dependents": specs,
                })
            self._submit(download)
            queued += 1

        for spec in specs:
            label = spec.clip.name or engine.default_name(spec)
            job = jobs.Job(ident=self._take_ident(), label=label, spec=spec)
            self._submit(job)
            queued += 1

        self.status.showMessage(
            f"Queued {queued} job{'s' if queued != 1 else ''}.", 4000)

    def _take_ident(self):
        ident = self._next_ident
        self._next_ident += 1
        return ident

    def _submit(self, job):
        self.jobs[job.ident] = job
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        label = QtWidgets.QTableWidgetItem(job.label)
        label.setData(QtCore.Qt.UserRole, job.ident)
        self.queue_table.setItem(row, 0, label)
        self.queue_table.setItem(row, 1, QtWidgets.QTableWidgetItem("Waiting"))
        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        self.queue_table.setCellWidget(row, 2, bar)
        self.runner.submit(job)

    def _row_for_job(self, ident):
        for row in range(self.queue_table.rowCount()):
            item = self.queue_table.item(row, 0)
            if item and item.data(QtCore.Qt.UserRole) == ident:
                return row
        return -1

    def _job_started(self, ident):
        job = self.jobs.get(ident)
        if job:
            job.status = jobs.RUNNING
        row = self._row_for_job(ident)
        if row >= 0:
            self.queue_table.item(row, 1).setText("Working")

    def _job_progress(self, ident, fraction, text):
        job = self.jobs.get(ident)
        if job:
            if fraction >= 0:
                job.progress = fraction
            if text:
                job.message = text
        row = self._row_for_job(ident)
        if row < 0:
            return
        if text:
            self.queue_table.item(row, 1).setText(text)
        if fraction >= 0:
            bar = self.queue_table.cellWidget(row, 2)
            if bar:
                bar.setValue(max(0, min(100, int(round(fraction * 100)))))

    def _job_finished(self, ident, path, note):
        job = self.jobs.get(ident)
        if job:
            job.status = jobs.DONE
            job.out_path = path
            job.note = note
            if job.kind == "download":
                self._local_path = path
        row = self._row_for_job(ident)
        if row >= 0:
            self.queue_table.item(row, 1).setText("Done" if not note else "Done · note")
            bar = self.queue_table.cellWidget(row, 2)
            if bar:
                bar.setValue(100)
        if job and job.kind == "export":
            message = f"Finished {os.path.basename(path)}"
            if note:
                message += f" — {note}"
            self.status.showMessage(message, 9000)

    def _job_failed(self, ident, message):
        job = self.jobs.get(ident)
        if job:
            job.status = jobs.FAILED
            job.message = message
        row = self._row_for_job(ident)
        if row >= 0:
            self.queue_table.item(row, 1).setText("Failed")
            self.queue_table.item(row, 1).setToolTip(message)
        self.status.showMessage(f"Export failed: {message.splitlines()[-1]}", 9000)

    def _job_cancelled(self, ident):
        job = self.jobs.get(ident)
        if job:
            job.status = jobs.CANCELLED
        row = self._row_for_job(ident)
        if row >= 0:
            self.queue_table.item(row, 1).setText("Cancelled")

    def cancel_selected_job(self):
        rows = self.queue_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.queue_table.item(rows[0].row(), 0)
        ident = item.data(QtCore.Qt.UserRole)
        job = self.jobs.get(ident)
        if job and job.status in (jobs.PENDING, jobs.RUNNING):
            self.runner.cancel(ident)
            self.queue_table.item(rows[0].row(), 1).setText("Cancelling…")

    def cancel_all_jobs(self):
        self.runner.cancel_all()
        for ident, job in self.jobs.items():
            if job.status in (jobs.PENDING, jobs.RUNNING):
                row = self._row_for_job(ident)
                if row >= 0:
                    self.queue_table.item(row, 1).setText("Cancelling…")

    def clear_finished(self):
        done = {jobs.DONE, jobs.FAILED, jobs.CANCELLED}
        for row in range(self.queue_table.rowCount() - 1, -1, -1):
            item = self.queue_table.item(row, 0)
            ident = item.data(QtCore.Qt.UserRole) if item else None
            job = self.jobs.get(ident)
            if job and job.status in done:
                self.queue_table.removeRow(row)
                del self.jobs[ident]

    def _reveal_job(self, index):
        item = self.queue_table.item(index.row(), 0)
        job = self.jobs.get(item.data(QtCore.Qt.UserRole)) if item else None
        if job and job.out_path and os.path.exists(job.out_path):
            path = job.out_path if os.path.isdir(job.out_path) \
                else os.path.dirname(job.out_path)
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    # -- tools, settings and dialogs ------------------------------------

    def _check_tools(self):
        if ffmpegtool.have_ffmpeg():
            return
        self.status.showMessage(
            "ffmpeg is not installed yet. It will be offered when you export.",
            9000)

    def _offer_ffmpeg(self):
        if not sys.platform.startswith("win"):
            self._warn("ffmpeg is required",
                       "Install it first, then reopen TubeClipper.\n\n"
                       "macOS:  brew install ffmpeg\n"
                       "Linux:  sudo apt install ffmpeg")
            return
        answer = QtWidgets.QMessageBox.question(
            self, "Download ffmpeg?",
            "TubeClipper needs ffmpeg to trim and encode media. Download a "
            "private copy for TubeClipper now?\n\nNo administrator access is needed.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes)
        if answer == QtWidgets.QMessageBox.Yes:
            self._download_ffmpeg()

    def _download_ffmpeg(self):
        if self._ffmpeg_task is not None:
            return

        def install(report):
            return ffmpegtool.install_ffmpeg(on_progress=report)

        task = jobs.Task(install)
        task.signals.progress.connect(
            lambda f, text: self.status.showMessage(text or f"Downloading ffmpeg… {f:.0%}"))
        task.signals.done.connect(self._ffmpeg_ready)
        task.signals.failed.connect(self._ffmpeg_failed)
        self._ffmpeg_task = task
        self.export_btn.setEnabled(False)
        self.export_all_btn.setEnabled(False)
        self.status.showMessage("Downloading ffmpeg…")
        self.pool.start(task)

    def _ffmpeg_ready(self, _path):
        self._ffmpeg_task = None
        self._sync_range_fields()
        self.export_all_btn.setEnabled(bool(self.clips))
        self.status.showMessage("ffmpeg is ready. You can export now.", 6000)

    def _ffmpeg_failed(self, message):
        self._ffmpeg_task = None
        self._sync_range_fields()
        self.export_all_btn.setEnabled(bool(self.clips))
        self._warn("Could not install ffmpeg", message)

    def open_settings(self):
        dialog = SettingsDialog(self, self._prefs)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        self._prefs.update(dialog.values())
        for key, value in self._prefs.items():
            self.settings.setValue(key, value)
        self._populate_quality()
        self._update_summary()

    def show_ffmpeg_status(self):
        if not ffmpegtool.have_ffmpeg():
            self._offer_ffmpeg()
            return
        QtWidgets.QMessageBox.information(
            self, "ffmpeg status",
            f"{ffmpegtool.version_string()}\n\n"
            f"ffmpeg: {ffmpegtool.tool_path('ffmpeg')}\n"
            f"ffprobe: {ffmpegtool.tool_path('ffprobe')}")

    def show_about(self):
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        box.setText(f"<b>{APP_NAME} {__version__}</b>")
        box.setInformativeText(
            "Trim YouTube videos and past livestreams, then export the "
            "selection as video, audio, or an animated GIF.\n\n"
            "Built with PySide6, yt-dlp, and ffmpeg.")
        from . import resource_path
        logo = resource_path("assets", "logo_256.png")
        if os.path.exists(logo):
            box.setIconPixmap(QtGui.QPixmap(logo).scaled(
                96, 96, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        box.exec()

    def _warn(self, title, text):
        QtWidgets.QMessageBox.warning(self, title, text)

    # -- lifetime --------------------------------------------------------

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("out_dir", self.out_dir_edit.text())
        if self._probe_task is not None:
            self._probe_task.cancel()
        if self._thumb_task is not None:
            self._thumb_task.cancel()
        self.runner.stop()
        self.runner.wait(2500)
        if self._thumb_dir:
            shutil.rmtree(self._thumb_dir, ignore_errors=True)
        super().closeEvent(event)


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")

    from . import resource_path
    for name in ("TubeClipper.ico", "logo_256.png", "logo.png"):
        path = resource_path("assets", name)
        if os.path.exists(path):
            app.setWindowIcon(QtGui.QIcon(path))
            break

    window = MainWindow()
    window.show()
    return app.exec()
