"""Main overlay window.

QWidget subclass that:
  * covers the whole virtual desktop,
  * is fully transparent except for the protractor / ruler drawing,
  * toggles X11 input-passthrough only when cursor state changes,
  * keeps the window interactive while a drag is in progress (so a fast
    move that briefly leaves the hit area doesn't drop the drag).

Coordinate rule: every numeric point is in *local* widget coordinates.
Conversion to/from global happens only at the platform boundary
(mapFromGlobal in, mapToGlobal out).
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QBrush
from PyQt5.QtWidgets import QApplication, QMenu, QWidget

from screen_ruler import platform_x11
from screen_ruler import state as state_mod
from screen_ruler.geometry import Vec
from screen_ruler.protractor import COL_BLUE, COL_ORANGE, Handle, Protractor
from screen_ruler.ruler import Ruler


# Hit-test radius in logical pixels. The WPF version uses 18 DIPs; we
# stay with the same number on the assumption that Qt's logical px and
# WPF's DIP are equivalent when AA_EnableHighDpiScaling is enabled.
HIT_RADIUS = 18.0

# Polling period (ms). 30 ms ≈ 33 Hz; matches the WPF version's timer.
POLL_MS = 30


class OverlayWindow(QWidget):
    def __init__(self, app_state: state_mod.OverlayState) -> None:
        super().__init__(None)
        self._state = app_state
        self._mode = self._state.mode  # "protractor" or "ruler"

        # Tools — created around screen centre, then overwritten by state.
        default_center = Vec(400.0, 300.0)
        self._protractor = Protractor(default_center)
        self._ruler = Ruler(default_center)
        self._apply_state_to_tools()

        # Window: frameless, always on top, no taskbar entry, translucent.
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        # WA_TranslucentBackground + WA_NoSystemBackground: the WM/compositor
        # must treat the surface as having per-pixel alpha. We never fill the
        # background — every painted element is its own shape on top of nothing.
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)

        # Cover the whole virtual desktop (all monitors, including negative
        # coordinates on a side-by-side layout).
        vx, vy, vw, vh = platform_x11.virtual_screen_geom()
        self.setGeometry(vx, vy, vw, vh)
        self._win_xid: Optional[int] = None
        self._last_interactive: Optional[bool] = None

        # Drag state
        self._drag_handle = Handle.NONE
        self._drag_last: Optional[Vec] = None
        self._painting = False  # paintEvent reentrancy guard

        # Cursor poll
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll_cursor)

    # ---- lifecycle ----

    def show(self) -> None:  # type: ignore[override]
        super().show()
        # winId() is only valid after the platform window exists.
        self._win_xid = int(self.winId())
        self._timer.start()
        # Make sure the *initial* state is "passthrough" so the overlay
        # doesn't grab clicks before the first poll.
        self._apply_interactive(False)

    def hide(self) -> None:  # type: ignore[override]
        self._timer.stop()
        # When hidden, make sure we *do* accept input next time we show.
        # Setting interactive=True clears the input-shape restriction.
        if self._win_xid is not None:
            platform_x11.set_input_passthrough(
                self._win_xid, False, self.width(), self.height()
            )
        super().hide()

    def closeEvent(self, event):  # type: ignore[override]
        self._timer.stop()
        self._save_state()
        super().closeEvent(event)

    # ---- state ----

    def _apply_state_to_tools(self) -> None:
        if self._state.protractor:
            self._protractor.from_state(self._state.protractor)
        if self._state.ruler:
            self._ruler.from_state(self._state.ruler)

    def _save_state(self) -> None:
        self._state.mode = self._mode
        self._state.protractor = self._protractor.to_state()
        self._state.ruler = self._ruler.to_state()
        state_mod.save(self._state)

    # ---- public API for tray/main ----

    def toggle_mode(self) -> None:
        self._mode = "ruler" if self._mode == "protractor" else "protractor"
        self._save_state()
        self.update()

    def reset_active(self) -> None:
        center = Vec(self.width() / 2.0, self.height() / 2.0)
        if self._mode == "ruler":
            self._ruler.reset(center)
        else:
            self._protractor.reset(center)
        self._save_state()
        self.update()

    def active_tool(self):
        return self._ruler if self._mode == "ruler" else self._protractor

    # ---- painting ----

    def paintEvent(self, event):  # type: ignore[override]
        # Reentrancy guard. Without this, a nested paintEvent — which
        # Qt can trigger from inside a paint op (QPainterPath updates,
        # backing-store invalidation) — creates a second QPainter(self)
        # on the same paint device, producing the "A paint device can
        # only be painted by one painter at a time" /
        # "QBackingStore::endPaint() called with active painter" error
        # cascade. Dropping the re-entered call costs at most one frame.
        if self._painting:
            return
        self._painting = True
        try:
            p = QPainter(self)
            # Deliberately no background fill: WA_TranslucentBackground + per-element
            # drawing is what makes the overlay truly see-through. If a particular
            # compositor refuses to alpha-blend an empty surface, switch to
            # `p.fillRect(self.rect(), QColor(0, 0, 0, 1))` here (alpha=1 hack).
            if self._mode == "ruler":
                center = self._ruler.center()
                # mapToGlobal only accepts QPoint in PyQt5, not QPointF.
                global_pt = self.mapToGlobal(QPoint(int(center.x), int(center.y)))
                dip_per_cm = platform_x11.dip_per_cm_at(
                    global_pt.x(), global_pt.y()
                )
                self._ruler.draw(p, dip_per_cm)
                length = self._ruler.length()
                if dip_per_cm > 0:
                    cm = length / dip_per_cm
                    value = f"{cm:.2f} cm  ({int(length)} px)"
                else:
                    value = f"{int(length)} px"
                self._draw_readout(p, center, value, COL_BLUE,
                                   "拖动尺身移动 · 拖动端点缩放/旋转")
            else:
                self._protractor.draw(p, "")
                angle = self._protractor.angle_deg()
                # 0° and "angle undefined" must look different on screen.
                # The protractor returns None when one arm has zero length;
                # in that case the geometry can't define an angle and we
                # refuse to lie with "0.0°".
                value = f"{angle:.1f}°" if angle is not None else "--°"
                self._draw_readout(p, self._protractor.vertex, value,
                                   COL_ORANGE,
                                   "拖动橙色点移动 · 拖动蓝色点旋转")
            p.end()
        finally:
            self._painting = False

    def _draw_readout(self, p: QPainter, anchor: Vec, value: str,
                      border: QColor, hint: str) -> None:
        # Sizing matches the WPF OverlayWindow.xaml readout exactly:
        #   AngleText FontSize=22 Bold, Foreground=White
        #   HintText   FontSize=11,       Foreground=#FFBBBBBB
        #   Border  CornerRadius=6, BorderThickness=1, BorderBrush=orange
        #   Padding 10 horizontal / 6 vertical, Background #CC202020
        big = QFont(p.font())
        big.setPointSizeF(22.0)
        big.setBold(True)
        fm_big = QFontMetrics(big)
        val_w = fm_big.horizontalAdvance(value)
        val_h = fm_big.height()

        small = QFont(p.font())
        small.setPointSizeF(11.0)
        small.setBold(False)
        fm_small = QFontMetrics(small)
        hint_w = fm_small.horizontalAdvance(hint)
        hint_h = fm_small.height()

        pad_x, pad_y = 10.0, 6.0
        w = max(val_w, hint_w) + 2 * pad_x
        h = val_h + hint_h + 2 * pad_y + 4

        x = anchor.x + 24
        y = anchor.y + 24
        bg = QColor(0x20, 0x20, 0x20, 0xCC)
        p.setPen(QPen(border, 1.0))
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(QRectF(x, y, w, h), 6.0, 6.0)

        p.setPen(QColor(255, 255, 255))
        p.setFont(big)
        p.drawText(QPointF(x + pad_x, y + pad_y + val_h - 4), value)
        p.setFont(small)
        p.setPen(QColor(0xBB, 0xBB, 0xBB))
        p.drawText(QPointF(x + pad_x, y + pad_y + val_h + hint_h - 2), hint)

    # ---- cursor polling / click-through ----

    def _poll_cursor(self) -> None:
        try:
            gx, gy = platform_x11.cursor_pos()
        except Exception:
            return
        local = self.mapFromGlobal(QPoint(gx, gy))
        local_v = Vec(local.x(), local.y())

        # Drag in progress ⇒ always interactive. This is the fix for the
        # "fast move drops the drag" bug: while we're holding a handle,
        # we don't care whether the cursor momentarily leaves the hit area.
        if self._drag_handle != Handle.NONE:
            interactive = True
        else:
            tool = self.active_tool()
            hit = tool.hit_test(local_v, HIT_RADIUS)
            interactive = (hit != Handle.NONE)

        if self._last_interactive is None or interactive != self._last_interactive:
            self._apply_interactive(interactive)

    def _apply_interactive(self, interactive: bool) -> None:
        if self._win_xid is None:
            return
        platform_x11.set_input_passthrough(
            self._win_xid, not interactive, self.width(), self.height()
        )
        self._last_interactive = interactive

    # ---- mouse events ----

    def mousePressEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            local = Vec(event.x(), event.y())
            hit = self.active_tool().hit_test(local, HIT_RADIUS)
            if hit != Handle.NONE:
                self._drag_handle = hit
                self._drag_last = local
                # grabMouse keeps us getting move events even if the
                # cursor leaves the widget during the drag.
                self.grabMouse()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())

    def mouseMoveEvent(self, event):  # type: ignore[override]
        if self._drag_handle == Handle.NONE or self._drag_last is None:
            return
        cur = Vec(event.x(), event.y())
        dx = cur.x - self._drag_last.x
        dy = cur.y - self._drag_last.y
        self._drag_last = cur
        if self._mode == "ruler" and self._drag_handle == Handle.BODY:
            self._ruler.move(Handle.BODY, dx, dy)
        else:
            self.active_tool().move(self._drag_handle, dx, dy)
        self.update()

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._drag_handle != Handle.NONE:
            self._drag_handle = Handle.NONE
            self._drag_last = None
            self.releaseMouse()
            self._save_state()
            # Force an immediate re-poll so the click-through state
            # updates if the cursor is no longer over a handle.
            self._poll_cursor()

    def _show_context_menu(self, global_pos) -> None:
        menu = QMenu(self)
        mode_text = "切换为直尺" if self._mode == "protractor" else "切换为量角器"
        act_mode = menu.addAction(mode_text)
        act_reset = menu.addAction("重置位置")
        menu.addSeparator()
        act_hide = menu.addAction("隐藏")
        act_exit = menu.addAction("退出")
        chosen = menu.exec_(global_pos)
        if chosen is act_mode:
            self.toggle_mode()
        elif chosen is act_reset:
            self.reset_active()
        elif chosen is act_hide:
            self.hide()
        elif chosen is act_exit:
            QApplication.instance().quit()
