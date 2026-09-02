"""Load/save the overlay state to ~/.config/screen-protractor/state.json.

Schema matches what the WPF version writes to
%AppData%\\ScreenProtractor\\state.json, so a port is byte-compatible.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Tuple


def _config_dir() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, "screen-protractor")
    os.makedirs(d, exist_ok=True)
    return d


def state_path() -> str:
    return os.path.join(_config_dir(), "state.json")


@dataclass
class OverlayState:
    mode: str = "protractor"     # "protractor" | "ruler"
    protractor: List[float] = field(default_factory=list)  # [vx,vy, ex1,ey1, ex2,ey2]
    ruler: List[float] = field(default_factory=list)      # [ax,ay, bx,by]


def load() -> OverlayState:
    p = state_path()
    if not os.path.exists(p):
        return OverlayState()
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[state] failed to load {p}: {e}", file=sys.stderr)
        return OverlayState()
    s = OverlayState()
    s.mode = raw.get("Mode", "protractor").lower()
    if s.mode not in ("protractor", "ruler"):
        s.mode = "protractor"
    for key, dst in (("Protractor", "protractor"), ("Ruler", "ruler")):
        v = raw.get(key)
        if isinstance(v, list):
            setattr(s, dst, [float(x) for x in v])
    return s


def save(s: OverlayState) -> None:
    p = state_path()
    # Match the WPF version's key casing so the two can share files.
    payload = {
        "Mode": "Protractor" if s.mode == "protractor" else "Ruler",
        "Protractor": list(s.protractor),
        "Ruler": list(s.ruler),
    }
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
