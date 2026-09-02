"""Test package.

Adds the in-repo `src/` directory to `sys.path` so the test files can
`import screen_ruler.*` without an editable install. This is the same
trick `main.py` and `tests/smoke_test.py` use, just centralised here
so every test under this package picks it up.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
