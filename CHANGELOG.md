# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

Initial release as a standalone project, extracted from
[`kingsimba/screen-ruler-protractor`](https://github.com/kingsimba/screen-ruler-protractor)'s
`linux/` subdirectory.

- **2026-09-02**: Standalone Ubuntu 20.04 / PyQt5 / X11 port
- Transparent fullscreen overlay, click-through that only activates on control points
- Protractor with two rays and an angle arc (0.1° precision)
- Ruler with mm/cm ticks, auto DPI detection
- System-tray icon with double-click and context menu
- State persistence to `$XDG_CONFIG_HOME/screen-protractor/state.json`
  (format-compatible with the WPF version's `%AppData%\ScreenProtractor\state.json`)
