# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: ftj_MRD; edit INST, CH1/CH2, params, CURRENT_RANGES and SAVE_DIR.
# Flow: run_test merges parameters -> build_waveform -> PMU execution/readout -> process and save results.
# PREVIEW_ONLY=True previews only; explicit run_test arguments override file defaults.
# Read build_waveform for waveform definitions; routine parameter changes do not require editing helpers below.

"""FTJ multilevel resistance distribution (MRD) measurement.

MRD means Multilevel Resistance Distribution.

Physical purpose:
    Evaluate FTJ reliability and cycle-to-cycle (C2C) variation. For each
    fixed write-voltage level, repeat the same reset/read/write/read cycle and
    measure how much the resulting resistance varies from trial to trial.

    The mean or median indicates the resistance level produced by a given
    programming voltage, while the standard deviation and full distribution
    quantify repeatability, state overlap, and programming reliability.

Important implementation detail:
    This script does not sweep write-pulse width. ``WRITE_DWELL`` is fixed.
    The programmed variable is ``WRITE_VOLTAGES``.

    It also does not wait for several accumulated write pulses before reading.
    Every cycle currently performs:

        reference/reset pulse
        -> reference-state read
        -> one write pulse at the selected voltage
        -> after-write read

    That four-pulse block is repeated ``CYCLES_PER_LEVEL`` times for every
    write voltage. Therefore the distribution comes from repeated, individually
    read trials at each voltage level, rather than from pulse-width modulation
    or sparse reading after every N programming pulses.
"""

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
SAVE_DIR = Path("data/pmu/ftj/ftj_MRD")
FILE_STEM = "MRD"

CURRENT_RANGES = {CH1: 1e-5, CH2: 1e-5}
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": False,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}

params = {
    # Voltage held before/after reference, write, and read pulses.
    "base_v": 0.0,
    "reference_v": -6.5,
    "write_voltages": [0.1, 0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5, 2, 2.2, 2.4, 2.6, 2.8, 3],
    "read_v": -1,
    "cycles_per_level": 1,
    "reference_rise": 1e-6,
    "reference_dwell": 5e-3,
    "reference_fall": 1e-6,
    "reference_idle": 0.5,
    "write_rise": 1e-6,
    "write_dwell": 1e-5,
    "write_fall": 1e-6,
    "write_idle": 0.5,
    "read_rise": 1e-6,
    "read_dwell": 5e-5,
    "read_fall": 1e-6,
    "read_idle": 0.5,
}


PREVIEW_ONLY = False

# Build expected read-point order to align acquired data with cycles and program voltages.
def expected_cycle_table(seq_metadata):
    """Return the expected read-point order from the sequence plan."""
    rows = []
    for item in seq_metadata:
        for cycle_index in range(1, item["cycles"] + 1):
            rows.extend(
                [
                    {
                        "SequenceID": item["seq_id"],
                        "WriteVoltage": item["write_voltage"],
                        "CycleIndex": cycle_index,
                        "ReadType": "RefStateRead",
                    },
                    {
                        "SequenceID": item["seq_id"],
                        "WriteVoltage": item["write_voltage"],
                        "CycleIndex": cycle_index,
                        "ReadType": "AfterWriteRead",
                    },
                ]
            )
    return pd.DataFrame(rows)

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

# Group resistance distributions by program voltage to compare variability across levels.
def build_distribution_summary(result_df):
    """Summarize resistance distribution for each write level."""
    if result_df.empty:
        return pd.DataFrame()

    summary_df = (
        result_df.groupby(["WriteVoltage", "ReadType"], dropna=False)["Resistance"]
        .agg(
            Count="count",
            Mean="mean",
            Std="std",
            Median="median",
            Min="min",
            Max="max",
        )
        .reset_index()
    )
    return summary_df


# Build this run's waveform configurations, execution order and metadata from parameters and channels.
# Return a dictionary shared by acquisition and preview; waveform construction does not connect to hardware.
def build_waveform(*, parameters=None, channels=None):
    """Build pulse arrays and execution metadata from this run's parameters."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    base_v = float(parameters["base_v"])
    reference_v = float(parameters["reference_v"])
    write_voltages = list(parameters["write_voltages"])
    read_v = float(parameters["read_v"])
    cycles_per_level = int(parameters["cycles_per_level"])
    reference_rise = float(parameters["reference_rise"])
    reference_dwell = float(parameters["reference_dwell"])
    reference_fall = float(parameters["reference_fall"])
    reference_idle_2 = float(parameters["reference_idle"])
    write_rise = float(parameters["write_rise"])
    write_dwell = float(parameters["write_dwell"])
    write_fall = float(parameters["write_fall"])
    write_idle_2 = float(parameters["write_idle"])
    read_rise = float(parameters["read_rise"])
    read_dwell = float(parameters["read_dwell"])
    read_fall = float(parameters["read_fall"])
    read_idle_2 = float(parameters["read_idle"])
    time_values_reference = [
        reference_rise, reference_dwell, reference_fall, reference_idle_2
    ]
    time_values_write = [write_rise, write_dwell, write_fall, write_idle_2]
    time_values_read = [read_rise, read_dwell, read_fall, read_idle_2]
    meas_types_reference = [0] * 4
    meas_start_reference = [0.0] * 4
    meas_stop_reference = [0.0] * 4
    meas_types_write = [0] * 4
    meas_start_write = [0.0] * 4
    meas_stop_write = [0.0] * 4
    meas_types_read = [0, 1, 0, 0]
    meas_start_read = [0.0, read_dwell * 0.5, 0.0, 0.0]
    meas_stop_read = [0.0, read_dwell * 0.9, 0.0, 0.0]
    base_seq_id = 1
    max_segments_per_seq = MAX_SEGMENTS_PER_SEQUENCE
    ch1_configs, ch2_configs, seq_plan, seq_metadata = build_all_sequences(
        write_voltages,
        base_seq_id=base_seq_id,
        base_v=base_v,
        cycles_per_level=cycles_per_level,
        max_segments_per_seq=max_segments_per_seq,
        meas_start_read=meas_start_read,
        meas_start_reference=meas_start_reference,
        meas_start_write=meas_start_write,
        meas_stop_read=meas_stop_read,
        meas_stop_reference=meas_stop_reference,
        meas_stop_write=meas_stop_write,
        meas_types_read=meas_types_read,
        meas_types_reference=meas_types_reference,
        meas_types_write=meas_types_write,
        read_v=read_v,
        reference_v=reference_v,
        time_values_read=time_values_read,
        time_values_reference=time_values_reference,
        time_values_write=time_values_write,
    )
    seq_configs = {ch1: ch1_configs, ch2: ch2_configs}
    seq_list = {ch1: list(seq_plan), ch2: list(seq_plan)}
    validate_segment_arb_configs(seq_configs)
    return {
        'base_v': base_v,
        'read_v': read_v,
        'reference_v': reference_v,
        'seq_list': seq_list,
        'seq_metadata': seq_metadata,
        'ch1_configs': ch1_configs,
        'seq_configs': seq_configs,
        'time_values_read': time_values_read,
        'time_values_reference': time_values_reference,
        'time_values_write': time_values_write,
    }


# Return pulse segments from baseline to target voltage and back, for sequence assembly.
def build_pulse_block(amplitude, time_values, *, base_v):
    """Return a 4-segment base -> absolute target -> base pulse block."""
    start_v = [base_v, amplitude, amplitude, base_v]
    stop_v = [amplitude, amplitude, base_v, base_v]
    return start_v, stop_v, list(time_values)


# Build one reference/reset-read-program-read sequence to compare states before and after programming.
def build_mrd_sequence(
    seq_id,
    write_voltage,
    *,
    base_v,
    max_segments_per_seq,
    meas_start_read,
    meas_start_reference,
    meas_start_write,
    meas_stop_read,
    meas_stop_reference,
    meas_stop_write,
    meas_types_read,
    meas_types_reference,
    meas_types_write,
    read_v,
    reference_v,
    time_values_read,
    time_values_reference,
    time_values_write,
):
    """Build one MRD sequence: reference pulse, read, write pulse, then read."""
    ch1_start_v = []
    ch1_stop_v = []
    ch2_start_v = []
    ch2_stop_v = []
    time_values = []
    meas_types = []
    meas_start = []
    meas_stop = []

    pulse_defs = [
        (reference_v, time_values_reference, meas_types_reference, meas_start_reference, meas_stop_reference),
        (read_v, time_values_read, meas_types_read, meas_start_read, meas_stop_read),
        (write_voltage, time_values_write, meas_types_write, meas_start_write, meas_stop_write),
        (read_v, time_values_read, meas_types_read, meas_start_read, meas_stop_read),
    ]

    for amplitude, pulse_times, pulse_meas_types, pulse_meas_start, pulse_meas_stop in pulse_defs:
        start_v, stop_v, local_times = build_pulse_block(amplitude, pulse_times, base_v=base_v)
        ch1_start_v.extend(start_v)
        ch1_stop_v.extend(stop_v)
        ch2_start_v.extend([0.0] * len(local_times))
        ch2_stop_v.extend([0.0] * len(local_times))
        time_values.extend(local_times)
        meas_types.extend(pulse_meas_types)
        meas_start.extend(pulse_meas_start)
        meas_stop.extend(pulse_meas_stop)

    if len(time_values) > max_segments_per_seq:
        raise ValueError(
            f"MRD sequence {seq_id} has {len(time_values)} segments, "
            f"above MAX_SEGMENTS_PER_SEQ={max_segments_per_seq}."
        )

    ch1_config = (seq_id, ch1_start_v, ch1_stop_v, time_values, meas_types, meas_start, meas_stop)
    ch2_config = (seq_id, ch2_start_v, ch2_stop_v, time_values, meas_types, meas_start, meas_stop)
    return ch1_config, ch2_config


# Build an MRD sequence and metadata for each program voltage, for execution and read-point alignment.
def build_all_sequences(
    write_voltages,
    *,
    base_seq_id,
    base_v,
    cycles_per_level,
    max_segments_per_seq,
    meas_start_read,
    meas_start_reference,
    meas_start_write,
    meas_stop_read,
    meas_stop_reference,
    meas_stop_write,
    meas_types_read,
    meas_types_reference,
    meas_types_write,
    read_v,
    reference_v,
    time_values_read,
    time_values_reference,
    time_values_write,
):
    """Build one sequence per write voltage."""
    ch1_configs = []
    ch2_configs = []
    seq_plan = []
    seq_metadata = []

    for index, write_voltage in enumerate(write_voltages):
        seq_id = base_seq_id + index
        ch1_config, ch2_config = build_mrd_sequence(seq_id, write_voltage, base_v=base_v, max_segments_per_seq=max_segments_per_seq, meas_start_read=meas_start_read, meas_start_reference=meas_start_reference, meas_start_write=meas_start_write, meas_stop_read=meas_stop_read, meas_stop_reference=meas_stop_reference, meas_stop_write=meas_stop_write, meas_types_read=meas_types_read, meas_types_reference=meas_types_reference, meas_types_write=meas_types_write, read_v=read_v, reference_v=reference_v, time_values_read=time_values_read, time_values_reference=time_values_reference, time_values_write=time_values_write)
        ch1_configs.append(ch1_config)
        ch2_configs.append(ch2_config)
        seq_plan.append((seq_id, cycles_per_level))
        seq_metadata.append(
            {
                "seq_id": seq_id,
                "write_voltage": write_voltage,
                "cycles": cycles_per_level,
            }
        )

    return ch1_configs, ch2_configs, seq_plan, seq_metadata


# Build the waveform plot without hardware access; save it when output_path is supplied.
def preview_waveform(
    output_path=None,
    *,
    show=True,
    title_prefix='FTJ MRD CH1',
    channels=None,
    parameters=None,
    waveform=None,
):
    """Preview all MRD sequences on CH1."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    return preview_sequence_configs(
        waveform['ch1_configs'],
        output_path,
        title_prefix=title_prefix,
        show=show,
    )


# Export commanded waveforms as time/voltage tables; these are not acquired instrument data.
def build_waveform_trace_table(*, channels=None, parameters=None, waveform=None):
    """Return one wide t-V table for plotting reference, write, and read waveforms."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    reference_points = []
    write_points = []
    read_points = []
    cursor = 0.0

    for item in waveform['seq_metadata']:
        for _cycle_index in range(item["cycles"]):
            reference_start_v, reference_stop_v, reference_times = build_pulse_block(waveform['reference_v'], waveform['time_values_reference'], base_v=waveform['base_v'])
            cursor = _extend_trace_points(
                reference_points,
                reference_start_v,
                reference_stop_v,
                reference_times,
                cursor,
            )

            read_start_v, read_stop_v, read_times = build_pulse_block(waveform['read_v'], waveform['time_values_read'], base_v=waveform['base_v'])
            cursor = _extend_trace_points(
                read_points,
                read_start_v,
                read_stop_v,
                read_times,
                cursor,
            )

            write_start_v, write_stop_v, write_times = build_pulse_block(item["write_voltage"], waveform['time_values_write'], base_v=waveform['base_v'])
            cursor = _extend_trace_points(
                write_points,
                write_start_v,
                write_stop_v,
                write_times,
                cursor,
            )

            read_start_v, read_stop_v, read_times = build_pulse_block(waveform['read_v'], waveform['time_values_read'], base_v=waveform['base_v'])
            cursor = _extend_trace_points(
                read_points,
                read_start_v,
                read_stop_v,
                read_times,
                cursor,
            )

    trace_columns = {
        "Time_Reference_s": [time for time, _voltage in reference_points],
        "Voltage_Reference_V": [voltage for _time, voltage in reference_points],
        "Time_Write_s": [time for time, _voltage in write_points],
        "Voltage_Write_V": [voltage for _time, voltage in write_points],
        "Time_Read_s": [time for time, _voltage in read_points],
        "Voltage_Read_V": [voltage for _time, voltage in read_points],
    }
    return pd.DataFrame({name: pd.Series(values) for name, values in trace_columns.items()})


# Align raw channel data with program conditions and return a per-read-point result table.
def build_readback_table(df_ch1, df_ch2, *, channels=None, parameters=None, waveform=None):
    """Return one row per measured read point."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
        raise ValueError("MRD run returned empty data.")

    expected_df = expected_cycle_table(waveform['seq_metadata'])
    expected_count = len(expected_df)
    actual_counts = (len(df_ch1), len(df_ch2))
    if actual_counts != (expected_count, expected_count):
        raise ValueError(
            "MRD readback count mismatch: "
            f"expected {expected_count}, got CH{ch1}={actual_counts[0]} "
            f"and CH{ch2}={actual_counts[1]}."
        )
    count = expected_count

    expected_df = expected_df.iloc[:count].reset_index(drop=True)
    result_df = expected_df.copy()
    result_df["ReadTimestamp"] = df_ch1[f"Timestamp {ch1}"].values[:count]
    result_df["ReadVoltage"] = df_ch1[f"Voltage {ch1}"].values[:count]
    result_df["ReadCurrent"] = df_ch1[f"Current {ch1}"].values[:count]
    result_df["Resistance"] = result_df["ReadVoltage"] / result_df["ReadCurrent"].replace(0, pd.NA)
    return result_df


# Merge params_override and execute repeated reset/program/read sequences at each voltage level.
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
    """Run the FTJ MRD test and optionally save the readback table."""
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

    result_df = build_readback_table(df_ch1, df_ch2, channels=channels, parameters=parameters, waveform=waveform)
    summary_df = build_distribution_summary(result_df)
    waveform_df = build_waveform_trace_table(channels=channels, parameters=parameters, waveform=waveform)

    output_path = None
    if save_results:
        save_dir.mkdir(parents=True, exist_ok=True)
        output_stem = reserve_output_stem(
            save_dir, measurement_name(file_stem, None,
                "Vwrite" + voltage_tag(min(parameters["write_voltages"])) + "to" + voltage_tag(max(parameters["write_voltages"])),
                "Vref" + voltage_tag(parameters["reference_v"]),
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
            result_df.to_excel(writer, sheet_name="MRD_ReadOnly", index=False)
            summary_df.to_excel(writer, sheet_name="MRD_Summary", index=False)
            df_ch1.to_excel(writer, sheet_name="Channel_1_ReadOnly", index=False)
            df_ch2.to_excel(writer, sheet_name="Channel_2_ReadOnly", index=False)
            waveform_df.to_excel(writer, sheet_name="Waveform", index=False)
            params_df.to_excel(writer, sheet_name="Parameters", index=False)

    result = {
        "df_ch1": df_ch1,
        "df_ch2": df_ch2,
        "result_df": result_df,
        "summary_df": summary_df,
        "waveform_df": waveform_df,
        "output_path": output_path,
    }
    result.update(params=dict(parameters), accepted_current_ranges={})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
