# Copyright (c) 2026 ssme / Haoran Yu.
"""Source persistence changes only accepted current-range defaults."""
import ast
from pathlib import Path
import sys
import tempfile
import subprocess
import os
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from keithley4200.parameter_defaults import remember_current_ranges, write_current_range_defaults


class RangeDefaultsTests(unittest.TestCase):
    def test_keyword_and_literal_dictionaries_preserve_other_code_and_comments(self):
        sources = [
            'params = dict(Vp=3.5, Irange1=1e-4, Irange2=1e-3)  # keep this\r\n',
            'PV2_PARAMS = {"Vp": 3.5, "Irange1": 1e-4, "Irange2": 1e-3} # keep\r\n',
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'experiment.py'
            for source in sources:
                with self.subTest(source=source):
                    original = b'\xef\xbb\xbf' + ('# 中文 parameters\r\n' + source + 'other = {"Irange1": 1e-4}\r\n').encode('utf-8')
                    path.write_bytes(original)
                    name = 'params' if source.startswith('params') else 'PV2_PARAMS'
                    write_current_range_defaults(path, {'Irange1': 1e-6, 'Irange2': 1e-5, 'Vp': 99}, name)
                    expected = original.replace(b'Irange1=1e-4', b'Irange1=1e-06').replace(b'Irange2=1e-3', b'Irange2=1e-05') if name == 'params' else original.replace(b'"Irange1": 1e-4', b'"Irange1": 1e-06', 1).replace(b'"Irange2": 1e-3', b'"Irange2": 1e-05', 1)
                    self.assertEqual(path.read_bytes(), expected)
                    namespace = {}
                    exec(compile(path.read_bytes(), str(path), 'exec'), namespace)
                    self.assertEqual(namespace[name]['Irange1'], 1e-6)
                    self.assertEqual(namespace[name]['Vp'], 3.5)
                    before = path.stat().st_mtime_ns
                    write_current_range_defaults(path, {'Irange1': 1e-6}, name)
                    self.assertEqual(path.stat().st_mtime_ns, before)

    def test_failed_write_keeps_valid_source_and_in_memory_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'experiment.py'
            source = 'params = dict(Irange1=1e-4, Irange2=1e-4)\n'
            path.write_text(source, encoding='utf-8')
            defaults = {'Irange1': 1e-4, 'Irange2': 1e-4, 'Vp': 3}
            with mock.patch('keithley4200.parameter_defaults.os.replace', side_effect=PermissionError('locked')):
                with self.assertWarnsRegex(RuntimeWarning, 'could not be saved'):
                    remember_current_ranges(defaults, {'Irange1': 1e-6}, path)
            self.assertEqual(path.read_text(encoding='utf-8'), source)
            self.assertEqual(defaults['Irange1'], 1e-6)
            self.assertEqual(defaults['Vp'], 3)
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_invalid_fields_or_ranges_do_not_rewrite_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'experiment.py'
            source = 'params = dict(Irange1=1e-4)\n'
            path.write_text(source, encoding='utf-8')
            for ranges in ({'Irange2': 1e-5}, {'Irange1': float('nan')}, {'Irange1': 0}):
                with self.assertRaises(ValueError):
                    write_current_range_defaults(path, ranges)
            self.assertEqual(path.read_text(encoding='utf-8'), source)

    def test_dry_run_hooks_never_write_source_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'experiment.py'
            source = 'params = dict(Irange1=1e-4, Irange2=1e-4)\n'
            path.write_text(source, encoding='utf-8')
            code = """
import sys
sys.path.insert(0, sys.argv[1] + '/src')
from keithley4200.tools.dry_run import install_dry_run_hooks
from keithley4200 import parameter_defaults
install_dry_run_hooks(no_save=False)
parameter_defaults.remember_current_ranges({}, {'Irange1': 1e-6}, sys.argv[2])
"""
            result = subprocess.run([sys.executable, '-c', code, str(ROOT), str(path)],
                                    capture_output=True, text=True, timeout=20,
                                    env={**os.environ, 'MPLBACKEND': 'Agg'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SKIP_DEFAULTS', result.stdout)
            self.assertEqual(path.read_text(encoding='utf-8'), source)


if __name__ == '__main__':
    unittest.main()
