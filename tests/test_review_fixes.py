"""Regression checks for entry isolation, FET mapping, and synthetic acquisition."""
from contextlib import ExitStack, redirect_stdout
import importlib
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from keithley4200.tools.dry_run import DryRunState, DryRunSession
from keithley4200.pmu.data_processing import read_channel_data, read_both_channels
from keithley4200.pmu.pmu_tests import (
    MAX_SEGMENTS_PER_SEQUENCE, configure_segARB_sequence, execute_segARB_test,
)


class ReviewFixTests(unittest.TestCase):
    def test_importing_pulse_entries_has_no_acquisition_or_save_side_effects(self):
        # Initialize Matplotlib before blocking measurement output directories.
        import matplotlib.pyplot

        for name in ("pulse_sweep", "pulse_train"):
            with self.subTest(name=name), mock.patch(
                "keithley4200.pmu.session.PMUSession", side_effect=AssertionError("instrument opened")
            ), mock.patch.object(Path, "mkdir", side_effect=AssertionError("directory created")), mock.patch(
                "keithley4200.output.reserve_output_stem", side_effect=AssertionError("name reserved")
            ):
                # run_path also checks a fresh execution if another test imported it.
                import runpy
                namespace = runpy.run_path(str(ROOT / "measurements/pmu/pulse" / (name + ".py")))
                self.assertTrue(callable(namespace["main"]))

    def test_fet_main_uses_selected_channels(self):
        for variant in ("program_read", "bipolar_program_read"):
            module = importlib.import_module("measurements.pmu.fet." + variant)
            with self.subTest(variant=variant), ExitStack() as stack:
                stack.enter_context(redirect_stdout(io.StringIO()))
                stack.enter_context(mock.patch.multiple(module, GATE_CH=2, DRAIN_CH=1,
                    PREVIEW_ONLY=False, USE_SOURCE_SMU=False, SAVE_WAVEFORM_PREVIEW=False,
                    PMUSession=DryRunSession))
                stack.enter_context(mock.patch.dict(module.params, {"read_delay": 1e-3}))
                stack.enter_context(mock.patch.object(module, "reserve_output_stem", return_value=Path("offline")))
                save = stack.enter_context(mock.patch.object(module, "save_fet_workbook"))
                stack.enter_context(mock.patch.object(module, "save_ids_dual_axis_plot"))
                module.run_test(preview_only=False)
                data = save.call_args.args[1]
                self.assertEqual(data["Ig"].tolist(), data["Current 2"].tolist())
                self.assertEqual(data["Id"].tolist(), data["Current 1"].tolist())
                self.assertEqual(data["MeasuredVg"].tolist(), data["Voltage 2"].tolist())
                self.assertEqual(data["MeasuredVd"].tolist(), data["Voltage 1"].tolist())
                self.assertNotEqual(data["Ig"].tolist(), data["Id"].tolist())
                self.assertEqual(module.params["max_segments_per_sequence"], 2048)
                self.assertEqual(module.MAX_SEGMENTS_PER_SEQUENCE, MAX_SEGMENTS_PER_SEQUENCE)

    def test_segment_limit_accepts_2048_and_rejects_2049_before_commands(self):
        query = mock.Mock()
        configure_segARB_sequence(query, 1, 1, [0]*2048, [1]*2048, [1e-6]*2048)
        self.assertTrue(query.called)
        query.reset_mock()
        with self.assertRaisesRegex(ValueError, "2048"):
            configure_segARB_sequence(query, 1, 1, [0]*2049, [1]*2049, [1e-6]*2049)
        query.assert_not_called()

    def test_synthetic_segments_preserve_windows_skips_loops_and_blocks(self):
        state = DryRunState()
        query = state.query_response
        query(":PMU:INIT 1")
        configure_segARB_sequence(query, 1, 1, [0, 2, 0], [0, 2, 4], [1, 1, 1],
                                 [0, 1, 2], [0, 0.2, 0.25], [0, 0.8, 0.75])
        query(":PMU:SARB:WFM:SEQ:LIST 1, 1, 2")
        query(":PMU:EXECUTE")
        frame = read_channel_data(query, 1, block=7)
        self.assertEqual(len(frame), 66)
        self.assertAlmostEqual(frame["Timestamp 1"].iloc[0], 1.5)
        self.assertAlmostEqual(frame["Timestamp 1"].iloc[33], 4.5)
        self.assertTrue(frame["Timestamp 1"].is_monotonic_increasing)
        self.assertTrue(frame["Voltage 1"].iloc[1:33].between(1, 3).all())
        query(":PMU:INIT 1")
        self.assertEqual(query(":PMU:DATA:COUNT? 1"), "0")

    def test_sarb_add_arrays_and_point_budget(self):
        state = DryRunState()
        query = state.query_response
        query(":PMU:INIT 1")
        configure_segARB_sequence(query, 1, 1, [1]*130, [1]*130, [1e-6]*130)
        self.assertEqual(len(state.sequences[1, 1]["TIME"]), 130)
        query(":PMU:SARB:WFM:SEQ:LIST 1, 1, 1")
        state.MAX_POINTS = 10
        with self.assertRaisesRegex(ValueError, "synthetic points"):
            query(":PMU:EXECUTE")

    def test_pv_and_pund_analysis_accept_command_driven_data(self):
        for name, builder, analyzer in (
            ("PV2", "make_pv2_seq_configs", "analyze_pv2"),
            ("PUND_tri", "make_pund_seq_configs", "analyze_pund_triangle_diff"),
            ("PUND_Squr", "make_pund_seq_configs", "analyze_pund_edge_diff"),
        ):
            module = importlib.import_module("measurements.pmu.fe_cap." + name)
            with self.subTest(name=name), redirect_stdout(io.StringIO()):
                state = DryRunState()
                execute_segARB_test(state.query_response, [module.CH1, module.CH2], getattr(module, builder)())
                first, second = read_both_channels(state.query_response, module.CH1, module.CH2)
                data = getattr(module, analyzer)(first, second)
                self.assertGreater(len(first), 4)
                self.assertFalse(data["df_total"].empty)

    def test_pulse_high_low_data_use_real_reader(self):
        module = importlib.import_module("measurements.pmu.pulse.pulse_train")
        for acquisition in ((True, True), (False, True), (True, False)):
            with self.subTest(acquisition=acquisition), redirect_stdout(io.StringIO()):
                state = DryRunState()
                parameters = {**module.params, "PULSE_COUNT": 3,
                              "ACQUIRE_HIGH": acquisition[0], "ACQUIRE_LOW": acquisition[1]}
                module.run_dual_channel_pulse_train(state.query_response, 1, 2, parameters, mode=1)
                first, second = read_both_channels(state.query_response, 1, 2, pulse_iv=acquisition)
                self.assertEqual(len(first), 3)
                self.assertEqual(len(first.columns), 8 if all(acquisition) else 4)
                if acquisition == (False, True):
                    self.assertIn("Voltage Low 1", first)
                self.assertEqual(len(second), 3)


if __name__ == "__main__":
    unittest.main()
