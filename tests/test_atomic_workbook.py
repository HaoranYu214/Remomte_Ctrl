# Copyright (c) 2026 ssme / Haoran Yu.
"""Atomic replacement retains the previous workbook when an update fails."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import pandas as pd
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from keithley4200.output import save_atomic_workbook


class AtomicWorkbookTests(unittest.TestCase):
    def test_multisheet_update_and_replace_failure_keep_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.xlsx"
            save_atomic_workbook({"Raw": pd.DataFrame({"I": [1]}),
                                  "Curves": pd.DataFrame({"Status": ["ok"]})}, path)
            before = path.read_bytes()
            self.assertEqual(set(pd.read_excel(path, sheet_name=None)), {"Raw", "Curves"})
            with mock.patch("os.replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    save_atomic_workbook({"Raw": pd.DataFrame({"I": [2]})}, path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            save_atomic_workbook({"Raw": pd.DataFrame({"I": [3]})}, path)
            self.assertEqual(pd.read_excel(path)["I"].tolist(), [3])

    def test_partial_write_failure_preserves_previous_file(self):
        class BrokenFrame:
            def to_excel(self, *args, **kwargs):
                raise RuntimeError("write failed")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.xlsx"
            save_atomic_workbook({"Raw": pd.DataFrame({"I": [1]})}, path)
            before = path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                save_atomic_workbook({"Raw": pd.DataFrame({"I": [2]}), "Other": BrokenFrame()}, path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])
