"""The loading states: what the window shows while it is waiting.

These are worth testing because every one of them looks identical from the
outside if it goes wrong, namely a black rectangle and dead buttons, and
because the states are driven by Qt signals that are easy to wire to the
wrong thing and never notice.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from tubeclipper.player import HAVE_MEDIA, PlayerPane
from tubeclipper.timeline import TimelineView

needs_media = unittest.skipUnless(HAVE_MEDIA, "Qt Multimedia is unavailable")


class Overlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        QtCore.QStandardPaths.setTestModeEnabled(True)
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.pane = PlayerPane()
        self.pane.resize(640, 400)

    def tearDown(self):
        self.pane.deleteLater()
        QtWidgets.QApplication.processEvents()

    def test_starts_with_nothing_showing(self):
        self.assertFalse(self.pane.overlay.isVisible())
        self.assertFalse(self.pane.ready())

    def test_busy_shows_and_animates(self):
        self.pane.busy("Loading video")
        self.assertTrue(self.pane.overlay.isVisibleTo(self.pane.surface))
        first = self.pane.overlay.text()
        self.pane._tick_busy()
        self.assertNotEqual(first, self.pane.overlay.text())
        self.assertTrue(self.pane.overlay.text().startswith("Loading video"))

    def test_idle_hides_it(self):
        self.pane.busy("Loading video")
        self.pane.idle()
        self.assertFalse(self.pane.overlay.isVisibleTo(self.pane.surface))

    def test_message_does_not_animate(self):
        self.pane.message("No preview available.")
        self.pane._tick_busy()
        self.assertEqual(self.pane.overlay.text(), "No preview available.")

    def test_overlay_follows_the_surface(self):
        self.pane.busy("Loading video")
        self.pane.resize(900, 600)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self.pane.overlay.width(),
                         self.pane.surface.rect().width() - 2)


@needs_media
class MediaStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        QtCore.QStandardPaths.setTestModeEnabled(True)
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.pane = PlayerPane()
        self.pane.resize(640, 400)
        from PySide6.QtMultimedia import QMediaPlayer
        self.S = QMediaPlayer.MediaStatus

    def tearDown(self):
        self.pane.deleteLater()
        QtWidgets.QApplication.processEvents()

    def test_loading_disables_the_transport(self):
        self.pane._on_media_status(self.S.LoadingMedia)
        self.assertFalse(self.pane.ready())
        self.assertFalse(self.pane.btn_play.isEnabled())
        self.assertIn("Loading video", self.pane.overlay.text())

    def test_buffering_says_buffering(self):
        self.pane._on_media_status(self.S.BufferingMedia)
        self.assertIn("Buffering", self.pane.overlay.text())

    def test_buffer_progress_is_shown_while_buffering(self):
        self.pane._on_media_status(self.S.BufferingMedia)
        self.pane._on_buffer(0.42)
        self.assertIn("42%", self.pane.overlay.text())

    def test_buffer_progress_is_ignored_once_playing(self):
        self.pane._on_media_status(self.S.BufferedMedia)
        self.pane._on_buffer(0.5)
        self.assertFalse(self.pane.overlay.isVisibleTo(self.pane.surface))

    def test_stalled_says_so(self):
        self.pane._on_media_status(self.S.StalledMedia)
        self.assertIn("Waiting for data", self.pane.overlay.text())

    def test_loaded_enables_the_transport_and_clears_the_overlay(self):
        self.pane._on_media_status(self.S.LoadingMedia)
        self.pane._on_media_status(self.S.LoadedMedia)
        self.assertTrue(self.pane.ready())
        self.assertTrue(self.pane.btn_play.isEnabled())
        self.assertFalse(self.pane.overlay.isVisibleTo(self.pane.surface))

    def test_invalid_media_is_reported_on_the_video(self):
        self.pane._on_media_status(self.S.InvalidMedia)
        self.assertFalse(self.pane.ready())
        self.assertIn("could not be previewed", self.pane.overlay.text())

    def test_ready_changes_are_announced(self):
        seen = []
        self.pane.readyChanged.connect(seen.append)
        self.pane._on_media_status(self.S.LoadedMedia)
        self.pane._on_media_status(self.S.LoadingMedia)
        self.assertEqual(seen, [True, False])

    def test_a_seek_before_load_is_not_thrown_away(self):
        # Dragging the timeline during the first seconds used to do nothing.
        self.pane._on_media_status(self.S.LoadingMedia)
        self.pane.seek(42.0)
        self.assertEqual(self.pane._pending_seek, 42.0)
        self.pane._on_media_status(self.S.LoadedMedia)
        self.assertIsNone(self.pane._pending_seek)


class Filmstrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_strip_says_it_is_working(self):
        view = TimelineView()
        view.resize(800, 130)
        view.set_duration(600.0)
        self.assertFalse(view._strip_busy)
        view.set_strip_busy(True)
        self.assertTrue(view._strip_busy)
        from PySide6 import QtGui
        image = QtGui.QImage(800, 130, QtGui.QImage.Format_ARGB32)
        view.render(image)          # the caption path must not throw
        self.assertFalse(image.isNull())

    def test_arriving_thumbs_clear_the_caption(self):
        view = TimelineView()
        view.set_duration(600.0)
        view.set_strip_busy(True)
        view.set_thumbs([])
        self.assertFalse(view._strip_busy)


@needs_media
class SplitAudio(unittest.TestCase):
    """Adaptive sources load video and audio as two separate streams."""

    @classmethod
    def setUpClass(cls):
        QtCore.QStandardPaths.setTestModeEnabled(True)
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        from PySide6.QtMultimedia import QMediaPlayer
        self.S = QMediaPlayer.MediaStatus
        self.pane = PlayerPane()
        self.pane.resize(640, 400)
        self.pane._split_audio = True
        self.pane._video_ready = False
        self.pane._audio_ready = False

    def tearDown(self):
        self.pane.deleteLater()
        QtWidgets.QApplication.processEvents()

    def test_video_alone_is_not_ready(self):
        # Otherwise playback starts and the first seconds are silent.
        self.pane._on_media_status(self.S.LoadedMedia)
        self.assertFalse(self.pane.ready())
        self.assertIn("Loading audio", self.pane.overlay.text())

    def test_ready_once_both_arrive(self):
        self.pane._on_media_status(self.S.LoadedMedia)
        self.pane._on_audio_status(self.S.LoadedMedia)
        self.assertTrue(self.pane.ready())
        self.assertFalse(self.pane.overlay.isVisibleTo(self.pane.surface))

    def test_audio_failure_does_not_strand_the_video(self):
        self.pane._on_media_status(self.S.LoadedMedia)
        self.pane._on_audio_status(self.S.InvalidMedia)
        self.assertTrue(self.pane.ready())


if __name__ == "__main__":
    unittest.main(verbosity=2)
