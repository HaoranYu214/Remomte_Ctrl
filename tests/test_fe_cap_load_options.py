# Copyright (c) 2026 ssme / Haoran Yu.
import ast
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.pmu.pmu_tests import _apply_common_pmu_options


FE_CAP_ROOT = REPO_ROOT / "measurements" / "pmu" / "fe_cap"
WORKFLOW_ROOT = REPO_ROOT / "measurements" / "workflows"
DIRECT_ENTRY_FILES = [
    FE_CAP_ROOT / "PV2.py",
    FE_CAP_ROOT / "PUND_Squr.py",
    FE_CAP_ROOT / "PUND_tri.py",
    FE_CAP_ROOT / "NLS_manually.py",
    FE_CAP_ROOT / "endurance.py",
]
REQUIRED_OPTIONS = {
    "ENABLE_CONNECTION_COMP",
    "ENABLE_LOAD_CONFIG",
    "LOAD_RESISTANCE",
    "ENABLE_LLEC",
}


def segarb_options_literal(tree):
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "SEGARB_OPTIONS" for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("SEGARB_OPTIONS assignment is missing")


class CommonPmuLoadTests(unittest.TestCase):
    def test_sample_rate_is_applied_and_validated(self):
        commands = []
        _apply_common_pmu_options(
            commands.append,
            (1, 2),
            options={"SAMPLE_RATE": 10e6},
        )
        self.assertEqual(commands, [":PMU:SAMPLE:RATE 10000000"])
        with self.assertRaisesRegex(ValueError, "SAMPLE_RATE"):
            _apply_common_pmu_options(
                commands.append,
                (1, 2),
                options={"SAMPLE_RATE": 500},
            )

    def test_uniform_load_is_applied_to_every_active_channel(self):
        commands = []
        _apply_common_pmu_options(
            commands.append,
            [1, 2],
            {
                "ENABLE_LOAD_CONFIG": True,
                "LOAD_RESISTANCE": 2.5e5,
            },
        )
        self.assertEqual(
            commands,
            [":PMU:LOAD 1, 250000.0", ":PMU:LOAD 2, 250000.0"],
        )

    def test_disabled_load_configuration_emits_no_load_command(self):
        commands = []
        _apply_common_pmu_options(
            commands.append,
            [1, 2],
            {
                "ENABLE_LOAD_CONFIG": False,
                "LOAD_RESISTANCE": 2.5e5,
            },
        )
        self.assertEqual(commands, [])

    def test_per_channel_loads_override_the_default(self):
        commands = []
        _apply_common_pmu_options(
            commands.append,
            [1, 2],
            {
                "ENABLE_LOAD_CONFIG": True,
                "LOAD_RESISTANCE": 1e6,
                "LOAD_RESISTANCES": {1: 1e3, 2: 2e3},
            },
        )
        self.assertEqual(commands, [":PMU:LOAD 1, 1000.0", ":PMU:LOAD 2, 2000.0"])


class FeCapEntryWiringTests(unittest.TestCase):
    def test_every_direct_entry_exposes_and_passes_common_options(self):
        for path in DIRECT_ENTRY_FILES:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
                options = segarb_options_literal(tree)
                self.assertTrue(REQUIRED_OPTIONS.issubset(options))

                execute_calls = [
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "execute_segARB_test"
                ]
                self.assertGreater(len(execute_calls), 0)
                for call in execute_calls:
                    keywords = {keyword.arg for keyword in call.keywords}
                    self.assertIn("options", keywords)

                if path.name == "endurance.py":
                    self.assertIn('"SEGARB_OPTIONS": segarb_options', source)
                else:
                    self.assertIn("segarb_options.items()", source.lower())

    def test_map_exposes_complete_params_and_propagates_common_options(self):
        path = WORKFLOW_ROOT / "pv2_pund_map.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        options = segarb_options_literal(tree)
        self.assertTrue(REQUIRED_OPTIONS.issubset(options))
        self.assertIn("effective_params = dict(base_params)", source)
        self.assertIn("module.run_test(", source)
        self.assertIn("segarb_options=options", source)
        self.assertIn('"area_cm2": DEVICE_AREA_CM2', source)

if __name__ == "__main__":
    unittest.main()
