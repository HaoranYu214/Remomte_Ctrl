# -*- coding: utf-8 -*-
"""Triangular-pulse PUND segARB test with branch-aware integration."""

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

from keithley4200.tools.waveform_preview import preview_sequence_configs
from keithley4200.output import measurement_name, reserve_output_stem, time_tag, saved_at
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
    delay_time=1e-3,
    offset_ramp_time=1e-4,
    Vp=4.5,
    offset=0,
    # area_cm2=1.2567e-5,
    # area_cm2=(10*1e-4)**2*3.14,
    area_cm2=(20*1e-4)**2,
    Irange1=1e-05,
    Irange2=1e-06,
)
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": True,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}

SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\10-09-2026\04A1_2700_1200_300\L20_2\PUND_Break")
PREVIEW_ONLY = False

PULSE_SEGMENTS = {
    "Preset": (2, 3),
    "P": (5, 6),
    "U": (8, 9),
    "N": (11, 12),
    "D": (14, 15),
}


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


def build_fname_base(*, parameters=None, save_dir=None):
    """Reserve one short output stem shared by the workbook and its plots."""
    parameters = params if parameters is None else parameters
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)

    name = measurement_name(
        "PUNDtri", parameters["Vp"], "tr" + time_tag(parameters["rise_time"]),
        "td" + time_tag(parameters["delay_time"]),
    )
    return reserve_output_stem(save_dir, name)


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


def preview_waveform(output_path=None, *, show=True, title_prefix=None, channels=None, parameters=None):
    """Preview the triangular PUND waveform without connecting to the PMU."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    return preview_sequence_configs(
        make_pund_seq_configs(channels=channels, parameters=parameters)[ch1],
        output_path,
        title_prefix=(
            "Triangular PUND CH1" if title_prefix is None else title_prefix
        ),
        show=show,
    )


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
    rows.extend([
        {"name": "inst", "value": inst},
        {"name": "channels", "value": repr((ch1, ch2))},
    ])
    rows.append({"name": "saved_at", "value": saved_at()})
    return pd.DataFrame(rows)


def save_pund_workbook(
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
    """Save raw data, analysis data, and parameters into one Excel workbook."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    inst = INST if inst is None else inst
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_ch1.to_excel(writer, sheet_name="Channel_1", index=False)
        df_ch2.to_excel(writer, sheet_name="Channel_2", index=False)
        data["df_total"].to_excel(writer, sheet_name="Total", index=False)
        data["pund_diff"].to_excel(writer, sheet_name="PUND_Diff", index=False)
        build_params_table(channels=channels, inst=inst, parameters=parameters, segarb_options=segarb_options).to_excel(writer, sheet_name="Parameters", index=False)
    return Path(output_path)


def acquire_with_auto_range(query, *, channels=None, parameters=None, segarb_options=None):
    """Acquire triangular PUND data using the shared automatic range helper."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)

    def acquire_once(ranges):
        current_ranges = {ch1: ranges["Irange1"], ch2: ranges["Irange2"]}
        execute_segARB_test(
            query,
            [ch1, ch2],
            make_pund_seq_configs(channels=channels, parameters=parameters),
            current_ranges=current_ranges,
            options=segarb_options,
        )
        df_ch1, df_ch2 = read_both_channels(query, ch1, ch2)
        power_off_outputs(query, (ch1, ch2))
        if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
            raise ValueError(
                "Triangular PUND returned empty channel data during range check."
            )
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
        test_name="Triangular PUND",
    )
    remember_current_ranges(params, final_ranges, __file__)
    parameters.update(final_ranges)
    return result


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
    segment_slices, segment_counts = _allocate_segment_slices(
        len(i_total),
        measured_segments,
        measured_durations,
    )

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
            branches.append(
                (
                    branch_name,
                    first_branch["voltage"][:point_count],
                    first_branch["current"][:point_count] - second_branch["current"][:point_count],
                    first_branch["current_i1"][:point_count] - second_branch["current_i1"][:point_count],
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


def run_test(
    params_override=None,
    *,
    channels=None,
    inst=None,
    preview_only=None,
    save_dir=None,
    segarb_options=None,
):
    """Run the PUND measurement and save raw/analysis files."""
    parameters = merge_parameters(params, params_override)
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    inst = INST if inst is None else inst
    preview_only = PREVIEW_ONLY if preview_only is None else preview_only
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)

    if preview_only:
        return {"preview": preview_waveform(channels=channels, parameters=parameters), "output_path": None, "params": dict(parameters), "accepted_current_ranges": {}}

    with PMUSession(inst, channels=(ch1, ch2)) as session:
        Q = session.query
        print("Running PUND...")
        df_ch1, df_ch2 = acquire_with_auto_range(Q, channels=channels, parameters=parameters, segarb_options=segarb_options)
        fname_base = build_fname_base(parameters=parameters, save_dir=save_dir)

        data = analyze_pund_triangle_diff(df_ch1, df_ch2, channels=channels, parameters=parameters)
        workbook_path = save_pund_workbook(f"{fname_base}.xlsx", df_ch1, df_ch2, data, channels=channels, inst=inst, parameters=parameters, segarb_options=segarb_options)

        fig_i2, ax_i2 = plt.subplots(figsize=(7, 5))
        for seg in ["P-U", "N-D"]:
            sub = data["pund_diff"][data["pund_diff"]["Segment"] == seg]
            ax_i2.plot(sub["Voltage"], sub["Polarization"], ".", label=seg, markersize=4)
        ax_i2.set_xlabel("Voltage (V)")
        ax_i2.set_ylabel("Polarization (uC/cm^2)")
        ax_i2.set_title("PUND Polarization from I2 Difference")
        ax_i2.legend()
        ax_i2.grid(alpha=0.3)
        fig_i2.tight_layout()
        fig_i2.savefig(f"{fname_base}_loop_i2diff.png", dpi=300)
        plt.close(fig_i2)



        fig_iv, ax_iv = plt.subplots(figsize=(7, 5))
        for seg in ["P-U", "N-D"]:
            sub = data["pund_diff"][data["pund_diff"]["Segment"] == seg]
            ax_iv.plot(sub["Voltage"], sub["DiffCurrent"], ".", label=f"{seg} I2", markersize=4)
            ax_iv.plot(sub["Voltage"], sub["DiffCurrentI1"], ".", label=f"{seg} I1", markersize=3, alpha=0.7)
        ax_iv.set_xlabel("Voltage (V)")
        ax_iv.set_ylabel("Differential Current (A)")
        ax_iv.set_title("PUND Differential I-V")
        ax_iv.legend()
        ax_iv.grid(alpha=0.3)
        fig_iv.tight_layout()
        fig_iv.savefig(f"{fname_base}_diff_iv.png", dpi=300)
        plt.close(fig_iv)
        print("PUND complete.")
    result = {"output_path": workbook_path}
    result.update(params=dict(parameters), accepted_current_ranges={key: parameters[key] for key in ("Irange1", "Irange2")})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
