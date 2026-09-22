# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: standard amplitude-swept pulse trains; edit params, INST, CH1/CH2, TEST_MODE and SAVE_DIR.
# Flow: main -> run_dual_channel_sweep_train configures/executes -> read/disable outputs -> save/display plots.
# main acquires data; TEST_MODE selects acquisition mode, not preview, and 0 does not mean offline.

"""Two-channel sweep plus pulse-train test."""

from pathlib import Path
import sys
import time

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.output import measurement_name, reserve_output_stem, voltage_tag, time_tag
from keithley4200.pmu.data_processing import (
    add_resistance_columns,
    merge_channels,
    read_both_channels,
    save_channels_separate_excel,
    select_pulse_iv_level,
)
from keithley4200.pmu.plotting import PlotManager, plot_time_series
from keithley4200.pmu.pmu_tests import (
    _apply_common_pmu_options,
    _configure_pulse_iv_acquisition,
    _get_mode_num,
    power_off_outputs,
)
from keithley4200.pmu.session import PMUSession


# Configure and execute two-channel amplitude-swept pulse trains through the existing connection; mode selects acquisition.
def run_dual_channel_sweep_train(query, ch1, ch2, parameters, mode="D"):
    """Configure and run this entry's sweep-plus-pulse-train waveform."""
    mode_number = _get_mode_num(mode)
    mode_names = {
        0: "no measurement",
        1: "spot measurement",
        2: "waveform measurement",
        3: "averaged spot measurement",
        4: "averaged waveform measurement",
    }
    print(
        "Configuring two-channel sweep plus pulse train - "
        f"mode {mode_number}: {mode_names[mode_number]}"
    )

    query(":PMU:INIT 0")
    query(f":PMU:RPM:CONFIGURE PMU1-{ch1}, 0")
    query(f":PMU:RPM:CONFIGURE PMU1-{ch2}, 0")
    _apply_common_pmu_options(query, (ch1, ch2), options=parameters)

    query(f":PMU:MEASURE:MODE {mode_number}")
    query(f":PMU:MEASURE:RANGE {ch2}, 2, {parameters['CH2_RANGE']}")
    query(
        f":PMU:PULSE:TRAIN {ch2}, "
        f"{parameters['CH2_BASE']}, {parameters['CH2_AMPLITUDE']}"
    )
    query(
        f":PMU:PULSE:TIMES {ch2}, {parameters['CH2_PERIOD']}, "
        f"{parameters['CH2_WIDTH']}, {parameters['CH2_RISE']}, "
        f"{parameters['CH2_FALL']}, {parameters['CH2_DELAY']}"
    )
    query(f":PMU:MEASURE:RANGE {ch1}, 2, {parameters['CH1_RANGE']}")
    query(
        f":PMU:SWEEP:PULSE:AMPLITUDE {ch1}, {parameters['CH1_START']}, "
        f"{parameters['CH1_STOP']}, {parameters['CH1_STEP']}, "
        f"{parameters['CH1_VBASE']}, {parameters['CH1_DUALSWEEP']}"
    )
    query(
        f":PMU:PULSE:TIMES {ch1}, {parameters['CH1_PERIOD']}, "
        f"{parameters['CH1_WIDTH']}, {parameters['CH1_RISE']}, "
        f"{parameters['CH1_FALL']}, {parameters['CH1_DELAY']}"
    )

    # Preserve the original command ordering used by this tested entry.
    query(f":PMU:MEASURE:MODE {mode_number}")
    if mode_number in (1, 3):
        _configure_pulse_iv_acquisition(query, (ch1, ch2), parameters)
        query(
            f":PMU:TIMES:PIV {ch1}, "
            f"{parameters['MEASURE_START_D']}, {parameters['MEASURE_STOP_D']}"
        )
        query(
            f":PMU:TIMES:PIV {ch2}, "
            f"{parameters['MEASURE_START_D']}, {parameters['MEASURE_STOP_D']}"
        )
    elif mode_number in (2, 4):
        query(
            f":PMU:TIMES:WAVEFORM {ch1}, "
            f"{parameters['MEASURE_START_W']}, {parameters['MEASURE_STOP_W']}"
        )
        query(
            f":PMU:TIMES:WAVEFORM {ch2}, "
            f"{parameters['MEASURE_START_W']}, {parameters['MEASURE_STOP_W']}"
        )

    query(f":PMU:PULSE:BURST:COUNT {parameters['PULSE_COUNT']}")
    query(f":PMU:OUTPUT:STATE {ch1}, 1")
    query(f":PMU:OUTPUT:STATE {ch2}, 1")
    query(":PMU:EXECUTE")

    while int(query(":PMU:TEST:STATUS?")) != 0:
        time.sleep(0.3)

params = dict(
    CH1_START=-2,
    CH1_STOP=2,
    CH1_STEP=0.5,
    CH1_VBASE=0.0,
    CH1_DUALSWEEP=1,
    CH1_PERIOD=2000e-6,
    CH1_WIDTH=750e-6,
    CH1_RISE=50e-6,
    CH1_FALL=50e-6,
    CH1_DELAY=100e-6,
    CH1_RANGE=1e-3,
    CH2_BASE=0,
    CH2_AMPLITUDE=0.5,
    CH2_PERIOD=2000e-6,
    CH2_WIDTH=750e-6,
    CH2_RISE=50e-6,
    CH2_FALL=50e-6,
    CH2_DELAY=1100e-6,
    CH2_RANGE=1e-7,
    PULSE_COUNT=1,
    ACQUIRE_HIGH=True,
    ACQUIRE_LOW=False,
    MEASURE_START_D=0.6,
    MEASURE_STOP_D=0.8,
    MEASURE_START_W=0.2,
    MEASURE_STOP_W=0.2,
    ENABLE_LOAD_CONFIG=False,
    LOAD_RESISTANCE=1e6,
    ENABLE_LLEC=False,
    ENABLE_CONNECTION_COMP=False,
    CURRENT_EPS=1e-12,
    RES_MIN=1.0,
    RES_MAX=1e15,
)
TEST_MODE = 2
INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2
RESISTANCE_SCALE = "linear"
SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\FTJ\Refined")

# Connect to the PMU, configure/execute both channels, read data, disable outputs, save Excel and display plots.
# TEST_MODE selects acquisition behavior; it is not an offline preview switch.
def main():
    """Run the configured measurement only when explicitly invoked."""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    width_us = int(params["CH1_WIDTH"] * 1e6)
    fname_base = reserve_output_stem(SAVE_DIR, measurement_name(
        "SweepTrain", params["CH1_STOP"], "from" + voltage_tag(params["CH1_START"]),
        "tw" + time_tag(params["CH1_WIDTH"]), f"mode{TEST_MODE}",
    ))


    with PMUSession(INST, channels=(CH1, CH2)) as session:
        Q = session.query
        print("Running sweep + pulse train...")
        run_dual_channel_sweep_train(Q, CH1, CH2, params, mode=TEST_MODE)
        pulse_iv = None
        if TEST_MODE in (1, 3):
            pulse_iv = (params["ACQUIRE_HIGH"], params["ACQUIRE_LOW"])
        df1, df2 = read_both_channels(Q, CH1, CH2, pulse_iv=pulse_iv)
        power_off_outputs(Q, (CH1, CH2))
        if df1 is None or df2 is None or df1.empty or df2.empty:
            raise ValueError("Sweep test returned empty channel data.")

        dfs = {1: df1, 2: df2}
        analysis_dfs = dfs
        if pulse_iv is not None:
            selected_level = "High" if params["ACQUIRE_HIGH"] else "Low"
            analysis_dfs = {
                1: select_pulse_iv_level(df1, CH1, selected_level),
                2: select_pulse_iv_level(df2, CH2, selected_level),
            }
        merged = add_resistance_columns(
            merge_channels(analysis_dfs),
            eps=params.get("CURRENT_EPS", 1e-12),
            res_min=params.get("RES_MIN", 1.0),
            res_max=params.get("RES_MAX", 1e15),
        )
        save_channels_separate_excel(
            dfs, f"{fname_base}.xlsx", parameters={**params, "TEST_MODE": TEST_MODE},
        )

        with PlotManager(mode="batched", block=True, close_after_show=False) as pm:
            pm.add(
                plot_time_series(
                    merged,
                    width_us=width_us,
                    amp_v=params["CH1_STOP"],
                    resistance_scale=RESISTANCE_SCALE,
                    show=False,
                    return_fig=True,
                )
            )
        print("Sweep + pulse train complete.")


if __name__ == "__main__":
    main()
