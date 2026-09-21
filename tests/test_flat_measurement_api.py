"""Flat entrypoints keep waveform ownership local and execute without adapters."""
import ast
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import importlib
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from keithley4200.tools.dry_run import DryRunSession
import matplotlib
matplotlib.use('Agg')

FTJ_NAMES = ('RV1', 'RV2', 'PWM', 'MRD', 'Identical_V1', 'Identical_V2', 'ISPP_V1', 'ISPP_V2')


class FlatMeasurementApiTests(unittest.TestCase):
    def test_entry_files_have_one_definition_per_function_and_no_measurement_classes(self):
        paths = [ROOT / 'measurements/pmu/ftj' / ('ftj_' + name + '.py') for name in FTJ_NAMES]
        paths += [ROOT / 'measurements/pmu/fet' / (name + '.py')
                  for name in ('program_read', 'bipolar_program_read')]
        paths += [ROOT / 'measurements/pmu/fe_cap' / (name + '.py')
                  for name in ('PV2', 'PUND_tri', 'PUND_Squr', 'retentionPV', 'retentionPUND')]
        for path in paths:
            with self.subTest(path=path.name):
                tree = ast.parse(path.read_text(encoding='utf-8'))
                definitions = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
                self.assertEqual(len(definitions), len(set(definitions)))
                self.assertIn('run_test', definitions)
                self.assertFalse(any(isinstance(n, (ast.ClassDef, ast.Global)) for n in ast.walk(tree)))
                self.assertFalse({'create_measurement', 'configure_measurement', '_rebuild_runtime_config'} & set(definitions))

    def test_all_ftj_entries_execute_with_one_waveform_build(self):
        for name in FTJ_NAMES:
            module = importlib.import_module('measurements.pmu.ftj.ftj_' + name)
            before = deepcopy(module.params)
            override = {}
            for key in before:
                if key.startswith('wait_after_'):
                    override[key] = 0
                elif key in ('positive_repeat_count', 'negative_repeat_count', 'sequence_cycle_count',
                             'plan_repeat_count', 'repeat_count', 'cycles_per_level'):
                    override[key] = 1
                elif key in ('positive_steps', 'negative_steps'):
                    override[key] = 2
            if name.startswith('RV'):
                override.update(vp=1.0, write_level_step=1.0)
                if "scan_cycles" in before:
                    override["scan_cycles"] = 1
            elif name == 'PWM':
                override.update(width_multipliers=[1, 2])
            elif name == 'MRD':
                override.update(write_voltages=[0.2])
            with self.subTest(name=name), ExitStack() as stack:
                stack.enter_context(redirect_stdout(io.StringIO()))
                stack.enter_context(mock.patch.object(module, 'PMUSession', DryRunSession))
                build = stack.enter_context(mock.patch.object(module, 'build_waveform', wraps=module.build_waveform))
                result = module.run_test(override, save_results=False, preview_only=False)
                build.assert_called_once()
                self.assertIsNone(result['output_path'])
                for key, value in override.items():
                    self.assertEqual(result['params'][key], value)
                self.assertEqual(module.params, before)

    def test_ftj_previews_build_once_and_never_open_hardware(self):
        import matplotlib.pyplot as plt
        for name in FTJ_NAMES:
            module = importlib.import_module('measurements.pmu.ftj.ftj_' + name)
            with self.subTest(name=name), mock.patch.object(module, 'PMUSession', side_effect=AssertionError('hardware accessed')):
                with mock.patch.object(module, 'build_waveform', wraps=module.build_waveform) as build:
                    module.preview_waveform(show=False)
                    build.assert_called_once()
            plt.close('all')


if __name__ == '__main__':
    unittest.main()
