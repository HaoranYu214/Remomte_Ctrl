# Copyright (c) 2026 ssme / Haoran Yu.
"""Check shared paths and actual experiment command sequences without hardware."""
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from contextlib import contextmanager
import numpy as np
from test_three_terminal_example import LinearFake
from keithley4200.smu.points import build_segmented_voltage_path


@contextmanager
def session(fake):
    yield type("Session", (), {"query": staticmethod(fake)})()


class LocalSMUPlanTests(unittest.TestCase):
    def test_local_segment_builders_preserve_paths_and_reject_huge_allocations(self):
        for name in ("2terminal.segmented_voltage_sweep", "2terminal.segmented_voltage_sweep_Memristor",
                     "3terminal.output", "3terminal.transfer"):
            module = importlib.import_module("measurements.smu." + name)
            for path, step in (([0, 1, -1, 0], .3), ([0, 0, -1, 0], [.1, .2, .5])):
                with self.subTest(module=name, path=path):
                    self.assertEqual(module.build_points(path, step), build_segmented_voltage_path(path, step))
            with self.assertRaises(ValueError):
                module.build_points([0, 1], 1e-300)

    def test_example_point_methods_and_list_commands(self):
        for name in ("2terminal", "3terminal"):
            module = importlib.import_module(f"measurements.smu.{name}.example")
            for method in ("linear", "list", "segments", "log"):
                with self.subTest(module=name, method=method), mock.patch.object(module, "POINT_METHOD", method):
                    values = module.build_points()
                    commands = []
                    module.configure(commands.append, values)
                    if method == "linear":
                        self.assertEqual(len(values), 21)
                    self.assertTrue(any(c.startswith("VL1,") for c in commands))
                    self.assertFalse(any(c.startswith("VR") for c in commands))
                    if method == "list":
                        self.assertEqual(values, module.LIST_POINTS)
                    if method == "segments":
                        np.testing.assert_allclose(values, build_segmented_voltage_path(module.TURNING_POINTS, module.STEP), atol=1e-12)
                    if method == "log":
                        ratios = np.array(values[1:]) / values[:-1]
                        np.testing.assert_allclose(ratios, ratios[0])

    def test_two_terminal_entries_send_points_and_record_them(self):
        for name in ("linear_voltage_sweep", "segmented_voltage_sweep", "segmented_voltage_sweep_Memristor"):
            module = importlib.import_module("measurements.smu.2terminal." + name)
            fake = LinearFake()
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory, \
                 mock.patch.object(module, "PREVIEW_ONLY", False), \
                 mock.patch.object(module, "SAVE_DIR", Path(directory)), \
                 mock.patch.object(module, "SMUSession", side_effect=lambda *a: session(fake)), \
                 mock.patch.object(module, "save_workbook") as save, \
                 mock.patch.object(module, "save_current_density_plots", return_value=(Path(directory)/"a.png", Path(directory)/"b.png")):
                module.main()
                frame = save.call_args.args[1]
                np.testing.assert_allclose(frame["CommandedVoltage"], fake.values)
                self.assertIn("ME1", fake.commands)
                self.assertEqual(fake.commands[-5:], ["DE", "CH1", "CH2", "CH3", "CH4"])

    def test_two_terminal_execution_error_aborts_and_does_not_save(self):
        module = importlib.import_module("measurements.smu.2terminal.segmented_voltage_sweep")
        fake = LinearFake(error_after_execute=True)
        with mock.patch.object(module, "SMUSession", side_effect=lambda *a: session(fake)), \
             mock.patch.object(module, "save_workbook") as save:
            with self.assertRaises(RuntimeError):
                module.run_test(turning_points=[0, 1, 0], segment_step=1, preview_only=False)
            save.assert_not_called()
        self.assertIn("ME4", fake.commands)
        self.assertNotIn("RP PMU1-1, 0", fake.commands)
        self.assertEqual(fake.commands[-5:], ["DE", "CH1", "CH2", "CH3", "CH4"])

    def test_spot_uses_direct_dv_and_powers_off_before_rpm_restore(self):
        module = importlib.import_module("measurements.smu.2terminal.user_mode_spot")
        commands = []
        def query(command):
            commands.append(command)
            if command == ":ERROR:LAST:GET":
                return "No error. (0)"
            if command.startswith("TI"):
                return "N1e-6"
            return "ACK"
        with mock.patch.object(module, "SMUSession", side_effect=lambda *a: session(query)), \
             mock.patch.object(module.time, "sleep"):
            module.main()
        self.assertIn(f"DV{module.CHANNEL}, {module.VOLTAGE_RANGE_CODE}, {module.SOURCE_VOLTAGE}, {module.CURRENT_COMPLIANCE}", commands)
        self.assertLess(commands.index(f"DV{module.CHANNEL}"), commands.index("RP PMU1-1, 0"))

    def test_two_terminal_kxci_graph_keeps_both_current_measurements(self):
        for name in ("linear_voltage_sweep", "segmented_voltage_sweep", "segmented_voltage_sweep_Memristor"):
            module = importlib.import_module("measurements.smu.2terminal." + name)
            fake = LinearFake()
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory, \
                 mock.patch.object(module, "KXCI_PLOT", True), \
                 mock.patch.object(module, "PREVIEW_ONLY", False), \
                 mock.patch.object(module, "SAVE_DIR", Path(directory)), \
                 mock.patch.object(module, "SMUSession", side_effect=lambda *a: session(fake)), \
                 mock.patch.object(module, "save_workbook") as save, \
                 mock.patch.object(module, "save_current_density_plots", return_value=(Path(directory)/"a.png", Path(directory)/"b.png")):
                module.main()
                self.assertTrue(save.call_args.args[2]["KXCI_PLOT"])
                self.assertTrue({"V1", "I1", "V2", "I2"} <= set(save.call_args.args[1]))
            self.assertIn("SM DM1", fake.commands)
            for command, key in (("XN", "sweep_voltage"), ("YA", "sweep_current"), ("YB", "bias_current")):
                self.assertTrue(any(c.startswith(f"{command} '{module.NAMES[key]}', 1,") for c in fake.commands))
            self.assertFalse(any(c.startswith("LI ") for c in fake.commands))
            self.assertEqual(len([c for c in fake.commands if c.startswith("DO ")]), 4)

    def test_two_terminal_example_graph_preview_and_invalid_limits(self):
        module = importlib.import_module("measurements.smu.2terminal.example")
        with mock.patch.object(module, "KXCI_PLOT", True):
            commands = []
            module.configure(commands.append, module.build_points())
            self.assertIn("SM DM1", commands)
            self.assertIn("XN 'V1', 1, 0, 1", commands)
            self.assertIn("YA 'I1', 1, -0.001, 0.001", commands)
            self.assertIn("YB 'I2', 1, -0.001, 0.001", commands)
            with self.assertRaisesRegex(ValueError, "distinct"):
                module.configure(lambda command: None, [0, 0])
