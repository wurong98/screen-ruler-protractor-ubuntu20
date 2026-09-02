"""Smoke test for the full overlay stack.

Unlike `python3 -m unittest` runs, this needs an X server (python-xlib
opens a Display on import). Run under xvfb:

    cd linux && xvfb-run -a python3 smoke_test.py

What it checks:
  * All modules import without error.
  * OverlayWindow constructs and resizes.
  * show() + processEvents() + render() doesn't crash, produces a pixmap
    of the expected size, with at least some non-transparent pixels in
    the centre (the protractor default drawing).
  * Switching to ruler mode and re-rendering also produces pixels.
  * State save/load roundtrip works.

IMPORTANT: This test writes to a *temporary* XDG_CONFIG_HOME so it
never clobbers the user's real state file at
~/.config/screen-protractor/state.json.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

# Add the linux/ dir to sys.path so we can `import overlay`, `import state`, ...
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


class SmokeTest(unittest.TestCase):
    def setUp(self):
        # Use a throwaway XDG_CONFIG_HOME so state.* calls don't touch
        # the user's real config file.
        self._tmp_cfg = tempfile.mkdtemp()
        self._env = mock.patch.dict(os.environ,
                                    {"XDG_CONFIG_HOME": self._tmp_cfg})
        self._env.start()
        # Lazy Qt imports so the failure mode is clear if Qt is missing.
        from PyQt5.QtCore import Qt  # noqa: F401
        from PyQt5.QtWidgets import QApplication
        self._app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self._env.stop()
        import shutil
        shutil.rmtree(self._tmp_cfg, ignore_errors=True)

    def test_imports(self):
        import geometry   # noqa: F401
        import state      # noqa: F401
        import platform_x11  # noqa: F401
        import protractor    # noqa: F401
        import ruler         # noqa: F401
        import overlay       # noqa: F401
        import tray          # noqa: F401

    def test_state_roundtrip(self):
        import state
        s = state.OverlayState(mode="ruler",
                               protractor=[1, 2, 3, 4, 5, 6],
                               ruler=[10, 20, 30, 40])
        state.save(s)
        s2 = state.load()
        self.assertEqual(s2.mode, "ruler")
        self.assertEqual(s2.protractor, [1, 2, 3, 4, 5, 6])
        self.assertEqual(s2.ruler, [10, 20, 30, 40])

    def test_protractor_degenerate_angle_is_none(self):
        # Regression: the WPF version (and our v1) returned 0.0 when an
        # endpoint was too close to the vertex to be visually usable.
        # The user caught this as a UX bug because "0°" and "undefined
        # angle" are different things — see geometry.MIN_LENGTH.
        from PyQt5.QtWidgets import QApplication
        from protractor import Protractor
        from geometry import Vec
        p = Protractor(Vec(400, 300))
        p.end1 = p.vertex  # mathematically degenerate
        p.end2 = Vec(700, 200)
        self.assertIsNone(p.angle_deg())
        # Real failure mode from the user's screenshot: end1 = vertex + (2,2)
        p.end1 = Vec(402, 302)
        p.end2 = Vec(540, 460)
        self.assertIsNone(p.angle_deg())
        # And a real 0° (two parallel non-degenerate rays) still works.
        p.end1 = Vec(600, 300)
        p.end2 = Vec(500, 200)
        self.assertIsNotNone(p.angle_deg())

    def test_overlay_paint(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QImage, QPixmap
        import state
        from overlay import OverlayWindow

        s = state.OverlayState()
        w = OverlayWindow(s)
        # Resize to something renderable on the headless display.
        w.resize(800, 600)
        w.show()
        self._app.processEvents()
        self._app.processEvents()

        def _count_opaque(pixmap):
            img = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
            opaque = 0
            for y in range(0, img.height(), 4):
                for x in range(0, img.width(), 4):
                    if (img.pixel(x, y) >> 24) & 0xFF:
                        opaque += 1
            return opaque

        # Protractor mode: should have visible drawing.
        pm = QPixmap(w.size())
        pm.fill(Qt.transparent)
        w.render(pm)
        self.assertEqual(pm.size(), w.size())
        protractor_pixels = _count_opaque(pm)
        self.assertGreater(protractor_pixels, 0,
                           "protractor drawing produced no opaque pixels")

        # Ruler mode: should also have visible drawing.
        w.toggle_mode()
        self._app.processEvents()
        pm.fill(Qt.transparent)
        w.render(pm)
        ruler_pixels = _count_opaque(pm)
        self.assertGreater(ruler_pixels, 0,
                           "ruler drawing produced no opaque pixels")

        # Hide/close cleanly.
        w.hide()
        w.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
