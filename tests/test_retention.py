"""Offline checks for explicitly split retention protocols."""
import os
os.environ.setdefault("MPLBACKEND", "Agg")
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
import pandas as pd
from measurements.pmu.fe_cap import retentionPV as pv, retentionPUND as pund
from measurements.pmu.fe_cap import _retention as local
from keithley4200.tools.dry_run import DryRunState


class FakeClock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        return self.now
    def sleep(self, seconds):
        assert seconds >= 0
        self.now += seconds


class RetentionTests(unittest.TestCase):
    def simulate(self, module, delay=1.0, fail_at=None):
        timer = FakeClock()
        state = DryRunState()
        params = dict(module.params, delay_time=delay)
        with mock.patch.dict(module.params, params):
            plan = module.make_retention_plan()
        frames, timing, events = {1: [], 2: []}, [], []
        executes = 0
        def query(command):
            nonlocal executes
            events.append(command)
            timer.now += 0.001
            if command == ":PMU:EXECUTE":
                executes += 1
                if executes == fail_at:
                    raise RuntimeError("injected failure")
                timer.now += sum(plan[executes-1]["configs"][1][0][3])
            return state.query_response(command)
        try:
            pair = local.execute_plan(query, plan, (1, 2), params, module.SEGARB_OPTIONS,
                                      frames, timing, clock=timer, sleep=timer.sleep)
        except RuntimeError:
            if fail_at is None:
                raise
            pair = None
        return pair, frames, timing, events

    def test_plan_preserves_waveforms_and_omits_long_delays(self):
        for module, expected in ((pv, ["Preset", "PV"]), (pund, ["Preset", "P", "U", "N", "D"])):
            with mock.patch.dict(module.params, {"delay_time": 5.0}):
                plan = module.make_retention_plan()
                local.validate_plan(plan, (1, 2), module.params)
            self.assertEqual([s["label"] for s in plan], expected)
            for stage in plan:
                self.assertLess(max(stage["configs"][1][0][3]), 0.1)
                self.assertEqual(stage["configs"][1][0][3], stage["configs"][2][0][3])
            self.assertEqual(plan[1]["delay_before_s"], 5.0)

    def test_delay_budget_includes_transfer_and_configuration(self):
        pair, frames, timing, events = self.simulate(pund, 0.1)
        self.assertEqual(events.count(":PMU:EXECUTE"), 5)
        for row in timing[1:]:
            self.assertAlmostEqual(row["estimated_delay_s"], 0.1)
            self.assertAlmostEqual(row["overrun_s"], 0)
        self.assertEqual(pair[0]["Stage"].unique().tolist(), ["Preset", "P", "U", "N", "D"])
        init_positions = [i for i,c in enumerate(events) if c == ":PMU:INIT 1"]
        for left,right in zip(init_positions,init_positions[1:]):
            self.assertTrue(any(c.startswith(":PMU:DATA:GET") for c in events[left:right]))
            self.assertIn(":PMU:OUTPUT:STATE 1, 0", events[left:right])

    def test_overrun_is_recorded_without_an_extra_full_sleep(self):
        _, _, timing, _ = self.simulate(pv, 0.001)
        self.assertGreater(timing[1]["overrun_s"], 0)
        self.assertAlmostEqual(timing[1]["estimated_delay_s"] - 0.001, timing[1]["overrun_s"])

    def test_long_delay_does_not_change_offline_read_waveform(self):
        short = self.simulate(pv, 0.1)[0]
        long = self.simulate(pv, 10.0)[0]
        self.assertEqual(len(short[0]), len(long[0]))
        np.testing.assert_array_equal(short[0]["Timestamp 1"], long[0]["Timestamp 1"])
        self.assertGreater(long[0]["EstimatedGlobalTime_s"].iloc[0], short[0]["EstimatedGlobalTime_s"].iloc[0])

    def test_pund_analysis_accepts_different_counts_per_execution(self):
        pair, _, _, _ = self.simulate(pund)
        reduced = []
        for df in pair:
            reduced.append(pd.concat([group.iloc[::2] if label == "U" else group
                                      for label, group in df.groupby("Stage", sort=False)], ignore_index=True))
        data = pund.analyze_pund_triangle_diff(*reduced)
        self.assertEqual(set(data["pund_diff"]["Segment"]), {"P-U", "N-D"})
        self.assertTrue(np.isfinite(data["pund_diff"]["Polarization"]).all())

    def test_failure_retains_earlier_stages_and_shuts_down(self):
        _, frames, timing, events = self.simulate(pund, fail_at=3)
        self.assertEqual([df["Stage"].iloc[0] for df in frames[1]], ["Preset", "P"])
        self.assertEqual(timing[-1]["status"], "failed")
        self.assertIn(":PMU:ABORT", events)
        self.assertIn(":PMU:OUTPUT:STATE 1, 0", events[-2:])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "partial.xlsx"
            local.save_raw(output, frames, timing, pund.build_params_table())
            self.assertTrue(output.is_file())
            self.assertEqual(pd.read_excel(output, sheet_name="ExecutionTiming")["status"].iloc[-1], "failed")

    def test_invalid_parameters_fail_before_hardware(self):
        for update in ({"delay_time": float("nan")}, {"delay_time": -1}, {"offset": 0.2}, {"rise_time": 2}):
            with mock.patch.dict(pv.params, update), mock.patch.object(pv, "PMUSession") as session:
                with self.assertRaises(ValueError):
                    pv.run_test(preview_only=False)
                session.assert_not_called()

    def test_preview_shows_gaps_channels_and_executes_without_hardware(self):
        import matplotlib.pyplot as plt
        for module, count in ((pv, 2), (pund, 5)):
            with mock.patch.object(module, "PMUSession", side_effect=AssertionError("hardware")):
                fig = module.preview_waveform(show=False)
                self.assertEqual(len(fig.axes), count+2)
                self.assertEqual(len(fig.axes[0].patches), count-1)
                self.assertIn("CH1", fig.axes[0].get_ylabel())
                self.assertIn("CH2", fig.axes[1].get_ylabel())
                self.assertTrue(any("Output off" in t.get_text() for t in fig.axes[0].texts))
                real = module.preview_waveform(show=False, compress_delay=False)
                self.assertGreater(real.axes[0].get_xlim()[1], fig.axes[0].get_xlim()[1])
                plt.close(fig)
                plt.close(real)
                with tempfile.TemporaryDirectory() as tmp, mock.patch.object(plt, "show") as show:
                    output = module.preview_waveform(Path(tmp) / "nested" / "preview.png")
                    self.assertTrue(output.is_file())
                    show.assert_not_called()

    def test_main_saves_raw_timing_analysis_and_plot_offline(self):
        for module in (pv, pund):
            pair, frames, timing, _ = self.simulate(module)
            def fake_execute(query, plan, channels, params, options, target_frames, target_timing):
                target_frames.update(frames)
                target_timing.extend(timing)
                return pair
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(module, "SAVE_DIR", Path(tmp)), mock.patch.object(
                module, "PMUSession"
            ), mock.patch.object(module, "execute_plan", side_effect=fake_execute):
                module.run_test(preview_only=False)
                workbook = next(Path(tmp).glob("*.xlsx"))
                with pd.ExcelFile(workbook) as saved:
                    self.assertIn("ExecutionTiming", saved.sheet_names)
                self.assertTrue(list(Path(tmp).glob("*_loops.png")))


if __name__ == "__main__":
    unittest.main()
