"""Entry point for the Linux port of the screen protractor / ruler.

Run from the repo root:
    python3 main.py

The app keeps running when the overlay is hidden (the tray icon stays
alive). To exit fully, use the tray menu or the overlay context menu.
"""
from __future__ import annotations

import os
import sys

# Make the in-repo `screen_ruler` package importable when this file is
# run directly, without requiring an editable install (`pip install -e .`).
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from screen_ruler import state as state_mod  # noqa: E402
from screen_ruler.overlay import OverlayWindow  # noqa: E402
from screen_ruler.tray import Tray  # noqa: E402


def main() -> int:
    # High-DPI attributes must be set *before* QApplication is constructed.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("screen-protractor")
    # The overlay is a top-level window that we hide/show; we do NOT
    # want the app to quit just because the overlay is hidden. The
    # tray icon is the persistent surface.
    app.setQuitOnLastWindowClosed(False)

    s = state_mod.load()
    overlay = OverlayWindow(s)
    overlay.show()

    def on_toggle() -> None:
        if overlay.isVisible():
            overlay.hide()
        else:
            overlay.show()
            overlay.activateWindow()

    def on_reset() -> None:
        overlay.reset_active()

    def on_mode() -> None:
        overlay.toggle_mode()

    def on_exit() -> None:
        overlay._save_state()
        app.quit()

    tray = Tray(
        on_toggle=on_toggle,
        on_reset=on_reset,
        on_mode=on_mode,
        on_exit=on_exit,
        is_ruler_mode=lambda: overlay._mode == "ruler",
    )
    tray.show()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
