import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from tubeclipper import engine, source
from tubeclipper.ui import MainWindow, TimecodeEdit, style_sheet


class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        QtCore.QStandardPaths.setTestModeEnabled(True)
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_timecode_edit_commits(self):
        edit = TimecodeEdit()
        values = []
        edit.committed.connect(values.append)
        edit.setText("1:02.5")
        edit._commit()
        self.assertEqual(values, [62.5])
        self.assertEqual(edit.text(), "01:02.500")

    def test_style_scales(self):
        small = style_sheet(1.0)
        large = style_sheet(2.0)
        self.assertIn("border-radius: 6px", small)
        self.assertIn("border-radius: 12px", large)

    def test_main_window_clip_flow(self):
        window = MainWindow()
        try:
            window.source = source.Source(
                url="https://youtube.invalid/watch?v=test",
                video_id="test", title="Test video", duration=120,
                heights=(1080, 720), fps=30, info={"formats": []})
            window.timeline.set_duration(120)
            window.timeline.set_range(10, 25)
            window.add_clip()
            self.assertEqual(len(window.clips), 1)
            self.assertEqual(window.clip_table.rowCount(), 1)
            self.assertEqual(window.clips[0].duration, 15)
            window.clip_table.selectRow(0)
            window.clip_table.item(0, 0).setText("Opening")
            self.assertEqual(window.clips[0].name, "Opening")
            window.timeline.set_range(30, 40)
            window.use_selected_clip()
            self.assertEqual(window.timeline.range(), (10.0, 25.0))
            window.remove_clips()
            self.assertEqual(window.clips, [])
        finally:
            window.close()

    def test_quality_and_format_switch(self):
        window = MainWindow()
        try:
            window.kind_audio.setChecked(True)
            keys = [window.format_combo.itemData(i)
                    for i in range(window.format_combo.count())]
            self.assertIn("wav", keys)
            self.assertNotIn("mp4", keys)
            window.format_combo.setCurrentIndex(window.format_combo.findData("mp3"))
            self.assertEqual(window._quality().abr, 192)
            window.kind_video.setChecked(True)
            window.format_combo.setCurrentIndex(window.format_combo.findData("gif"))
            self.assertFalse(window.mode_fast.isEnabled())
            self.assertTrue(window.mode_exact.isChecked())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
