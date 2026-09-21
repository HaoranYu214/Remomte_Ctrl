# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: retentionPV; edit INST, CH1/CH2, params, SEGARB_OPTIONS and SAVE_DIR.
# Flow: run_test -> make_retention_plan -> execute stages/wait with outputs off -> save raw data/timing -> analyze.
# PREVIEW_ONLY=True previews only; this test uses fixed ranges without automatic range retries.
# params_override replaces matching defaults; _retention.py executes waits while this file defines waveforms.

"""Output-off retention PV with explicit split executions and host timing."""

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

from keithley4200.output import measurement_name, reserve_output_stem, time_tag, saved_at
from keithley4200.pmu.session import PMUSession
from keithley4200.measurement_parameters import merge_parameters, remap_channel_options
from measurements.pmu.fe_cap._retention import execute_plan, validate_plan, save_raw, preview_plan

INST = "TCPIP0::192.0.2.1::1225::SOCKET"
CH1, CH2 = 1, 2
params = dict(
    rise_time=2.5e-5,
    delay_time=1.0,
    Vp=4.5,
    offset=0,
    area_cm2=(10*1e-4)**2*3.14,
    # area_cm2=4e-6,
    # area_cm2=(20*1e-4)**2,
    Irange1=1e-4,
    Irange2=1e-4,
)
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": False,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}
PREVIEW_ONLY = True
SAVE_DIR = Path("data/pmu/fe_cap/retentionPV")


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
        "retentionPV", parameters["Vp"], "tr" + time_tag(parameters["rise_time"]),
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


# Build staged preset -> output-off wait -> continuous acquisition of two PV loops.
def make_retention_plan(*, channels=None, parameters=None):
    """Preset, output-off wait, then both PV loops in one execution."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    configs = make_pv2_seq_configs(channels=channels, parameters=parameters)
    stages = []
    for label, first, last, delay in (("Preset", 0, 4, 0.0), ("PV", 5, 10, parameters["delay_time"])):
        sliced = {ch: [(1, *(list(values[first:last]) for values in cfgs[0][1:]))]
                  for ch, cfgs in configs.items()}
        stages.append(dict(label=label, configs=sliced, delay_before_s=delay))
    return stages


# Preview execution boundaries, acquisition windows and output-off waits; optionally compress long waits.
def preview_waveform(
    output_path=None,
    *,
    show=True,
    compress_delay=True,
    title_prefix=None,
    channels=None,
    parameters=None,
):
    """Show execution boundaries, acquisition windows and output-off waits."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    plan = make_retention_plan(channels=channels, parameters=parameters)
    validate_plan(plan, (ch1, ch2), parameters)
    fig = preview_plan(plan, ch1, show=False, compress_delay=compress_delay,
                       title_prefix=title_prefix or "retentionPV")
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        return output_path
    if show:
        plt.show()
    return fig


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
    rows.extend({"name": k, "value": repr(v)} for k, v in {
        "wait_state": "output_off", "execution_mode": "software_split",
        "timing_basis": "host_estimate", "auto_range": False,
    }.items())
    rows.extend([
        {"name": "inst", "value": inst},
        {"name": "channels", "value": repr((ch1, ch2))},
    ])
    rows.append({"name": "saved_at", "value": saved_at()})
    return pd.DataFrame(rows)


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
    # Exported timestamp precision can be coarser than sample spacing.
    # Preserve the existing PV2 integration based on programmed loop duration.
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


# Merge params_override and run the retention test at fixed ranges, disabling outputs between stages.
# preview_only=True previews only; acquisition saves raw data/timing before analysis and returns a result dictionary.
# Do not retry at another range: extra pulses would alter retention history.
def run_test(
    params_override=None,
    *,
    channels=None,
    inst=None,
    preview_only=None,
    save_dir=None,
    segarb_options=None,
):
    """Run the complete retention protocol once with fixed current ranges."""
    parameters = merge_parameters(params, params_override)
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    inst = INST if inst is None else inst
    preview_only = PREVIEW_ONLY if preview_only is None else preview_only
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)

    if preview_only:
        return {"preview": preview_waveform(channels=channels, parameters=parameters), "output_path": None, "params": dict(parameters), "accepted_current_ranges": {}}

    plan = make_retention_plan(channels=channels, parameters=parameters)
    validate_plan(plan, (ch1, ch2), parameters)
    fname_base = build_fname_base(parameters=parameters, save_dir=save_dir)
    raw_path = f"{fname_base}.xlsx"
    frames, timing = {ch1: [], ch2: []}, []
    try:
        with PMUSession(inst, channels=(ch1, ch2)) as session:
            df_ch1, df_ch2 = execute_plan(session.query, plan, (ch1, ch2), parameters,
                                          segarb_options, frames, timing)
    finally:
        save_raw(raw_path, frames, timing, build_params_table(channels=channels, inst=inst, parameters=parameters, segarb_options=segarb_options))
    data = analyze_pv2(df_ch1, df_ch2, channels=channels, parameters=parameters)
    with pd.ExcelWriter(raw_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        writer.book.properties.creator = "ssme / Haoran Yu"
        for label, frame in data.items():
            if isinstance(frame, pd.DataFrame):
                frame.to_excel(writer, sheet_name=label[:31], index=False)
    fig, axis = plt.subplots(figsize=(6, 4))
    for suffix in ("delay", "no_delay"):
        frame = data["i2_" + suffix]
        axis.plot(frame["Voltage"], frame["Polarization"], label=suffix)
    axis.set_title("I2")
    axis.set_xlabel("Voltage (V)")
    axis.set_ylabel("Polarization (uC/cm^2)")
    axis.legend()
    axis.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{fname_base}_loops.png", dpi=200)
    plt.close(fig)
    print(f"Saved retentionPV: {raw_path}")
    data["output_path"] = Path(raw_path)
    result = data
    result.update(params=dict(parameters), accepted_current_ranges={})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
