# Copyright (c) 2026 ssme / Haoran Yu.
"""Offline checks for Identical V2 empty reads and interrupted checkpoints."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock
import tempfile
import pandas as pd
from measurements.pmu.ftj import ftj_Identical_V2 as module


class IdenticalCheckpointTests(TestCase):
    def test_empty_read_stops_and_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(module, 'PMUSession') as session, \
             mock.patch.object(module, 'run_single_test', return_value=(None, None)) as acquire, \
             mock.patch.object(module.time, 'sleep'):
            session.return_value.__enter__.return_value = SimpleNamespace(query=mock.Mock())
            with self.assertRaisesRegex(RuntimeError, 'Read step 2 returned no data'):
                module.run_test(dict(positive_repeat_count=2, negative_repeat_count=0,
                                     plan_repeat_count=1), save_dir=tmp, preview_only=False)
            self.assertEqual(acquire.call_count, 2)
            files = list(Path(tmp).glob('*.xlsx'))
            self.assertEqual(len(files), 1)
            with pd.ExcelFile(files[0]) as book:
                rows = pd.read_excel(book, 'Summary')
            self.assertEqual(rows['status'].tolist(), ['ok', 'failed'])
            self.assertIn('returned no data', rows.iloc[-1]['error'])

    def test_completed_read_is_saved_before_next_acquisition_and_survives_interrupt(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(module, 'PMUSession') as session, \
             mock.patch.object(module.time, 'sleep'):
            session.return_value.__enter__.return_value = SimpleNamespace(query=mock.Mock())
            counter = 0
            def acquire(*args, **kwargs):
                nonlocal counter
                counter += 1
                if counter == 1:
                    return None, None
                if counter == 2:
                    return (pd.DataFrame({'Voltage 3': [1.0], 'Current 3': [1e-6]}),
                            pd.DataFrame({'Voltage 4': [0.0], 'Current 4': [-1e-6]}))
                with pd.ExcelFile(next(Path(tmp).glob('*.xlsx'))) as book:
                    raw = pd.read_excel(book, 'RawCombined')
                    self.assertEqual(len(raw), 1)
                    self.assertIn('Voltage 4', raw)
                raise KeyboardInterrupt()
            with mock.patch.object(module, 'run_single_test', side_effect=acquire):
                with self.assertRaises(KeyboardInterrupt):
                    module.run_test(dict(positive_repeat_count=2, negative_repeat_count=0,
                                         plan_repeat_count=1), channels=(3, 4),
                                    save_dir=tmp, preview_only=False)
            with pd.ExcelFile(next(Path(tmp).glob('*.xlsx'))) as book:
                self.assertEqual(len(pd.read_excel(book, 'RawCombined')), 1)
                self.assertEqual(pd.read_excel(book, 'Summary').iloc[-1]['status'], 'interrupted')


class IdenticalReadCommandTests(TestCase):
    def read_step(self):
        parameters = dict(module.params, positive_repeat_count=1, negative_repeat_count=0,
                          plan_repeat_count=1, read_dwell=50e-6, read_trf=1e-6, read_idle=1e-3)
        return module.build_waveform(parameters=parameters)['test_plan'][1]

    def test_read_window_and_nondefault_sequence_are_sent_before_execute(self):
        commands = []
        def query(command):
            commands.append(command)
            if command == ':ERROR:LAST:GET':
                return 'No error (0)'
            if command == ':PMU:TEST:STATUS?':
                return '0'
            if command.startswith(':PMU:DATA:COUNT?'):
                return '1'
            if command.startswith(':PMU:DATA:GET'):
                return '-2, 1e-6, 3e-5, 0;'
            return 'ACK'
        first, second = module.run_single_test(query, self.read_step())
        self.assertEqual((len(first), len(second)), (1, 1))
        for channel in (1, 2):
            for command in (
                f':PMU:SARB:SEQ:MEAS:TYPE {channel}, 2, 0, 1, 0, 0',
                f':PMU:SARB:SEQ:MEAS:START {channel}, 2, 0, 2.5e-05, 0, 0',
                f':PMU:SARB:SEQ:MEAS:STOP {channel}, 2, 0, 4.5e-05, 0, 0',
                f':PMU:SARB:WFM:SEQ:LIST {channel}, 2, 1',
            ):
                self.assertLess(commands.index(command), commands.index(':PMU:EXECUTE'))
        self.assertLess(commands.index(':PMU:DATA:GET 2, 0, 2048'),
                        commands.index(':PMU:OUTPUT:STATE 2, 0'))

    def test_configuration_and_execute_errors_stop_before_fetching_data(self):
        for failure_phase in ('configuration', 'execute'):
            commands = []
            def query(command):
                commands.append(command)
                if command == ':ERROR:LAST:GET':
                    if failure_phase == 'configuration' or ':PMU:EXECUTE' in commands:
                        return 'KXCI command error. (-992)'
                    return 'No error (0)'
                return 'ACK'
            with self.subTest(phase=failure_phase), self.assertRaisesRegex(RuntimeError, '-992'):
                module.run_single_test(query, self.read_step())
            self.assertFalse(any(c.startswith(':PMU:DATA:') for c in commands))
            if failure_phase == 'configuration':
                self.assertNotIn(':PMU:EXECUTE', commands)
            self.assertEqual(commands[-2:], [':PMU:OUTPUT:STATE 1, 0', ':PMU:OUTPUT:STATE 2, 0'])
