"""Unit tests for state.py.

Run:
    cd linux && python3 -m unittest test_state
"""
import json
import os
import tempfile
import unittest
from unittest import mock

import state


class StateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        # mkdtemp returns a real dir; rmtree it.
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _with_config_home(self):
        return mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp})

    def test_load_missing_returns_defaults(self):
        with self._with_config_home():
            s = state.load()
            self.assertEqual(s.mode, "protractor")
            self.assertEqual(s.protractor, [])
            self.assertEqual(s.ruler, [])

    def test_save_then_load_roundtrip(self):
        with self._with_config_home():
            s = state.OverlayState(
                mode="ruler",
                protractor=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                ruler=[10.0, 20.0, 30.0, 40.0],
            )
            state.save(s)
            loaded = state.load()
            self.assertEqual(loaded.mode, "ruler")
            self.assertEqual(loaded.protractor,
                             [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
            self.assertEqual(loaded.ruler, [10.0, 20.0, 30.0, 40.0])

    def test_save_windows_style_keys(self):
        # State file must use the WPF version's casing so the two ports
        # can share a config file if mounted cross-platform.
        with self._with_config_home():
            s = state.OverlayState(mode="protractor",
                                   protractor=[1, 2, 3, 4, 5, 6])
            state.save(s)
            with open(state.state_path()) as f:
                raw = json.load(f)
            self.assertIn("Mode", raw)
            self.assertIn("Protractor", raw)
            self.assertIn("Ruler", raw)
            self.assertEqual(raw["Mode"], "Protractor")

    def test_save_atomic(self):
        # save() must not leave a partial .tmp behind on success.
        with self._with_config_home():
            state.save(state.OverlayState())
            self.assertFalse(os.path.exists(state.state_path() + ".tmp"))

    def test_load_garbage_returns_defaults(self):
        with self._with_config_home():
            p = state.state_path()
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write("{ not valid json")
            s = state.load()
            self.assertEqual(s.mode, "protractor")

    def test_load_unknown_mode_falls_back(self):
        with self._with_config_home():
            p = state.state_path()
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                json.dump({"Mode": "garbage", "Protractor": [], "Ruler": []}, f)
            s = state.load()
            self.assertEqual(s.mode, "protractor")


if __name__ == "__main__":
    unittest.main()
