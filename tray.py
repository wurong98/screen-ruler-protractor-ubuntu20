"""System-tray icon: runtime-drawn protractor glyph + context menu.

The WPF version uses WinForms' NotifyIcon and paints the icon at runtime
with System.Drawing. We mirror both behaviours with Qt:

  * QSystemTrayIcon as the tray surface.
  * QPainter to draw the same 32×32 protractor glyph.

The double-click toggles overlay visibility; the context menu mirrors the
right-click menu on the overlay itself, so both surfaces offer the same
controls.
"""
from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QSystemTrayIcon


_TRAY_BLUE = QColor(0x1E, 0x90, 0xFF)
_TRAY_ORANGE = QColor(0xFF, 0x8C, 0x00)


def build_tray_icon() -> QIcon:
    """Paint a 32×32 protractor glyph that matches the WPF tray icon.

    Layout: vertex at (6, 26); arms to (29, 26) and (24, 6); arc
    centred on the vertex, sweeping -65°..65° (i.e. opening upward).
    """
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    pen = QPen(_TRAY_BLUE, 3.0, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(6, 26), QPointF(29, 26))
    p.drawLine(QPointF(6, 26), QPointF(24, 6))

    arc_pen = QPen(_TRAY_ORANGE, 2.0, Qt.SolidLine, Qt.RoundCap)
    p.setPen(arc_pen)
    p.drawArc(QRectF(6 - 12, 26 - 12, 24, 24), -65 * 16, 65 * 16 + 65 * 16)

    p.end()
    return QIcon(pm)


class Tray:
    """Wrapper around QSystemTrayIcon. Construct *after* QApplication."""

    def __init__(self, on_toggle, on_reset, on_mode, on_exit,
                 is_ruler_mode: Callable[[], bool]) -> None:
        self._is_ruler_mode = is_ruler_mode
        self._tray = QSystemTrayIcon(build_tray_icon())
        self._tray.setToolTip("屏幕量角器")

        menu = QMenu()
        self._act_toggle = QAction("显示 / 隐藏", menu)
        self._act_toggle.triggered.connect(on_toggle)
        self._act_reset = QAction("重置位置", menu)
        self._act_reset.triggered.connect(on_reset)
        self._act_mode = QAction("切换 直尺 / 量角器", menu)
        self._act_mode.triggered.connect(on_mode)
        self._act_exit = QAction("退出", menu)
        self._act_exit.triggered.connect(on_exit)
        menu.addAction(self._act_toggle)
        menu.addAction(self._act_reset)
        menu.addAction(self._act_mode)
        menu.addSeparator()
        menu.addAction(self._act_exit)
        self._tray.setContextMenu(menu)

        # Refresh the menu label when opened, so the user always sees
        # the *current* "切换为…" wording.
        menu.aboutToShow.connect(self._refresh_labels)
        self._tray.activated.connect(self._on_activated)

    def _refresh_labels(self) -> None:
        if self._is_ruler_mode():
            self._act_mode.setText("切换为量角器")
        else:
            self._act_mode.setText("切换为直尺")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Double-click (or single-click on DEs that report it) toggles.
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self._act_toggle.trigger()

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()
