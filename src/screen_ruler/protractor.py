"""Protractor tool: two rays from a shared vertex, plus an angle arc.

Pure drawing + state. No X11 / Qt platform integration here.
The overlay widget owns the QPainter, the tool just paints.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import List, Optional

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush

from screen_ruler.geometry import Vec, angle_between, cross, near


class Handle(Enum):
    NONE = 0
    VERTEX = 1
    END1 = 2
    END2 = 3
    BODY = 4   # only used by ruler


# Colours — matched to the WPF version (OverlayWindow.xaml).
#   Inner core / line stroke:    #FF1E90FF (DodgerBlue), #FFFF8C00 (DarkOrange)
#   Endpoint outer halo:         #553399FF (slightly lighter blue, alpha 0x55)
#   Vertex outer halo:           #55FF8C00 (orange, alpha 0x55)
COL_BLUE = QColor(0x1E, 0x90, 0xFF)
COL_BLUE_HALO = QColor(0x33, 0x99, 0xFF)
COL_ORANGE = QColor(0xFF, 0x8C, 0x00)


def _qcolor(c: QColor, alpha: int) -> QColor:
    out = QColor(c)
    out.setAlpha(alpha)
    return out


class Protractor:
    """Two-ray protractor. Vertex is the angle origin; end1/end2 are the tips."""

    RAY_OVERHANG = 600.0   # how far past the endpoint the visible line extends
    ARC_RADIUS = 50.0

    # An arm shorter than this in *screen* pixels can't be aimed at a
    # feature and the user can't see the two arms as distinct. The
    # readout then shows "--°" instead of a misleading "0.0°". 20 px
    # matches the WPF handle's outer halo (14 px) plus a small margin.
    MIN_USABLE_LENGTH = 20.0

    def __init__(self, default_center: Vec) -> None:
        self._default = default_center
        self.vertex = default_center
        self.end1 = default_center + Vec(200.0, 0.0)
        self.end2 = default_center + Vec(140.0, -140.0)

    # ---- mode API used by the overlay ----

    def reset(self, center: Vec) -> None:
        self.vertex = center
        self.end1 = center + Vec(200.0, 0.0)
        self.end2 = center + Vec(140.0, -140.0)

    def move(self, handle: Handle, dx: float, dy: float) -> None:
        d = Vec(dx, dy)
        if handle == Handle.VERTEX:
            # Vertex drag moves the whole protractor.
            self.vertex = self.vertex + d
            self.end1 = self.end1 + d
            self.end2 = self.end2 + d
        elif handle == Handle.END1:
            self.end1 = self.end1 + d
        elif handle == Handle.END2:
            self.end2 = self.end2 + d
        # END1/END2 drag in ruler mode never reaches here — the overlay
        # dispatches the ruler's own move() first.

    def hit_test(self, pt: Vec, radius: float) -> Handle:
        if near(pt, self.vertex, radius):
            return Handle.VERTEX
        if near(pt, self.end1, radius):
            return Handle.END1
        if near(pt, self.end2, radius):
            return Handle.END2
        return Handle.NONE

    def angle_deg(self) -> Optional[float]:
        # Invariant: reads the same self.vertex / self.end1 / self.end2
        # that draw() uses (see the comment at the top of draw()).
        # Returns None when either arm is shorter than MIN_USABLE_LENGTH
        # (visually too short to be usable), so the overlay can show
        # "--°" rather than a misleading "0.0°".
        v1 = self.end1 - self.vertex
        v2 = self.end2 - self.vertex
        if v1.length < self.MIN_USABLE_LENGTH or v2.length < self.MIN_USABLE_LENGTH:
            return None
        return angle_between(v1, v2)

    # ---- persistence ----

    def to_state(self) -> List[float]:
        return [self.vertex.x, self.vertex.y,
                self.end1.x, self.end1.y,
                self.end2.x, self.end2.y]

    def from_state(self, vals: List[float]) -> None:
        if len(vals) != 6:
            return
        self.vertex = Vec(vals[0], vals[1])
        self.end1 = Vec(vals[2], vals[3])
        self.end2 = Vec(vals[4], vals[5])

    # ---- drawing ----

    def draw(self, p: QPainter, label_text: str) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)

        # Invariant: every pixel drawn below comes from the same
        # self.vertex / self.end1 / self.end2 that angle_deg() reads.
        # z-order: endpoints first, vertex last. The vertex is the
        # "anchor" the user moves to translate the whole protractor,
        # and it's also the larger of the two handle types, so keeping
        # it on top means the user always sees the centre even when
        # an endpoint sits on top of it.
        self._draw_ray(p, self.vertex, self.end1)
        self._draw_ray(p, self.vertex, self.end2)
        self._draw_arc(p, self.angle_deg())
        self._draw_handle(p, self.end1, big=False)
        self._draw_handle(p, self.end2, big=False)
        self._draw_handle(p, self.vertex, big=True)

    @staticmethod
    def _draw_ray(p: QPainter, frm: Vec, through: Vec) -> None:
        d = (through - frm)
        if d.length < 1e-4:
            d = Vec(1.0, 0.0)
        d = d.normalized()
        end = through + d * Protractor.RAY_OVERHANG
        pen = QPen(COL_BLUE, 2.0)
        p.setPen(pen)
        p.drawLine(QPointF(frm.x, frm.y), QPointF(end.x, end.y))

    def _draw_arc(self, p: QPainter, angle_deg: float) -> None:
        v1 = self.end1 - self.vertex
        v2 = self.end2 - self.vertex
        if v1.length < 1e-4 or v2.length < 1e-4:
            return
        v1 = v1.normalized()
        v2 = v2.normalized()
        p1 = self.vertex + v1 * self.ARC_RADIUS
        p2 = self.vertex + v2 * self.ARC_RADIUS
        # Screen y-down: positive cross ⇒ v1→v2 sweep is clockwise.
        sweep_clockwise = cross(v1, v2) >= 0
        # atan2 returns the math angle (CCW from +x); in a y-down screen
        # that lands in the *opposite* visual quadrant from PyQt5's
        # arcTo, which measures CCW from +x in screen orientation
        # (so CCW from +x in y-down is visually CW). Negate to align.
        start_angle = -math.degrees(math.atan2(v1.y, v1.x))

        from PyQt5.QtGui import QPainterPath
        path = QPainterPath()
        path.moveTo(p1.x, p1.y)
        r = self.ARC_RADIUS
        # WPF's ArcSegment uses Size + SweepDirection + IsLargeArc; the
        # equivalent in Qt is QPainterPath.arcTo(rect, startAngle, sweepLength)
        # where positive sweepLength is CCW in math convention (CCW in Qt's
        # y-down screen too, because y is flipped). WPF Clockwise ⇒ Qt
        # negative sweep, and vice versa.
        if sweep_clockwise:
            path.arcTo(self.vertex.x - r, self.vertex.y - r, 2 * r, 2 * r,
                       start_angle, -angle_deg)
        else:
            path.arcTo(self.vertex.x - r, self.vertex.y - r, 2 * r, 2 * r,
                       start_angle, angle_deg)
        pen = QPen(COL_ORANGE, 3.0)
        p.setPen(pen)
        p.setBrush(_qcolor(COL_ORANGE, 0x33))
        p.drawPath(path)

    @staticmethod
    def _draw_handle(p: QPainter, center: Vec, big: bool) -> None:
        # Sizing matches the WPF XAML exactly:
        #   VertexThumb: 28x28 outer, Margin=6 inner ellipse (16x16), stroke 2
        #   HandleThumb: 22x22 outer, Margin=5 inner ellipse (12x12), stroke 2
        if big:
            outer_r = 14.0   # 28 diameter — matches VertexThumb
            inner_r = 8.0    # 16 diameter — matches Margin=6 inside 28
            halo = _qcolor(COL_ORANGE, 0x55)
            core = COL_ORANGE
        else:
            outer_r = 11.0   # 22 diameter — matches HandleThumb
            inner_r = 6.0    # 12 diameter — matches Margin=5 inside 22
            halo = _qcolor(COL_BLUE_HALO, 0x55)
            core = COL_BLUE
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(center.x, center.y), outer_r, outer_r)
        p.setBrush(QBrush(core))
        p.setPen(QPen(QColor(255, 255, 255), 2.0))
        p.drawEllipse(QPointF(center.x, center.y), inner_r, inner_r)
