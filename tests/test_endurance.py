from pathlib import Path
import sys
import unittest
from unittest import mock
import tempfile
from copy import deepcopy
from contextlib import redirect_stdout
import io

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from measurements.pmu.fe_cap import endurance
from keithley4200.tools.dry_run import DryRunSession
from keithley4200.pmu.pmu_tests import (
    MAX_SEGMENTS_PER_SEQUENCE,
    _validate_segment_arb_storage,
    configure_segARB_sequence,
)


class SegmentArbMeasurementWindowTests(unittest.TestCase):
    def test_multiple_sequences_share_limit_per_channel_not_between_channels(self):
        segment_count = MAX_SEGMENTS_PER_SEQUENCE // 2
        sequence = (1, [0.0] * segment_count, [0.0] * segment_count,
                    [1e-5] * segment_count)
        second_sequence = (2, sequence[1], sequence[2], sequence[3])

        # Both channels may independently use all 2048 stored segments.
        _validate_segment_arb_storage(
            {1: [sequence, second_sequence], 2: [sequence, second_sequence]}
        )

        extra = (3, [0.0], [0.0], [1e-5])
        with self.assertRaisesRegex(ValueError, "per-channel 4225-PMU limit"):
            _validate_segment_arb_storage(
                {1: [sequence, second_sequence, extra], 2: [sequence]}
            )

    def test_sequence_above_hardware_segment_limit_is_rejected(self):
        commands = []
        values = [0.0] * (MAX_SEGMENTS_PER_SEQUENCE + 1)
        with self.assertRaisesRegex(ValueError, "4225-PMU limit"):
            configure_segARB_sequence(
                commands.append,
                1,
                1,
                values,
                values,
                [1e-5] * len(values),
                [0] * len(values),
            )
        self.assertEqual(commands, [])

    def test_unmeasured_segments_are_sent_with_zero_windows(self):
        commands = []
        configure_segARB_sequence(
            commands.append,
            1,
            1,
            [0.0, 0.0],
            [0.0, 1.0],
            [1e-5, 2e-5],
            [0, 2],
        )

        for prefix, expected in ((":PMU:SARB:SEQ:MEAS:START", [0.0, 0.0]),
                                 (":PMU:SARB:SEQ:MEAS:STOP", [0.0, 2e-5])):
            command = next(c for c in commands if c.startswith(prefix + " "))
            self.assertEqual([float(v) for v in command.split(",")[2:]], expected)

    def test_invalid_measured_window_is_rejected_before_commands_are_sent(self):
        commands = []
        with self.assertRaisesRegex(ValueError, "outside its"):
            configure_segARB_sequence(
                commands.append,
                1,
                1,
                [0.0],
                [1.0],
                [1e-5],
                [2],
                [0.0],
                [1.0],
            )
        self.assertEqual(commands, [])


class EnduranceConfigurationTests(unittest.TestCase):
    def test_cycle_segments_are_explicitly_unmeasured(self):
        for configs in endurance.make_cycle_seq_configs().values():
            config = configs[0]
            self.assertEqual(config[4], [0, 0, 0, 0])
            self.assertEqual(config[5], [0.0, 0.0, 0.0, 0.0])
            self.assertEqual(config[6], [0.0, 0.0, 0.0, 0.0])

    def test_cycle_targets_are_converted_to_increments(self):
        self.assertEqual(
            endurance.build_cycle_schedule([1, 10, 100, 1000]),
            [(1, 1), (10, 9), (100, 90), (1000, 900)],
        )
        full_schedule = endurance.build_cycle_schedule(endurance.cycle_counts)
        self.assertEqual(sum(increment for _target, increment in full_schedule), int(endurance.cycle_counts[-1]))

    def test_cycle_targets_must_increase(self):
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            endurance.build_cycle_schedule([1, 10, 10])

    def test_pv2_measures_only_the_two_readback_loops(self):
        config = endurance.make_pv2_seq_configs()[endurance.CH1][0]
        self.assertEqual(config[4], [0, 0, 0, 0, 0, 2, 2, 2, 2, 2])
        self.assertEqual(config[3][4], endurance.params_pv2["delay_time"])

    def test_cycle_block_emits_valid_zero_windows_and_increment(self):
        commands = []

        def fake_query(command):
            commands.append(command)
            return "0"

        endurance.run_cycle_block(fake_query, 9)

        self.assertIn(":PMU:SARB:WFM:SEQ:LIST 1, 1, 9", commands)
        measurement_stop_commands = [
            command for command in commands if ":PMU:SARB:SEQ:MEAS:STOP" in command
        ]
        self.assertEqual(len(measurement_stop_commands), 2)
        for command in measurement_stop_commands:
            self.assertEqual([float(v) for v in command.split(",")[2:]], [0.0] * 4)

    def test_pv2_analysis_splits_and_integrates_each_loop(self):
        loop_voltage = np.array([0.0, 1.0, 0.0, -1.0, 0.0])
        voltage = np.concatenate([loop_voltage, loop_voltage])
        point_count = len(voltage)
        time = np.arange(point_count, dtype=float) * 1e-6
        current = np.linspace(1e-6, 2e-6, point_count)
        status = np.zeros(point_count, dtype=int)
        ch1 = pd.DataFrame(
            {
                "Voltage 1": voltage,
                "Current 1": current,
                "Timestamp 1": time,
                "Status 1": status,
            }
        )
        ch2 = pd.DataFrame(
            {
                "Voltage 2": np.zeros(point_count),
                "Current 2": -current,
                "Timestamp 2": time,
                "Status 2": status,
            }
        )

        result = endurance.PV2.analyze_pv2(ch1, ch2, parameters=endurance.params_pv2)

        self.assertEqual(len(result["i1_delay"]), 5)
        self.assertEqual(len(result["i1_no_delay"]), 5)
        self.assertEqual(len(result["i2_delay"]), 5)
        self.assertEqual(len(result["i2_no_delay"]), 5)
        self.assertTrue(np.isfinite(result["i2_loops"].to_numpy()).all())


class EnduranceReadbackTests(unittest.TestCase):
    def test_readback_waveforms_match_current_standalone_entries(self):
        for defaults, builder, standalone in (
            (endurance.params_pv2, endurance.make_pv2_seq_configs, endurance.PV2.make_pv2_seq_configs),
            (endurance.params_pund, endurance.make_pund_seq_configs, endurance.PUND_tri.make_pund_seq_configs),
        ):
            parameters = {**defaults, "Vp": 3.2, "offset": 0.1, "rise_time": 30e-6, "delay_time": 2e-3}
            self.assertEqual(builder(parameters=parameters, channels=(2, 1)),
                             standalone(parameters=parameters, channels=(2, 1)))
        config = endurance.make_pund_seq_configs()[endurance.CH1][0]
        self.assertEqual(sum(mode == 2 for mode in config[4]), 10)
        self.assertEqual(len(config[3]), 17)

    def test_cycle_delay_adds_two_unmeasured_holds(self):
        parameters = {**endurance.params_cycle, "delay_time": 20e-6}
        cfg = endurance.make_cycle_seq_configs(parameters=parameters)[endurance.CH1][0]
        self.assertEqual(cfg[3], [parameters["rise_time"], parameters["rise_time"], 20e-6] * 2)
        self.assertEqual(cfg[4], [0] * 6)
        self.assertEqual(cfg[1][2], parameters["offset"])
        self.assertEqual(cfg[2][5], parameters["offset"])

    def test_invalid_readback_rejected_before_fatigue_or_hardware(self):
        with mock.patch.object(endurance, "PMUSession") as session:
            for overrides in ({"delay_time": 2.0}, {"rise_time": float("nan")}, {"Vp": 11}, {"area_cm2": 0}):
                with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                    endurance.run_test(pund_params_override=overrides, preview_only=False)
            session.assert_not_called()

    def test_preview_has_no_hardware_or_output_directory(self):
        import matplotlib.pyplot as plt
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(endurance, "PMUSession") as session, mock.patch.object(plt, "show"):
            path = Path(tmp) / "unused"
            result = endurance.run_test(save_dir=path, preview_only=True)
            self.assertEqual(len(result["preview"]), 3)
            self.assertFalse(path.exists())
            session.assert_not_called()
        plt.close("all")

    def test_real_save_path_uses_effective_parameters_and_fixed_acquisitions(self):
        before = deepcopy((endurance.params_cycle, endurance.params_pv2, endurance.params_pund))
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()), mock.patch.object(endurance, "PMUSession", DryRunSession), mock.patch.object(endurance, "execute_segARB_test", wraps=endurance.execute_segARB_test) as execute:
            result = endurance.run_test(pv2_params_override={"delay_time": 0.002, "Vp": 3.25},
                                        pund_params_override={"delay_time": 0.003, "offset_ramp_time": 40e-6},
                                        cycle_targets=[1, 10], channels=(2, 1), save_dir=tmp, preview_only=False)
            self.assertEqual(execute.call_count, 6)
            self.assertEqual(result["summary"]["stage"].tolist(), ["cycle", "PV2", "PUND_tri"] * 2)
            self.assertEqual(result["summary"]["status"].tolist(), ["ok"] * 6)
            pv_row = result["summary"].iloc[1]
            with pd.ExcelFile(result["readback_paths"][0]) as book:
                self.assertTrue({"Channel_2", "Channel_1", "Parameters", "Waveform", "Total", "I1_Loops", "I2_Loops"}.issubset(book.sheet_names))
                table = pd.read_excel(book, sheet_name="Parameters")
                self.assertEqual(table[(table.section == "PV2") & (table.name == "delay_time")].value.iloc[0], "0.002")
            self.assertIn("03.25V", Path(result["readback_paths"][0]).name)
            self.assertIn("_cycles01_r001.xlsx", Path(result["readback_paths"][0]).name)
            self.assertIn("_cycles10_r001.xlsx", Path(result["readback_paths"][2]).name)
            with pd.ExcelFile(result["readback_paths"][1]) as book:
                diff = pd.read_excel(book, sheet_name="PUND_Diff")
                self.assertEqual(set(diff.Segment), {"P-U", "N-D"})
            self.assertTrue(result["output_path"].exists())
            self.assertFalse(list(Path(tmp).glob("*.csv")))
            self.assertFalse(list(Path(tmp).glob("*_i1.png")))
            self.assertTrue(list(Path(tmp).glob("endurance_summary*_loops.png")))
            summary = pd.read_excel(result["output_path"])
            self.assertNotIn("output_path", summary.columns)
            readbacks = summary[summary.stage != "cycle"]
            self.assertTrue(np.isfinite(readbacks[["Pr_positive_uC_cm2", "Pr_negative_uC_cm2"]].to_numpy()).all())
            pv_rows = summary[summary.stage == "PV2"]
            self.assertTrue(np.isfinite(pv_rows[["Pr_positive_no_delay_uC_cm2", "Pr_negative_no_delay_uC_cm2"]].to_numpy()).all())
        self.assertEqual((endurance.params_cycle, endurance.params_pv2, endurance.params_pund), before)

    def test_analysis_failure_preserves_raw_and_stops_later_stages(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()), mock.patch.object(endurance, "PMUSession", DryRunSession), mock.patch.object(endurance.PV2, "analyze_pv2", side_effect=ValueError("analysis failed")), mock.patch.object(endurance, "execute_segARB_test", wraps=endurance.execute_segARB_test) as execute:
            with self.assertRaisesRegex(ValueError, "analysis failed"):
                endurance.run_test(cycle_targets=[1, 3], save_dir=tmp, preview_only=False)
            self.assertEqual(execute.call_count, 2)
            raw = next(Path(tmp).glob("PV2_*.xlsx"))
            with pd.ExcelFile(raw) as book:
                self.assertIn("Channel_1", book.sheet_names)
                self.assertIn("Parameters", book.sheet_names)
            summary = pd.read_excel(next(Path(tmp).glob("endurance_summary*.xlsx")))
            self.assertEqual(summary.status.tolist(), ["ok", "failed"])


if __name__ == "__main__":
    unittest.main()
