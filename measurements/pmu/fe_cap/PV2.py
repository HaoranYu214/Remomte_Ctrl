# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: PV2; edit INST, CH1/CH2, params, SEGARB_OPTIONS and SAVE_DIR.
# Flow: run_test merges settings -> waveform generation -> acquisition/range checks -> polarization analysis -> workbook/plots.
# PREVIEW_ONLY=True previews only; params_override replaces matching defaults in run_test.
# make_pv2_seq_configs defines waveforms; analysis functions process acquired data without hardware access.
# Accepted Irange1/Irange2 values are persisted; voltage, timing and other overrides are not written back.

"""PV2 segARB test with direct sequence definitions."""

from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.pmu.preview import preview_sequence_configs
from keithley4200.output import measurement_name, reserve_output_stem, time_tag, saved_at
from keithley4200.output import set_workbook_author
from keithley4200.pmu.current_range import acquire_with_auto_current_range
from keithley4200.pmu.data_processing import read_both_channels
from keithley4200.pmu.pmu_tests import execute_segARB_test, power_off_outputs
from keithley4200.pmu.session import PMUSession
from keithley4200.measurement_parameters import merge_parameters, remap_channel_options
from keithley4200.parameter_defaults import remember_current_ranges

INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2
params = dict(
    rise_time=2.5e-4,
    delay_time=0.9,
    Vp=4.5,
    offset=0,
    # area_cm2=(10*1e-4)**2*3.14,
    # area_cm2=4e-6,
    area_cm2=(30*1e-4)**2,
    Irange1=1e-05,
    Irange2=1e-06,
)
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": True,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}
PREVIEW_ONLY = True
SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\14-09-2026\04A1_2700_1200_300\L30_3")


# Split returned samples equally into two PV loops, with and without a wait.
def _split_complete_loops(time, voltage, current):
    """Split measured points equally into delayed and non-delayed loops."""
    point_count = len(voltage)
    split_index = point_count // 2
    if split_index < 3 or point_count - split_index < 3:
        raise ValueError("PV2 returned too few points to split into two loops.")

    return (
        (time[:split_index], voltage[:split_index], current[:split_index]),
        (time[split_index:], voltage[split_index:], current[split_index:]),
    )

# Arrange two loops side by side in four columns, padding unequal lengths with NaN.
def _build_loop_sheet(delay_loop, no_delay_loop):
    """Build one four-column loop table, padding unequal point counts with NaN."""
    return pd.DataFrame(
        {
            "Voltage_Delay": pd.Series(delay_loop["Voltage"].to_numpy()),
            "Polarization_Delay": pd.Series(delay_loop["Polarization"].to_numpy()),
            "Voltage_NoDelay": pd.Series(no_delay_loop["Voltage"].to_numpy()),
            "Polarization_NoDelay": pd.Series(no_delay_loop["Polarization"].to_numpy()),
        }
    )


# Reserve one shared file stem for data and plots, registering a run number to avoid overwrites.
def build_fname_base(*, parameters=None, save_dir=None):
    """Reserve one short output stem shared by the workbook and its plots."""
    parameters = params if parameters is None else parameters
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)

    name = measurement_name(
        "PV2", parameters["Vp"], "tr" + time_tag(parameters["rise_time"]),
        "td" + time_tag(parameters["delay_time"]),
    )
    return reserve_output_stem(save_dir, name)


# Build both PV2 channel segment waveforms and acquisition windows; no commands are sent.
def make_pv2_seq_configs(*, channels=None, parameters=None):
    """Build PV2 seq_configs directly in this script."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    rise_time = parameters["rise_time"]
    delay_time = parameters["delay_time"]
    vp = parameters["Vp"]
    offset = parameters["offset"]

    start_voltages = [
        0,
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        vp + offset,
        -vp + offset,
        vp + offset,
        -vp + offset,
    ]
    stop_voltages = [
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        vp + offset,
        -vp + offset,
        vp + offset,
        -vp + offset,
        offset,
    ]
    time_values = [
        rise_time,
        rise_time,
        rise_time,
        rise_time,
        delay_time,
        rise_time,
        2 * rise_time,
        2 * rise_time,
        2 * rise_time,
        rise_time,
    ]
    # Segments 0-3 are the pre/post triangle and segment 4 is the offset hold.
    # Only the main PV2 sweep in segments 5-9 is measured and integrated.
    meas_types = [0, 0, 0, 0, 0, 2, 2, 2, 2, 2]

    ch1_config = (1, start_voltages, stop_voltages, time_values, meas_types)
    ch2_config = (1, [0.0] * len(time_values), [0.0] * len(time_values), time_values, meas_types)
    return {ch1: [ch1_config], ch2: [ch2_config]}


# Build the waveform plot without hardware access; save it when output_path is supplied.
def preview_waveform(output_path=None, *, show=True, title_prefix=None, channels=None, parameters=None):
    """Preview the PV2 waveform without connecting to the PMU."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    return preview_sequence_configs(
        make_pv2_seq_configs(channels=channels, parameters=parameters)[ch1],
        output_path,
        title_prefix="PV2 CH1" if title_prefix is None else title_prefix,
        show=show,
    )


# Build a parameter table from this run's settings and instrument options without acquiring data.
def build_params_table(*, channels=None, inst=None, parameters=None, segarb_options=None):
    """Return the PV2 run parameters as a two-column table."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    inst = INST if inst is None else inst
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)

    rows = [{"name": name, "value": repr(value)} for name, value in parameters.items()]
    rows.extend(
        {"name": name, "value": repr(value)}
        for name, value in segarb_options.items()
    )
    rows.extend([
        {"name": "inst", "value": inst},
        {"name": "channels", "value": repr((ch1, ch2))},
    ])
    rows.append({"name": "saved_at", "value": saved_at()})
    return pd.DataFrame(rows)


# Acquire both channels through an existing query connection; adjust fixed current ranges and retry as needed.
# Update this run's parameters and persist accepted Irange1/Irange2 defaults; a retry reapplies the waveform.
def acquire_with_auto_range(query, *, channels=None, parameters=None, segarb_options=None):
    """Repeat PV2 acquisition until both channel ranges are suitable."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)

    # Execute once at fixed ranges, read both channels and turn outputs off; empty data raises an error.
    def acquire_once(ranges):
        current_ranges = {ch1: ranges["Irange1"], ch2: ranges["Irange2"]}
        execute_segARB_test(
            query,
            [ch1, ch2],
            make_pv2_seq_configs(channels=channels, parameters=parameters),
            current_ranges=current_ranges,
            options=segarb_options,
        )
        df_ch1, df_ch2 = read_both_channels(query, ch1, ch2)
        power_off_outputs(query, (ch1, ch2))
        if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
            raise ValueError("PV2 returned empty channel data during range check.")
        return df_ch1, df_ch2

    result, final_ranges, _assessments = acquire_with_auto_current_range(
        acquire_once,
        {
            "Irange1": parameters["Irange1"],
            "Irange2": parameters["Irange2"],
        },
        {
            "Irange1": lambda data: data[0][f"Current {ch1}"].to_numpy(),
            "Irange2": lambda data: data[1][f"Current {ch2}"].to_numpy(),
        },
        labels={"Irange1": "I1", "Irange2": "I2"},
        test_name="PV2",
    )
    remember_current_ranges(params, final_ranges, __file__)
    parameters.update(final_ranges)
    return result


# Integrate current from zero charge, then shift polarization to make positive/negative remanence symmetric.
def _integrate_loop_from_zero(time, voltage, current, area_cm2, *, parameters=None):
    """Integrate from Q=0, then shift polarization so the two Pr values are symmetric."""
    parameters = params if parameters is None else parameters

    if len(current) < 3:
        raise ValueError("PV2 loop has too few points for integration.")
    if area_cm2 <= 0:
        raise ValueError("area_cm2 must be positive.")

    raw_time = np.asarray(time, dtype=float)
    voltage = np.asarray(voltage, dtype=float)
    current = np.asarray(current, dtype=float)
    loop_duration = 4.0 * parameters["rise_time"]
    # PMU timestamps are quantized to 100 ns, while waveform samples can be much
    # denser (20 ns in the current setup). Use the programmed loop duration so
    # every measured point receives its actual uniform integration interval.
    local_time = np.linspace(0.0, loop_duration, len(current))
    charge = np.zeros(len(current), dtype=float)
    dt = np.diff(local_time)
    charge[1:] = np.cumsum(0.5 * (current[:-1] + current[1:]) * dt)
    polarization = charge / area_cm2 * 1e6

    positive_peak = int(np.argmax(voltage))
    negative_peak = positive_peak + int(np.argmin(voltage[positive_peak:]))
    if negative_peak <= positive_peak:
        raise ValueError("PV2 loop does not contain positive and negative peaks.")

    offset = parameters["offset"]
    positive_pr_index = positive_peak + int(
        np.argmin(np.abs(voltage[positive_peak : negative_peak + 1] - offset))
    )
    negative_pr_index = negative_peak + int(
        np.argmin(np.abs(voltage[negative_peak:] - offset))
    )
    pr_center = 0.5 * (
        polarization[positive_pr_index] + polarization[negative_pr_index]
    )
    polarization_centered = polarization - pr_center

    return pd.DataFrame(
        {
            "Time": local_time,
            "RawTime": raw_time,
            "Voltage": voltage,
            "Current": current,
            "Polarization": polarization_centered,
        }
    )


# Split and independently integrate both PV loops; return per-channel analysis tables without hardware access.
def analyze_pv2(df_ch1, df_ch2, *, channels=None, parameters=None):
    """Split points in half and integrate each PV2 loop independently from zero."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
        raise ValueError("PV2 returned empty channel data.")

    point_count = min(len(df_ch1), len(df_ch2))
    time = df_ch1[f"Timestamp {ch1}"].values[:point_count]
    voltage = (
        df_ch1[f"Voltage {ch1}"].values[:point_count]
        - df_ch2[f"Voltage {ch2}"].values[:point_count]
    )
    current_i1 = df_ch1[f"Current {ch1}"].values[:point_count]
    current_i2 = -df_ch2[f"Current {ch2}"].values[:point_count]
    area_cm2 = parameters.get("area_cm2", 1.0)

    df_total = pd.DataFrame(
        {
            "Time": time,
            "Voltage": voltage,
            "CurrentI1": current_i1,
            "CurrentI2": current_i2,
        }
    )

    i1_parts = _split_complete_loops(time, voltage, current_i1)
    i2_parts = _split_complete_loops(time, voltage, current_i2)
    i1_delay = _integrate_loop_from_zero(*i1_parts[0], area_cm2, parameters=parameters)
    i1_no_delay = _integrate_loop_from_zero(*i1_parts[1], area_cm2, parameters=parameters)
    i2_delay = _integrate_loop_from_zero(*i2_parts[0], area_cm2, parameters=parameters)
    i2_no_delay = _integrate_loop_from_zero(*i2_parts[1], area_cm2, parameters=parameters)

    return {
        "df_total": df_total,
        "i1_delay": i1_delay,
        "i1_no_delay": i1_no_delay,
        "i2_delay": i2_delay,
        "i2_no_delay": i2_no_delay,
        "i1_loops": _build_loop_sheet(i1_delay, i1_no_delay),
        "i2_loops": _build_loop_sheet(i2_delay, i2_no_delay),
    }


# Save both raw channels, PV2 analysis and parameters in one Excel workbook.
def save_pv2_workbook(
    output_path,
    df_ch1,
    df_ch2,
    data,
    *,
    channels=None,
    inst=None,
    parameters=None,
    segarb_options=None,
):
    """Save raw channels, processed PV2 data, and parameters in one workbook."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    inst = INST if inst is None else inst
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        set_workbook_author(writer.book)
        df_ch1.to_excel(writer, sheet_name="Channel_1", index=False)
        df_ch2.to_excel(writer, sheet_name="Channel_2", index=False)
        data["df_total"].to_excel(writer, sheet_name="Total", index=False)
        data["i1_loops"].to_excel(writer, sheet_name="I1_Loops", index=False)
        data["i2_loops"].to_excel(writer, sheet_name="I2_Loops", index=False)
        build_params_table(channels=channels, inst=inst, parameters=parameters, segarb_options=segarb_options).to_excel(writer, sheet_name="Parameters", index=False)
    return output_path


# Merge params_override with local params, then acquire, analyze and save this PV2 run.
# preview_only=True previews only; acquisition returns parameters, accepted ranges and output paths; data is in the workbook.
def run_test(
    params_override=None,
    *,
    channels=None,
    inst=None,
    preview_only=None,
    save_dir=None,
    segarb_options=None,
):
    """Run PV2 and save one workbook plus the loop figure."""
    parameters = merge_parameters(params, params_override)
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    inst = INST if inst is None else inst
    preview_only = PREVIEW_ONLY if preview_only is None else preview_only
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)

    if preview_only:
        return {"preview": preview_waveform(channels=channels, parameters=parameters), "output_path": None, "params": dict(parameters), "accepted_current_ranges": {}}

    fname_base = build_fname_base(parameters=parameters, save_dir=save_dir)
    with PMUSession(inst, channels=(ch1, ch2)) as session:
        Q = session.query
        print("Running PV2...")
        df_ch1, df_ch2 = acquire_with_auto_range(Q, channels=channels, parameters=parameters, segarb_options=segarb_options)
        data = analyze_pv2(df_ch1, df_ch2, channels=channels, parameters=parameters)
        workbook_path = save_pv2_workbook(
            f"{fname_base}.xlsx",
            df_ch1,
            df_ch2,
            data,
            channels=channels,
            inst=inst,
            parameters=parameters,
            segarb_options=segarb_options,
        )

        fig_i2, ax_i2 = plt.subplots(figsize=(6, 5))
        ax_i2.plot(
            data["i2_delay"]["Voltage"],
            data["i2_delay"]["Polarization"],
            "b-",
            label=f"Delay {parameters['delay_time'] * 1e3:g} ms",
        )
        ax_i2.plot(
            data["i2_no_delay"]["Voltage"],
            data["i2_no_delay"]["Polarization"],
            "c-",
            label="No delay",
        )
        ax_i2.set_xlabel("Voltage (V)")
        ax_i2.set_ylabel("Polarization (uC/cm^2)")
        ax_i2.set_title("PV2 Loop from I2")
        ax_i2.legend()
        ax_i2.grid(alpha=0.3)
        fig_i2.tight_layout()
        i2_plot_path = Path(f"{fname_base}_i2.png")
        fig_i2.savefig(i2_plot_path, dpi=300)
        plt.close(fig_i2)



        print(f"Saved PV2 workbook: {workbook_path.resolve()}")
        print(f"Saved PV2 I2 loop: {i2_plot_path.resolve()}")
        print("PV2 complete.")
    result = {"output_path": workbook_path}
    result.update(params=dict(parameters), accepted_current_ranges={key: parameters[key] for key in ("Irange1", "Irange2")})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
