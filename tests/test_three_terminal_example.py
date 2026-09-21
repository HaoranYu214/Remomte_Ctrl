# Copyright (c) 2026 ssme / Haoran Yu.
"""Offline checks for the generic three-channel command example."""
from contextlib import contextmanager
import importlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from test_fet_3terminal import FakeKxci
from keithley4200.smu.system_mode import linear_sweep_point_count


class LinearFake(FakeKxci):
    def __call__(self, command):
        if command.startswith("CH") and "," in command and command.split(",")[-1].strip() == "1":
            self.sweep_channel = int(command.split(",")[0][2:])
        if command.startswith("VR1,"):
            start, stop, step, _ = map(float, command.split(",")[1:])
            self.values = [start + i * step for i in range(linear_sweep_point_count(start, stop, step))]
        return super().__call__(command)


class ThreeTerminalExampleTests(unittest.TestCase):
    module_name = "measurements.smu.3terminal.example"
    channels = (1, 2, 3)

    def setUp(self):
        self.module = importlib.import_module(self.module_name)
        self.variables = [f"{kind}{channel}" for channel in self.channels for kind in ("V", "I")]

    def tearDown(self):
        plt.close("all")

    @contextmanager
    def session(self, fake):
        yield type("Session", (), {"query": staticmethod(fake)})()

    def test_preview_prints_all_three_channels_without_connecting(self):
        with mock.patch.object(self.module, "PREVIEW_ONLY", True), \
             mock.patch.object(plt, "show"), \
             mock.patch.object(self.module, "SMUSession") as session, \
             mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.module.main()
        session.assert_not_called()
        last = self.channels[-1]
        self.assertIn(f"CH{last}, 'V{last}', 'I{last}', 1, 3", output.getvalue())
        self.assertIn(f"VC{last}, 0.0, 0.001", output.getvalue())
        self.assertIn("21 points", output.getvalue())

    def test_acquires_six_buffers_and_saves_csv(self):
        fake = LinearFake()
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(self.module, "PREVIEW_ONLY", False), \
             mock.patch.object(self.module, "SAVE_DIR", Path(directory)), \
             mock.patch.object(self.module, "SMUSession", side_effect=lambda *a: self.session(fake)):
            data = self.module.main()
            self.assertEqual(len(list(Path(directory).glob("*.csv"))), 1)
        self.assertEqual(len(data), 21)
        self.assertTrue(set(self.variables) <= set(data))
        self.assertEqual([c for c in fake.commands if c.startswith("DO")],
                         [f"DO '{v}'" for v in self.variables])
        self.assertEqual(fake.commands[-5:], ["DE", "CH1", "CH2", "CH3", "CH4"])

    def test_channel_remapping_and_independent_range(self):
        with mock.patch.object(self.module, "CHANNEL_1", 4), \
             mock.patch.dict(self.module.PARAMS, {"ch1_current_compliance": 2e-4, "ch2_current_range": 1e-6}):
            commands = []
            variables = self.module.configure(commands.append, [0, .5, 1])
        self.assertIn("CH4, 'V4', 'I4', 1, 1", commands)
        self.assertIn("VL4,1,0.0002,0,0.5,1", commands)
        self.assertIn("RG 2, 1e-06", commands)
        self.assertIn("V4", variables)
        self.assertNotIn("V1", variables)

    def test_invalid_compliance_prevents_commands(self):
        commands = []
        with mock.patch.dict(self.module.PARAMS, {"ch2_current_compliance": -1}):
            with self.assertRaises(ValueError):
                self.module.configure(commands.append, [0, 1])
        self.assertEqual(commands, [])

    def test_execution_error_aborts_disables_and_does_not_save(self):
        fake = LinearFake(error_after_execute=True)
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(self.module, "PREVIEW_ONLY", False), \
             mock.patch.object(self.module, "SAVE_DIR", Path(directory)), \
             mock.patch.object(self.module, "SMUSession", side_effect=lambda *a: self.session(fake)):
            with self.assertRaises(RuntimeError):
                self.module.main()
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertIn("ME4", fake.commands)
        self.assertNotIn("RP PMU1-1, 0", fake.commands)
        self.assertEqual(fake.commands[-5:], ["DE", "CH1", "CH2", "CH3", "CH4"])


class TwoTerminalExampleTests(ThreeTerminalExampleTests):
    module_name = "measurements.smu.2terminal.example"
    channels = (1, 2)


if __name__ == "__main__":
    unittest.main()
