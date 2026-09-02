"""Unit tests for geometry.py.

Run:
    cd linux && python3 -m unittest test_geometry
"""
import math
import unittest

from geometry import Vec, angle_between, cross, near, point_in_polygon


class VecTests(unittest.TestCase):
    def test_add_sub(self):
        a, b = Vec(1, 2), Vec(3, 5)
        self.assertEqual((a + b).x, 4)
        self.assertEqual((b - a).y, 3)

    def test_scalar_mul(self):
        self.assertEqual((Vec(2, 3) * 4).x, 8)
        self.assertEqual((4 * Vec(2, 3)).y, 12)

    def test_length(self):
        self.assertAlmostEqual(Vec(3, 4).length, 5.0)

    def test_normalized_degenerate(self):
        # Zero vector must NOT divide by zero.
        v = Vec(0, 0).normalized()
        self.assertEqual(v, Vec(1, 0))

    def test_normalized_unit(self):
        v = Vec(10, 0).normalized()
        self.assertAlmostEqual(v.length, 1.0)
        self.assertEqual(v, Vec(1, 0))


class AngleTests(unittest.TestCase):
    def test_right_angle(self):
        a = angle_between(Vec(1, 0), Vec(0, 1))
        self.assertAlmostEqual(a, 90.0, places=6)

    def test_parallel(self):
        # Two non-degenerate parallel vectors give a real 0°.
        a = angle_between(Vec(1, 0), Vec(1, 0))
        self.assertAlmostEqual(a, 0.0, places=6)
        a = angle_between(Vec(2, 0), Vec(-3, 0))
        self.assertAlmostEqual(a, 180.0, places=6)

    def test_zero_degenerate(self):
        # Mathematically-degenerate (zero-length) vectors: angle is
        # defined as 0° by convention, but protractor.angle_deg adds
        # its own screen-scale check that turns this into None. The
        # raw math function stays a pure float so unit tests can use
        # short vectors.
        self.assertEqual(angle_between(Vec(0, 0), Vec(1, 0)), 0.0)
        self.assertEqual(angle_between(Vec(1, 0), Vec(0, 0)), 0.0)
        self.assertEqual(angle_between(Vec(0, 0), Vec(0, 0)), 0.0)

    def test_45_deg(self):
        a = angle_between(Vec(1, 0), Vec(1, 1))
        self.assertAlmostEqual(a, 45.0, places=6)


class CrossTests(unittest.TestCase):
    def test_screen_y_down_clockwise(self):
        # In screen coords (y-down), rotating (1,0) toward (0,1) is
        # clockwise. Cross product > 0 ⇒ clockwise.
        self.assertGreater(cross(Vec(1, 0), Vec(0, 1)), 0)
        self.assertLess(cross(Vec(0, 1), Vec(1, 0)), 0)


class PointInPolygonTests(unittest.TestCase):
    def setUp(self):
        # Unit square at (0,0)-(1,1)
        self.square = [Vec(0, 0), Vec(1, 0), Vec(1, 1), Vec(0, 1)]

    def test_inside(self):
        self.assertTrue(point_in_polygon(Vec(0.5, 0.5), self.square))

    def test_outside(self):
        self.assertFalse(point_in_polygon(Vec(2, 2), self.square))
        self.assertFalse(point_in_polygon(Vec(-1, 0.5), self.square))

    def test_too_few_vertices(self):
        self.assertFalse(point_in_polygon(Vec(0, 0), [Vec(0, 0), Vec(1, 1)]))

    def test_concave(self):
        # L-shaped polygon; (0.7, 0.7) is in the notch — outside.
        l_shape = [Vec(0, 0), Vec(1, 0), Vec(1, 0.3), Vec(0.3, 0.3),
                   Vec(0.3, 1), Vec(0, 1)]
        self.assertFalse(point_in_polygon(Vec(0.7, 0.7), l_shape))
        self.assertTrue(point_in_polygon(Vec(0.1, 0.1), l_shape))


class NearTests(unittest.TestCase):
    def test_inside_radius(self):
        self.assertTrue(near(Vec(0, 0), Vec(3, 4), 5.5))
        self.assertTrue(near(Vec(0, 0), Vec(3, 4), 5.0))

    def test_outside_radius(self):
        self.assertFalse(near(Vec(0, 0), Vec(3, 4), 4.999))


if __name__ == "__main__":
    unittest.main()
