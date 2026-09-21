# Copyright (c) 2026 ssme / Haoran Yu.
"""Point generation contract, independent of instrument command construction."""
import unittest
from keithley4200.smu.points import (
    build_linear_voltage_path, build_segmented_voltage_path,
    build_log_voltage_path, validate_list_points,
)


class PointTests(unittest.TestCase):
    def test_linear_short_last_interval_and_reverse(self):
        self.assertEqual(build_linear_voltage_path(0, 1, .3), [0, .3, .6, .9, 1])
        self.assertEqual(build_linear_voltage_path(1, 0, -.3), [1, .7, .4, .1, 0])
        self.assertEqual(build_linear_voltage_path(1, 1, .1), [1])

    def test_segment_steps_and_shared_endpoints(self):
        self.assertEqual(build_segmented_voltage_path([0, 1, 1, 0], [.5, .1, .25]),
                         [0, .5, 1, .75, .5, .25, 0])

    def test_limit_is_applied_to_expanded_points(self):
        self.assertEqual(len(build_linear_voltage_path(0, 4095, 1)), 4096)
        with self.assertRaisesRegex(ValueError, "4096"):
            build_linear_voltage_path(0, 4096, 1)
        with self.assertRaisesRegex(ValueError, "4096"):
            build_segmented_voltage_path([0, 1], 1e-300)
        with self.assertRaisesRegex(ValueError, "4096"):
            validate_list_points(range(4097))

    def test_custom_list_keeps_order_and_repeated_points(self):
        original = [1, 0, 0, -1]
        values = validate_list_points(original)
        self.assertEqual(values, original)
        self.assertIsNot(values, original)

    def test_invalid_inputs(self):
        for args in [(0, 1, -1), (1, 0, 1), (0, 1, 0), (0, float("inf"), 1)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                build_linear_voltage_path(*args)
        for path, step in [([0], 1), ([0, 1], [1, 2]), ([0, 1], 0), ([0, float("nan")], 1)]:
            with self.subTest(path=path, step=step), self.assertRaises(ValueError):
                build_segmented_voltage_path(path, step)
        for values in [[], [float("nan")], [float("inf")]]:
            with self.assertRaises(ValueError):
                validate_list_points(values)

    def test_log_endpoints_and_signed_geometric_spacing(self):
        for sign in [1, -1]:
            self.assertEqual(build_log_voltage_path(sign, sign*100, 3), [sign, sign*10, sign*100])
        for args in [(0, 1, 3), (-1, 1, 3), (1, 10, 2.5), (1, 10, True), (1, 10, 4097)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                build_log_voltage_path(*args)
