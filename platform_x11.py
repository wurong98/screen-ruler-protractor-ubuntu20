"""X11 platform layer.

This is the *only* module allowed to import python-xlib or call X11 C
libraries directly. `ruler.py` and `protractor.py` go through this layer
for any X11-specific capability; that keeps the door open to a
`platform_wayland.py` swap-in later (Wayland has no input shape —
click-through would need the pointer-constraint protocol).

The public surface:
    cursor_pos()                       -> (x, y)       # global, XQueryPointer
    set_input_passthrough(win, on, w, h) -> None      # XFixes input shape
    virtual_screen_geom()              -> (x, y, w, h) # all monitors
    dip_per_cm_at(x, y)                -> float        # logical px per cm
                                                       # (0 if unknown)
"""
from __future__ import annotations

import ctypes
import ctypes.util
import re
import subprocess
from typing import List, Optional, Tuple

from Xlib import display
from Xlib.ext import shape


# --- singleton X11 connection ---------------------------------------------

_dpy: Optional[display.Display] = None


def _x11() -> display.Display:
    global _dpy
    if _dpy is None:
        _dpy = display.Display()
    return _dpy


# --- cursor ----------------------------------------------------------------

def cursor_pos() -> Tuple[int, int]:
    """Global cursor position via XQueryPointer on the root window."""
    d = _x11()
    root = d.screen().root
    reply = root.query_pointer()
    return int(reply.root_x), int(reply.root_y)


# --- click-through via XFixes (ctypes, own X11 connection) -----------------
#
# Why a separate connection: python-xlib's `Xlib.ext.shape.init` raises
# AssertionError on Ubuntu 20.04 python-xlib 0.33 (it tries to
# re-register a display method that's already there), and `Xlib.ext.xfixes`
# has no region API at all. So we open our own X11 connection via ctypes
# and talk to libXfixes.so.3 directly. python-xlib stays for the cursor
# query, where its socket protocol is plenty.

class _XRect(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_int16),
        ("y", ctypes.c_int16),
        ("width", ctypes.c_uint16),
        ("height", ctypes.c_uint16),
    ]


_libx11 = None
_libxfixes = None
_dpy_ptr: Optional[ctypes.c_void_p] = None
_xfixes_unavailable = False


def _xfixes_loaded() -> bool:
    """Lazily load libX11 + libXfixes and open our own Display connection."""
    global _libx11, _libxfixes, _dpy_ptr, _xfixes_unavailable
    if _xfixes_unavailable:
        return False
    if _dpy_ptr is not None:
        return True
    try:
        if _libx11 is None:
            x11_path = ctypes.util.find_library("X11") or "libX11.so.6"
            _libx11 = ctypes.CDLL(x11_path)
            _libx11.XOpenDisplay.restype = ctypes.c_void_p
            _libx11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            _libx11.XCloseDisplay.restype = ctypes.c_int
            _libx11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            _libx11.XSync.restype = ctypes.c_int
            _libx11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        if _libxfixes is None:
            for soname in ("libXfixes.so.3", "libXfixes.so.4", "libXfixes.so"):
                try:
                    _libxfixes = ctypes.CDLL(soname)
                    break
                except OSError:
                    continue
            if _libxfixes is None:
                _xfixes_unavailable = True
                return False
            _libxfixes.XFixesSetWindowShapeRegion.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong,
                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_void_p,
            ]
            _libxfixes.XFixesSetWindowShapeRegion.restype = ctypes.c_int
            _libxfixes.XFixesCreateRegion.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
            ]
            _libxfixes.XFixesCreateRegion.restype = ctypes.c_ulong
            _libxfixes.XFixesDestroyRegion.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong,
            ]
            _libxfixes.XFixesDestroyRegion.restype = ctypes.c_int
        _dpy_ptr = _libx11.XOpenDisplay(None)
        if not _dpy_ptr:
            _xfixes_unavailable = True
            return False
        return True
    except Exception:
        _xfixes_unavailable = True
        return False


# ShapeKind values (from Xfixes.h). Bounding=0, Clip=1, Input=2.
_SHAPE_KIND_INPUT = 2


def set_input_passthrough(window_xid: int, passthrough: bool,
                          win_w: int, win_h: int) -> None:
    """Toggle the *input shape* of an X11 window.

    passthrough=True  → empty input region (clicks pass through)
    passthrough=False → full-window input region (window receives input)

    Only call this on a state change — overlay.py caches the last value.
    Sending a Shape request every animation tick floods the X server and
    on some compositors also fights the window's own shape cache.
    """
    if not _xfixes_loaded():
        return  # libXfixes / X11 missing — silently degrade

    if passthrough:
        region = _libxfixes.XFixesCreateRegion(_dpy_ptr, None, 0)
    else:
        # Client-relative rectangle covering the whole window. Survives
        # window moves on mutter/KWin; server-relative can drift.
        rect = _XRect(0, 0, max(1, win_w), max(1, win_h))
        region = _libxfixes.XFixesCreateRegion(
            _dpy_ptr, ctypes.byref(rect), 1
        )

    _libxfixes.XFixesSetWindowShapeRegion(
        _dpy_ptr,
        ctypes.c_ulong(window_xid),
        _SHAPE_KIND_INPUT,
        0, 0,
        region,
    )
    _libxfixes.XFixesDestroyRegion(_dpy_ptr, region)
    _libx11.XSync(_dpy_ptr, 0)


# Backwards-compat alias for older callers; remove if no one uses it.
def set_click_through(*args, **kwargs):  # pragma: no cover
    return set_input_passthrough(*args, **kwargs)


# --- monitor geometry from xrandr (fallback) -------------------------------

def _xrandr_monitors() -> List[dict]:
    """Parse `xrandr --query` into a list of active outputs.

    Returned dict keys: name, x, y, w, h, wmm, hmm. Missing physical size
    is reported as 0 — the caller should treat that as "EDID not honoured".
    """
    try:
        out = subprocess.check_output(["xrandr", "--query"], text=True, timeout=2)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return []
    result: List[dict] = []
    for line in out.splitlines():
        m = re.match(
            r"^(\S+)\s+connected(?:\s+primary)?\s+"
            r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+).*?"
            r"(\d+)mm\s+x\s+(\d+)mm",
            line,
        )
        if m:
            name, w, h, x, y, wmm, hmm = m.groups()
            result.append({
                "name": name, "x": int(x), "y": int(y),
                "w": int(w), "h": int(h),
                "wmm": int(wmm), "hmm": int(hmm),
            })
    return result


def virtual_screen_geom() -> Tuple[int, int, int, int]:
    """Bounding rect of all monitors: (x, y, width, height).

    Tries Qt first (it knows about all screens including ones XRandR doesn't
    report, e.g. some nested-display-server setups). Falls back to xrandr
    output, then to the default X screen.
    """
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            screens = app.screens()
            if screens:
                x0 = min(s.geometry().x() for s in screens)
                y0 = min(s.geometry().y() for s in screens)
                x1 = max(s.geometry().x() + s.geometry().width() for s in screens)
                y1 = max(s.geometry().y() + s.geometry().height() for s in screens)
                return (x0, y0, x1 - x0, y1 - y0)
    except Exception:
        pass

    mons = _xrandr_monitors()
    if mons:
        x0 = min(m["x"] for m in mons)
        y0 = min(m["y"] for m in mons)
        x1 = max(m["x"] + m["w"] for m in mons)
        y1 = max(m["y"] + m["h"] for m in mons)
        return (x0, y0, x1 - x0, y1 - y0)

    d = _x11()
    s = d.screen()
    return (0, 0, s.width_in_pixels, s.height_in_pixels)


# --- DPI: logical pixels per centimetre ------------------------------------

def dip_per_cm_at(x: int, y: int) -> float:
    """Logical (device-independent) pixels per centimetre on the screen that
    contains the given global point. Returns 0.0 if the physical size is
    unknown or the calculation is impossible.

    Primary path: Qt's QScreen reports both `physicalSize()` (mm) and
    `geometry()` (device pixels). We divide by `devicePixelRatio()` to get
    logical pixels, which is the coordinate space the ruler draws in.

    Fallback path: parse xrandr for the same output and use its mm values.
    """
    # 1) Qt path.
    try:
        from PyQt5.QtCore import QPoint
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            screen = app.screenAt(QPoint(int(x), int(y)))
            if screen is None:
                # nearest screen
                screens = app.screens()
                if screens:
                    screen = screens[0]
            if screen is not None:
                w_mm = screen.physicalSize().width()
                if w_mm > 0:
                    phys_px = screen.size().width()
                    dpr = screen.devicePixelRatio() or 1.0
                    # logical_px_per_mm = phys_px / (dpr * mm)
                    return (phys_px / dpr) / (w_mm / 10.0)
    except Exception:
        pass

    # 2) xrandr fallback.
    for m in _xrandr_monitors():
        if m["x"] <= x < m["x"] + m["w"] and m["y"] <= y < m["y"] + m["h"]:
            if m["wmm"] > 0:
                return (m["w"] / (m["wmm"] / 10.0))  # px per cm, no DPR info
            return 0.0
    return 0.0
