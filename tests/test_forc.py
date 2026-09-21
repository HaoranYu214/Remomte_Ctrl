# Copyright (c) 2026 ssme / Haoran Yu.
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from measurements.pmu.programmed import FORC as forc


class ForcSequenceTests(unittest.TestCase):
    def test_each_reversal_curve_has_two_equal_measured_ramps(self):
        reversal_voltages = (4.0, 0.0, -5.0)
        configs = forc.make_forc_seq_configs(
            reversal_voltages=reversal_voltages,
        )

        self.assertEqual(set(configs), {forc.CH1, forc.CH2})
        self.assertEqual(len(configs[forc.CH1]), len(reversal_voltages))
        for curve_index, reversal_voltage in enumerate(reversal_voltages):
            ch1_config = configs[forc.CH1][curve_index]
            ch2_config = configs[forc.CH2][curve_index]
            self.assertEqual(ch1_config[0], curve_index + 1)
            self.assertEqual(ch1_config[4], [0, 0, 2, 2, 0])
            self.assertAlmostEqual(ch1_config[3][2], ch1_config[3][3])
            self.assertAlmostEqual(
                ch1_config[3][2],
                forc._branch_time(forc.PARAMS, reversal_voltage),
            )
            constant_segments = [
                index
                for index, (start, stop) in enumerate(
                    zip(ch1_config[1], ch1_config[2])
                )
                if start == stop
            ]
            self.assertEqual(constant_segments, [1])
            self.assertEqual(ch1_config[3], ch2_config[3])
            self.assertTrue(all(value == 0.0 for value in ch2_config[1]))
            self.assertTrue(all(value == 0.0 for value in ch2_config[2]))

    def test_invalid_reversal_levels_are_rejected_before_hardware(self):
        with self.assertRaisesRegex(ValueError, "Vr < Vmax"):
            forc.make_forc_seq_configs(reversal_voltages=(forc.PARAMS["Vmax"],))
        with self.assertRaisesRegex(ValueError, "duplicates"):
            forc.make_forc_seq_configs(reversal_voltages=(0.0, 0.0))

    def test_preview_saves_without_opening_a_pmu_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "forc_preview.png"
            forc.preview_forc_waveforms(
                output,
                reversal_voltages=(4.0, 0.0, -5.0),
            )
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)


class ForcAnalysisTests(unittest.TestCase):
    def test_curve_is_split_and_integrated_from_positive_saturation(self):
        voltage = np.concatenate((np.linspace(5.0, 0.0, 5), np.linspace(0.0, 5.0, 5)))
        timestamp = np.linspace(0.0, 5e-4, len(voltage))
        df_ch1 = pd.DataFrame(
            {
                "Voltage 1": voltage,
                "Current 1": np.full(len(voltage), 1e-6),
                "Timestamp 1": timestamp,
            }
        )
        df_ch2 = pd.DataFrame(
            {
                "Voltage 2": np.zeros(len(voltage)),
                "Current 2": np.full(len(voltage), -2e-6),
                "Timestamp 2": timestamp,
            }
        )

        curve = forc.analyze_forc_curve(
            df_ch1,
            df_ch2,
            reversal_voltage=0.0,
            curve_index=7,
        )

        self.assertEqual(list(curve["Branch"][:5]), ["Descending"] * 5)
        self.assertEqual(list(curve["Branch"][5:]), ["Return"] * 5)
        self.assertTrue((curve["CurveIndex"] == 7).all())
        self.assertAlmostEqual(curve["LocalTime"].iloc[0], 0.0)
        self.assertAlmostEqual(curve["LocalTime"].iloc[-1], 5e-4)
        self.assertAlmostEqual(curve["ChargeI2"].iloc[0], 0.0)
        self.assertGreater(curve["PolarizationRelativeI2"].iloc[-1], 0.0)


if __name__ == "__main__":
    unittest.main()
