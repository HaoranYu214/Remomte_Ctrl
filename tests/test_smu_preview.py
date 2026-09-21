# Copyright (c) 2026 ssme / Haoran Yu.
"""Offline preview displays the voltage commanded on every physical channel."""
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import matplotlib.pyplot as plt
from keithley4200.smu.preview import preview_channel_voltages
from keithley4200.smu.fet import validate_fet_sweep
from keithley4200.smu.preview import preview_fet_family


class ChannelPreviewTests(unittest.TestCase):
    def tearDown(self):
        plt.close("all")

    def test_segmented_preview_includes_remapped_bias(self):
        module = importlib.import_module("measurements.smu.2terminal.segmented_voltage_sweep")
        with mock.patch.object(module, "SMUSession") as session:
            figure = module.preview_waveform(show=False, turning_points=[0, 1, 0],
                segment_step=.5, sweep_channel=3, bias_channel=4, bias_voltage=.2)
        session.assert_not_called()
        lines = {line.get_label(): list(line.get_ydata()) for line in figure.axes[0].lines}
        self.assertEqual(lines, {"CH3": [0, .5, 1, .5, 0], "CH4": [.2]*5})

    def test_fet_preview_uses_absolute_voltages_and_includes_source(self):
        config = validate_fet_sweep(values=[0, 1], sweep_terminal="gate", bias_voltage=.1,
            source_voltage=.2, gate_channel=4, drain_channel=2, source_channel=3,
            smu_connections={4: "direct", 2: "direct", 3: "direct"})
        figure = preview_fet_family([config], show=False)
        lines = {line.get_label(): list(line.get_ydata()) for line in figure.axes[0].lines}
        self.assertEqual(lines["CH4 (gate, curve 1)"], [.2, 1.2])
        self.assertAlmostEqual(lines["CH2 (drain, curve 1)"][0], .3)
        self.assertEqual(lines["CH3 (source, curve 1)"], [.2, .2])

    def test_save_returns_path_and_closes_figure(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(plt, "show") as show:
            path = Path(directory) / "preview" / "iv.png"
            self.assertEqual(preview_channel_voltages({"CH1": [0, 1]}, path), path)
            self.assertGreater(path.stat().st_size, 0)
            self.assertEqual(plt.get_fignums(), [])
            show.assert_not_called()

    def test_invalid_paths_fail_before_creating_figure(self):
        for paths in ({}, {"CH1": []}, {"CH1": [0], "CH2": [0, 1]}, {"CH1": [float("nan")]}):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                preview_channel_voltages(paths, show=False)
        self.assertEqual(plt.get_fignums(), [])


class PreviewSwitchTests(unittest.TestCase):
    def tearDown(self):
        plt.close("all")

    def test_standalone_switch_prevents_hardware_and_saving(self):
        for name in ("linear_voltage_sweep", "segmented_voltage_sweep", "segmented_voltage_sweep_Memristor"):
            module = importlib.import_module("measurements.smu.2terminal." + name)
            with self.subTest(name=name), mock.patch.object(module, "PREVIEW_ONLY", True), \
                 mock.patch.object(module, "SMUSession") as session, \
                 mock.patch.object(module, "save_workbook") as save, \
                 mock.patch.object(plt, "show"):
                module.main()
                session.assert_not_called()
                save.assert_not_called()
                self.assertEqual(len(plt.gcf().axes[0].lines), 2)
                plt.close("all")

    def test_segmented_preview_uses_per_call_parameters(self):
        module = importlib.import_module("measurements.smu.2terminal.segmented_voltage_sweep")
        with mock.patch.object(module, "SMUSession") as session, mock.patch.object(plt, "show"):
            result = module.run_test({"bias_voltage": .2}, turning_points=[0, 1],
                segment_step=.5, sweep_channel=3, bias_channel=4, preview_only=True)
        session.assert_not_called()
        self.assertIsNone(result["output_path"])
        lines = {line.get_label(): list(line.get_ydata()) for line in result["preview"].axes[0].lines}
        self.assertEqual(lines, {"CH3": [0, .5, 1], "CH4": [.2]*3})
