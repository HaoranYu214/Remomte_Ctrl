import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def top_level_functions(relative_path):
    path = REPO_ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


class WaveformOwnershipTests(unittest.TestCase):
    def test_shared_pmu_module_contains_no_experiment_protocols(self):
        functions = top_level_functions("src/keithley4200/pmu/pmu_tests.py")
        hidden_protocols = {
            "dual_channel_pulse_train",
            "dual_channel_sweep_train",
            "hy_pv2_segARB",
            "hy_pund_segARB",
            "hy_NISswitch_segARB",
            "hy_Endurance_segARB",
            "build_endurance_exec_list",
        }
        self.assertTrue(hidden_protocols.isdisjoint(functions))

    def test_fet_entries_own_their_pulse_protocols(self):
        self.assertIn(
            "run_dual_channel_pulse_train",
            top_level_functions("measurements/pmu/pulse/pulse_train.py"),
        )
        self.assertIn(
            "run_dual_channel_sweep_train",
            top_level_functions("measurements/pmu/pulse/pulse_sweep.py"),
        )

    def test_segment_arb_waveforms_are_owned_by_experiment_entries(self):
        expected_builders = {
            "measurements/pmu/fe_cap/PV2.py": {"make_pv2_seq_configs"},
            "measurements/pmu/fe_cap/PUND_Squr.py": {"make_pund_seq_configs"},
            "measurements/pmu/fe_cap/endurance.py": {
                "make_cycle_seq_configs",
                "make_pv2_seq_configs",
                "make_pund_seq_configs",
            },
            "measurements/pmu/programmed/NLS_1C_switch.py": {
                "make_nls_seq_configs"
            },
        }
        for relative_path, expected in expected_builders.items():
            with self.subTest(path=relative_path):
                self.assertTrue(expected.issubset(top_level_functions(relative_path)))


if __name__ == "__main__":
    unittest.main()
