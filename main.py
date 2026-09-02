"""Entry point for the Linux port of the screen protractor / ruler.

Run:
    python3 linux/main.py

The app keeps running when the overlay is hidden (the tray icon stays
alive). To exit fully, use the tray menu or the overlay context menu.
"""
from __future__ import annotations

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

import state as state_mod
from overlay import OverlayWindow
from tray import Tray


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
