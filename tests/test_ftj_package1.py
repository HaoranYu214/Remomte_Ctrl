from pathlib import Path
import importlib.util
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.smu.system_mode import build_segmented_voltage_path, run_list_voltage_sweep


PACKAGE_PATH = REPO_ROOT / "workflows" / "package1.py"


def load_package():
    spec = importlib.util.spec_from_file_location("ftj_package1_test", PACKAGE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeKxci:
    def __init__(self):
        self.commands = []

    def __call__(self, command):
        self.commands.append(command)
        return "ACK"


class FtjPackage1Tests(unittest.TestCase):
    def test_run_mode_and_current_counts_are_valid(self):
        package = load_package()
        modules = {
            "iv": SimpleNamespace(
                build_segmented_voltage_path=build_segmented_voltage_path
            )
        }
        counts = package.validate_package_config(modules)

        self.assertIsInstance(package.PREVIEW_ONLY, bool)
        expected_iv_counts = {
            iv_test["name"]: len(
                build_segmented_voltage_path(
                    package.iv_turning_points(iv_test["vmax_v"]),
                    package.SEGMENTED_IV["segment_step"],
                )
            )
            for iv_test in package.IV_TESTS
        }
        self.assertEqual(counts["iv_point_counts"], expected_iv_counts)
        self.assertEqual(
            counts["map_parameter_points"],
            len(package.PV2_PUND_MAP["vp_values"])
            * len(package.PV2_PUND_MAP["frequency_values_hz"])
            * len(package.PV2_PUND_MAP["delay_time_values_s"]),
        )

    def test_pv2_and_pund_share_the_common_baseline_values(self):
        package = load_package()
        for params in (package.PV2_PARAMS, package.PUND_PARAMS):
            self.assertEqual(params["Vp"], package.PV_PUND_VP)
            self.assertEqual(params["rise_time"], package.PV_PUND_RISE_TIME_S)
            self.assertEqual(params["delay_time"], package.PV_PUND_DELAY_TIME_S)
            self.assertEqual(params["offset"], package.PV_PUND_OFFSET_V)
            self.assertEqual(params["area_cm2"], package.DEVICE_AREA_CM2)
    def test_package_applies_configs_and_runs_six_stages_in_order(self):
        package = load_package()
        calls = []

        pair = SimpleNamespace(
            run_pv_and_pund=lambda **_kwargs: calls.append("pair"),
        )
        map_pv2 = SimpleNamespace(params={}, SEGARB_OPTIONS={})
        map_pund = SimpleNamespace(params={}, SEGARB_OPTIONS={})
        expected_map_runs = (
            len(package.PV2_PUND_MAP["vp_values"])
            * len(package.PV2_PUND_MAP["frequency_values_hz"])
            * len(package.PV2_PUND_MAP["delay_time_values_s"])
            * (
                int(package.PV2_PUND_MAP["run_pv2"])
                + int(package.PV2_PUND_MAP["run_pund_tri"])
            )
        )
        map_module = SimpleNamespace(
            PV2=map_pv2,
            PUND_tri=map_pund,
            SEGARB_OPTIONS={},
            run_map=lambda **_kwargs: (
                calls.append("map")
                or pd.DataFrame(
                    [{"status": "ok"}] * expected_map_runs
                )
            ),
        )
        iv = SimpleNamespace(
            build_segmented_voltage_path=build_segmented_voltage_path,
            main=lambda: calls.append("iv"),
        )
        fake_modules = {"pair": pair, "map": map_module, "iv": iv}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package.BASE_SAVE_DIR = root
            package.STAGE_SETTLE_TIME_S = 0
            package.SEGMENTED_IV["settle_time_s"] = 0
            package.SAVE_DIRS = {
                name: root / name for name in package.SAVE_DIRS
            }

            with mock.patch.object(package, "load_test_modules", return_value=fake_modules):
                result = package.run_package()

        self.assertEqual(
            calls,
            ["pair", "map", "pair", "pair"]
            + ["iv"] * sum(
                int(iv_test["repeat_count"])
                for iv_test in package.IV_TESTS
            )
            + ["pair"],
        )
        self.assertEqual(result["stage"].tolist(), package.RUN_ORDER)
        self.assertNotIn("output_root", result.columns)
        self.assertNotIn("new_files", result.columns)
        self.assertTrue((result["status"] == "ok").all())
        last_iv = package.IV_TESTS[-1]
        self.assertEqual(
            iv.TURNING_POINTS,
            package.iv_turning_points(last_iv["vmax_v"]),
        )
        self.assertIsNone(iv.PARAMS["timeout_s"])
        self.assertEqual(
            iv.SAVE_DIR,
            package.SAVE_DIRS["segmented_iv"] / last_iv["name"],
        )

    def test_preview_generates_waveforms_without_opening_sessions(self):
        package = load_package()

        def forbid_session(*_args, **_kwargs):
            raise AssertionError("Preview attempted to create an instrument session.")

        with tempfile.TemporaryDirectory() as temp_dir:
            package.BASE_SAVE_DIR = Path(temp_dir)
            package.SAVE_DIRS = {
                name: package.BASE_SAVE_DIR / name for name in package.SAVE_DIRS
            }
            modules = package.load_test_modules()
            pair_measurements = modules["pair"].load_measurements()
            pair_measurements["PV2"].PMUSession = forbid_session
            pair_measurements["PUND_tri"].PMUSession = forbid_session
            modules["map"].PV2.PMUSession = forbid_session
            modules["map"].PUND_tri.PMUSession = forbid_session
            modules["iv"].SMUSession = forbid_session
            with (
                mock.patch.object(package, "load_test_modules", return_value=modules),
                mock.patch("matplotlib.pyplot.show") as show_mock,
            ):
                results = package.preview_package()
            map_preview_count = (
                2
                * (
                    int(package.PV2_PUND_MAP["run_pv2"])
                    + int(package.PV2_PUND_MAP["run_pund_tri"])
                )
            )
            self.assertEqual(
                len(results),
                2 + map_preview_count + len(package.IV_TESTS),
            )
            self.assertEqual(show_mock.call_count, 1)
            titles = [figure.axes[0].get_title() for figure in results]
            self.assertTrue(any("Package baseline" in title for title in titles))
            self.assertTrue(any("PV2/PUND Map" in title for title in titles))
            self.assertTrue(any("IV1" in title for title in titles))
            self.assertFalse((package.BASE_SAVE_DIR / "00_previews").exists())

    def test_oversized_list_is_rejected_before_any_hardware_command(self):
        fake = FakeKxci()
        with self.assertRaisesRegex(ValueError, "4096"):
            run_list_voltage_sweep(
                fake,
                values=[0.0] * 4097,
                sweep_channel=1,
                bias_channel=2,
            )
        self.assertEqual(fake.commands, [])


if __name__ == "__main__":
    unittest.main()
