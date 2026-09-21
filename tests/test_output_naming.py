"""Hardware-free regression checks for output grouping and overwrite protection."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "src"), str(REPO_ROOT)]

from keithley4200.output import (
    prepare_output_dir, reserve_summary_stem, measurement_name, reserve_output_stem, time_tag, voltage_tag,
)


class OutputNamingTests(unittest.TestCase):
    def test_voltage_order_and_sub_microsecond_labels(self):
        values = [3, 3.01, 3.02, 3.12, 3.5, 4, 9.5, 10, 40]
        labels = [voltage_tag(value) for value in values]
        self.assertEqual(labels, sorted(labels))
        self.assertEqual(labels[:3], ["03.00V", "03.01V", "03.02V"])
        self.assertEqual(voltage_tag(-3.5), "-03.50V")
        self.assertEqual(voltage_tag(3.126), "03.13V")
        self.assertEqual(time_tag(1e-7), "0.1us")

    def test_rounded_voltages_reserve_distinct_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = reserve_output_stem(tmp, measurement_name("PV2", 3.001))
            second = reserve_output_stem(tmp, measurement_name("PV2", 3.004))
            self.assertEqual(first.name, "PV2_03.00V_r001")
            self.assertEqual(second.name, "PV2_03.00V_r002")
        self.assertEqual(voltage_tag(-0.001), "00.00V")

    def test_old_companion_files_and_failed_reservations_are_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            name = measurement_name("PV2", 3.5, "tr250us", "td1000us")
            old = directory / f"{name}_r001_i1.png"
            old.write_bytes(b"old image")
            first = reserve_output_stem(directory, name)
            # No workbook is written for first, simulating a failed acquisition.
            second = reserve_output_stem(directory, name)
            self.assertTrue(first.name.endswith("r002"))
            self.assertTrue(second.name.endswith("r003"))
            self.assertEqual(old.read_bytes(), b"old image")
            metadata = json.loads((directory / ".reservations" / f"{first.name.lower()}.json").read_text())
            self.assertIsNotNone(datetime.fromisoformat(metadata["reserved_at"]).tzinfo)

    def test_threads_get_unique_group_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            with ThreadPoolExecutor(max_workers=8) as pool:
                stems = list(pool.map(lambda _: reserve_output_stem(tmp, "PV2_03.00V"), range(32)))
            self.assertEqual(len(set(stems)), 32)
            self.assertEqual({int(stem.name.rsplit("r", 1)[1]) for stem in stems}, set(range(1, 33)))

    def test_separate_processes_and_restart_do_not_overwrite(self):
        script = (
            "import sys; from pathlib import Path; "
            "sys.path.insert(0, sys.argv[1]); "
            "from keithley4200.output import reserve_output_stem; "
            "s=reserve_output_stem(sys.argv[2], 'PV2_03.00V'); "
            "Path(str(s)+'.xlsx').write_bytes(s.name.encode()); print(s.name)"
        )
        with tempfile.TemporaryDirectory() as tmp:
            command = [sys.executable, "-c", script, str(REPO_ROOT / "src"), tmp]
            processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)]
            names = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, stderr)
                names.append(stdout.strip())
            self.assertEqual(len(set(names)), 8)
            for name in names:
                self.assertEqual((Path(tmp) / (name + ".xlsx")).read_text(), name)
            restarted = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
            self.assertEqual(restarted.stdout.strip(), "PV2_03.00V_r009")

    def test_same_second_summaries_are_unique_without_time_directories(self):
        stamp = "2026-09-11T14:30:25.123456+02:00"
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "keithley4200.output.saved_at", return_value=stamp
        ):
            self.assertEqual(prepare_output_dir(tmp), Path(tmp))
            first, first_time = reserve_summary_stem(tmp, "map_summary")
            second, second_time = reserve_summary_stem(tmp, "map_summary")
            self.assertEqual(first.name, "map_summary_20260911_143025_r001")
            self.assertEqual(second.name, "map_summary_20260911_143025_r002")
            self.assertEqual(first_time, second_time)
            self.assertEqual(first.parent, Path(tmp))
            self.assertEqual([p.name for p in Path(tmp).iterdir() if p.is_dir()], [".reservations"])

    def test_invalid_names_do_not_escape_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("../escape", "a/b", "a:b", "", "name."):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    reserve_output_stem(tmp, name)

    def test_pv_pund_names_keep_delay_and_group_workbook_with_images(self):
        for module_name, label in (("PV2", "PV2"), ("PUND_tri", "PUNDtri"), ("PUND_Squr", "PUND")):
            module = importlib.import_module("measurements.pmu.fe_cap." + module_name)
            parameters = {**module.params, "Vp": 3.5, "rise_time": 250e-6, "delay_time": 1e-3}
            with self.subTest(module=module_name), tempfile.TemporaryDirectory() as tmp:
                with mock.patch.object(module, "SAVE_DIR", Path(tmp)), mock.patch.object(module, "params", parameters):
                    stem = module.build_fname_base()
                    self.assertTrue(stem.name.startswith(f"{label}_03.50V_tr250us_td1000us"))
                    workbook = Path(f"{stem}.xlsx")
                    image = Path(f"{stem}_i1.png")
                    workbook.write_bytes(b"original workbook")
                    image.write_bytes(b"original image")
                    second = module.build_fname_base()
                    self.assertTrue(second.name.endswith("r002"))
                    self.assertEqual(workbook.read_bytes(), b"original workbook")
                    # Exercise the real workbook writer, including retained settings.
                    import pandas as pd
                    frame = pd.DataFrame({"value": [1.0]})
                    data = {key: frame for key in ("df_total", "i1_loops", "i2_loops", "pund_diff")}
                    writer = module.save_pv2_workbook if module_name == "PV2" else module.save_pund_workbook
                    writer(Path(f"{second}.xlsx"), frame, frame, data)
                    metadata = pd.read_excel(f"{second}.xlsx", sheet_name="Parameters")
                    values = dict(zip(metadata["name"], metadata["value"]))
                    self.assertAlmostEqual(float(values["delay_time"]), 1e-3)
                    self.assertIn("Irange1", values)
                    self.assertIsNotNone(datetime.fromisoformat(values["saved_at"]).tzinfo)
                    parameters["delay_time"] = 2e-3
                    changed = module.build_fname_base()
                    self.assertIn("td2000us", changed.name)
                    self.assertTrue(changed.name.endswith("r001"))
                    self.assertIn("saved_at", module.build_params_table()["name"].tolist())

    def test_repeated_maps_save_time_summaries_without_extra_directories(self):
        from measurements.workflows import pv2_pund_map as workflow
        import pandas as pd

        def fake_test(module, test_name, base_params, save_dir, vp, frequency, delay, index, total):
            stem = reserve_output_stem(save_dir, measurement_name("PV2", vp))
            Path(f"{stem}.xlsx").write_bytes(b"map data")
            return {"status": "ok"}

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dirs = {"PV2": base / "PV2", "PUND_tri": base / "PUND_tri"}
            with mock.patch.multiple(workflow, SAVE_ROOT=base, SAVE_DIRS=dirs,
                                     RUN_PV2=True, RUN_PUND_TRI=False, VP_VALUES=[3, 3.5],
                                     FREQUENCY_VALUES_HZ=[1000], DELAY_TIME_VALUES_S=[1e-3],
                                     SETTLE_TIME_S=0), mock.patch.object(workflow, "run_one_test", side_effect=fake_test):
                workflow.run_map()
                workflow.run_map()
                self.assertEqual(workflow.SAVE_ROOT, base)
                self.assertEqual(workflow.SAVE_DIRS, dirs)
            summaries = sorted(base.glob("map_summary_*.xlsx"))
            self.assertEqual(len(summaries), 2)
            self.assertEqual(len(list((base / "PV2").glob("*.xlsx"))), 4)
            self.assertEqual({p.name for p in base.iterdir() if p.is_dir()}, {"PV2", ".reservations"})
            for summary in summaries:
                live = summary.with_name(summary.stem + "_live.csv")
                self.assertFalse(live.exists())
                rows = pd.read_excel(summary)
                self.assertEqual(rows["time"].nunique(), 1)
                time_text = datetime.fromisoformat(rows["time"].iloc[0]).strftime("%Y%m%d_%H%M%S")
                self.assertIn(time_text, summary.name)
                self.assertNotIn("output_files", rows.columns)

    def test_package_failure_does_not_change_configured_directories(self):
        from measurements.workflows import FEcap_package1
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dirs = {"stage": base / "stage"}
            with mock.patch.multiple(FEcap_package1, BASE_SAVE_DIR=base, SAVE_DIRS=dirs), mock.patch.object(
                FEcap_package1, "load_test_modules", side_effect=RuntimeError("failure")
            ):
                with self.assertRaisesRegex(RuntimeError, "failure"):
                    FEcap_package1.run_package()
                self.assertEqual(FEcap_package1.BASE_SAVE_DIR, base)
                self.assertIs(FEcap_package1.SAVE_DIRS, dirs)


if __name__ == "__main__":
    unittest.main()
