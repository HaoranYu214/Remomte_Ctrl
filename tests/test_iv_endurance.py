# Copyright (c) 2026 ssme / Haoran Yu.
import importlib
"""Offline coverage for repeated segmented IV acquisition and checkpoints."""
import sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'src'), str(Path(__file__).resolve().parents[1])]
from copy import deepcopy
from unittest import TestCase, mock
import tempfile
import pandas as pd
endurance = importlib.import_module("measurements.smu.2terminal.iv_endurance")
segmented = importlib.import_module("measurements.smu.2terminal.segmented_voltage_sweep")


class IVEnduranceTests(TestCase):
    def test_repeats_complete_paths_and_updates_single_summary(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(segmented, 'run_test') as acquire:
            acquire.side_effect = lambda **kw: {'output_path': Path(tmp) / (kw['file_stem'] + '.xlsx')}
            result = endurance.run_endurance(loop_count=3, turning_points=[0, 1, 0, -2, 0],
                segment_step=.5, params_override={'sweep_delay': .1}, save_dir=tmp, preview_only=False)
            self.assertEqual(acquire.call_count, 3)
            self.assertEqual(len(result['output_paths']), 3)
            for index, call in enumerate(acquire.call_args_list, 1):
                self.assertEqual(call.kwargs['turning_points'], [0, 1, 0, -2, 0])
                self.assertEqual(call.kwargs['params_override']['sweep_delay'], .1)
                self.assertIn(f'run{index}', call.kwargs['file_stem'])
            summaries = list(Path(tmp).glob('*.xlsx'))
            self.assertEqual(len(summaries), 1)
            with pd.ExcelFile(summaries[0]) as book:
                rows = pd.read_excel(book)
            self.assertEqual(rows.status.tolist(), ['ok'] * 3)
            self.assertNotIn('output_path', rows)

    def test_failure_and_interrupt_keep_completed_runs_and_stop(self):
        for error in (RuntimeError('acquisition failed'), KeyboardInterrupt()):
            with self.subTest(error=type(error)), tempfile.TemporaryDirectory() as tmp, \
                 mock.patch.object(segmented, 'run_test', side_effect=[{'output_path': Path(tmp)/'first.xlsx'}, error]) as acquire:
                with self.assertRaises(type(error)):
                    endurance.run_endurance(loop_count=3, save_dir=tmp, preview_only=False)
                self.assertEqual(acquire.call_count, 2)
                with pd.ExcelFile(next(Path(tmp).glob('*.xlsx'))) as book:
                    rows = pd.read_excel(book)
                self.assertEqual(rows.status.iloc[0], 'ok')
                self.assertEqual(rows.status.iloc[1], 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed')

    def test_preview_has_no_acquisition_or_files_and_invalid_plan_fails_early(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(segmented, 'run_test') as acquire, \
             mock.patch.object(segmented, 'preview_waveform', return_value='figure'):
            result = endurance.run_endurance(loop_count=2, preview_only=True, save_dir=tmp)
            self.assertEqual(result['preview'], 'figure')
            self.assertEqual(list(Path(tmp).iterdir()), [])
            for count in (0, -1, 1.5):
                with self.assertRaises(ValueError):
                    endurance.run_endurance(loop_count=count, save_dir=tmp, preview_only=False)
            with self.assertRaisesRegex(ValueError, '4096'):
                endurance.run_endurance(turning_points=[0, 10, 0], segment_step=.001, save_dir=tmp, preview_only=False)
            acquire.assert_not_called()

    def test_segmented_explicit_overrides_reach_acquisition_and_saved_parameters(self):
        before = deepcopy(segmented.PARAMS)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(segmented, 'SMUSession') as connection, \
             mock.patch.object(segmented, 'execute_and_wait'), \
             mock.patch.object(segmented, 'raise_for_kxci_error'), \
             mock.patch.object(segmented, 'connect_smus_to_probes', return_value=()), \
             mock.patch.object(segmented, 'retrieve_variables', return_value=pd.DataFrame({'V1':[0,1,0], 'I1':[0,1e-6,0], 'V2':[0,0,0], 'I2':[0,-1e-6,0]})), \
             mock.patch.object(segmented, 'save_workbook') as save, \
             mock.patch.object(segmented, 'save_current_density_plots', return_value=(Path(tmp)/'j.png', Path(tmp)/'log.png')):
            result = segmented.run_test({'sweep_delay': .123}, turning_points=[0,1,0],
                segment_step=1, save_dir=tmp, inst='offline', device_area_cm2=1e-4, preview_only=False)
            commands = [call.args[0] for call in connection.return_value.__enter__.return_value.query.call_args_list]
            self.assertIn('VL1,1,0.0001,0,1,0', commands)
            self.assertIn('DT 0.123', commands)
            self.assertEqual(save.call_args.args[2]['TURNING_POINTS'], [0,1,0])
            self.assertEqual(save.call_args.args[2]['DEVICE_AREA_CM2'], 1e-4)
            self.assertEqual(result['point_count'], 3)
        self.assertEqual(segmented.PARAMS, before)
