# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: ftj_RV2; edit INST, CH1/CH2, params, CURRENT_RANGES and SAVE_DIR.
# Flow: run_test merges parameters -> build_waveform -> PMU execution/readout -> process and save results.
# PREVIEW_ONLY=True previews only; explicit run_test arguments override file defaults.
# Read build_waveform for waveform definitions; routine parameter changes do not require editing helpers below.

"""FTJ RV script with one prepost sequence and one full write+read scan sequence."""
"""从+VP开始测试, 到-Vp然后回到VP"""

from pathlib import Path
import sys

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
from keithley4200.output import measurement_name, reserve_output_stem, time_tag, saved_at, voltage_tag
from keithley4200.pmu.data_processing import read_both_channels
from keithley4200.pmu.pmu_tests import (
    MAX_SEGMENTS_PER_SEQUENCE,
    execute_segARB_test,
    power_off_outputs,
    validate_segment_arb_configs,
)
from keithley4200.pmu.session import PMUSession
from keithley4200.measurement_parameters import merge_parameters, remap_channel_options

INST = "TCPIP0::192.0.2.1::1225::SOCKET"
CH1, CH2 = 1, 2
SAVE_DIR = Path("data/pmu/ftj/ftj_RV2")
FILE_STEM = "RV2"

CURRENT_RANGES = {CH1: 1e-4, CH2: 1e-4}
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": False,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}

# PREVIEW_ONLY = True
PREVIEW_ONLY = False

params = {
    # Voltage held before/after every pulse. This is deliberately independent
    # from offset_v, which only shifts the commanded write-voltage window.
    "base_v": 0.0,
    "offset_v": -2,
    "vp": 6,
    "write_level_step": 0.2,
    "read_v": -1,
    "scan_cycles": 1,
    "prepost_dwell": 5e-5,
    "write_dwell": 5e-5,
    "read_dwell": 5e-5,
    "prepost_rise": 1e-5,
    "prepost_fall": 1e-5,
    "prepost_idle": 1e-3,
    "write_rise": 1e-5,
    "write_fall": 1e-5,
    "write_idle": 1e-3,
    "read_rise": 1e-5,
    "read_fall": 1e-5,
    "read_idle": 1e-3,
}


# Generate voltage levels from start to stop, including both endpoints.
def _levels_between(start_level, stop_level, step):
    """Return inclusive levels from start_level to stop_level."""
    if start_level == stop_level:
        return [round(start_level, 10)]

    step = abs(step)
    direction = 1 if stop_level > start_level else -1
    step *= direction

    levels = []
    current = start_level
    while (direction > 0 and current < stop_level) or (direction < 0 and current > stop_level):
        levels.append(round(current, 10))
        current += step
    levels.append(round(stop_level, 10))
    return levels

# Build the relative path +Vp -> -Vp -> +Vp and repeat it for cycles.
def voltage_sweep_path(vp, step, cycles=1):
    """Return relative levels: +Vp -> -Vp -> +Vp, repeated for the requested cycles."""
    if vp == 0:
        return []

    path = []
    for cycle_index in range(cycles):
        down_leg = _levels_between(vp, -vp, step)
        up_leg = _levels_between(-vp, vp, step)
        if cycle_index == 0:
            path.extend(down_leg)
        else:
            path.extend(down_leg[1:])
        path.extend(up_leg[1:])
    return path

# Append a waveform block to time/voltage endpoints for reconstructing commanded-waveform plots.
def _extend_trace_points(points, start_v, stop_v, time_values, start_time, *, add_gap=True):
    """Append t-V endpoint pairs for one waveform block."""
    cursor = start_time
    for segment_start_v, segment_stop_v, segment_time in zip(start_v, stop_v, time_values):
        next_cursor = cursor + segment_time
        points.append((cursor, segment_start_v))
        points.append((next_cursor, segment_stop_v))
        cursor = next_cursor
    if add_gap:
        points.append((None, None))
    return cursor


# Build this run's waveform configurations, execution order and metadata from parameters and channels.
# Return a dictionary shared by acquisition and preview; waveform construction does not connect to hardware.
def build_waveform(*, parameters=None, channels=None):
    """Build pulse arrays and execution metadata from this run's parameters."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    base_v = float(parameters["base_v"])
    offset_v = float(parameters["offset_v"])
    vp = float(parameters["vp"])
    write_level_step = float(parameters["write_level_step"])
    read = float(parameters["read_v"])
    read_level = read - offset_v
    prepost_level = -vp
    scan_cycles = int(parameters["scan_cycles"])
    prepost_dwell = float(parameters["prepost_dwell"])
    write_dwell = float(parameters["write_dwell"])
    read_dwell = float(parameters["read_dwell"])
    prepost_rise = float(parameters["prepost_rise"])
    prepost_fall = float(parameters["prepost_fall"])
    prepost_idle_2 = float(parameters["prepost_idle"])
    write_rise = float(parameters["write_rise"])
    write_fall = float(parameters["write_fall"])
    write_idle_2 = float(parameters["write_idle"])
    read_rise = float(parameters["read_rise"])
    read_fall = float(parameters["read_fall"])
    read_idle_2 = float(parameters["read_idle"])
    time_values_prepost = [prepost_rise, prepost_dwell, prepost_fall, prepost_idle_2]
    time_values_write = [write_rise, write_dwell, write_fall, write_idle_2]
    time_values_read = [read_rise, read_dwell, read_fall, read_idle_2]
    meas_start_read = [0.0, read_dwell * 0.5, 0.0, 0.0]
    meas_stop_read = [0.0, read_dwell * 0.9, 0.0, 0.0]
    scan_levels = voltage_sweep_path(vp, write_level_step, scan_cycles)
    scan_voltages = [offset_v + level for level in scan_levels]
    max_segments_per_seq = MAX_SEGMENTS_PER_SEQUENCE
    segments_per_scan_point = 8
    scan_level_chunks = chunk_scan_voltages(scan_levels, max_segments_per_seq=max_segments_per_seq, segments_per_scan_point=segments_per_scan_point)
    prepost_seq_id = 1
    meas_start_prepost = [0.0] * len(time_values_prepost)
    meas_stop_prepost = [0.0] * len(time_values_prepost)
    meas_types_prepost = [0, 0, 0, 0]
    ch1_prepost_config, ch2_prepost_config = make_prepost_sequence(base_v=base_v, meas_start_prepost=meas_start_prepost, meas_stop_prepost=meas_stop_prepost, meas_types_prepost=meas_types_prepost, offset_v=offset_v, prepost_level=prepost_level, prepost_seq_id=prepost_seq_id, time_values_prepost=time_values_prepost)
    first_scan_seq_id = 2
    scan_seq_ids = [first_scan_seq_id + index for index in range(len(scan_level_chunks))]
    meas_start_write = [0.0, write_dwell* 0, 0.0, 0.0]
    meas_stop_write = [0.0, 0.0, 0.0, 0.0]
    meas_types_read = [0, 1, 0, 0]
    meas_types_write = [0, 0, 0, 0]
    scan_config_pairs = [
        make_scan_sequence(seq_id, chunk, base_v=base_v, max_segments_per_seq=max_segments_per_seq, meas_start_read=meas_start_read, meas_start_write=meas_start_write, meas_stop_read=meas_stop_read, meas_stop_write=meas_stop_write, meas_types_read=meas_types_read, meas_types_write=meas_types_write, offset_v=offset_v, read_level=read_level, time_values_read=time_values_read, time_values_write=time_values_write)
        for seq_id, chunk in zip(scan_seq_ids, scan_level_chunks)
    ]
    ch1_scan_configs = [pair[0] for pair in scan_config_pairs]
    ch2_scan_configs = [pair[1] for pair in scan_config_pairs]
    seq_configs = {
        ch1: [ch1_prepost_config] + ch1_scan_configs,
        ch2: [ch2_prepost_config] + ch2_scan_configs,
    }
    seq_plan = [(prepost_seq_id, 1)] + [(seq_id, 1) for seq_id in scan_seq_ids]
    seq_list = {ch1: list(seq_plan), ch2: list(seq_plan)}
    validate_segment_arb_configs(seq_configs)
    return {
        'base_v': base_v,
        'offset_v': offset_v,
        'read_level': read_level,
        'scan_levels': scan_levels,
        'scan_level_chunks': scan_level_chunks,
        'scan_voltages': scan_voltages,
        'seq_list': seq_list,
        'ch1_prepost_config': ch1_prepost_config,
        'ch1_scan_configs': ch1_scan_configs,
        'seq_configs': seq_configs,
        'time_values_read': time_values_read,
        'time_values_write': time_values_write,
    }


# Return pulse segments from baseline to target voltage and back, for sequence assembly.
def build_pulse_block(level, time_values, *, base_v, offset_v):
    """Return a base -> (write offset + relative level) -> base pulse."""
    target_v = offset_v + level
    start_v = [base_v, target_v, target_v, base_v]
    stop_v = [target_v, target_v, base_v, base_v]
    return start_v, stop_v, list(time_values)


# Build a two-channel sequence for one preset pulse.
def make_prepost_sequence(
    *,
    base_v,
    meas_start_prepost,
    meas_stop_prepost,
    meas_types_prepost,
    offset_v,
    prepost_level,
    prepost_seq_id,
    time_values_prepost,
):
    """Build the prepost sequence: one pulse only."""
    start_v, stop_v, time_values = build_pulse_block(prepost_level, time_values_prepost, base_v=base_v, offset_v=offset_v)
    ch1_config = (prepost_seq_id, start_v, stop_v, time_values, meas_types_prepost, meas_start_prepost, meas_stop_prepost)
    ch2_config = (
        prepost_seq_id,
        [0.0] * len(time_values),
        [0.0] * len(time_values),
        time_values,
        meas_types_prepost,
        meas_start_prepost,
        meas_stop_prepost,
    )
    return ch1_config, ch2_config


# Convert scan voltages into two-channel pointwise program/low-voltage-read sequences.
def make_scan_sequence(
    seq_id,
    voltages,
    *,
    base_v,
    max_segments_per_seq,
    meas_start_read,
    meas_start_write,
    meas_stop_read,
    meas_stop_write,
    meas_types_read,
    meas_types_write,
    offset_v,
    read_level,
    time_values_read,
    time_values_write,
):
    """Build one scan sequence: write pulse, then small read pulse, for a chunk of scan points."""
    ch1_start_v = []
    ch1_stop_v = []
    ch2_start_v = []
    ch2_stop_v = []
    time_values = []
    meas_types = []
    meas_start = []
    meas_stop = []

    for voltage in voltages:
        write_start_v, write_stop_v, write_times = build_pulse_block(voltage, time_values_write, base_v=base_v, offset_v=offset_v)
        ch1_start_v.extend(write_start_v)
        ch1_stop_v.extend(write_stop_v)
        ch2_start_v.extend([0.0] * len(write_times))
        ch2_stop_v.extend([0.0] * len(write_times))
        time_values.extend(write_times)
        meas_types.extend(meas_types_write)
        meas_start.extend(meas_start_write)
        meas_stop.extend(meas_stop_write)

        read_start_v, read_stop_v, read_times = build_pulse_block(read_level, time_values_read, base_v=base_v, offset_v=offset_v)
        ch1_start_v.extend(read_start_v)
        ch1_stop_v.extend(read_stop_v)
        ch2_start_v.extend([0.0] * len(read_times))
        ch2_stop_v.extend([0.0] * len(read_times))
        time_values.extend(read_times)
        meas_types.extend(meas_types_read)
        meas_start.extend(meas_start_read)
        meas_stop.extend(meas_stop_read)

    if len(time_values) > max_segments_per_seq:
        raise ValueError(
            f"RV scan sequence has {len(time_values)} segments, "
            f"above MAX_SEGMENTS_PER_SEQ={max_segments_per_seq}."
        )

    ch1_config = (seq_id, ch1_start_v, ch1_stop_v, time_values, meas_types, meas_start, meas_stop)
    ch2_config = (seq_id, ch2_start_v, ch2_stop_v, time_values, meas_types, meas_start, meas_stop)
    return ch1_config, ch2_config


# Split the voltage list by segments per point so each sequence stays within the segment limit.
def chunk_scan_voltages(voltages, *, max_segments_per_seq, segments_per_scan_point):
    """Split scan voltages into multiple sequences to stay below the PMU segment limit."""
    max_points_per_seq = max(1, max_segments_per_seq // segments_per_scan_point)
    return [
        voltages[index : index + max_points_per_seq]
        for index in range(0, len(voltages), max_points_per_seq)
    ]


# Build the waveform plot without hardware access; save it when output_path is supplied.
def preview_waveform(
    output_path=None,
    *,
    show=True,
    title_prefix='FTJ RV CH1',
    channels=None,
    parameters=None,
    waveform=None,
):
    """Preview the generated RV waveform on CH1."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    return preview_sequence_configs(
        [waveform['ch1_prepost_config']] + waveform['ch1_scan_configs'],
        output_path,
        title_prefix=title_prefix,
        show=show,
    )


# Export commanded waveforms as time/voltage tables; these are not acquired instrument data.
def build_waveform_trace_table(*, channels=None, parameters=None, waveform=None):
    """Return one wide t-V table for plotting prepost, write, and read waveforms."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    prepost_points = []
    write_points = []
    read_points = []
    cursor = 0.0

    cursor = _extend_trace_points(
        prepost_points,
        waveform['ch1_prepost_config'][1],
        waveform['ch1_prepost_config'][2],
        waveform['ch1_prepost_config'][3],
        cursor,
        add_gap=False,
    )

    for chunk in waveform['scan_level_chunks']:
        for level in chunk:
            write_start_v, write_stop_v, write_times = build_pulse_block(level, waveform['time_values_write'], base_v=waveform['base_v'], offset_v=waveform['offset_v'])
            cursor = _extend_trace_points(
                write_points,
                write_start_v,
                write_stop_v,
                write_times,
                cursor,
            )

            read_start_v, read_stop_v, read_times = build_pulse_block(waveform['read_level'], waveform['time_values_read'], base_v=waveform['base_v'], offset_v=waveform['offset_v'])
            cursor = _extend_trace_points(
                read_points,
                read_start_v,
                read_stop_v,
                read_times,
                cursor,
            )

    trace_columns = {
        "Time_Prepost_s": [time for time, _voltage in prepost_points],
        "Voltage_Prepost_V": [voltage for _time, voltage in prepost_points],
        "Time_Write_s": [time for time, _voltage in write_points],
        "Voltage_Write_V": [voltage for _time, voltage in write_points],
        "Time_Read_s": [time for time, _voltage in read_points],
        "Voltage_Read_V": [voltage for _time, voltage in read_points],
    }
    return pd.DataFrame({name: pd.Series(values) for name, values in trace_columns.items()})


# Align raw channel data with program conditions and return a per-read-point result table.
def build_readback_table(df_ch1, df_ch2, *, channels=None, parameters=None, waveform=None):
    """Return only the readback points, one row per commanded write level."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
        raise ValueError("RV run returned empty data.")

    expected_count = len(waveform['scan_voltages'])
    actual_counts = (len(df_ch1), len(df_ch2))
    if actual_counts != (expected_count, expected_count):
        raise ValueError(
            "RV readback count mismatch: "
            f"expected {expected_count}, got CH{ch1}={actual_counts[0]} "
            f"and CH{ch2}={actual_counts[1]}."
        )
    count = expected_count
    rv_df = pd.DataFrame(
        {
            "CommandedWriteLevel": waveform['scan_levels'][:count],
            "CommandedWriteVoltage": waveform['scan_voltages'][:count],
            "TimestampI1": df_ch1[f"Timestamp {ch1}"].values[:count],
            "TimestampI2": df_ch2[f"Timestamp {ch2}"].values[:count],
            "ReadVoltageI1": df_ch1[f"Voltage {ch1}"].values[:count],
            "ReadVoltageI2": df_ch2[f"Voltage {ch2}"].values[:count],
            "CurrentI1": df_ch1[f"Current {ch1}"].values[:count],
            "CurrentI2": df_ch2[f"Current {ch2}"].values[:count],
        }
    )
    rv_df["ReadVoltageDiff"] = rv_df["ReadVoltageI1"] - rv_df["ReadVoltageI2"]
    rv_df["ResistanceI1"] = rv_df["ReadVoltageI1"] / rv_df["CurrentI1"].replace(0, pd.NA)
    rv_df["ResistanceI2"] = rv_df["ReadVoltageDiff"] / (-rv_df["CurrentI2"]).replace(0, pd.NA)
    return rv_df


# Merge params_override, build waveforms and execute repeated program-voltage sweeps with pointwise reads.
# preview_only=True previews only; acquisition returns data and paths; save_results controls file output.
# Unspecified settings use local defaults; current ranges and channels have separate keyword overrides.
def run_test(
    params_override=None,
    *,
    save_results=True,
    save_dir=None,
    file_stem=None,
    channels=None,
    current_ranges=None,
    inst=None,
    preview_only=None,
    segarb_options=None,
):
    """Run the FTJ RV test and optionally save readback-only results."""
    parameters = merge_parameters(params, params_override)
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    current_ranges = dict(current_ranges) if current_ranges is not None else dict(zip(channels, (CURRENT_RANGES[CH1], CURRENT_RANGES[CH2])))
    file_stem = FILE_STEM if file_stem is None else str(file_stem)
    inst = INST if inst is None else inst
    preview_only = PREVIEW_ONLY if preview_only is None else preview_only
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)
    waveform = build_waveform(parameters=parameters, channels=channels)

    if preview_only:
        return {"preview": preview_waveform(channels=channels, parameters=parameters, waveform=waveform), "output_path": None, "params": dict(parameters), "accepted_current_ranges": {}}

    with PMUSession(inst, channels=(ch1, ch2)) as session:
        query = session.query
        execute_segARB_test(
            query,
            channels=[ch1, ch2],
            seq_configs=waveform['seq_configs'],
            seq_list=waveform['seq_list'],
            current_ranges=current_ranges,
            options=segarb_options,
        )

        df_ch1, df_ch2 = read_both_channels(query, ch1, ch2)
        power_off_outputs(query, (ch1, ch2))

    rv_df = build_readback_table(df_ch1, df_ch2, channels=channels, parameters=parameters, waveform=waveform)
    waveform_df = build_waveform_trace_table(channels=channels, parameters=parameters, waveform=waveform)

    output_path = None
    if save_results:
        save_dir.mkdir(parents=True, exist_ok=True)
        output_stem = reserve_output_stem(
            save_dir, measurement_name(file_stem, None,
                "Vp" + voltage_tag(float(parameters["offset_v"]) + abs(float(parameters["vp"]))),
                "Vn" + voltage_tag(float(parameters["offset_v"]) - abs(float(parameters["vp"]))),
                "tw" + time_tag(parameters["write_dwell"])),
        )
        output_path = Path(f"{output_stem}.xlsx")
        saved_params = {
            "saved_at": saved_at(),
            **parameters,
            "inst": inst,
            "channels": (ch1, ch2),
            "current_ranges": current_ranges,
            "segarb_options": segarb_options,
        }
        params_df = pd.DataFrame(
            {"name": saved_params.keys(), "value": map(repr, saved_params.values())}
        )

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            writer.book.properties.creator = "ssme / Haoran Yu"
            rv_df.to_excel(writer, sheet_name="RV_ReadOnly", index=False)
            df_ch1.to_excel(writer, sheet_name="Channel_1_ReadOnly", index=False)
            df_ch2.to_excel(writer, sheet_name="Channel_2_ReadOnly", index=False)
            waveform_df.to_excel(writer, sheet_name="Waveform", index=False)
            params_df.to_excel(writer, sheet_name="Parameters", index=False)

    result = {
        "df_ch1": df_ch1,
        "df_ch2": df_ch2,
        "rv_df": rv_df,
        "waveform_df": waveform_df,
        "output_path": output_path,
    }
    result.update(params=dict(parameters), accepted_current_ranges={})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
