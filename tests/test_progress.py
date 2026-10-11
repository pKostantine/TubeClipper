"""Loading percentages, YouTube's "still processing" state, and go to start."""

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from tubeclipper import engine, source
from tubeclipper.player import HAVE_MEDIA, PlayerPane
from tubeclipper.timeline import TimelineView

needs_media = unittest.skipUnless(HAVE_MEDIA, "Qt Multimedia is unavailable")


def _app():
    QtCore.QStandardPaths.setTestModeEnabled(True)
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class LoadPercentage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.pane = PlayerPane()
        self.pane.resize(640, 400)

    def tearDown(self):
        self.pane.deleteLater()
        QtWidgets.QApplication.processEvents()

    def test_begin_load_starts_at_zero(self):
        self.pane.begin_load()
        self.assertIn("0%", self.pane.overlay.text())
        self.assertTrue(self.pane.loading())

    def test_percentage_is_shown(self):
        self.pane.begin_load()
        self.pane.progress("Contacting YouTube", 0.2, 0.3)
        self.assertEqual(self.pane.overlay.text(), "Contacting YouTube  20%")
        self.assertAlmostEqual(self.pane.overlay.fraction(), 0.2)

    def test_percentage_never_goes_backwards(self):
        self.pane.begin_load()
        self.pane.progress("Loading video", 0.5, 0.8)
        self.pane.progress("Contacting YouTube", 0.2, 0.3)
        self.assertGreaterEqual(self.pane.overlay.fraction(), 0.5)

    def test_creeps_toward_the_ceiling_but_not_past_it(self):
        self.pane.begin_load()
        self.pane.progress("Loading video", 0.4, 0.8)
        for _ in range(200):
            self.pane._tick_busy()
        value = self.pane.overlay.fraction()
        self.assertGreater(value, 0.75)
        self.assertLessEqual(value, 0.8)

    def test_creep_moves_the_number(self):
        self.pane.begin_load()
        self.pane.progress("Loading video", 0.4, 0.8)
        before = self.pane.overlay.text()
        for _ in range(3):
            self.pane._tick_busy()
        self.assertNotEqual(before, self.pane.overlay.text())

    def test_a_message_ends_the_load(self):
        self.pane.begin_load()
        self.pane.message("Could not read that link.")
        self.assertFalse(self.pane.loading())
        self.assertIsNone(self.pane.overlay.fraction())

    def test_overlay_with_a_bar_renders(self):
        self.pane.begin_load()
        self.pane.progress("Loading video", 0.6, 0.8)
        image = QtGui.QImage(640, 400, QtGui.QImage.Format_ARGB32)
        self.pane.render(image)
        self.assertFalse(image.isNull())


@needs_media
class LoadStages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        from PySide6.QtMultimedia import QMediaPlayer
        self.S = QMediaPlayer.MediaStatus
        self.pane = PlayerPane()
        self.pane.resize(640, 400)

    def tearDown(self):
        self.pane.deleteLater()
        QtWidgets.QApplication.processEvents()

    def test_opening_the_video_continues_from_the_link(self):
        self.pane.begin_load()
        self.pane.progress("Reading the stream formats", 0.3, 0.34)
        self.pane._on_media_status(self.S.LoadingMedia)
        self.assertGreaterEqual(self.pane.overlay.fraction(), 0.4)
        self.assertRegex(self.pane.overlay.text(), r"Loading video  \d+%")

    def test_split_audio_is_the_last_stage(self):
        self.pane._split_audio = True
        self.pane._audio_ready = False
        self.pane._on_media_status(self.S.LoadingMedia)
        self.pane._on_media_status(self.S.LoadedMedia)
        self.assertGreaterEqual(self.pane.overlay.fraction(), 0.85)
        self.assertIn("Loading audio", self.pane.overlay.text())
        self.pane._on_audio_status(self.S.LoadedMedia)
        self.assertFalse(self.pane.loading())
        self.assertFalse(self.pane.overlay.isVisibleTo(self.pane.surface))


@needs_media
class Transport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def setUp(self):
        self.pane = PlayerPane()

    def tearDown(self):
        self.pane.deleteLater()
        QtWidgets.QApplication.processEvents()

    def test_start_button_goes_to_zero_not_one_frame_back(self):
        self.pane.seek(42.0)                   # queued, nothing loaded yet
        self.pane.btn_start.click() if self.pane.btn_start.isEnabled() \
            else self.pane.go_to_start()
        self.assertEqual(self.pane._pending_seek, 0.0)

    def test_frame_buttons_say_what_they_do(self):
        self.assertEqual(self.pane.btn_frame_back.text(), "1f")
        self.assertEqual(self.pane.btn_frame_fwd.text(), "1f")
        self.assertIn("start", self.pane.btn_start.toolTip())
        self.assertIn("end", self.pane.btn_end.toolTip())


class StillProcessing(unittest.TestCase):
    def test_post_live_is_still_processing(self):
        src = source.from_info({"id": "x", "title": "t",
                                "live_status": "post_live", "formats": []})
        self.assertTrue(src.still_processing)

    def test_ordinary_video_is_not(self):
        src = source.from_info({"id": "x", "title": "t",
                                "live_status": "not_live", "formats": []})
        self.assertFalse(src.still_processing)

    def test_processing_error_is_explained(self):
        text = source._readable(Exception(
            "ERROR: [youtube] abc: This video is still being processed."))
        self.assertTrue(text.startswith("YouTube is still processing"))

    def test_other_errors_are_left_alone(self):
        text = source._readable(Exception("ERROR: [youtube] abc: Private video"))
        self.assertEqual(text, "Private video")


class ProbeSteps(unittest.TestCase):
    def test_known_steps_climb(self):
        lines = ["[youtube] Extracting URL: https://youtu.be/x",
                 "[youtube] x: Downloading webpage",
                 "[youtube] x: Downloading visionos player API JSON",
                 "[youtube] x: Downloading m3u8 information"]
        fractions = [source.probe_step(l)[0] for l in lines]
        self.assertEqual(fractions, sorted(fractions))
        self.assertLess(fractions[-1], 1.0)

    def test_unknown_lines_are_ignored(self):
        self.assertIsNone(source.probe_step("[info] something else"))


class DefaultSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_new_video_selects_the_whole_thing(self):
        view = TimelineView()
        view.set_duration(10523.0)
        self.assertEqual(view.range(), (0.0, 10523.0))


class FilmstripProgress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_grab_frames_reports_each_frame(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(engine.ffmpegtool, "run"):
            engine.grab_frames("http://example.invalid/v", [0, 1, 2, 3], tmp,
                               report=lambda f, t: seen.append(f))
        self.assertEqual(seen, [0.0, 0.25, 0.5, 0.75])

    def test_strip_shows_progress(self):
        view = TimelineView()
        view.resize(800, 130)
        view.set_duration(600.0)
        view.set_strip_busy(True)
        view.set_strip_progress(0.5)
        self.assertEqual(view._strip_progress, 0.5)
        image = QtGui.QImage(800, 130, QtGui.QImage.Format_ARGB32)
        view.render(image)
        view.set_thumbs([])
        self.assertIsNone(view._strip_progress)


if __name__ == "__main__":
    unittest.main(verbosity=2)
