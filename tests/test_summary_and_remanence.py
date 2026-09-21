"""Single summary checkpoints and signed zero-voltage remanence."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import subprocess
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from keithley4200.output import save_summary_workbook
from keithley4200.pmu.data_processing import remanent_polarization


class RemanenceTests(unittest.TestCase):
    def test_interpolates_return_branches_not_initial_zero_or_peak(self):
        voltage = [0, 2, 1, -1, -2, -1, 1, 0]
        polarization = [99, 10, 8, 4, -10, -8, -4, 0]
        self.assertEqual(remanent_polarization(voltage, polarization), (6.0, -6.0))

    def test_exact_zero_on_return_and_missing_polarity(self):
        self.assertEqual(remanent_polarization([0, 2, 0, -2, 0], [99, 10, 4, -10, -3]), (4.0, -3.0))
        positive, negative = remanent_polarization([2, 1, 0], [10, 6, 2])
        self.assertEqual(positive, 2)
        self.assertTrue(np.isnan(negative))

    def test_programmed_zero_endpoint_allows_only_one_sample_extrapolation(self):
        positive, _ = remanent_polarization([2, 1, 0.25], [10, 6, 3], zero_endpoint=True)
        self.assertEqual(positive, 2)
        _, negative = remanent_polarization([-2, -1, -0.25], [-10, -6, -3], zero_endpoint=True)
        self.assertEqual(negative, -2)
        self.assertTrue(np.isnan(remanent_polarization([2, 1.5, 1], [10, 6, 3], zero_endpoint=True)).all())

    def test_no_extrapolation_or_interpolation_across_missing_samples(self):
        self.assertTrue(np.isnan(remanent_polarization([2, 1, 0.5], [10, 6, 3])).all())
        positive, _ = remanent_polarization([2, 1, -1, -2], [10, np.nan, 4, -10])
        self.assertTrue(np.isnan(positive))
        self.assertTrue(np.isnan(remanent_polarization([], [])).all())
        with self.assertRaises(ValueError):
            remanent_polarization([1, 0], [1])


class SummaryCheckpointTests(unittest.TestCase):
    def test_updates_one_workbook_with_no_companion_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.xlsx"
            save_summary_workbook([{"cycle": 1, "Pr": 2.5}], path)
            save_summary_workbook([{"cycle": 1, "Pr": 2.5}, {"cycle": 10, "Pr": -1.5}], path)
            self.assertEqual(pd.read_excel(path).cycle.tolist(), [1, 10])
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["summary.xlsx"])

    def test_failed_update_retains_previous_workbook_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.xlsx"
            save_summary_workbook([{"cycle": 1}], path)
            original = path.read_bytes()
            with mock.patch.object(pd.DataFrame, "to_excel", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    save_summary_workbook([{"cycle": 10}], path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["summary.xlsx"])

    def test_dry_run_no_save_does_not_create_summary(self):
        script = "import sys; sys.path.insert(0, sys.argv[1]); from keithley4200.tools.dry_run import install_dry_run_hooks; install_dry_run_hooks(no_save=True); from keithley4200.output import save_summary_workbook; save_summary_workbook([{'cycle': 1}], sys.argv[2])"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.xlsx"
            subprocess.run([sys.executable, "-c", script, str(ROOT / "src"), str(path)],
                           check=True, capture_output=True, text=True, timeout=20)
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
