# -*- coding: utf-8 -*-
"""FTJ pulse-width-modulation (PWM) experiment using true width sweep.

The script keeps write voltage fixed, varies the dwell time of one write pulse,
and reads the resistance after each width:

    write width 1x   -> read
    write width 2x   -> read
    write width 5x   -> read

Positive write widths are swept first, followed by negative write widths. The
whole plan is flattened into one segARB sequence, so the PMU sequence list only
contains one sequence per channel.
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

from keithley4200.tools.waveform_preview import preview_sequence_configs
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


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2
SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\06-07-2026\03C6\L40um6\PWM")
FILE_STEM = "PWM"

CURRENT_RANGES = {CH1: 1e-4, CH2: 1e-4}
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": False,
    "LOAD_RESISTANCE": 1e6,
    # LLEC is not available for Segment Arb measurements.
    "ENABLE_LLEC": False,
}

params = {
    # Voltage held before/after every write and read pulse.
    "base_v": 0.0,
    "write_positive_v": 2,
    "write_negative_v": -6,
    "read_v": -1,
    "write_base_dwell": 1e-6,
    "width_multipliers": [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000],
    "repeat_count": 5,
    "read_dwell": 5e-5,
    "write_positive_trf": 1e-6,
    "write_negative_trf": 1e-6,
    "read_trf": 1e-5,
    "write_positive_idle": 0.5,
    "write_negative_idle": 0.5,
    "read_idle": 1e-3,
}


PREVIEW_ONLY = False
SAVE_WAVEFORM_PREVIEW = False

def append_block(target, start_v, stop_v, time_values, meas_types, meas_start, meas_stop):
    target["start_v"].extend(start_v)
    target["stop_v"].extend(stop_v)
    target["time_values"].extend(time_values)
    target["meas_types"].extend(meas_types)
    target["meas_start"].extend(meas_start)
    target["meas_stop"].extend(meas_stop)

def make_empty_sequence_accumulator():
    return {
        "start_v": [],
        "stop_v": [],
        "time_values": [],
        "meas_types": [],
        "meas_start": [],
        "meas_stop": [],
    }

def expand_config_for_preview(config, repeat_count, *, seq_id=0):
    """Return a repeated copy for preview/export-only waveform tracing."""
    start_v = []
    stop_v = []
    time_values = []
    meas_types = []
    meas_start = []
    meas_stop = []

    for _ in range(repeat_count):
        start_v.extend(config[1])
        stop_v.extend(config[2])
        time_values.extend(config[3])
        meas_types.extend(config[4])
        meas_start.extend(config[5])
        meas_stop.extend(config[6])

    return (seq_id, start_v, stop_v, time_values, meas_types, meas_start, meas_stop)

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


def build_waveform(*, parameters=None, channels=None):
    """Build pulse arrays and execution metadata from this run's parameters."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    base_v = float(parameters["base_v"])
    write_positive_v = float(parameters["write_positive_v"])
    write_negative_v = float(parameters["write_negative_v"])
    read_v = float(parameters["read_v"])
    write_base_dwell = float(parameters["write_base_dwell"])
    width_multipliers = list(parameters["width_multipliers"])
    write_widths = [write_base_dwell * float(value) for value in width_multipliers]
    pwm_repeat_count = int(parameters["repeat_count"])
    read_dwell = float(parameters["read_dwell"])
    write_positive_trf = float(parameters["write_positive_trf"])
    write_negative_trf = float(parameters["write_negative_trf"])
    read_trf = float(parameters["read_trf"])
    write_positive_idle = float(parameters["write_positive_idle"])
    write_negative_idle = float(parameters["write_negative_idle"])
    read_idle = float(parameters["read_idle"])
    meas_start_read = [0.0, read_dwell * 0.5, 0.0, 0.0]
    meas_stop_read = [0.0, read_dwell * 0.9, 0.0, 0.0]
    full_pwm_seq_id = 1
    meas_start_write = [0.0, 0.0, 0.0, 0.0]
    meas_stop_write = [0.0, 0.0, 0.0, 0.0]
    meas_types_read = [0, 1, 0, 0]
    meas_types_write = [0, 0, 0, 0]
    ch1_full_pwm_config, ch2_full_pwm_config, pwm_single_run_steps = make_pwm_sequence(
        full_pwm_seq_id,
        base_v=base_v,
        meas_start_read=meas_start_read,
        meas_start_write=meas_start_write,
        meas_stop_read=meas_stop_read,
        meas_stop_write=meas_stop_write,
        meas_types_read=meas_types_read,
        meas_types_write=meas_types_write,
        read_dwell=read_dwell,
        read_idle=read_idle,
        read_trf=read_trf,
        read_v=read_v,
        write_base_dwell=write_base_dwell,
        write_negative_idle=write_negative_idle,
        write_negative_trf=write_negative_trf,
        write_negative_v=write_negative_v,
        write_positive_idle=write_positive_idle,
        write_positive_trf=write_positive_trf,
        write_positive_v=write_positive_v,
        write_widths=write_widths,
    )
    pwm_steps = [
        {"RepeatIndex": repeat_index, **step}
        for repeat_index in range(1, pwm_repeat_count + 1)
        for step in pwm_single_run_steps
    ]
    seq_configs = {ch1: [ch1_full_pwm_config], ch2: [ch2_full_pwm_config]}
    seq_list = {
        ch1: [(full_pwm_seq_id, pwm_repeat_count)],
        ch2: [(full_pwm_seq_id, pwm_repeat_count)],
    }
    validate_segment_arb_configs(seq_configs)
    max_segments_per_seq = MAX_SEGMENTS_PER_SEQUENCE
    return {
        'base_v': base_v,
        'max_segments_per_seq': max_segments_per_seq,
        'pwm_repeat_count': pwm_repeat_count,
        'pwm_steps': pwm_steps,
        'read_dwell': read_dwell,
        'read_idle': read_idle,
        'read_trf': read_trf,
        'read_v': read_v,
        'seq_list': seq_list,
        'write_negative_idle': write_negative_idle,
        'write_negative_trf': write_negative_trf,
        'write_positive_idle': write_positive_idle,
        'write_positive_trf': write_positive_trf,
        'ch1_full_pwm_config': ch1_full_pwm_config,
        'seq_configs': seq_configs,
    }


def build_pulse_block(level, trf, dwell, idle, *, base_v):
    """Return a 4-segment base -> absolute target -> base pulse block."""
    start_v = [base_v, level, level, base_v]
    stop_v = [level, level, base_v, base_v]
    time_values = [trf, dwell, trf, idle]
    return start_v, stop_v, time_values


def make_pwm_sequence(
    seq_id,
    *,
    base_v,
    meas_start_read,
    meas_start_write,
    meas_stop_read,
    meas_stop_write,
    meas_types_read,
    meas_types_write,
    read_dwell,
    read_idle,
    read_trf,
    read_v,
    write_base_dwell,
    write_negative_idle,
    write_negative_trf,
    write_negative_v,
    write_positive_idle,
    write_positive_trf,
    write_positive_v,
    write_widths,
):
    """Build one sequence: positive width sweep, then negative width sweep."""
    ch1 = make_empty_sequence_accumulator()
    ch2 = make_empty_sequence_accumulator()
    steps = []

    for polarity, write_voltage, trf, idle in (
        ("positive", write_positive_v, write_positive_trf, write_positive_idle),
        ("negative", write_negative_v, write_negative_trf, write_negative_idle),
    ):
        for width in write_widths:
            write_start_v, write_stop_v, write_times = build_pulse_block(write_voltage, trf, width, idle, base_v=base_v)
            read_start_v, read_stop_v, read_times = build_pulse_block(read_v, read_trf, read_dwell, read_idle, base_v=base_v)

            append_block(ch1, write_start_v, write_stop_v, write_times, meas_types_write, meas_start_write, meas_stop_write)
            append_block(ch1, read_start_v, read_stop_v, read_times, meas_types_read, meas_start_read, meas_stop_read)

            zero_write = [0.0] * len(write_times)
            zero_read = [0.0] * len(read_times)
            append_block(ch2, zero_write, zero_write, write_times, meas_types_write, meas_start_write, meas_stop_write)
            append_block(ch2, zero_read, zero_read, read_times, meas_types_read, meas_start_read, meas_stop_read)

            steps.append(
                {
                    "Polarity": polarity,
                    "WriteVoltage": write_voltage,
                    "WriteWidth_s": width,
                    "WidthMultiplier": width / write_base_dwell,
                }
            )

    ch1_config = (
        seq_id,
        ch1["start_v"],
        ch1["stop_v"],
        ch1["time_values"],
        ch1["meas_types"],
        ch1["meas_start"],
        ch1["meas_stop"],
    )
    ch2_config = (
        seq_id,
        ch2["start_v"],
        ch2["stop_v"],
        ch2["time_values"],
        ch2["meas_types"],
        ch2["meas_start"],
        ch2["meas_stop"],
    )
    return ch1_config, ch2_config, steps


def validate_sequence_configs(
    configs_by_channel,
    seq_list_by_channel,
    *,
    channels=None,
    parameters=None,
    waveform=None,
):
    """Catch common parameter edit mistakes before sending configs to the PMU."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    for channel, configs in configs_by_channel.items():
        config_by_id = {config[0]: config for config in configs}
        for config in configs:
            seq_id, start_v, stop_v, times, meas_types, meas_start, meas_stop = config
            lengths = {
                len(start_v),
                len(stop_v),
                len(times),
                len(meas_types),
                len(meas_start),
                len(meas_stop),
            }
            if len(lengths) != 1:
                raise ValueError(f"CH{channel} seq {seq_id} has mismatched segment array lengths.")
            if len(times) > waveform['max_segments_per_seq']:
                raise ValueError(
                    f"CH{channel} seq {seq_id} has {len(times)} segments, "
                    f"above MAX_SEGMENTS_PER_SEQ={waveform['max_segments_per_seq']}."
                )
            if any(time_value <= 0 for time_value in times):
                raise ValueError(f"CH{channel} seq {seq_id} has non-positive segment time.")
            for index, (meas_type, start, stop, segment_time) in enumerate(zip(meas_types, meas_start, meas_stop, times), start=1):
                if meas_type == 0 and (start != 0.0 or stop != 0.0):
                    raise ValueError(f"CH{channel} seq {seq_id} segment {index} has a window but no measurement.")
                if meas_type != 0 and not (0.0 <= start < stop <= segment_time):
                    raise ValueError(f"CH{channel} seq {seq_id} segment {index} has an invalid measurement window.")

        missing_seq_ids = [
            seq_id
            for seq_id, _repeat_count in seq_list_by_channel[channel]
            if seq_id not in config_by_id
        ]
        if missing_seq_ids:
            raise ValueError(f"CH{channel} SEQ_LIST references missing seq IDs: {missing_seq_ids}")


def preview_waveform(
    output_path=None,
    *,
    show=True,
    title_prefix='FTJ PWM CH1',
    channels=None,
    parameters=None,
    waveform=None,
):
    """Preview the full generated PWM waveform on CH1."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    preview_config = expand_config_for_preview(waveform['ch1_full_pwm_config'], waveform['pwm_repeat_count'], seq_id=0)
    return preview_sequence_configs(
        [preview_config],
        output_path,
        title_prefix=title_prefix,
        show=show,
    )


def build_waveform_trace_table(*, channels=None, parameters=None, waveform=None):
    """Return one wide t-V table for plotting write/read command waveforms."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    write_positive_points = []
    write_negative_points = []
    read_points = []
    cursor = 0.0

    for step in waveform['pwm_steps']:
        write_start_v, write_stop_v, write_times = build_pulse_block(
            step["WriteVoltage"],
            waveform['write_positive_trf'] if step["Polarity"] == "positive" else waveform['write_negative_trf'],
            step["WriteWidth_s"],
            waveform['write_positive_idle'] if step["Polarity"] == "positive" else waveform['write_negative_idle'],
            base_v=waveform['base_v'],
        )
        write_points = write_positive_points if step["Polarity"] == "positive" else write_negative_points
        cursor = _extend_trace_points(write_points, write_start_v, write_stop_v, write_times, cursor)

        read_start_v, read_stop_v, read_times = build_pulse_block(waveform['read_v'], waveform['read_trf'], waveform['read_dwell'], waveform['read_idle'], base_v=waveform['base_v'])
        cursor = _extend_trace_points(read_points, read_start_v, read_stop_v, read_times, cursor)

    trace_columns = {
        "Time_WritePositive_s": [time for time, _voltage in write_positive_points],
        "Voltage_WritePositive_V": [voltage for _time, voltage in write_positive_points],
        "Time_WriteNegative_s": [time for time, _voltage in write_negative_points],
        "Voltage_WriteNegative_V": [voltage for _time, voltage in write_negative_points],
        "Time_Read_s": [time for time, _voltage in read_points],
        "Voltage_Read_V": [voltage for _time, voltage in read_points],
    }
    return pd.DataFrame({name: pd.Series(values) for name, values in trace_columns.items()})


def build_readback_table(df_ch1, df_ch2, *, channels=None, parameters=None, waveform=None):
    """Return one readback row per commanded PWM width."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
        raise ValueError("PWM run returned empty data.")

    expected_count = len(waveform['pwm_steps'])
    actual_counts = (len(df_ch1), len(df_ch2))
    if actual_counts != (expected_count, expected_count):
        raise ValueError(
            "PWM readback count mismatch: "
            f"expected {expected_count}, got CH{ch1}={actual_counts[0]} "
            f"and CH{ch2}={actual_counts[1]}."
        )
    count = expected_count
    step_df = pd.DataFrame(waveform['pwm_steps'][:count])
    pwm_df = pd.DataFrame(
        {
            "TimestampI1": df_ch1[f"Timestamp {ch1}"].values[:count],
            "TimestampI2": df_ch2[f"Timestamp {ch2}"].values[:count],
            "ReadVoltageI1": df_ch1[f"Voltage {ch1}"].values[:count],
            "ReadVoltageI2": df_ch2[f"Voltage {ch2}"].values[:count],
            "CurrentI1": df_ch1[f"Current {ch1}"].values[:count],
            "CurrentI2": df_ch2[f"Current {ch2}"].values[:count],
        }
    )
    pwm_df = pd.concat([step_df, pwm_df], axis=1)
    pwm_df["ReadVoltageDiff"] = pwm_df["ReadVoltageI1"] - pwm_df["ReadVoltageI2"]
    pwm_df["ResistanceI1"] = pwm_df["ReadVoltageI1"] / pwm_df["CurrentI1"].replace(0, pd.NA)
    pwm_df["ResistanceI2"] = pwm_df["ReadVoltageDiff"] / (-pwm_df["CurrentI2"]).replace(0, pd.NA)
    return pwm_df


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
    save_waveform_preview=None,
    segarb_options=None,
):
    """Run the FTJ PWM width sweep and optionally save data."""
    parameters = merge_parameters(params, params_override)
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    current_ranges = dict(current_ranges) if current_ranges is not None else dict(zip(channels, (CURRENT_RANGES[CH1], CURRENT_RANGES[CH2])))
    file_stem = FILE_STEM if file_stem is None else str(file_stem)
    inst = INST if inst is None else inst
    preview_only = PREVIEW_ONLY if preview_only is None else preview_only
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)
    save_waveform_preview = SAVE_WAVEFORM_PREVIEW if save_waveform_preview is None else save_waveform_preview
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

    pwm_df = build_readback_table(df_ch1, df_ch2, channels=channels, parameters=parameters, waveform=waveform)
    waveform_df = build_waveform_trace_table(channels=channels, parameters=parameters, waveform=waveform)
    output_path = None
    preview_path = None
    if save_results:
        save_dir.mkdir(parents=True, exist_ok=True)
        output_stem = reserve_output_stem(
            save_dir, measurement_name(file_stem, None,
                "Vp" + voltage_tag(parameters["write_positive_v"]),
                "Vn" + voltage_tag(parameters["write_negative_v"]),
                "tw" + time_tag(parameters["write_base_dwell"])),
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
            pwm_df.to_excel(writer, sheet_name="PWM_ReadOnly", index=False)
            df_ch1.to_excel(writer, sheet_name="Channel_1_ReadOnly", index=False)
            df_ch2.to_excel(writer, sheet_name="Channel_2_ReadOnly", index=False)
            waveform_df.to_excel(writer, sheet_name="Waveform", index=False)
            params_df.to_excel(writer, sheet_name="Parameters", index=False)

        if save_waveform_preview:
            preview_path = Path(f"{output_stem}_waveform.png")
            preview_waveform(preview_path, channels=channels, parameters=parameters, waveform=waveform)

    result = {
        "df_ch1": df_ch1,
        "df_ch2": df_ch2,
        "pwm_df": pwm_df,
        "waveform_df": waveform_df,
        "output_path": output_path,
        "preview_path": preview_path,
    }
    result.update(params=dict(parameters), accepted_current_ranges={})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
