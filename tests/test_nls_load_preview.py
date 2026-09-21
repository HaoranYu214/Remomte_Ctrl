import ast
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock



REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

MEASUREMENT_ROOT = REPO_ROOT / "measurements" / "pmu" / "programmed"

from measurements.pmu.programmed import NLS_1C_switch as nls_switch
from measurements.pmu.programmed import NLS_1C_switch_list as nls_list
from measurements.pmu.fe_cap import NLS_manually as nls_manual
from keithley4200.pmu.timing import nls_padding_time


REQUIRED_OPTIONS = {
    "ENABLE_CONNECTION_COMP",
    "ENABLE_LOAD_CONFIG",
    "LOAD_RESISTANCE",
    "ENABLE_LLEC",
}


def assignment_literal(tree, name):
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} assignment is missing")


class NlsSequenceTests(unittest.TestCase):
    def test_entry_owns_the_exact_nls_waveform(self):
        params = nls_switch.PARAMS
        configs = nls_switch.make_nls_seq_configs(1, 2, params)
        ch1_config = configs[1][0]

        offset = params["offset"]
        vp = params["Vp"]
        vsquare = params["Vsquare"]
        self.assertEqual(
            ch1_config[1],
            [
                0, 0, offset, -vp + offset, offset,
                offset, vsquare + offset, vsquare + offset, offset,
                offset, offset, vp + offset, offset, offset, vp + offset,
            ],
        )
        self.assertEqual(
            ch1_config[2],
            [
                0, offset, -vp + offset, offset, offset,
                vsquare + offset, vsquare + offset, offset, offset,
                offset, vp + offset, offset, offset, vp + offset, offset,
            ],
        )
        self.assertEqual(
            ch1_config[3],
            [
                params["Rt_p"], params["Rt_p"], params["Rt_p"],
                params["Rt_p"], params["Delaytime"], params["Rt_s"],
                params["Dwell"], params["Rt_s"], params["Delaytime"],
                nls_padding_time(params),
                params["Rt_p"], params["Rt_p"], params["Delaytime"],
                params["Rt_p"], params["Rt_p"],
            ],
        )
        square_measurement = 2 if params.get("MeasureSquare", True) else 0
        self.assertEqual(
            ch1_config[4],
            [0, 0, 0, 0, 0, square_measurement, square_measurement,
             square_measurement, 0, 0, 2, 2, 0, 2, 2],
        )

    def test_sequence_has_the_expected_two_aligned_15_segment_channels(self):
        configs = nls_switch.make_nls_seq_configs(1, 2, nls_switch.PARAMS)
        self.assertEqual(set(configs), {1, 2})
        self.assertEqual(len(configs[1]), 1)
        self.assertEqual(len(configs[2]), 1)
        for channel in (1, 2):
            config = configs[channel][0]
            self.assertEqual(len(config[1]), 15)
            self.assertEqual(len(config[2]), 15)
            self.assertEqual(len(config[3]), 15)
            self.assertEqual(len(config[4]), 15)

    def test_read_onset_is_fixed_across_sweep_widths_and_both_entries(self):
        for dwell in (1e-7, 1e-4, 0.1):
            for measure_square in (False, True):
                params = dict(nls_switch.PARAMS, Dwell=dwell, MeasureSquare=measure_square)
                with mock.patch.dict(nls_manual.params, params, clear=True):
                    variants = (
                        nls_switch.make_nls_seq_configs(1, 2, params),
                        nls_manual.make_nls_seq_configs(),
                    )
                for configs in variants:
                    first, second = configs[1][0], configs[2][0]
                    self.assertAlmostEqual(sum(first[3][4:10]), params["TotalDelay"])
                    self.assertEqual(first[3], second[3])
                    self.assertEqual(first[1][9], 0)
                    self.assertEqual(first[2][9], 0)
                    self.assertEqual(first[4][9], 0)
                    self.assertEqual(first[4][10:], [2, 2, 0, 2, 2])

    def test_zero_padding_omits_segment_and_invalid_timing_fails(self):
        params = dict(nls_switch.PARAMS)
        params["TotalDelay"] = 2*params["Delaytime"] + 2*params["Rt_s"] + params["Dwell"]
        config = nls_switch.make_nls_seq_configs(1, 2, params)[1][0]
        self.assertEqual(len(config[3]), 14)
        self.assertAlmostEqual(sum(config[3][4:9]), params["TotalDelay"])
        for total in (0, float("nan"), float("inf"), params["TotalDelay"] - 1e-6,
                      params["TotalDelay"] + 1e-9, params["TotalDelay"] + 1.1):
            with self.subTest(total=total), self.assertRaises(ValueError):
                nls_switch.make_nls_seq_configs(1, 2, dict(params, TotalDelay=total))

    def test_invalid_sweep_fails_before_session_or_output(self):
        with mock.patch.dict(nls_list.BASE_PARAMS, {"TotalDelay": 1e-3}), mock.patch.object(
            nls_list, "PMUSession"
        ) as session, mock.patch.object(nls_list, "prepare_output_dir") as output:
            with self.assertRaises(ValueError):
                nls_list.run_sweep()
            session.assert_not_called()
            output.assert_not_called()

    def test_timing_is_saved_in_parameters(self):
        table = nls_switch.build_params_table(nls_switch.PARAMS, nls_switch.SEGARB_OPTIONS)
        values = table.set_index("name")["value"]
        self.assertEqual(float(values["TotalDelay"]), nls_switch.PARAMS["TotalDelay"])
        self.assertEqual(float(values["PaddingDelay"]), nls_padding_time(nls_switch.PARAMS))

    def test_preview_saves_without_opening_a_pmu_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "nls_preview.png"
            nls_switch.preview_nls_waveform(nls_switch.PARAMS, output)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)


class NlsEntryWiringTests(unittest.TestCase):
    def test_single_entry_exposes_options_and_passes_them_to_execute(self):
        path = MEASUREMENT_ROOT / "NLS_1C_switch.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        options = assignment_literal(tree, "SEGARB_OPTIONS")
        self.assertTrue(REQUIRED_OPTIONS.issubset(options))

        execute_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "execute_segARB_test"
        ]
        self.assertEqual(len(execute_calls), 1)
        self.assertIn("options", {keyword.arg for keyword in execute_calls[0].keywords})
        self.assertIn("def preview_nls_waveform", source)
        self.assertIn("PREVIEW_ONLY", source)

    def test_sweep_entry_exposes_options_and_preview(self):
        path = MEASUREMENT_ROOT / "NLS_1C_switch_list.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        options = assignment_literal(tree, "SEGARB_OPTIONS")
        self.assertTrue(REQUIRED_OPTIONS.issubset(options))
        self.assertIn("segarb_options=SEGARB_OPTIONS", source)
        self.assertIn("def preview_sweep_waveform", source)
        self.assertIn("PREVIEW_ONLY", source)


if __name__ == "__main__":
    unittest.main()
