"""Optional SSR command, transition, FET and preview regression tests."""
import os
os.environ.setdefault("MPLBACKEND", "Agg")
from pathlib import Path
import sys
import unittest
from unittest import mock
from contextlib import redirect_stdout
import io

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from keithley4200.pmu.pmu_tests import configure_segARB_sequence, execute_segARB_test, auto_align_channels
from keithley4200.pmu.fet_three_terminal_common import read_fet_channels, execute_program_read_with_software_delay
from keithley4200.tools.dry_run import DryRunState
from keithley4200.tools.waveform_preview import sequence_configs_to_dataframe, preview_sequence_configs
from measurements.pmu.fet import program_read as single, bipolar_program_read as bipolar


class SsrTests(unittest.TestCase):
    def test_omitted_ssr_sends_no_command_and_arrays_use_add(self):
        q = mock.Mock()
        configure_segARB_sequence(q, 1, 1, [0], [0], [1e-6], [0])
        self.assertFalse(any(":SSR" in c.args[0] for c in q.call_args_list))
        q.reset_mock()
        configure_segARB_sequence(q, 1, 1, [0]*130, [0]*130, [50e-6]*130, [0]*130, ssr=[0]*130)
        commands = [c.args[0] for c in q.call_args_list]
        self.assertEqual(sum(c.startswith(":PMU:SARB:SEQ:SSR ") for c in commands), 1)
        self.assertEqual(sum(c.startswith(":PMU:SARB:SEQ:SSR:ADD ") for c in commands), 1)

    def test_bad_ssr_rejected_before_commands(self):
        for ssr in ([0], [1, 2], [1, float("nan")], [1, 0]):
            q = mock.Mock()
            with self.assertRaises(ValueError):
                configure_segARB_sequence(q, 1, 1, [0,0], [0,0], [1e-6]*2, [0,0], ssr=ssr)
            q.assert_not_called()

    def test_sequence_and_loop_boundaries_checked_before_init(self):
        first = (1, [0], [0], [50e-6], [0], None, None, [0])
        second = (2, [0], [0], [1e-6], [0])
        q = mock.Mock()
        with self.assertRaises(ValueError):
            execute_segARB_test(q, [1], {1:[first,second]}, {1:[(1,1),(2,1)]})
        q.assert_not_called()
        repeated = (1, [0,0], [0,0], [1e-6,50e-6], [0,0], None,None,[1,0])
        with self.assertRaises(ValueError):
            execute_segARB_test(q, [1], {1:[repeated]}, {1:[(1,2)]})
        q.assert_not_called()

    def test_auto_alignment_preserves_constant_ssr_and_rejects_switches(self):
        reference = (1,[0,1],[1,0],[50e-6]*2,[0,0])
        hold = (1,[0],[0],[100e-6],[0],None,None,[0])
        aligned = auto_align_channels({1:[reference],2:[hold]})
        self.assertEqual(aligned[2][0][7], [0,0])
        changing = (1,[0,0],[0,0],[40e-6,60e-6],[0,0],None,None,[0,1])
        with self.assertRaises(ValueError):
            auto_align_channels({1:[reference],2:[changing]})

    def test_both_fet_variants_read_drain_with_gate_missing(self):
        for module in (single, bipolar):
            with mock.patch.dict(module.params, {"float_gate_during_read":True, "cycles":1}):
                plan, configs, lists = module.build_program_read_sequence()
                gate_cfg = configs[module.GATE_CH][-1]
                self.assertEqual(gate_cfg[3][-1], 50e-6)
                self.assertEqual(gate_cfg[7][-6:], [0,0,0,0,0,1])
                self.assertFalse(any(gate_cfg[4]))
                state = DryRunState()
                with redirect_stdout(io.StringIO()):
                    execute_segARB_test(state.query_response, [module.GATE_CH,module.DRAIN_CH], configs, lists)
                gate, drain = read_fet_channels(state.query_response,module.GATE_CH,module.DRAIN_CH,float_gate=True)
                self.assertEqual(len(drain),len(plan))
                self.assertTrue(gate[f"Voltage {module.GATE_CH}"].isna().all())
                self.assertTrue(gate[f"Current {module.GATE_CH}"].isna().all())
                self.assertEqual(state.records[module.GATE_CH], [])
                expanded = module.expanded_preview_configs()[0]
                self.assertIn(0, expanded[7])
            with mock.patch.dict(module.params, {"float_gate_during_read":False}):
                self.assertTrue(all(len(c)==7 for values in module.build_program_read_sequence()[1].values() for c in values))

    def test_split_read_preserves_ssr(self):
        with mock.patch.dict(single.params, {"float_gate_during_read":True,"cycles":1}):
            plan, configs, _ = single.build_program_read_sequence(include_delay=False)
            state = DryRunState()
            with mock.patch("keithley4200.pmu.fet_three_terminal_common.time.sleep"), redirect_stdout(io.StringIO()):
                gate, drain = execute_program_read_with_software_delay(state.query_response,plan,configs,2,
                    single.GATE_CH,single.DRAIN_CH,{}, {},float_gate=True)
            self.assertTrue(gate[f"Current {single.GATE_CH}"].isna().all())
            self.assertEqual(len(drain),len(plan))

    def test_preview_masks_floating_voltage_and_exports_states(self):
        cfg = (1,[0,0,0],[0,0,0],[50e-6]*3,[0,0,0],None,None,[1,0,1])
        table = sequence_configs_to_dataframe([cfg])
        self.assertEqual(table["SSR_CH1"].tolist(),[1,1,0,0,1,1])
        self.assertTrue(table.loc[2:3,"V_CH1"].isna().all())
        fig = preview_sequence_configs([cfg],show=False)
        self.assertTrue(any("floating" in label for label in fig.axes[0].get_legend_handles_labels()[1]))
        import matplotlib.pyplot as plt
        plt.close(fig)


if __name__ == "__main__":
    unittest.main()
