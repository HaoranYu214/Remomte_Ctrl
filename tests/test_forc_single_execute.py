# Copyright (c) 2026 ssme / Haoran Yu.
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from measurements.pmu.programmed import FORC_1excute as forc_single


def synthetic_combined_data(reversal_voltages, sample_rate=1e6):
    layout = forc_single.build_combined_forc_layout(
        reversal_voltages=reversal_voltages,
    )
    voltages = []
    timestamp = []
    elapsed = 0.0
    for item in layout["measured_segments"]:
        point_count = int(round(item["duration"] * sample_rate))
        reversal = item["reversal_voltage"]
        if item["branch"] == "Descending":
            branch_voltage = np.linspace(forc_single.PARAMS["Vmax"], reversal, point_count)
        else:
            branch_voltage = np.linspace(reversal, forc_single.PARAMS["Vmax"], point_count)
        voltages.extend(branch_voltage)
        timestamp.extend(elapsed + np.arange(point_count) / sample_rate)
        elapsed += item["duration"]

    voltages = np.asarray(voltages)
    timestamp = np.asarray(timestamp)
    df_ch1 = pd.DataFrame(
        {
            "Voltage 1": voltages,
            "Current 1": np.full(len(voltages), 1e-6),
            "Timestamp 1": timestamp,
        }
    )
    df_ch2 = pd.DataFrame(
        {
            "Voltage 2": np.zeros(len(voltages)),
            "Current 2": np.full(len(voltages), -2e-6),
            "Timestamp 2": timestamp,
        }
    )
    return layout, df_ch1, df_ch2


class CombinedForcConfigurationTests(unittest.TestCase):
    def test_configured_family_is_one_continuous_sequence(self):
        layout = forc_single.build_combined_forc_layout()
        curve_count = len(forc_single.REVERSAL_VOLTAGES)
        offset_transition_count = 0 if np.isclose(
            forc_single.PARAMS["offset"], 0.0
        ) else 2
        expected_segment_count = 3 * curve_count + 2 + offset_transition_count
        expected_measurement_time = 2 * sum(
            forc_single._branch_time(forc_single.PARAMS, reversal)
            for reversal in forc_single.REVERSAL_VOLTAGES
        )
        expected_automatic_rate = min(
            forc_single.KXCI_DEFAULT_SAMPLE_RATE,
            forc_single.KXCI_MAX_DATA_POINTS / expected_measurement_time,
        )

        self.assertEqual(layout["segment_count"], expected_segment_count)
        self.assertEqual(len(layout["measured_segments"]), 2 * curve_count)
        self.assertAlmostEqual(
            layout["measurement_time"], expected_measurement_time
        )
        self.assertAlmostEqual(
            layout["automatic_sample_rate"], expected_automatic_rate
        )
        self.assertLessEqual(
            layout["estimated_samples"], forc_single.KXCI_MAX_DATA_POINTS
        )
        self.assertNotIn("SAMPLE_RATE", forc_single.SEGARB_OPTIONS)

        configs = layout["seq_configs"]
        self.assertEqual(len(configs[forc_single.CH1]), 1)
        self.assertEqual(len(configs[forc_single.CH2]), 1)
        ch1_config = configs[forc_single.CH1][0]
        starts, stops = ch1_config[1], ch1_config[2]
        self.assertEqual(starts[0], 0.0)
        self.assertEqual(stops[-1], 0.0)
        self.assertTrue(
            all(abs(stop - start) < 1e-12 for stop, start in zip(stops[:-1], starts[1:]))
        )

    def test_automatic_rate_can_resolve_the_shortest_measured_segment(self):
        layout = forc_single.build_combined_forc_layout()
        self.assertLessEqual(
            layout["minimum_usable_sample_rate"],
            layout["automatic_sample_rate"],
        )


class CombinedForcDataTests(unittest.TestCase):
    def test_one_buffer_is_split_back_into_exact_reversal_pairs(self):
        reversal_voltages = (4.0, 0.0, -4.0)
        layout, df_ch1, df_ch2 = synthetic_combined_data(reversal_voltages)
        raw_ch1, raw_ch2, curves = forc_single.split_combined_forc_data(
            df_ch1,
            df_ch2,
            layout["measured_segments"],
        )
        self.assertEqual(len(raw_ch1), 3)
        self.assertEqual(len(raw_ch2), 3)
        self.assertEqual(len(curves), 3)
        for reversal, curve in zip(reversal_voltages, curves):
            self.assertEqual(curve["ReversalVoltage"].iloc[0], reversal)
            self.assertEqual(curve["Branch"].iloc[0], "Descending")
            self.assertEqual(curve["Branch"].iloc[-1], "Return")
            self.assertAlmostEqual(curve["Voltage"].iloc[0], forc_single.PARAMS["Vmax"])
            self.assertAlmostEqual(curve["Voltage"].iloc[-1], forc_single.PARAMS["Vmax"])

    def test_run_calls_segment_arb_execute_only_once(self):
        reversal_voltages = (4.0, 0.0, -4.0)
        _layout, df_ch1, df_ch2 = synthetic_combined_data(reversal_voltages)
        options = dict(forc_single.SEGARB_OPTIONS)
        commands = []
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(forc_single, "execute_segARB_test") as execute:
                with mock.patch.object(
                    forc_single,
                    "read_both_channels",
                    return_value=(df_ch1, df_ch2),
                ):
                    with mock.patch.object(
                        forc_single.separate_forc,
                        "save_forc_workbook",
                    ):
                        with mock.patch.object(
                            forc_single.separate_forc,
                            "save_forc_plots",
                            return_value=(Path("p.png"), Path("i.png")),
                        ):
                            result = forc_single.run_forc_test(
                                commands.append,
                                reversal_voltages=reversal_voltages,
                                save_dir=temp_dir,
                                segarb_options=options,
                            )

        execute.assert_called_once()
        self.assertEqual(result["completed_curves"], 3)
        self.assertEqual(commands[-2:], [
            ":PMU:OUTPUT:STATE 1, 0",
            ":PMU:OUTPUT:STATE 2, 0",
        ])


if __name__ == "__main__":
    unittest.main()
