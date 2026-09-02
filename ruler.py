"""Ruler tool: draggable body between two endpoints, mm/cm ticks, rotated labels.

Pure drawing + state. No X11. The overlay passes `dip_per_cm` for the screen
that contains the ruler's centre; the ruler never queries the platform layer
itself. That keeps the layering clean (`ruler` only knows about `geometry`).
"""
from __future__ import annotations

import math
from typing import List

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF

from geometry import Vec, near, point_in_polygon
from protractor import COL_BLUE, COL_ORANGE, Handle


class Ruler:
    """Two-endpoint ruler. Body is a rectangle perpendicular to (a→b)."""

    BODY_WIDTH = 44.0
    BODY_HIT_FUDGE = 6.0        # pixels of extra tolerance inside the body
    FLIP_THRESHOLD = 0.20       # hysteresis: 0.20 mirrors the WPF version
    PIXEL_FALLBACK_TICK = 10    # if dip_per_cm unknown, tick every 10 px
    MAJOR_TICK_PX = 5           # every Nth pixel tick is "major" in fallback

    def __init__(self, default_center: Vec) -> None:
        self._default = default_center
        self.a = default_center + Vec(-150.0, 0.0)
        self.b = default_center + Vec(150.0, 0.0)
        self._flip = False       # ticks on this side of the line a→b

    # ---- mode API used by the overlay ----

    def reset(self, center: Vec) -> None:
        self.a = center + Vec(-150.0, 0.0)
        self.b = center + Vec(150.0, 0.0)
        self._flip = False

    def move(self, handle: Handle, dx: float, dy: float) -> None:
        d = Vec(dx, dy)
        if handle == Handle.END1:
            self.a = self.a + d
        elif handle == Handle.END2:
            self.b = self.b + d
        elif handle == Handle.BODY:
            self.a = self.a + d
            self.b = self.b + d

    def hit_test(self, pt: Vec, radius: float) -> Handle:
        # The visible blue handle rings are drawn on the body's *far* edge
        # (opposite the ticks) via _handle_positions(); a/b themselves sit
        # at the tick-side corners. Hit-test against the *visible* positions
        # so clicking the ring the user sees actually grabs the endpoint.
        ha, hb = self._handle_positions()
        if near(pt, ha, radius):
            return Handle.END1
        if near(pt, hb, radius):
            return Handle.END2
        if point_in_polygon(pt, self._body_polygon()):
            return Handle.BODY
        return Handle.NONE

    def length(self) -> float:
        return (self.b - self.a).length

    def center(self) -> Vec:
        return Vec((self.a.x + self.b.x) / 2.0, (self.a.y + self.b.y) / 2.0)

    # ---- persistence ----

    def to_state(self) -> List[float]:
        return [self.a.x, self.a.y, self.b.x, self.b.y]

    def from_state(self, vals: List[float]) -> None:
        if len(vals) != 4:
            return
        self.a = Vec(vals[0], vals[1])
        self.b = Vec(vals[2], vals[3])

    # ---- internal geometry ----

    def _direction_normal(self) -> Vec:
        """Unit vector along a→b and the perpendicular to its left (y-up math)."""
        d = self.b - self.a
        if d.length < 1e-4:
            d = Vec(1.0, 0.0)
        d = d.normalized()
        # Perpendicular: rotate 90° CCW in math coords (y-up), but our
        # coordinates are y-down (screen), so this is the visual-right
        # side of the line a→b.
        n = Vec(d.y, -d.x)
        return n

    def _update_flip(self, n: Vec) -> Vec:
        """Hysteresis: keep ticks on the same side until the perpendicular
        clearly crosses the opposite threshold."""
        if n.y > self.FLIP_THRESHOLD:
            self._flip = False
        elif n.y < -self.FLIP_THRESHOLD:
            self._flip = True
        if self._flip:
            n = -n
        return n

    def _body_polygon(self) -> List[Vec]:
        d = self.b - self.a
        if d.length < 1e-4:
            d = Vec(1.0, 0.0)
        d = d.normalized()
        n = self._update_flip(Vec(d.y, -d.x))
        a2 = self.a + n * self.BODY_WIDTH
        b2 = self.b + n * self.BODY_WIDTH
        return [self.a, self.b, b2, a2]

    def _handle_positions(self) -> tuple[Vec, Vec]:
        """Endpoints are placed on the body's far (plain) edge — opposite
        the ticks — so they sit on the ruler body, not floating in space."""
        d = self.b - self.a
        if d.length < 1e-4:
            d = Vec(1.0, 0.0)
        d = d.normalized()
        n = self._update_flip(Vec(d.y, -d.x))
        return (self.a + n * self.BODY_WIDTH, self.b + n * self.BODY_WIDTH)

    # ---- drawing ----

    def draw(self, p: QPainter, dip_per_cm: float) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)

        # Body polygon
        poly = self._body_polygon()
        qpoly = QPolygonF([QPointF(v.x, v.y) for v in poly])
        body_fill = QColor(COL_BLUE)
        body_fill.setAlpha(0x22)
        p.setPen(QPen(COL_BLUE, 2.0))
        p.setBrush(QBrush(body_fill))
        p.drawPolygon(qpoly)

        # Ticks + labels
        if dip_per_cm > 0:
            self._draw_metric_ticks(p, dip_per_cm)
        else:
            self._draw_pixel_ticks(p)

        # End handles on the far edge
        ha, hb = self._handle_positions()
        self._draw_handle(p, ha, big=False)
        self._draw_handle(p, hb, big=False)

    def _draw_metric_ticks(self, p: QPainter, dip_per_cm: float) -> None:
        d = (self.b - self.a)
        length = d.length
        if length < 1e-4:
            return
        d = d.normalized()
        n = self._update_flip(Vec(d.y, -d.x))

        dip_per_mm = dip_per_cm / 10.0
        # Keep labels readable when the ruler is dragged either way.
        angle_deg = math.degrees(math.atan2(d.y, d.x))
        if angle_deg > 90.0:
            angle_deg -= 180.0
        elif angle_deg < -90.0:
            angle_deg += 180.0

        pen = QPen(COL_BLUE, 1.5)
        p.setPen(pen)

        i = 0
        d_pos = 0.0
        while d_pos <= length + 0.5:
            whole = (i % 10 == 0)
            half = (i % 5 == 0)
            tick_len = 16.0 if whole else (11.0 if half else 6.0)
            p1 = self.a + d * d_pos
            p2 = p1 + n * tick_len
            p.drawLine(QPointF(p1.x, p1.y), QPointF(p2.x, p2.y))
            if whole and i > 0:
                self._draw_label(p, str(i // 10),
                                 p1 + n * (tick_len + 2.0), angle_deg)
            d_pos += dip_per_mm
            i += 1

        # "cm" tag at the far end
        self._draw_label(p, "cm",
                         self.a + d * length + n * 18.0, angle_deg)

    def _draw_pixel_ticks(self, p: QPainter) -> None:
        d = (self.b - self.a)
        length = d.length
        if length < 1e-4:
            return
        d = d.normalized()
        n = self._update_flip(Vec(d.y, -d.x))
        angle_deg = math.degrees(math.atan2(d.y, d.x))
        if angle_deg > 90.0:
            angle_deg -= 180.0
        elif angle_deg < -90.0:
            angle_deg += 180.0

        pen = QPen(COL_BLUE, 1.5)
        p.setPen(pen)
        i = 0
        d_pos = 0.0
        while d_pos <= length + 0.5:
            major = (i % self.MAJOR_TICK_PX == 0)
            tick_len = 14.0 if major else 7.0
            p1 = self.a + d * d_pos
            p2 = p1 + n * tick_len
            p.drawLine(QPointF(p1.x, p1.y), QPointF(p2.x, p2.y))
            if major and i > 0:
                self._draw_label(p, str(i * self.PIXEL_FALLBACK_TICK),
                                 p1 + n * (tick_len + 2.0), angle_deg)
            d_pos += self.PIXEL_FALLBACK_TICK
            i += 1

    @staticmethod
    def _draw_label(p: QPainter, text: str, at: Vec, angle_deg: float) -> None:
        p.save()
        p.translate(at.x, at.y)
        p.rotate(angle_deg)
        font = p.font()
        font.setPointSizeF(8.5)
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        p.setPen(COL_BLUE)
        p.drawText(QPointF(0, 0), text)
        p.restore()

    @staticmethod
    def _draw_handle(p: QPainter, center: Vec, big: bool) -> None:
        # Ruler endpoint handles reuse the same WPF HandleThumb template
        # as the protractor endpoints. The ruler body itself is the "big"
        # marker (no body handle in the WPF design).
        outer_r = 14.0 if big else 11.0
        inner_r = 8.0 if big else 6.0
        from protractor import COL_BLUE_HALO
        halo = QColor(COL_BLUE_HALO)
        halo.setAlpha(0x55)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(center.x, center.y), outer_r, outer_r)
        p.setBrush(QBrush(COL_BLUE))
        p.setPen(QPen(QColor(255, 255, 255), 2.0))
        p.drawEllipse(QPointF(center.x, center.y), inner_r, inner_r)
