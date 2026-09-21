# Copyright (c) 2026 ssme / Haoran Yu.
"""SARB command precision and companion-waveform alignment regressions."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from keithley4200.pmu.pmu_tests import configure_segARB_sequence, execute_segARB_test, auto_align_channels


class SarbWaveformFidelityTests(unittest.TestCase):
    def test_time_commands_preserve_ten_nanosecond_differences(self):
        commands = []
        durations = [0.12345678, 0.12345679]
        starts = [0.01234567, 0.01234568]
        configure_segARB_sequence(commands.append, 1, 1, [0, 1], [1, 0],
                                  durations, [2, 2], starts, durations)
        for command, expected in (("TIME", durations), ("MEAS:START", starts),
                                  ("MEAS:STOP", durations)):
            text = next(c for c in commands if c.startswith(":PMU:SARB:SEQ:" + command + " "))
            actual = [float(v) for v in text.split(",")[2:]]
            self.assertEqual(actual, expected)
            self.assertAlmostEqual(actual[1] - actual[0], 1e-8, places=15)

    def test_stepped_plateaus_are_not_replaced_with_a_constant_voltage(self):
        reference = (1, [0, 1, 0], [1, 0, 0], [1e-3] * 3, [0] * 3)
        staircase = (1, [0, 2], [0, 2], [1e-3, 2e-3], [0, 0])
        configs = {1: [reference], 2: [staircase]}
        original = deepcopy(configs)
        query = Mock()
        with self.assertRaisesRegex(ValueError, "not constant"):
            execute_segARB_test(query, [1, 2], configs)
        query.assert_not_called()
        self.assertEqual(configs, original)

    def test_constant_companion_remains_at_its_original_level(self):
        reference = (1, [0, 1, 0], [1, 0, 0], [1e-3] * 3, [0] * 3)
        hold = (1, [2], [2], [3e-3], [0])
        result = auto_align_channels({1: [reference], 2: [hold]})[2][0]
        self.assertEqual(result[1:4], ([2] * 3, [2] * 3, [1e-3] * 3))


if __name__ == "__main__":
    unittest.main()
