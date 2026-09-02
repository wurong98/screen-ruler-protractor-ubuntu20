# Screen Protractor / Ruler — Linux port

> **Forked from:** [kingsimba/screen-ruler-protractor](https://github.com/kingsimba/screen-ruler-protractor)
> (original WPF / .NET 6 Windows version — see [upstream README](https://github.com/kingsimba/screen-ruler-protractor#readme) and [upstream workflow](https://github.com/kingsimba/screen-ruler-protractor/blob/master/.github/workflows/dotnet-desktop.yml))
>
> This project is a **PyQt5 + X11 port** targeting **Ubuntu 20.04**.
> Code is not shared with the WPF build — same feature surface, different stack.
> State file format is compatible with the Windows version so a single
> `state.json` can drive both ports if mounted cross-platform.

PyQt5 + X11 port of the WPF screen protractor & ruler for **Ubuntu 20.04 (X11)**.

Functionally equivalent to the Windows version: transparent fullscreen
overlay, click-through that only activates on control points, protractor
with two rays and an angle arc, ruler with mm/cm ticks, system-tray icon,
state persistence.

## Architecture

```
.
├── main.py                 QApplication entry point (thin launcher)
│
├── src/screen_ruler/       the package — only place that holds implementation
│   ├── geometry.py         pure-Python math (Vec, angle, point_in_polygon, hysteresis)
│   ├── state.py            XDG config + atomic JSON save (file format compatible with WPF)
│   ├── platform_x11.py     the only module that touches X11: cursor + XFixes input shape
│   │                       + monitor/DPI lookup (Qt primary, xrandr fallback)
│   ├── protractor.py       protractor tool: state + QPainter drawing (no Xlib)
│   ├── ruler.py            ruler tool: state + QPainter drawing + hysteresis (no Xlib)
│   ├── overlay.py          main QWidget: fullscreen transparent window, hit-test polling,
│   │                       drag handling, click-through toggle (calls platform_x11)
│   └── tray.py             QSystemTrayIcon with a 32×32 runtime-painted protractor glyph
│
├── tests/                  unittest suite
│   ├── test_geometry.py    unit tests (no display required)
│   ├── test_state.py       unit tests (no display required)
│   └── smoke_test.py       full-stack paint test (needs Xvfb)
│
├── .github/workflows/      CI (ubuntu-20.04 + xvfb)
├── README.md
├── CHANGELOG.md
├── LICENSE                 MIT
└── .gitignore
```

Strict layering: `ruler` and `protractor` only import `geometry`. They
never touch X11, so the door is open to a `platform_wayland.py` swap that
keeps the same public surface (`cursor_pos`, `set_input_passthrough`,
`virtual_screen_geom`, `dip_per_cm_at`).

## Requirements

Ubuntu 20.04 ships everything needed:

| Package                | Version on 20.04 | Notes                                 |
|------------------------|------------------|---------------------------------------|
| `python3`              | 3.8.10           | system Python                         |
| `python3-pyqt5`        | 5.14.1           | Qt 5 widgets + QPainter               |
| `python3-xlib`         | 0.33             | X11 protocol, used only for cursor    |
| `libxfixes-dev`        | 1:5.0.3-2        | XFixes input shape (click-through)    |
| `libxrandr`            | 1.5.2            | monitor geometry fallback             |
| `xrandr`               | any              | CLI tool used as DPI fallback         |
| `xvfb`                 | 2:1.20.13        | only needed for the smoke test        |

**No `pip install` is required.** All of the above are pre-installed on
a typical Ubuntu 20.04 desktop with `python3-pyqt5` available; verify
with:

```bash
python3 -c "import PyQt5.QtWidgets, Xlib; print('OK')"
```

## Run

```bash
# from the repo root
python3 main.py
```

The overlay appears fullscreen, the tray icon shows up in the system
tray, and the overlay is click-through by default. Move the cursor near
a control point (the orange/blue circles) and the overlay starts
accepting input so you can drag.

Right-click any handle for the context menu, or double-click the tray
icon to show/hide the overlay.

## State

```text
$XDG_CONFIG_HOME/screen-protractor/state.json
   (default: ~/.config/screen-protractor/state.json)
```

Schema matches the WPF version's `%AppData%\ScreenProtractor\state.json`
so the two ports can share a state file if mounted cross-platform.

## Tests

```bash
# Unit tests — no display required
python3 -m unittest discover -t . -s tests -p "test_*.py" -v

# Smoke test — needs an X server, use Xvfb
xvfb-run -a python3 -m unittest discover -t . -s tests -p "smoke_test.py" -v
```

The `-t .` (top-level dir) flag is what makes the in-repo
`src/screen_ruler` package importable from the test files without an
editable install. `main.py` and `tests/__init__.py` add the same path
when invoked directly.

The smoke test:
1. Imports every module (catches `ImportError`s from X11 path).
2. Roundtrips `state.save` → `state.load`.
3. Constructs `OverlayWindow`, resizes, shows, and `render()`s into a
   `QPixmap`. Asserts the protractor drawing produces opaque pixels and
   the ruler drawing (after `toggle_mode()`) does too.

## Known limitations vs. the WPF version

- **Physical-cm calibration on cheap monitors.** If `xrandr` reports
  `0mm × 0mm` (panels without proper EDID), the ruler falls back to
  pixel mode. The WPF version uses `GetDpiForMonitor(MDT_RAW_DPI)` which
  is a closer reading of the panel's true density; the two numbers may
  differ by a few percent on those monitors.
- **Click-through edge cases.** Some X11 compositors (mutter, KWin in
  certain focus modes) re-translate the input shape on window move; we
  use client-relative rectangles to minimise this, but if you see the
  overlay suddenly grab clicks after a fast drag, that is the cause.
- **Tray icon on GNOME.** GNOME does not show StatusNotifierItem icons
  without the `appindicator` extension installed
  (`sudo apt install gnome-shell-extension-appindicator`).
- **Transparency on X11.** We rely on `WA_TranslucentBackground` with no
  background fill. If a particular compositor refuses to alpha-blend an
  empty surface, switch the commented line in `overlay.paintEvent` to
  `p.fillRect(self.rect(), QColor(0, 0, 0, 1))` (the 1-alpha hack from
  the WPF version).

## Troubleshooting

| Symptom                                  | Likely cause                              |
|------------------------------------------|-------------------------------------------|
| `libXfixes.so.3: cannot open shared object file` | missing `libxfixes-dev`                |
| `qt.qpa.xcb: could not connect to display`       | run under `xvfb-run` (or a real display) |
| Tray icon invisible on GNOME                    | install `gnome-shell-extension-appindicator` |
| `import Xlib` fails                             | `sudo apt install python3-xlib`           |
| Ruler shows "px" instead of "cm"                | monitor EDID missing; install or update it |
