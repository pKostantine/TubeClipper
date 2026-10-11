"""The native Window menu hookup (macOS only)."""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@unittest.skipUnless(sys.platform == "darwin", "macOS only")
class WindowMenu(unittest.TestCase):
    def test_objc_bridge_round_trips_a_string(self):
        from tubeclipper import macwindow
        self.assertEqual(macwindow._py(macwindow._str("Fill ✓")), "Fill ✓")

    def test_missing_menu_is_harmless(self):
        from tubeclipper import macwindow
        self.assertIsNone(macwindow.install_window_menu("No Such Menu"))


if __name__ == "__main__":
    unittest.main()
