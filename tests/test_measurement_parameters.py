# Copyright (c) 2026 ssme / Haoran Yu.
"""Regression tests for isolated run parameters and saved configuration."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import importlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from keithley4200.tools.dry_run import DryRunSession
from keithley4200.measurement_parameters import merge_parameters
import pandas as pd
import matplotlib
matplotlib.use("Agg")


class MeasurementParametersTests(unittest.TestCase):
    def setUp(self):
        # Synthetic acquisitions must never rewrite the real experiment files.
        patcher = mock.patch('keithley4200.parameter_defaults.write_current_range_defaults')
        self.persist = patcher.start()
        self.addCleanup(patcher.stop)
        from measurements.pmu.fe_cap import PV2, PUND_tri, PUND_Squr
        from measurements.workflows import pv_and_pund, pv2_pund_map
        dictionaries = [PV2.params, PUND_tri.params, PUND_Squr.params,
                        pv_and_pund.PV2_PARAMS, pv_and_pund.PUND_PARAMS,
                        pv2_pund_map.PV2_BASE_PARAMS, pv2_pund_map.PUND_BASE_PARAMS]
        for defaults in dictionaries:
            patcher = mock.patch.dict(defaults, deepcopy(defaults), clear=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_ftj_partial_overrides_and_nested_defaults_are_independent(self):
        names = ('RV1', 'RV2', 'PWM', 'MRD', 'Identical_V1', 'Identical_V2', 'ISPP_V1', 'ISPP_V2')
        for name in names:
            module = importlib.import_module('measurements.pmu.ftj.ftj_' + name)
            original = deepcopy(module.params)
            with self.subTest(name=name):
                first_params = merge_parameters(module.params, {'base_v': 0.125})
                second_params = merge_parameters(module.params, {'base_v': 0.25})
                first = module.build_waveform(parameters=first_params)
                second = module.build_waveform(parameters=second_params)
                self.assertEqual(first['seq_configs'][module.CH1][0][1][0], 0.125)
                self.assertEqual(second['seq_configs'][module.CH1][0][1][0], 0.25)
                self.assertEqual(module.params, original)
        module = importlib.import_module('measurements.pmu.ftj.ftj_PWM')
        override = {'width_multipliers': [1, 2]}
        first = merge_parameters(module.params, override)
        override['width_multipliers'].append(3)
        first['width_multipliers'].append(4)
        self.assertEqual(override['width_multipliers'], [1, 2, 3])
        self.assertNotEqual(module.params['width_multipliers'], first['width_multipliers'])

    def test_fet_overrides_reach_waveform_ranges_and_saved_metadata(self):
        for name in ('program_read', 'bipolar_program_read'):
            module = importlib.import_module('measurements.pmu.fet.' + name)
            original = deepcopy(module.params)
            override = {'read_delay': 0.002, 'read_drain_voltage': 0.75,
                        'gate_current_range': 1e-4, 'cycles': 1}
            if name == 'program_read':
                override.update(train_count=1, program_levels=(1.25,))
            else:
                override.update(positive_program_read_repeats=1, negative_program_read_repeats=1)
            with self.subTest(name=name), ExitStack() as stack:
                stack.enter_context(redirect_stdout(io.StringIO()))
                stack.enter_context(mock.patch.object(module, 'PMUSession', DryRunSession))
                stack.enter_context(mock.patch.object(module, 'reserve_output_stem', return_value=Path('offline')))
                save = stack.enter_context(mock.patch.object(module, 'save_fet_workbook'))
                stack.enter_context(mock.patch.object(module, 'save_ids_dual_axis_plot'))
                result = module.run_test(override, channels=(2, 1), preview_only=False,
                                         save_waveform_preview=False, use_source_smu=False,
                                         segarb_options={'ENABLE_LLEC': False, 'SAMPLE_RATE': 1e6})
                metadata = save.call_args.args[2]
                data = save.call_args.args[1]
                self.assertEqual(metadata['read_delay'], 0.002)
                self.assertEqual(metadata['CURRENT_RANGES'][2], 1e-4)
                self.assertEqual(metadata['channels'], (2, 1))
                self.assertEqual(metadata['SAMPLE_RATE'], 1e6)
                self.assertTrue((data['MeasuredVd'] == 0.75).all())
                self.assertEqual(result['params']['read_delay'], 0.002)
                self.assertEqual(module.params, original)
                self.assertEqual(override['read_delay'], 0.002)

    def test_auto_range_callback_uses_overrides_and_saves_final_ranges(self):
        for name in ('PV2', 'PUND_tri', 'PUND_Squr'):
            module = importlib.import_module('measurements.pmu.fe_cap.' + name)
            original = deepcopy(module.params)
            override = {'Vp': 2.75, 'delay_time': 0.002, 'Irange1': 1e-4, 'Irange2': 1e-4}
            seen = []
            original_execute = module.execute_segARB_test
            def execute(query, channels, configs, **kwargs):
                seen.append((channels, configs, kwargs))
                return original_execute(query, channels, configs, **kwargs)
            def adjust(acquire, initial, extractors, **kwargs):
                final = {'Irange1': 1e-5, 'Irange2': 1e-6}
                data = acquire(final)
                for extractor in extractors.values():
                    self.assertGreater(len(extractor(data)), 0)
                return data, final, {}
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
                stack.enter_context(redirect_stdout(io.StringIO()))
                stack.enter_context(mock.patch.object(module, 'PMUSession', DryRunSession))
                stack.enter_context(mock.patch.object(module, 'execute_segARB_test', side_effect=execute))
                stack.enter_context(mock.patch.object(module, 'acquire_with_auto_current_range', side_effect=adjust))
                stack.enter_context(mock.patch('matplotlib.figure.Figure.savefig'))
                result = module.run_test(override, channels=(2, 1), save_dir=tmp, preview_only=False)
                self.assertTrue(result['output_path'].exists())
                with pd.ExcelFile(result['output_path']) as workbook:
                    table = pd.read_excel(workbook, 'Parameters')
                saved = dict(zip(table['name'], table['value']))
                self.assertEqual(float(saved['Vp']), 2.75)
                self.assertEqual(float(saved['Irange1']), 1e-5)
                self.assertEqual(float(saved['Irange2']), 1e-6)
                self.assertEqual(saved['channels'], '(2, 1)')
                self.assertEqual(seen[0][0], [2, 1])
                driven = seen[0][1][2][0]
                self.assertAlmostEqual(max(driven[1] + driven[2]), 2.75 + original['offset'])
                self.assertEqual(seen[0][2]['current_ranges'], {2: 1e-5, 1: 1e-6})
                self.assertEqual(result['params']['Irange1'], 1e-5)
                self.assertEqual(module.params, dict(original, Irange1=1e-5, Irange2=1e-6))
                self.persist.assert_any_call(module.__file__, {"Irange1": 1e-5, "Irange2": 1e-6}, "params")
                self.assertEqual(override['Irange1'], 1e-4)
                self.assertEqual(merge_parameters(module.params)['Irange1'], 1e-5)

    def test_failed_run_and_invalid_key_leave_defaults_intact(self):
        from measurements.pmu.fe_cap import PV2
        original = deepcopy(PV2.params)
        with self.assertRaisesRegex(ValueError, 'Unknown measurement parameters'):
            PV2.run_test({'Vpp': 3})
        with mock.patch.object(PV2, 'PMUSession', side_effect=RuntimeError('offline failure')):
            with mock.patch.object(PV2, 'reserve_output_stem', return_value=Path('offline')):
                with self.assertRaisesRegex(RuntimeError, 'offline failure'):
                    PV2.run_test({'Vp': 2}, preview_only=False)
        self.assertEqual(PV2.params, original)
        self.assertEqual(merge_parameters(PV2.params), original)

    def test_fet_ssr_and_retention_preview_use_independent_parameters(self):
        from measurements.pmu.fet import program_read
        from measurements.pmu.fe_cap import retentionPV, retentionPUND
        parameters = merge_parameters(program_read.params,
                                      {'float_gate_during_read': True, 'read_delay': 0.003})
        plan, configs, _ = program_read.build_program_read_sequence(parameters=parameters)
        self.assertEqual(parameters['ssr_switch_time'], 50e-6)
        self.assertTrue(any(len(config) == 8 and 0 in config[7] for config in configs[program_read.GATE_CH]))
        self.assertFalse(program_read.params['float_gate_during_read'])
        for module in (retentionPV, retentionPUND):
            before = deepcopy(module.params)
            parameters = merge_parameters(module.params, {'delay_time': 3.0, 'Vp': 2.0})
            stages = module.make_retention_plan(parameters=parameters)
            self.assertEqual(module.params, before)
            with mock.patch.object(module, 'PMUSession', side_effect=AssertionError('hardware accessed')):
                fig = module.preview_waveform(parameters=parameters, show=False)
            import matplotlib.pyplot as plt
            plt.close(fig)
            self.assertGreater(len(stages), 1)

    def test_workflow_preview_does_not_modify_imported_measurement(self):
        from measurements.workflows.pv_and_pund import preview_pv_and_pund
        from measurements.pmu.fe_cap import PV2, PUND_tri
        before = deepcopy(PV2.params)
        with mock.patch.object(PV2, 'preview_waveform') as pv_preview, \
             mock.patch.object(PUND_tri, 'preview_waveform'):
            preview_pv_and_pund(pv2_params={'Vp': 1.5}, channels=(2, 1), show=False)
        self.assertEqual(pv_preview.call_args.kwargs['parameters']['Vp'], 1.5)
        self.assertEqual(pv_preview.call_args.kwargs['channels'], (2, 1))
        self.assertEqual(PV2.params, before)
        self.persist.assert_not_called()

    def test_ftj_run_saves_the_effective_partial_override(self):
        from measurements.pmu.ftj import ftj_RV2
        original = deepcopy(ftj_RV2.params)
        override = {'vp': 1.0, 'write_level_step': 1.0, 'offset_v': 0.0, 'write_dwell': 20e-6}
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            with mock.patch.object(ftj_RV2, 'PMUSession', DryRunSession):
                result = ftj_RV2.run_test(override, save_dir=tmp, preview_only=False)
            with pd.ExcelFile(result['output_path']) as workbook:
                parameters = pd.read_excel(workbook, 'Parameters')
                trace = pd.read_excel(workbook, 'RV_ReadOnly')
            saved = dict(zip(parameters['name'], parameters['value']))
            self.assertEqual(float(saved['write_dwell']), 20e-6)
            self.assertEqual(trace['CommandedWriteVoltage'].tolist(), [1, 0, -1, 0, 1])
            self.assertEqual(result['params']['vp'], 1.0)
        self.assertEqual(ftj_RV2.params, original)

    def test_map_summary_uses_final_run_ranges_without_polluting_defaults(self):
        from measurements.workflows import pv2_pund_map
        from measurements.pmu.fe_cap import PV2
        original = deepcopy(PV2.params)
        def adjust(acquire, initial, extractors, **kwargs):
            final = {'Irange1': 1e-5, 'Irange2': 1e-6}
            return acquire(final), final, {}
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(mock.patch.object(PV2, 'PMUSession', DryRunSession))
            stack.enter_context(mock.patch.object(PV2, 'acquire_with_auto_current_range', side_effect=adjust))
            stack.enter_context(mock.patch('matplotlib.figure.Figure.savefig'))
            row = pv2_pund_map.run_one_test(PV2, 'PV2', original, tmp, 2.5, 1000, 0.001, 1, 1)
        self.assertEqual(row['status'], 'ok')
        self.assertEqual(row['Vp_V'], 2.5)
        self.assertEqual(row['Irange1_A'], 1e-5)
        self.assertEqual(row['Irange2_A'], 1e-6)
        self.assertEqual(PV2.params, original)
        self.assertEqual(original['Irange1'], 1e-5)
        self.assertEqual(original['Irange2'], 1e-6)


if __name__ == '__main__':
    unittest.main()
