# Copyright (c) 2026 ssme / Haoran Yu.
"""FTJ waveform and workflow coverage using direct function calls."""
from copy import deepcopy
from importlib import reload
from pathlib import Path
from types import SimpleNamespace
import inspect
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from keithley4200.pmu.pmu_tests import MAX_SEGMENTS_PER_SEQUENCE, _normalize_seg_arb_measurements
from measurements.pmu.ftj import (
    ftj_RV1, ftj_RV2, ftj_PWM, ftj_MRD, ftj_Identical_V1, ftj_Identical_V2,
    ftj_ISPP_V1, ftj_ISPP_V2, ftj_endurance,
)
from measurements.workflows import ftj_package1

MODULES = (ftj_RV1, ftj_RV2, ftj_PWM, ftj_MRD, ftj_Identical_V1,
           ftj_Identical_V2, ftj_ISPP_V1, ftj_ISPP_V2)


def assert_configs_are_pmu_valid(test_case, configs_by_channel):
    for configs in configs_by_channel.values():
        test_case.assertLessEqual(sum(len(c[3]) for c in configs), MAX_SEGMENTS_PER_SEQUENCE)
        for config in configs:
            _normalize_seg_arb_measurements(config[3], config[4], config[5], config[6])


class FtjWorkflowConfigTests(unittest.TestCase):
    def test_every_ftj_entry_builds_from_explicit_parameters(self):
        for imported_module in MODULES:
            module = reload(imported_module)
            before = deepcopy(module.params)
            with self.subTest(module=module.__name__):
                waveform = module.build_waveform(parameters=module.params)
                for config in waveform['seq_configs'][module.CH1]:
                    self.assertEqual(config[1][0], before['base_v'])
                    self.assertEqual(config[2][-1], before['base_v'])
                assert_configs_are_pmu_valid(self, waveform['seq_configs'])
                self.assertEqual(module.params, before)

    def test_rv2_rebuilds_offset_scan_read_level_and_channels(self):
        module = reload(ftj_RV2)
        configured = dict(module.params, base_v=0.25, offset_v=-1.5, vp=1.0,
                          write_level_step=0.5, read_v=-0.25, scan_cycles=2)
        waveform = module.build_waveform(parameters=configured, channels=(3, 4))
        self.assertEqual(waveform['scan_levels'], [1.0, 0.5, 0.0, -0.5, -1.0, -0.5, 0.0, 0.5, 1.0, 0.5, 0.0, -0.5, -1.0, -0.5, 0.0, 0.5, 1.0])
        self.assertEqual(waveform['scan_voltages'][0], -0.5)
        self.assertEqual(waveform['scan_voltages'][4], -2.5)
        first_scan = waveform['ch1_scan_configs'][0]
        self.assertEqual(first_scan[1][0], 0.25)
        self.assertEqual(first_scan[1][1], -0.5)
        self.assertEqual(first_scan[1][5], -0.25)
        self.assertEqual(first_scan[2][-1], 0.25)
        self.assertEqual(set(waveform['seq_configs']), {3, 4})
        assert_configs_are_pmu_valid(self, waveform['seq_configs'])

    def test_pwm_rebuilds_widths_repeat_metadata_and_sequence_list(self):
        module = reload(ftj_PWM)
        configured = dict(module.params, write_base_dwell=2e-6,
                          width_multipliers=[1, 3, 10], repeat_count=2, read_v=-0.8)
        waveform = module.build_waveform(parameters=configured)
        for step, width in zip(waveform['pwm_steps'], [2e-6, 6e-6, 20e-6]):
            self.assertAlmostEqual(step['WriteWidth_s'], width)
        self.assertEqual(len(waveform['pwm_steps']), 12)
        self.assertEqual(waveform['seq_list'][module.CH1], [(1, 2)])
        assert_configs_are_pmu_valid(self, waveform['seq_configs'])

    def test_identical_rebuilds_counts_voltages_and_stored_segments(self):
        module = reload(ftj_Identical_V1)
        configured = dict(module.params, write_positive_v=1.2, write_negative_v=-3.4,
                          read_v=-0.6, positive_repeat_count=2, negative_repeat_count=3,
                          sequence_cycle_count=2)
        waveform = module.build_waveform(parameters=configured)
        self.assertEqual(len(waveform['seq_plan']), 20)
        configs = waveform['seq_configs'][module.CH1]
        self.assertEqual(len(configs), 2)
        self.assertIn(1.2, configs[0][1])
        self.assertIn(-3.4, configs[0][1])
        assert_configs_are_pmu_valid(self, waveform['seq_configs'])

    def test_oversized_workflow_config_is_rejected_during_build(self):
        configured = dict(ftj_Identical_V1.params, positive_repeat_count=100,
                          negative_repeat_count=100, sequence_cycle_count=2)
        with self.assertRaisesRegex(ValueError, 'stored Segment Arb segments'):
            ftj_Identical_V1.build_waveform(parameters=configured)

    def test_mrd_rebuilds_voltage_levels_cycles_and_measurement_windows(self):
        configured = dict(ftj_MRD.params, base_v=0.2, reference_v=-4.0,
                          write_voltages=[0.5, 1.0], read_v=-0.75, cycles_per_level=3)
        waveform = ftj_MRD.build_waveform(parameters=configured)
        self.assertEqual(waveform['seq_list'][ftj_MRD.CH1], [(1, 3), (2, 3)])
        self.assertEqual(waveform['ch1_configs'][0][1][0], 0.2)
        self.assertEqual(waveform['ch1_configs'][0][1][1], -4.0)
        self.assertEqual(waveform['ch1_configs'][0][2][-1], 0.2)
        expected = ftj_MRD.expected_cycle_table(waveform['seq_metadata'])
        self.assertEqual(len(expected), 12)
        self.assertEqual(expected['ReadType'].tolist()[:2], ['RefStateRead', 'AfterWriteRead'])
        assert_configs_are_pmu_valid(self, waveform['seq_configs'])

    def test_runtime_save_defaults_are_not_captured_at_import(self):
        for module in MODULES:
            parameters = inspect.signature(module.run_test).parameters
            self.assertIsNone(parameters['save_dir'].default)
            self.assertIsNone(parameters['file_stem'].default)

    def test_package_imports_maintained_modules_and_full_configs_are_valid(self):
        self.assertEqual(ftj_package1.FTJ_TESTS['rv2']['module'], 'measurements.pmu.ftj.ftj_RV2')
        modules = ftj_package1.load_test_modules()
        for name, config in ftj_package1.FTJ_TESTS.items():
            module = modules[name]
            waveform = module.build_waveform(parameters={**module.params, **config['params']})
            assert_configs_are_pmu_valid(self, waveform['seq_configs'])

    def test_package_runs_configured_stages_in_order_without_hardware(self):
        calls = []
        modules = {name: SimpleNamespace(run_test=lambda _name=name, **kwargs:
                   (calls.append((_name, kwargs)) or {'output_path': None}))
                   for name in ftj_package1.FTJ_TESTS}
        with mock.patch.object(ftj_package1, 'STAGE_SETTLE_TIME_S', 0):
            results = ftj_package1.run_package(modules=modules)
        self.assertEqual(list(results), ftj_package1.RUN_ORDER)
        self.assertEqual([name for name, _ in calls], ftj_package1.RUN_ORDER)
        for name, kwargs in calls:
            self.assertEqual(kwargs['params_override'], ftj_package1.FTJ_TESTS[name]['params'])
            self.assertEqual(kwargs['current_ranges'], ftj_package1.FTJ_TESTS[name]['current_ranges'])
            self.assertEqual(kwargs['save_dir'], ftj_package1.FTJ_TESTS[name]['save_dir'])
            self.assertFalse(kwargs['preview_only'])

    def test_package_previews_all_stages_with_one_final_show(self):
        calls = []
        modules = {name: SimpleNamespace(params={}, preview_waveform=lambda _name=name, **kwargs:
                   (calls.append((_name, kwargs)) or _name)) for name in ftj_package1.FTJ_TESTS}
        with mock.patch('matplotlib.pyplot.show') as show:
            figures = ftj_package1.preview_package(modules=modules)
        self.assertEqual(figures, ftj_package1.RUN_ORDER)
        self.assertTrue(all(kwargs['show'] is False for _, kwargs in calls))
        for name, kwargs in calls:
            self.assertEqual(kwargs['parameters'], ftj_package1.FTJ_TESTS[name]['params'])
        show.assert_called_once_with()

    def test_endurance_selects_both_identical_targets_and_passes_overrides(self):
        for target, repeat_key in ((ftj_Identical_V1, 'sequence_cycle_count'),
                                   (ftj_Identical_V2, 'plan_repeat_count')):
            before = deepcopy(target.params)
            overrides = dict(write_positive_v=2.5, write_negative_v=-4.0,
                             positive_repeat_count=2, negative_repeat_count=3)
            overrides[repeat_key] = 1
            with self.subTest(target=target.__name__), tempfile.TemporaryDirectory() as tmp:
                with mock.patch.object(ftj_endurance, 'TARGET_MODULE_NAME', target.__name__), \
                     mock.patch.object(target, 'run_test', return_value={}) as execute:
                    self.assertIs(ftj_endurance.load_ftj_module(), target)
                    result = ftj_endurance.run_endurance(
                        param_overrides=overrides, loop_count=2, save_dir=tmp)
                self.assertEqual(execute.call_count, 2)
                for call in execute.call_args_list:
                    settings = call.kwargs
                    self.assertEqual(settings['params_override'], dict(before, **overrides))
                    self.assertFalse(settings['preview_only'])
                    self.assertTrue(settings['save_results'])
                    waveform = target.build_waveform(parameters=settings['params_override'])
                    assert_configs_are_pmu_valid(self, waveform['seq_configs'])
                self.assertEqual(result['summary_df']['status'].tolist(), ['ok', 'ok'])
                self.assertEqual(target.params, before)

    def test_endurance_merges_overrides_and_uses_runtime_save_path(self):
        calls = []
        fake = SimpleNamespace(params={'vp': 4.0, 'read_v': -1.0},
                               run_test=lambda **kwargs: (calls.append(kwargs) or {'output_path': None}))
        with tempfile.TemporaryDirectory() as tmp:
            result = ftj_endurance.run_endurance(module=fake, param_overrides={'vp': 3.0},
                                                save_dir=Path(tmp), loop_count=2,
                                                save_every_run=False, file_stem_prefix='offline')
        self.assertEqual(len(calls), 2)
        for kwargs in calls:
            self.assertEqual(kwargs['params_override'], {'vp': 3.0, 'read_v': -1.0})
            self.assertEqual(kwargs['file_stem'], 'offline')
            self.assertEqual(Path(kwargs['save_dir']), Path(tmp))
        self.assertEqual(fake.params, {'vp': 4.0, 'read_v': -1.0})
        self.assertIn('time', result['summary_df'].columns)
        self.assertEqual(result['summary_df']['status'].tolist(), ['ok', 'ok'])


if __name__ == '__main__':
    unittest.main()
