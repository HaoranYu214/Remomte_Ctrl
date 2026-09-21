"""Check tools imports and CLI bootstrapping outside the repository cwd."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class ToolsPackageTests(unittest.TestCase):
    def test_package_imports_and_default_script_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, "-c",
                 "import sys; from pathlib import Path; "
                 "sys.path.insert(0,sys.argv[1]); "
                 "from keithley4200.tools import dry_run, waveform_preview; "
                 "assert dry_run.REPO_ROOT == Path(sys.argv[2]); "
                 "assert dry_run.DEFAULT_SCRIPT.is_file(); "
                 "assert callable(waveform_preview.preview_sequence_configs)",
                 str(SRC), str(ROOT)],
                cwd=tmp, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_direct_and_module_cli_intercept_instrument_calls(self):
        probe = '''from keithley4200.pmu.session import PMUSession
from keithley4200.pmu.pmu_tests import execute_segARB_test
from keithley4200.pmu.data_processing import read_channel_data
assert PMUSession.__name__ == "SharedDryRunSession"
with PMUSession("offline-only", channels=(1,)) as session:
    execute_segARB_test(session.query, [1], {1: [(1, [0], [1], [1e-6])]})
    data = read_channel_data(session.query, 1)
    assert len(data) == 32
print("PROBE_OK")
'''
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "probe.py"
            target.write_text(probe, encoding="utf-8")
            env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONPATH": str(SRC)}
            for entry in ([str(SRC / "keithley4200/tools/dry_run.py")],
                          ["-m", "keithley4200.tools.dry_run"]):
                with self.subTest(entry=entry):
                    # Direct execution must also bootstrap without PYTHONPATH.
                    command_env = env.copy()
                    if len(entry) == 1:
                        command_env.pop("PYTHONPATH", None)
                    result = subprocess.run(
                        [sys.executable, *entry, "--no-save", str(target)],
                        cwd=tmp, env=command_env, capture_output=True, text=True,
                        encoding="utf-8", timeout=30,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("PROBE_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
