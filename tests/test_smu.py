# Copyright (c) 2026 ssme / Haoran Yu.
from pathlib import Path
import sys
import importlib
from contextlib import contextmanager
import tempfile
import unittest
from unittest import mock

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.smu.data_processing import build_plot_data, retrieve_variables, save_workbook
from keithley4200.smu.plotting import format_log_tick, save_current_density_plots
from keithley4200.smu.session import SMUSession
from keithley4200.smu.routing import (
    connect_smus_to_probes,
    normalize_smu_connections,
    restore_rpms_to_pulse,
)
from keithley4200.smu.system_mode import (
    configure_measurement_list,
    estimate_smu_timeout_s,
    execute_and_wait,
    linear_sweep_point_count,
    resolve_smu_timeout_s,
    validate_linear_sweep,
)
from keithley4200.smu.user_mode import source_voltage
from keithley4200.pmu.session import PMUSession
from keithley4200.transport import Communications


class FakeKxci:
    def __init__(self, *, error="No error. (0)", status="1", buffers=None):
        self.commands = []
        self.error = error
        self.status = status
        self.buffers = buffers or {}

    def __call__(self, command):
        self.commands.append(command)
        if command == ":ERROR:LAST:GET":
            return self.error
        if command == "SP":
            return self.status
        if command.startswith("DO '"):
            variable = command.split("'", 2)[1]
            return self.buffers.get(variable, "")
        return "ACK"


class SmuSystemModeTests(unittest.TestCase):
    CONNECTIONS = {
        1: "rpm:PMU1-1",
        2: "rpm:PMU1-2",
        3: "direct",
        4: "direct",
    }

    def _exercise_linear_entry(self, fake, *, sweep_channel, bias_channel,
                               available_channels=(1, 2, 3, 4), smu_connections=None,
                               **parameters):
        """Inject fake I/O into the real experiment; do not reproduce its sequence."""
        module = importlib.import_module("measurements.smu.2terminal.linear_voltage_sweep")
        settings = dict(module.PARAMS, **parameters)
        count = linear_sweep_point_count(settings["start"], settings["stop"], settings["step"])
        fake.buffers = {name: ",".join(["N0"] * count) for name in ("I1", "V1", "I2", "V2")}

        @contextmanager
        def session(*args):
            yield type("Session", (), {"query": staticmethod(fake)})()

        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(module, "SMUSession", side_effect=session), \
             mock.patch.object(module, "PARAMS", settings), \
             mock.patch.object(module, "SWEEP_CHANNEL", sweep_channel), \
             mock.patch.object(module, "BIAS_CHANNEL", bias_channel), \
             mock.patch.object(module, "AVAILABLE_CHANNELS", available_channels), \
             mock.patch.object(module, "SMU_CONNECTIONS", smu_connections), \
             mock.patch.object(module, "SAVE_DIR", Path(directory)), \
             mock.patch.object(module, "save_workbook"), \
             mock.patch.object(module, "save_current_density_plots", return_value=(Path(directory)/"j.png", Path(directory)/"log.png")):
            module.main()
        return [command.split("'")[1] for command in fake.commands if command.startswith("DO '")]

    def test_linear_sweep_disables_every_available_channel_before_defining_use(self):
        fake = FakeKxci()

        variables = self._exercise_linear_entry(
            fake,
            sweep_channel=2,
            bias_channel=1,
            available_channels=(1, 2, 3, 4),
            start=0,
            stop=1,
            step=0.1,
            timeout_s=1,
        )

        disable_positions = [fake.commands.index(f"CH{channel}") for channel in (1, 2, 3, 4)]
        first_definition = min(
            index
            for index, command in enumerate(fake.commands)
            if command.startswith(("CH1,", "CH2,"))
        )
        self.assertLess(max(disable_positions), first_definition)
        self.assertIn("ST 1, 1", fake.commands)
        self.assertIn("ST 2, 1", fake.commands)
        self.assertIn(":ERROR:LAST:CLEAR", fake.commands)
        self.assertIn(":ERROR:LAST:GET", fake.commands)
        self.assertIn("ME1", fake.commands)
        self.assertEqual(variables, ["I2", "V2", "I1", "V1"])

    def test_rpm_channels_switch_after_reset_and_restore_after_measurement(self):
        fake = FakeKxci()

        self._exercise_linear_entry(
            fake,
            sweep_channel=2,
            bias_channel=1,
            available_channels=(1, 2, 3, 4),
            smu_connections=self.CONNECTIONS,
            start=0,
            stop=0.1,
            step=0.1,
            timeout_s=1,
        )

        reset_position = fake.commands.index("*RST")
        smu1_position = fake.commands.index("RP PMU1-1, 2")
        smu2_position = fake.commands.index("RP PMU1-2, 2")
        execute_position = fake.commands.index("ME1")
        pulse1_position = fake.commands.index("RP PMU1-1, 0")
        pulse2_position = fake.commands.index("RP PMU1-2, 0")
        self.assertLess(reset_position, smu1_position)
        self.assertLess(reset_position, smu2_position)
        self.assertLess(smu1_position, execute_position)
        self.assertLess(smu2_position, execute_position)
        self.assertLess(execute_position, pulse1_position)
        self.assertLess(execute_position, pulse2_position)

    def test_direct_channels_do_not_send_rpm_commands(self):
        fake = FakeKxci()

        self._exercise_linear_entry(
            fake,
            sweep_channel=4,
            bias_channel=3,
            available_channels=(1, 2, 3, 4),
            smu_connections=self.CONNECTIONS,
            start=0,
            stop=0.1,
            step=0.1,
            timeout_s=1,
        )

        self.assertFalse(any(command.startswith("RP ") for command in fake.commands))

    def test_mixed_direct_and_rpm_run_switches_only_the_rpm_channel(self):
        fake = FakeKxci()

        self._exercise_linear_entry(
            fake,
            sweep_channel=3,
            bias_channel=1,
            available_channels=(1, 2, 3, 4),
            smu_connections=self.CONNECTIONS,
            start=0,
            stop=0.1,
            step=0.1,
            timeout_s=1,
        )

        rp_commands = [command for command in fake.commands if command.startswith("RP ")]
        self.assertEqual(rp_commands, ["RP PMU1-1, 2", "RP PMU1-1, 0"])

    def test_explicit_connections_require_every_active_channel(self):
        with self.assertRaisesRegex(ValueError, "SMU2"):
            normalize_smu_connections(
                {1: "rpm:PMU1-1"},
                active_channels=(1, 2),
            )

    def test_duplicate_rpm_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "same RPM"):
            normalize_smu_connections(
                {1: "rpm:PMU1-1", 2: "rpm:PMU1-1"},
                active_channels=(1, 2),
            )

    def test_rpm_helpers_use_documented_modes(self):
        fake = FakeKxci()
        targets = connect_smus_to_probes(
            fake,
            (1,),
            {1: "rpm:PMU1-1"},
        )
        restore_rpms_to_pulse(fake, targets)
        self.assertEqual(
            [command for command in fake.commands if command.startswith("RP ")],
            ["RP PMU1-1, 2", "RP PMU1-1, 0"],
        )

    def test_setup_error_aborts_and_disables_channels(self):
        fake = FakeKxci(error="KXCI command error. (-992)")

        with self.assertRaisesRegex(RuntimeError, "-992"):
            self._exercise_linear_entry(
                fake,
                sweep_channel=2,
                bias_channel=1,
                available_channels=(1, 2, 3, 4),
                timeout_s=1,
            )

        self.assertNotIn("ME1", fake.commands)
        # No measurement was started, so setup cleanup must not issue ME4.
        self.assertNotIn("ME4", fake.commands)
        for channel in (1, 2, 3, 4):
            self.assertIn(f"CH{channel}", fake.commands)

    def test_timeout_sends_me4(self):
        fake = FakeKxci(status="16")
        with mock.patch(
            "keithley4200.smu.system_mode.time.monotonic",
            side_effect=(0.0, 1.0),
        ):
            with self.assertRaises(TimeoutError):
                execute_and_wait(
                    fake,
                    timeout_s=0.5,
                    poll_interval_s=0,
                )
        self.assertEqual(fake.commands[-1], "ME4")
        self.assertEqual(fake.commands.count("MD"), 1)
        self.assertEqual(fake.commands.count("ME4"), 1)

    def test_auto_timeout_scales_for_dense_quiet_sweep(self):
        timeout_s = estimate_smu_timeout_s(
            1201,
            sweep_delay=0.02,
            integration="IT3",
        )
        self.assertGreater(timeout_s, 300.0)
        self.assertAlmostEqual(timeout_s, 852.66, places=2)

    def test_auto_timeout_keeps_short_sweep_minimum(self):
        self.assertEqual(
            estimate_smu_timeout_s(11, sweep_delay=0.02, integration="IT1"),
            300.0,
        )

    def test_none_disables_overall_test_deadline(self):
        self.assertIsNone(resolve_smu_timeout_s(None, point_count=1201))
        self.assertIsNone(resolve_smu_timeout_s("off", point_count=1201))

    def test_timeout_does_not_switch_an_uncertain_output_back_to_pulse(self):
        fake = FakeKxci(status="16")
        with mock.patch(
            "keithley4200.smu.system_mode.time.monotonic",
            side_effect=(0.0, 1.0),
        ):
            with self.assertRaises(TimeoutError):
                self._exercise_linear_entry(
                    fake,
                    sweep_channel=2,
                    bias_channel=1,
                    available_channels=(1, 2, 3, 4),
                    smu_connections=self.CONNECTIONS,
                    start=0,
                    stop=0.1,
                    step=0.1,
                    timeout_s=0.5,
                )
        self.assertIn("RP PMU1-1, 2", fake.commands)
        self.assertIn("RP PMU1-2, 2", fake.commands)
        self.assertNotIn("RP PMU1-1, 0", fake.commands)
        self.assertNotIn("RP PMU1-2, 0", fake.commands)

    def test_sweep_point_limit_is_checked_before_hardware(self):
        self.assertEqual(linear_sweep_point_count(0, 1, 0.1), 11)
        with self.assertRaisesRegex(ValueError, "1024"):
            validate_linear_sweep(0, 2, 0.001)

    def test_measurement_names_allow_only_documented_suffix_extension(self):
        fake = FakeKxci()
        configure_measurement_list(fake, ("ABCDEF", "ABCDEFT"))
        self.assertIn("LI 'ABCDEF', 'ABCDEFT'", fake.commands)
        with self.assertRaisesRegex(ValueError, "T/S suffix"):
            configure_measurement_list(fake, ("ABCDEFG",))


class SmuDataTests(unittest.TestCase):
    def test_completed_buffers_must_match_expected_point_count(self):
        fake = FakeKxci(
            buffers={
                "V1": "N 0.0,N 0.5,N 1.0",
                "I1": "N 1e-9,N 2e-9,N 3e-9",
            }
        )
        data = retrieve_variables(
            fake,
            ("V1", "I1"),
            expected_point_count=3,
        )
        self.assertEqual(len(data), 3)
        self.assertEqual(list(data["V1_Status"]), ["N", "N", "N"])

    def test_empty_or_mismatched_buffers_fail(self):
        empty = FakeKxci(buffers={"V1": "", "I1": ""})
        with self.assertRaisesRegex(ValueError, "empty buffers"):
            retrieve_variables(empty, ("V1", "I1"))

        mismatch = FakeKxci(
            buffers={
                "V1": "N 0.0,N 1.0",
                "I1": "N 1e-9",
            }
        )
        with self.assertRaisesRegex(ValueError, "lengths do not match"):
            retrieve_variables(mismatch, ("V1", "I1"))

    def test_buffer_request_and_expected_count_must_be_unambiguous(self):
        fake = FakeKxci(buffers={"V1": "N 0.0"})
        with self.assertRaisesRegex(ValueError, "at least one"):
            retrieve_variables(fake, ())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            retrieve_variables(fake, ("V1", "V1"))
        with self.assertRaisesRegex(ValueError, "positive integer"):
            retrieve_variables(fake, ("V1",), expected_point_count=1.5)

    def test_compliance_status_is_visible(self):
        fake = FakeKxci(buffers={"I1": "N 1e-9,C 2e-9"})
        with self.assertWarnsRegex(RuntimeWarning, "compliance"):
            data = retrieve_variables(fake, ("I1",), expected_point_count=2)
        self.assertEqual(list(data["I1_Status"]), ["N", "C"])

    def test_plot_data_has_stable_columns_and_absolute_currents(self):
        raw = pd.DataFrame(
            {
                "CommandedVoltage": [0.0, 0.1],
                "V1": [0.0, 0.099],
                "I1": [-1e-7, 2e-7],
                "I1_Status": ["N", "N"],
                "V2": [0.0, 1e-6],
                "I2": [1.1e-7, -1.9e-7],
                "I2_Status": ["N", "N"],
            }
        )

        plot_data = build_plot_data(raw, area_cm2=2e-6)

        self.assertEqual(
            list(plot_data.columns),
            [
                "CommandedVoltage",
                "V1",
                "I1",
                "J1_A_per_cm2",
                "AbsI1",
                "AbsJ1_A_per_cm2",
                "V2",
                "I2",
                "J2_A_per_cm2",
                "AbsI2",
                "AbsJ2_A_per_cm2",
            ],
        )
        self.assertEqual(list(plot_data["AbsI1"]), [1e-7, 2e-7])
        self.assertEqual(list(plot_data["AbsI2"]), [1.1e-7, 1.9e-7])
        self.assertEqual(list(plot_data["J1_A_per_cm2"]), [-0.05, 0.1])
        self.assertAlmostEqual(plot_data.loc[0, "J2_A_per_cm2"], 0.055)
        self.assertAlmostEqual(plot_data.loc[1, "J2_A_per_cm2"], -0.095)

    def test_workbook_separates_raw_plot_data_and_parameters(self):
        raw = pd.DataFrame(
            {
                "CommandedVoltage": [0.0, 0.1],
                "V1": [0.0, 0.099],
                "I1": [-1e-7, 2e-7],
                "I1_Status": ["N", "C"],
                "V2": [0.0, 1e-6],
                "I2": [1.1e-7, -1.9e-7],
                "I2_Status": ["N", "N"],
            }
        )
        plot_data = build_plot_data(raw, area_cm2=2e-6)

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "smu.xlsx"
            save_workbook(output, raw, {"step": 0.1}, plot_data=plot_data)
            with pd.ExcelFile(output) as workbook:
                self.assertEqual(
                    workbook.sheet_names,
                    ["Raw", "PlotData", "Parameters"],
                )
                saved_raw = pd.read_excel(workbook, sheet_name="Raw")
                saved_plot = pd.read_excel(workbook, sheet_name="PlotData")

        self.assertIn("I1_Status", saved_raw.columns)
        self.assertNotIn("I1_Status", saved_plot.columns)
        self.assertEqual(
            list(saved_plot.columns),
            [
                "CommandedVoltage",
                "V1",
                "I1",
                "J1_A_per_cm2",
                "AbsI1",
                "AbsJ1_A_per_cm2",
                "V2",
                "I2",
                "J2_A_per_cm2",
                "AbsI2",
                "AbsJ2_A_per_cm2",
            ],
        )


class SmuPlotTests(unittest.TestCase):
    def test_log_axis_tick_labels_show_current_values(self):
        self.assertEqual(format_log_tick(1e-7), "1e-7")
        self.assertEqual(format_log_tick(1e-6), "1e-6")
        self.assertEqual(format_log_tick(2e-7), "")

    def test_current_plots_are_created(self):
        data = pd.DataFrame(
            {
                "V1": [-0.1, 0.0, 0.1],
                "J1_A_per_cm2": [-0.1, 0.01, 1.0],
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "smu.xlsx"
            jv_path, log_path = save_current_density_plots(
                data,
                output,
                voltage_column="V1",
                current_density_column="J1_A_per_cm2",
            )
            self.assertGreater(jv_path.stat().st_size, 0)
            self.assertGreater(log_path.stat().st_size, 0)


class SmuUserModeTests(unittest.TestCase):
    def test_source_voltage_checks_kxci_error_queue(self):
        fake = FakeKxci()
        source_voltage(fake, 1, 0.1, 1e-3, range_code=0)
        self.assertEqual(fake.commands, ["DV1, 0, 0.1, 0.001", ":ERROR:LAST:GET"])

    def test_fractional_range_code_is_rejected_instead_of_truncated(self):
        fake = FakeKxci()
        with self.assertRaisesRegex(ValueError, "integer"):
            source_voltage(fake, 1, 0.1, 1e-3, range_code=1.5)
        self.assertEqual(fake.commands, [])


class SharedTransportTests(unittest.TestCase):
    def test_transport_supports_both_query_and_explicit_io_then_closes_all_resources(self):
        instrument = mock.Mock()
        instrument.write.return_value = 4
        instrument.read.return_value = "READ"
        instrument.query.return_value = "ACK\n"
        resource_manager = mock.Mock()
        resource_manager.open_resource.return_value = instrument

        with mock.patch(
            "keithley4200.transport.visa.ResourceManager",
            return_value=resource_manager,
        ):
            client = Communications("TCPIP0::example::1225::SOCKET")
            client.connect(timeout=1234)
            self.assertEqual(client.write("CMD"), 4)
            self.assertEqual(client.read(), "READ")
            self.assertEqual(client.query("QUERY"), "ACK")
            client.close()

        resource_manager.open_resource.assert_called_once_with(
            "TCPIP0::example::1225::SOCKET"
        )
        self.assertEqual(instrument.timeout, 1234)
        self.assertTrue(instrument.send_end)
        instrument.close.assert_called_once_with()
        resource_manager.close.assert_called_once_with()


class SmuSessionTests(unittest.TestCase):
    def test_pmu_connection_setup_failure_uses_shared_transport_cleanup(self):
        class BadInstrument:
            @property
            def write_termination(self):
                return None

            @write_termination.setter
            def write_termination(self, value):
                raise RuntimeError("termination setup failed")

        client = mock.Mock()
        client._instrument_object = BadInstrument()
        with mock.patch("keithley4200.pmu.session.Communications", return_value=client):
            session = PMUSession("TCPIP0::example::SOCKET")
            with self.assertRaisesRegex(RuntimeError, "termination setup failed"):
                session.connect()
        client.close.assert_called_once_with()
        self.assertIsNone(session.client)

    def test_connection_setup_failure_closes_all_visa_resources(self):
        class BadInstrument:
            @property
            def write_termination(self):
                return None

            @write_termination.setter
            def write_termination(self, value):
                raise RuntimeError("termination setup failed")

        client = mock.Mock()
        client._instrument_object = BadInstrument()
        with mock.patch("keithley4200.smu.session.Communications", return_value=client):
            session = SMUSession("TCPIP0::example::SOCKET")
            with self.assertRaisesRegex(RuntimeError, "termination setup failed"):
                session.connect()
        client.close.assert_called_once_with()
        self.assertIsNone(session.client)


if __name__ == "__main__":
    unittest.main()
