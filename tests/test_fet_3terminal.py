# Copyright (c) 2026 ssme / Haoran Yu.
"""Hardware-free command, checkpoint and entry tests for three-terminal FETs."""
from contextlib import contextmanager
import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from keithley4200.smu import fet
from keithley4200.smu.points import build_segmented_voltage_path

CONNECTIONS = {1: "rpm:PMU1-1", 2: "rpm:PMU1-2", 3: "direct", 4: "direct"}


class FakeKxci:
    def __init__(self, *, error_after_execute=False, compliance=False, empty=False, source_offset=0.0, source_compliance=False):
        self.commands = []
        self.names = {}
        self.values = []
        self.sweep_channel = None
        self.bias = {}
        self.executed = False
        self.error_after_execute = error_after_execute
        self.compliance = compliance
        self.empty = empty
        self.source_offset = source_offset
        self.source_compliance = source_compliance

    def __call__(self, command):
        self.commands.append(command)
        if command.startswith("CH") and "," in command:
            parts = command.split(",")
            self.names[int(parts[0][2:])] = (parts[1].strip(" '"), parts[2].strip(" '"))
        elif command.startswith("VL"):
            parts = command.split(",")
            self.sweep_channel = int(parts[0][2:])
            self.values = [float(v) for v in parts[3:]]
        elif command.startswith("VC"):
            parts = command.split(",")
            self.bias[int(parts[0][2:])] = float(parts[1])
        elif command == "ME1":
            self.executed = True
        elif command == ":ERROR:LAST:GET":
            return "Failure (-992)" if self.executed and self.error_after_execute else "No error. (0)"
        elif command == "SP":
            return "1"
        elif command.startswith("DO '"):
            if self.empty:
                return ""
            variable = command.split("'")[1]
            channel = next(c for c, names in self.names.items() if variable in names)
            values = self.values if channel == self.sweep_channel else [self.bias[channel]] * len(self.values)
            if variable == "ID":
                values = [v * 1e-5 + 1e-8 for v in values]
            elif variable == "IG":
                values = [v * 1e-10 for v in values]
            elif variable == "VS":
                values = [v + self.source_offset for v in values]
            elif variable == "IS":
                values = [-2e-6] * len(values)
            return ",".join(("C" if (self.compliance and variable == "ID" or self.source_compliance and variable == "IS") and i == 0 else "N") + str(v)
                            for i, v in enumerate(values))
        return "ACK"


class FetCommandTests(unittest.TestCase):
    def acquire(self, fake, **settings):
        config = fet.validate_fet_sweep(**settings)
        module = importlib.import_module("measurements.smu.3terminal.transfer")
        @contextmanager
        def session(*args):
            yield type("Session", (), {"query": staticmethod(fake)})()
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(module, "build_plan", return_value=[config]), \
             mock.patch.object(module, "SMUSession", side_effect=session), \
             mock.patch.object(module, "save_fet_checkpoint"), \
             mock.patch.object(module, "save_fet_plot"):
            return module.run_test(preview_only=False, save_dir=directory, show=False)["data"]

    def settings(self, **updates):
        return dict(values=[-0.1, 0.0, 0.1], sweep_terminal="gate", bias_voltage=0.1,
                    smu_connections=CONNECTIONS, **updates)

    def test_transfer_forces_source_voltage_and_measures_all_six_buffers(self):
        fake = FakeKxci()
        data = self.acquire(fake, **self.settings())
        self.assertIn("CH3, 'VS', 'IS', 1, 3", fake.commands)
        self.assertIn("CH1, 'VG', 'IG', 1, 1", fake.commands)
        self.assertIn("CH2, 'VD', 'ID', 1, 3", fake.commands)
        self.assertIn("VL1,1,1e-06,-0.1,0,0.1", fake.commands)
        self.assertIn("VC2, 0.1, 0.001", fake.commands)
        self.assertIn("VC3, 0.0, 0.001", fake.commands)
        self.assertIn("SM DM2", fake.commands)
        self.assertIn("LI 'VG', 'IG', 'VD', 'ID', 'VS', 'IS'", fake.commands)
        for ch in (1, 2, 3):
            self.assertIn(f"ST {ch}, 1", fake.commands)
        self.assertEqual([c for c in fake.commands if c.startswith("DO")],
                         ["DO 'VG'", "DO 'IG'", "DO 'VD'", "DO 'ID'", "DO 'VS'", "DO 'IS'"])
        self.assertEqual(data["VGS"].tolist(), [-0.1, 0, 0.1])
        self.assertEqual(data["VDS"].tolist(), [0.1] * 3)
        self.assertIn("ID_Status", data)
        self.assertEqual(data["IS"].tolist(), [-2e-6] * 3)
        self.assertLess(fake.commands.index("*RST"), fake.commands.index("RP PMU1-1, 2"))
        self.assertLess(fake.commands.index("DO 'ID'"), fake.commands.index("RP PMU1-1, 0"))

    def test_output_swaps_sweep_role_without_swapping_compliances(self):
        fake = FakeKxci()
        settings = self.settings()
        settings.update(sweep_terminal="drain", bias_voltage=-0.5)
        data = self.acquire(fake, **settings)
        self.assertIn("VL2,1,0.001,-0.1,0,0.1", fake.commands)
        self.assertIn("VC1, -0.5, 1e-06", fake.commands)
        self.assertEqual(data["VGS"].tolist(), [-0.5] * 3)
        self.assertEqual(data["VDS"].tolist(), [-0.1, 0, 0.1])

    def test_channel_remapping_and_list_mode(self):
        fake = FakeKxci()
        settings = self.settings(kxci_plot=False, gate_channel=4, drain_channel=3, source_channel=1, source_current_range=1e-6)
        data = self.acquire(fake, **settings)
        self.assertIn("CH1, 'VS', 'IS', 1, 3", fake.commands)
        self.assertIn("VL4,1,1e-06,-0.1,0,0.1", fake.commands)
        self.assertIn("VC1, 0.0, 0.001", fake.commands)
        self.assertIn("RG 1, 1e-06", fake.commands)
        self.assertIn("SM DM2", fake.commands)
        self.assertIn("LI 'VG', 'IG', 'VD', 'ID', 'VS', 'IS'", fake.commands)
        self.assertNotIn("RP PMU1-2, 2", fake.commands)
        self.assertEqual(data["CommandedVGS_V"].tolist(), [-0.1, 0, 0.1])

    def test_graph_trial_still_requests_all_six_buffers(self):
        fake = FakeKxci()
        data = self.acquire(fake, **self.settings(kxci_plot=True))
        self.assertLess(fake.commands.index("LI 'VG', 'IG', 'VD', 'ID', 'VS', 'IS'"),
                        fake.commands.index("SM DM1"))
        self.assertIn("XN 'VG', 1, -0.1, 0.1", fake.commands)
        self.assertIn("YA 'IG', 1, -1e-06, 1e-06", fake.commands)
        self.assertIn("YB 'IS', 1, -0.001, 0.001", fake.commands)
        self.assertTrue({"VG", "IG", "VD", "ID", "VS", "IS"} <= set(data))
        self.assertEqual(len([c for c in fake.commands if c.startswith("DO '")]), 6)

    def test_graph_trial_missing_unplotted_current_fails(self):
        fake = FakeKxci()
        def missing_id(command):
            result = fake(command)
            return "" if command == "DO 'ID'" else result
        with self.assertRaises((ValueError, RuntimeError)):
            self.acquire(missing_id, **self.settings(kxci_plot=True))
        self.assertNotIn("RP PMU1-1, 0", fake.commands)

    def test_sequential_calls_reset_and_reapply_source_settings(self):
        fake = FakeKxci()
        self.acquire(fake, **self.settings(source_voltage=0.2, source_current_range=1e-6))
        split = len(fake.commands)
        self.acquire(fake, **self.settings())
        second = fake.commands[split:]
        self.assertIn("*RST", second)
        self.assertIn("CH3, 'VS', 'IS', 1, 3", second)
        self.assertIn("VC3, 0.0, 0.001", second)
        self.assertFalse(any(c.startswith("RG ") for c in second))
        self.assertLess(second.index("*RST"), second.index("VC3, 0.0, 0.001"))

    def test_per_call_overrides_do_not_change_either_module_defaults(self):
        modules = [importlib.import_module("measurements.smu.3terminal." + name)
                   for name in ("output", "transfer")]
        defaults = [dict(module.PARAMS) for module in modules]
        for module in modules:
            with mock.patch.object(module, "preview_fet_family") as preview:
                module.run_test({"source_voltage": 0.2}, preview_only=True, show=False)
                self.assertEqual(preview.call_args.args[0][0]["source_voltage"], 0.2)
                module.run_test(preview_only=True, show=False)
                self.assertEqual(preview.call_args.args[0][0]["source_voltage"],
                                 module.PARAMS["source_voltage"])
        self.assertEqual([module.PARAMS for module in modules], defaults)

    def test_source_has_independent_bias_compliance_and_range(self):
        fake = FakeKxci(source_offset=0.02)
        data = self.acquire(fake, **self.settings(source_voltage=0.2, source_compliance=2e-3, source_current_range=1e-6))
        self.assertIn("VC3, 0.2, 0.002", fake.commands)
        self.assertIn("RG 3, 1e-06", fake.commands)
        self.assertIn("VL1,1,1e-06,0.1,0.2,0.3", fake.commands)
        np.testing.assert_allclose(data["VGS"], [-0.12, -0.02, 0.08])
        np.testing.assert_allclose(data["VDS"], [0.08] * 3)
        self.assertEqual(data["IS"].tolist(), [-2e-6] * 3)

    def test_invalid_settings_rejected_before_commands(self):
        for update in (
            {"source_channel": 1}, {"source_channel": 5}, {"gate_channel": True},
            {"values": [0, float("nan")]}, {"values": [0, 211]},
            {"values": [0, 0]}, {"values": [0, 1] * 2049},
            {"bias_voltage": float("inf")}, {"gate_compliance": 0},
            {"drain_current_range": float("nan")}, {"integration": "IT2;ME1"},
            {"hold_time": 656}, {"sweep_delay": -1}, {"timeout_s": float("nan")},
            {"kxci_plot": "yes"}, {"source_compliance": 0}, {"source_voltage": float("nan")},
            {"source_current_range": -1}, {"source_current_range": float("inf")}, {"kxci_ig_limits": (1, -1)},
            {"smu_connections": {1: "direct", 2: "direct"}},
        ):
            with self.subTest(update=update):
                fake = FakeKxci()
                settings = self.settings()
                settings.update(update)
                with self.assertRaises((ValueError, TypeError)):
                    self.acquire(fake, **settings)
                self.assertEqual(fake.commands, [])

    def test_reverse_path_includes_turnaround_once(self):
        self.assertEqual(build_segmented_voltage_path([-1, 1, -1], 1), [-1, 0, 1, 0, -1])
        for step in (0, -1, float("nan"), 1e-300):
            with self.assertRaises(ValueError):
                build_segmented_voltage_path([0, 1], step)

    def test_execution_failure_aborts_and_does_not_restore_rpm(self):
        fake = FakeKxci(error_after_execute=True)
        with self.assertRaisesRegex(RuntimeError, "-992"):
            self.acquire(fake, **self.settings())
        self.assertIn("ME4", fake.commands)
        self.assertNotIn("RP PMU1-1, 0", fake.commands)
        self.assertEqual(fake.commands[-5:], ["DE", "CH1", "CH2", "CH3", "CH4"])

    def test_short_or_empty_readout_cannot_look_like_completed_curve(self):
        fake = FakeKxci(empty=True)
        with self.assertRaisesRegex(ValueError, "empty"):
            self.acquire(fake, **self.settings())
        self.assertNotIn("RP PMU1-1, 0", fake.commands)


class FetEntryTests(unittest.TestCase):
    def entry(self, name):
        module = importlib.import_module("measurements.smu.3terminal." + name)
        module.MODE = name
        module.TURNING_POINTS = [0, 1] if name == "output" else [-1, 1, -1]
        module.FIXED_BIASES = [0, 0.5, 1] if name == "output" else [0.1]
        return module

    @contextmanager
    def fake_session(self, fake):
        yield type("Session", (), {"query": staticmethod(fake)})()

    def test_preview_is_offline_and_creates_no_files(self):
        import matplotlib.pyplot as plt
        for name in ("transfer", "output"):
            module = self.entry(name)
            with tempfile.TemporaryDirectory() as directory, mock.patch.object(module, "SMUSession") as session:
                result = module.run_test(preview_only=True, save_dir=directory, show=False)
                self.assertIsNone(result["output_path"])
                session.assert_not_called()
                self.assertEqual(list(Path(directory).iterdir()), [])
                plt.close(result["preview"])

    def test_output_saves_all_curves_with_compliance_and_separate_plan_rows(self):
        module = self.entry("output")
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(module, "TURNING_POINTS", [0, 0.1]), \
             mock.patch.object(module, "STEP", 0.1), \
             mock.patch.object(module, "FIXED_BIASES", [0.0, 0.5]), \
             mock.patch.object(module, "SMUSession", side_effect=lambda *a: self.fake_session(FakeKxci(compliance=True, source_compliance=True))):
            with self.assertWarnsRegex(RuntimeWarning, "compliance"):
                result = module.run_test(preview_only=False, save_dir=directory, show=False)
            self.assertEqual(result["data"]["CurveIndex"].tolist(), [1, 1, 2, 2])
            self.assertEqual(result["curves"]["CompliancePoints"].tolist(), [1, 1])
            self.assertTrue(result["plot_path"].is_file())
            with pd.ExcelFile(result["output_path"]) as book:
                self.assertEqual(book.sheet_names, ["Raw", "Curves", "SweepPlan", "Parameters"])
                plan = pd.read_excel(book, "SweepPlan")
                self.assertEqual(plan["CommandedVGS_V"].tolist(), [0, 0, 0.5, 0.5])
                raw = pd.read_excel(book, "Raw")
                self.assertEqual(raw["ID_Status"].tolist(), ["C", "N", "C", "N"])
                self.assertEqual(raw["IS_Status"].tolist(), ["C", "N", "C", "N"])
                self.assertEqual(raw["IS"].tolist(), [-2e-6] * 4)
                self.assertEqual(raw["VS"].tolist(), [0] * 4)
                params = pd.read_excel(book, "Parameters")
                self.assertIn("curve_1.source_compliance", params["name"].tolist())
                self.assertIn("curve_1.source_current_range", params["name"].tolist())

    def test_source_only_compliance_is_counted(self):
        module = self.entry("transfer")
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(module, "TURNING_POINTS", [0, 0.1]), \
             mock.patch.object(module, "STEP", 0.1), \
             mock.patch.object(module, "SMUSession", side_effect=lambda *a: self.fake_session(FakeKxci(source_compliance=True))), \
             mock.patch.object(module, "save_fet_plot"):
            with self.assertWarnsRegex(RuntimeWarning, "compliance"):
                result = module.run_test(preview_only=False, save_dir=directory, show=False)
            self.assertEqual(result["curves"]["CompliancePoints"].tolist(), [1])
            self.assertEqual(result["data"]["ID_Status"].tolist(), ["N", "N"])
            self.assertEqual(result["data"]["IS_Status"].tolist(), ["C", "N"])

    def test_transfer_keeps_forward_reverse_order(self):
        module = self.entry("transfer")
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(module, "TURNING_POINTS", [-1, 1, -1]), \
             mock.patch.object(module, "STEP", 1), \
             mock.patch.object(module, "SMUSession", side_effect=lambda *a: self.fake_session(FakeKxci())):
            result = module.run_test(preview_only=False, save_dir=directory, show=False)
            self.assertEqual(result["data"]["VG"].tolist(), [-1, 0, 1, 0, -1])
            self.assertEqual(result["data"]["VD"].tolist(), [0.1] * 5)

    def test_second_curve_interruption_preserves_first_and_stops_third(self):
        module = self.entry("output")
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(module, "TURNING_POINTS", [0, 0.1]), \
             mock.patch.object(module, "STEP", 0.1), \
             mock.patch.object(module, "SMUSession", side_effect=[self.fake_session(FakeKxci()), KeyboardInterrupt(), AssertionError("third curve started")]) as session:
            with self.assertRaises(KeyboardInterrupt):
                module.run_test(preview_only=False, save_dir=directory, show=False)
            self.assertEqual(session.call_count, 2)
            workbook = next(Path(directory).glob("*.xlsx"))
            self.assertEqual(len(pd.read_excel(workbook, "Raw")), 2)
            curves = pd.read_excel(workbook, "Curves")
            self.assertEqual(curves["Status"].tolist(), ["complete", "interrupted"])

    def test_all_biases_validated_before_connecting_or_saving(self):
        module = self.entry("output")
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(module, "FIXED_BIASES", [0, float("nan")]), \
             mock.patch.object(module, "SMUSession") as session:
            with self.assertRaises(ValueError):
                module.run_test(preview_only=False, save_dir=directory)
            session.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_invalid_mode_is_rejected_before_connecting(self):
        module = self.entry("output")
        with mock.patch.object(module, "MODE", "typo"), \
             mock.patch.object(module, "SMUSession") as session:
            with self.assertRaisesRegex(ValueError, "MODE"):
                module.run_test(preview_only=False, show=False)
            session.assert_not_called()

    def test_failed_checkpoint_replacement_preserves_old_workbook(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.xlsx"
            fet.save_fet_checkpoint(path, [], [], {})
            original = path.read_bytes()
            with mock.patch("os.replace", side_effect=PermissionError("Excel open")):
                with self.assertRaises(PermissionError):
                    fet.save_fet_checkpoint(path, [], [{"Status": "complete"}], {})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_long_scan_configuration_is_not_truncated_to_one_excel_cell(self):
        values = np.linspace(-1, 1, 4096).tolist()
        config = fet.validate_fet_sweep(values=values, sweep_terminal="gate", bias_voltage=0.1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.xlsx"
            fet.save_fet_checkpoint(path, [], [], {"curve_configs": [config]})
            plan = pd.read_excel(path, "SweepPlan")
            self.assertEqual(len(plan), 4096)
            self.assertAlmostEqual(plan["CommandedVGS_V"].iloc[-1], 1)


if __name__ == "__main__":
    unittest.main()
