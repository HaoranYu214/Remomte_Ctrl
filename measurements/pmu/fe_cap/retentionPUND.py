# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: retentionPUND; edit INST, CH1/CH2, params, SEGARB_OPTIONS and SAVE_DIR.
# Flow: run_test -> make_retention_plan -> execute stages/wait with outputs off -> save raw data/timing -> analyze.
# PREVIEW_ONLY=True previews only; this test uses fixed ranges without automatic range retries.
# params_override replaces matching defaults; _retention.py executes waits while this file defines waveforms.

"""Output-off retention PUND with explicit split executions and host timing."""

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
    rise_time=2.5e-4,
    delay_time=1.0,
    offset_ramp_time=1e-4,
    Vp=4.5,
    offset=0,
    # area_cm2=1.2567e-5,
    # area_cm2=(10*1e-4)**2*3.14,
    area_cm2=(20*1e-4)**2,
    Irange1=1e-5,
    Irange2=1e-6,
)
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": True,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}

SAVE_DIR = Path("data/pmu/fe_cap/retentionPUND")
PREVIEW_ONLY = True

PULSE_SEGMENTS = {
    "Preset": (2, 3),
    "P": (5, 6),
    "U": (8, 9),
    "N": (11, 12),
    "D": (14, 15),
}


# Allocate returned data slices by acquisition-window duration to identify pulse branches.
def _allocate_segment_slices(total_points, measured_segments, measured_durations):
    """Allocate returned samples to measured segments by measurement duration."""
    total_duration = sum(measured_durations)
    if not measured_segments or total_duration <= 0:
        raise ValueError("PUND has no valid measured segments in the current seq config.")

    exact_counts = [total_points * duration / total_duration for duration in measured_durations]
    counts = [int(np.floor(value)) for value in exact_counts]
    remainder = total_points - sum(counts)
    fractions = [value - count for value, count in zip(exact_counts, counts)]
    for pick in np.argsort(fractions)[::-1][:remainder]:
        counts[int(pick)] += 1

    segment_slices = {}
    cursor = 0
    for segment_index, point_count in zip(measured_segments, counts):
        segment_slices[segment_index] = slice(cursor, cursor + point_count)
        cursor += point_count
    return segment_slices, counts

# Integrate corresponding current differences separately, without integrating across waits; normalize by area.
def _integrate_branches(branches, area_cm2):
    """Integrate matched differential-current branches without crossing delays."""
    if area_cm2 <= 0:
        raise ValueError("area_cm2 must be positive for polarization calculation.")

    frames = []
    elapsed = 0.0
    charge = 0.0
    charge_i1 = 0.0

    for branch_name, voltage, current, current_i1, duration in branches:
        point_count = len(current)
        if point_count == 0:
            continue

        sample_dt = duration / (point_count - 1) if point_count > 1 else 0.0
        local_time = elapsed + np.arange(point_count, dtype=float) * sample_dt
        charge_values = np.empty(point_count, dtype=float)
        charge_i1_values = np.empty(point_count, dtype=float)
        charge_values[0] = charge
        charge_i1_values[0] = charge_i1

        for index in range(1, point_count):
            charge_values[index] = (
                charge_values[index - 1]
                + 0.5 * (current[index - 1] + current[index]) * sample_dt
            )
            charge_i1_values[index] = (
                charge_i1_values[index - 1]
                + 0.5 * (current_i1[index - 1] + current_i1[index]) * sample_dt
            )

        frame = pd.DataFrame(
            {
                "Time": local_time,
                "Voltage": voltage,
                "DiffCurrent": current,
                "DiffCurrentI1": current_i1,
                "Charge": charge_values,
                "ChargeI1": charge_i1_values,
                "Polarization": charge_values / area_cm2 * 1e6,
                "PolarizationI1": charge_i1_values / area_cm2 * 1e6,
                "Branch": branch_name,
            }
        )
        frames.append(frame)
        charge = charge_values[-1]
        charge_i1 = charge_i1_values[-1]
        elapsed += duration

    if not frames:
        raise ValueError("PUND triangular branch integration received no samples.")
    return pd.concat(frames, ignore_index=True)

# Join positive and negative PUND half-loops and center the complete polarization loop.
def _connect_and_center_pairs(frames, area_cm2):
    """Connect positive/negative PUND halves and center the complete loop."""
    connected = []
    elapsed = 0.0
    charge_offset = 0.0
    charge_i1_offset = 0.0

    for frame in frames:
        frame = frame.copy()
        frame["Time"] += elapsed
        frame["Charge"] += charge_offset
        frame["ChargeI1"] += charge_i1_offset
        connected.append(frame)

        elapsed = float(frame["Time"].iloc[-1])
        charge_offset = float(frame["Charge"].iloc[-1])
        charge_i1_offset = float(frame["ChargeI1"].iloc[-1])

    loop = pd.concat(connected, ignore_index=True)
    negative_start = loop.index[loop["Segment"] == "N-D"][0]
    charge_center = 0.5 * (loop["Charge"].iloc[0] + loop["Charge"].iloc[negative_start])
    charge_i1_center = 0.5 * (
        loop["ChargeI1"].iloc[0] + loop["ChargeI1"].iloc[negative_start]
    )
    loop["Polarization"] = (loop["Charge"] - charge_center) / area_cm2 * 1e6
    loop["PolarizationI1"] = (loop["ChargeI1"] - charge_i1_center) / area_cm2 * 1e6
    return loop


# Reserve one shared file stem for data and plots, registering a run number to avoid overwrites.
def build_fname_base(*, parameters=None, save_dir=None):
    """Reserve one short output stem shared by the workbook and its plots."""
    parameters = params if parameters is None else parameters
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)

    name = measurement_name(
        "retentionPUND", parameters["Vp"], "tr" + time_tag(parameters["rise_time"]),
        "td" + time_tag(parameters["delay_time"]),
    )
    return reserve_output_stem(save_dir, name)


# Build both PUND channel segment waveforms and acquisition windows; no commands are sent.
def make_pund_seq_configs(*, channels=None, parameters=None):
    """Build five triangular PUND pulses separated by unmeasured delays."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    rise_time = parameters["rise_time"]
    delay_time = parameters["delay_time"]
    offset_ramp_time = parameters["offset_ramp_time"]
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
        offset,
        offset,
        vp + offset,
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        -vp + offset,
        offset,
    ]
    stop_voltages = [
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        vp + offset,
        offset,
        offset,
        vp + offset,
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
    ]
    time_values = [
        offset_ramp_time,
        delay_time,
        rise_time,
        rise_time,
        delay_time,
        rise_time,
        rise_time,
        delay_time,
        rise_time,
        rise_time,
        delay_time,
        rise_time,
        rise_time,
        delay_time,
        rise_time,
        rise_time,
        delay_time,
    ]
    # Only the two slopes of each triangle contribute samples to PUND.
    measured_segments = {
        segment for pulse_segments in PULSE_SEGMENTS.values() for segment in pulse_segments
    }
    meas_types = [2 if index in measured_segments else 0 for index in range(len(time_values))]

    ch1_config = (1, start_voltages, stop_voltages, time_values, meas_types)
    ch2_config = (1, [0.0] * len(time_values), [0.0] * len(time_values), time_values, meas_types)
    return {ch1: [ch1_config], ch2: [ch2_config]}


# Build separate Preset/P/U/N/D stages with the same host-side wait between pulses.
def make_retention_plan(*, channels=None, parameters=None):
    """Execute Preset/P/U/N/D separately, with the same inter-pulse host delay."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    configs = make_pund_seq_configs(channels=channels, parameters=parameters)
    return [
        dict(label=label, delay_before_s=0.0 if label == "Preset" else parameters["delay_time"],
             configs={ch: [(1, *(list(values[first:last+1]) for values in cfgs[0][1:]))]
                      for ch, cfgs in configs.items()})
        for label, (first, last) in PULSE_SEGMENTS.items()
    ]


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
                       title_prefix=title_prefix or "retentionPUND")
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
    """Return the PUND run parameters as a two-column table."""
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


# Subtract matching P/U and N/D branches and integrate them into analysis tables; no hardware access.
def analyze_pund_triangle_diff(df_ch1, df_ch2, *, channels=None, parameters=None):
    """Subtract and integrate corresponding branches of triangular PUND pulses."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
        raise ValueError("PUND returned empty channel data.")

    ch1_config = make_pund_seq_configs(channels=channels, parameters=parameters)[ch1][0]
    time_values = ch1_config[3]
    meas_types = ch1_config[4]
    meas_start = ch1_config[5] if len(ch1_config) > 5 else [0.0] * len(time_values)
    meas_stop = ch1_config[6] if len(ch1_config) > 6 else list(time_values)

    v_total = df_ch1[f"Voltage {ch1}"].values - df_ch2[f"Voltage {ch2}"].values
    i1_total = df_ch1[f"Current {ch1}"].values
    i_total = -df_ch2[f"Current {ch2}"].values
    t_total = df_ch1[f"Timestamp {ch1}"].values
    df_total = pd.DataFrame(
        {
            "Time": t_total,
            "Voltage": v_total,
            "CurrentI1": i1_total,
            "CurrentI2": i_total,
        }
    )

    measured_segments = [index for index, mode in enumerate(meas_types) if mode != 0]
    measured_durations = [max(0.0, meas_stop[index] - meas_start[index]) for index in measured_segments]
    if not df_ch1["Stage"].equals(df_ch2["Stage"]):
        raise ValueError("PUND channel stage labels differ.")
    segment_slices, count_by_segment = {}, {}
    for label, segments in PULSE_SEGMENTS.items():
        indices = np.flatnonzero(df_ch1["Stage"].to_numpy() == label)
        if len(indices) < 4 or not np.all(np.diff(indices) == 1):
            raise ValueError(f"Missing or insufficient contiguous data for {label}.")
        split = len(indices) // 2
        for segment, lo, hi in ((segments[0], 0, split), (segments[1], split, len(indices))):
            segment_slices[segment] = slice(int(indices[0])+lo, int(indices[0])+hi)
            count_by_segment[segment] = hi-lo
    segment_counts = [count_by_segment[i] for i in measured_segments]

    pulses = {}
    for label, segments in PULSE_SEGMENTS.items():
        branches = []
        for segment_index in segments:
            segment_slice = segment_slices.get(segment_index)
            if segment_slice is None:
                continue
            branches.append(
                {
                    "voltage": v_total[segment_slice],
                    "current_i1": i1_total[segment_slice],
                    "current": i_total[segment_slice],
                    "duration": measured_durations[measured_segments.index(segment_index)],
                }
            )
        if len(branches) == 2:
            pulses[label] = branches

    pair_defs = [("P", "U", "P-U"), ("N", "D", "N-D")]
    frames = []
    for first, second, label in pair_defs:
        if first not in pulses or second not in pulses:
            raise ValueError(f"Missing measured triangular pulse data for {label}.")

        branches = []
        for branch_index, branch_name in enumerate(("outbound", "return")):
            first_branch = pulses[first][branch_index]
            second_branch = pulses[second][branch_index]
            point_count = min(len(first_branch["current"]), len(second_branch["current"]))
            if point_count < 2:
                raise ValueError("Too few samples in a retention PUND branch.")
            grid = np.linspace(0.0, 1.0, point_count)
            # Interpolate selected branch data onto a shared normalized grid for pointwise subtraction.
            def resample(branch, key):
                values = branch[key]
                return np.interp(grid, np.linspace(0.0, 1.0, len(values)), values)
            branches.append(
                (
                    branch_name,
                    resample(first_branch, "voltage"),
                    resample(first_branch, "current") - resample(second_branch, "current"),
                    resample(first_branch, "current_i1") - resample(second_branch, "current_i1"),
                    min(first_branch["duration"], second_branch["duration"]),
                )
            )
        pair_frame = _integrate_branches(branches, parameters.get("area_cm2", 1.0))
        pair_frame["Segment"] = label
        frames.append(pair_frame)

    if not frames:
        raise ValueError("PUND edge differential analysis failed.")

    pund_diff = _connect_and_center_pairs(frames, parameters.get("area_cm2", 1.0))
    return {
        "df_total": df_total,
        "pund_diff": pund_diff,
        "meta": {
            "measured_segments": measured_segments,
            "segment_point_counts": {
                segment: segment_counts[idx] for idx, segment in enumerate(measured_segments)
            },
            "measured_pulses": list(pulses.keys()),
            "pairs": pair_defs,
        },
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
    data = analyze_pund_triangle_diff(df_ch1, df_ch2, channels=channels, parameters=parameters)
    with pd.ExcelWriter(raw_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        writer.book.properties.creator = "ssme / Haoran Yu"
        for label, frame in data.items():
            if isinstance(frame, pd.DataFrame):
                frame.to_excel(writer, sheet_name=label[:31], index=False)
    fig, axis = plt.subplots(figsize=(6, 4))
    for label in ("P-U", "N-D"):
        frame = data["pund_diff"].query("Segment == @label")
        axis.plot(frame["Voltage"], frame["Polarization"], label=label)
    axis.set_title("PUND from I2")
    axis.set_xlabel("Voltage (V)")
    axis.set_ylabel("Polarization (uC/cm^2)")
    axis.legend()
    axis.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{fname_base}_loops.png", dpi=200)
    plt.close(fig)
    print(f"Saved retentionPUND: {raw_path}")
    data["output_path"] = Path(raw_path)
    result = data
    result.update(params=dict(parameters), accepted_current_ranges={})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
