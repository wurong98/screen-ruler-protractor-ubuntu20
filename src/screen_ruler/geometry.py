"""Pure-Python math helpers — ported from the WPF version's OverlayWindow.xaml.cs.

No Qt, no X11. Unit-agnostic — never assumes pixels. Imported by both
protractor.py and ruler.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# --- 2D primitives (in window/device-independent pixels) -------------------

@dataclass(frozen=True)
class Vec:
    x: float
    y: float

    def __add__(self, other: "Vec") -> "Vec":
        return Vec(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec") -> "Vec":
        return Vec(self.x - other.x, self.y - other.y)

    def __mul__(self, k: float) -> "Vec":
        return Vec(self.x * k, self.y * k)

    __rmul__ = __mul__

    def __neg__(self) -> "Vec":
        return Vec(-self.x, -self.y)

    @property
    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Vec":
        n = self.length
        if n < 1e-9:
            return Vec(1.0, 0.0)
        return Vec(self.x / n, self.y / n)


# --- geometry --------------------------------------------------------------

# Mathematically-degenerate threshold. A vector shorter than this has
# no defined direction; below this, angle_between returns 0.0 (parallel).
# Note: this is *not* the visual / screen-pixel threshold. The protractor
# keeps its own MIN_USABLE_LENGTH in screen units so math unit tests can
# use short vectors and still get real angles.
_MATH_EPS = 1e-9


def angle_between(v1: Vec, v2: Vec) -> float:
    """Unsigned angle (0..180) in degrees between two vectors sharing an origin.

    Returns 0.0 when either vector is mathematically degenerate (shorter
    than _MATH_EPS). For a *visual* / screen-scale "is the arm too short
    to measure" check, use Protractor.angle_deg, which has its own
    MIN_USABLE_LENGTH in screen pixels.
    """
    a = v1.length
    b = v2.length
    if a < _MATH_EPS or b < _MATH_EPS:
        return 0.0
    cos = (v1.x * v2.x + v1.y * v2.y) / (a * b)
    cos = max(-1.0, min(1.0, cos))
    return math.degrees(math.acos(cos))


def cross(v1: Vec, v2: Vec) -> float:
    """2D cross product. Screen coords (y-down): >0 ⇒ v1→v2 sweep is clockwise."""
    return v1.x * v2.y - v1.y * v2.x


def point_in_polygon(pt: Vec, poly: list[Vec]) -> bool:
    """Standard ray-cast test. poly is a list of vertices (no need to close)."""
    if len(poly) < 3:
        return False
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        if (poly[i].y > pt.y) != (poly[j].y > pt.y):
            x_intersect = (poly[j].x - poly[i].x) * (pt.y - poly[i].y) / (
                poly[j].y - poly[i].y
            ) + poly[i].x
            if pt.x < x_intersect:
                inside = not inside
        j = i
    return inside


def near(a: Vec, b: Vec, radius: float) -> bool:
    return (a - b).length <= radius
