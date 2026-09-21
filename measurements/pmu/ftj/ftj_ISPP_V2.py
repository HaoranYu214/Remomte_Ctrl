# -*- coding: utf-8 -*-
"""FTJ ISPP V2: pack each complete voltage ladder into one sequence."""

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
from keithley4200.tools.waveform_preview import preview_sequence_configs


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2
SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\FTJ\ISPP_V2")
FILE_STEM = "ISPP2"

CURRENT_RANGES = {CH1: 1e-5, CH2: 1e-5}
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": False,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}

params = {
    # Voltage held during pre-delay and after every write/read pulse.
    "base_v": 0.0,
    "read_v": 0.1,
    "positive_start_v": 0.5,
    "positive_stop_v": 2.0,
    "positive_steps": 10,
    "negative_start_v": -0.5,
    "negative_stop_v": -2.0,
    "negative_steps": 10,
    "write_dwell": 1e-6,
    "read_dwell": 1e-5,
    "pre_delay": 1e-3,
    "rise_time": 2e-7,
    "fall_time": 2e-7,
    "idle_time": 1e-3,
}

WRITE_POSITIVE_SEQ_ID = 1
WRITE_NEGATIVE_SEQ_ID = 2
MAX_SEGMENTS_PER_SEQ = MAX_SEGMENTS_PER_SEQUENCE
PREVIEW_ONLY = True


def voltage_steps(start, stop, steps):
    if int(steps) <= 0:
        raise ValueError("ISPP step count must be positive.")
    if int(steps) == 1:
        return [float(stop)]
    step = (float(stop) - float(start)) / (int(steps) - 1)
    return [float(start) + index * step for index in range(int(steps))]


def build_waveform(*, parameters=None, channels=None):
    """Build pulse arrays and execution metadata from this run's parameters."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    base_v = float(parameters["base_v"])
    read_v = float(parameters["read_v"])
    pos_v_start = float(parameters["positive_start_v"])
    pos_v_stop = float(parameters["positive_stop_v"])
    pos_steps = int(parameters["positive_steps"])
    neg_v_start = float(parameters["negative_start_v"])
    neg_v_stop = float(parameters["negative_stop_v"])
    neg_steps = int(parameters["negative_steps"])
    write_dwell = float(parameters["write_dwell"])
    read_dwell = float(parameters["read_dwell"])
    pre_delay = float(parameters["pre_delay"])
    rise_time = float(parameters["rise_time"])
    fall_time = float(parameters["fall_time"])
    idle_time = float(parameters["idle_time"])
    time_values_write = [pre_delay, rise_time, write_dwell, fall_time, idle_time]
    time_values_read = [pre_delay, rise_time, read_dwell, fall_time, idle_time]
    meas_types_write = [0, 0, 1, 0, 0]
    meas_start_write = [0.0, 0.0, write_dwell * 0.5, 0.0, 0.0]
    meas_stop_write = [0.0, 0.0, write_dwell * 0.9, 0.0, 0.0]
    meas_types_read = [0, 0, 1, 0, 0]
    meas_start_read = [0.0, 0.0, read_dwell * 0.5, 0.0, 0.0]
    meas_stop_read = [0.0, 0.0, read_dwell * 0.9, 0.0, 0.0]
    pos_voltages = voltage_steps(pos_v_start, pos_v_stop, pos_steps)
    neg_voltages = voltage_steps(neg_v_start, neg_v_stop, neg_steps)
    ch1_pos_config, ch2_pos_config = make_ispp_sequence(
        WRITE_POSITIVE_SEQ_ID, pos_voltages,
        base_v=base_v,
        meas_start_read=meas_start_read,
        meas_start_write=meas_start_write,
        meas_stop_read=meas_stop_read,
        meas_stop_write=meas_stop_write,
        meas_types_read=meas_types_read,
        meas_types_write=meas_types_write,
        read_v=read_v,
        time_values_read=time_values_read,
        time_values_write=time_values_write,
    )
    ch1_neg_config, ch2_neg_config = make_ispp_sequence(
        WRITE_NEGATIVE_SEQ_ID, neg_voltages,
        base_v=base_v,
        meas_start_read=meas_start_read,
        meas_start_write=meas_start_write,
        meas_stop_read=meas_stop_read,
        meas_stop_write=meas_stop_write,
        meas_types_read=meas_types_read,
        meas_types_write=meas_types_write,
        read_v=read_v,
        time_values_read=time_values_read,
        time_values_write=time_values_write,
    )
    seq_configs = {
        ch1: [ch1_pos_config, ch1_neg_config],
        ch2: [ch2_pos_config, ch2_neg_config],
    }
    seq_plan = [(WRITE_POSITIVE_SEQ_ID, 1), (WRITE_NEGATIVE_SEQ_ID, 1)]
    seq_list = {ch1: list(seq_plan), ch2: list(seq_plan)}
    validate_segment_arb_configs(seq_configs)
    return {
        'neg_voltages': neg_voltages,
        'pos_voltages': pos_voltages,
        'read_dwell': read_dwell,
        'read_v': read_v,
        'seq_list': seq_list,
        'write_dwell': write_dwell,
        'ch1_neg_config': ch1_neg_config,
        'ch1_pos_config': ch1_pos_config,
        'seq_configs': seq_configs,
        'time_values_read': time_values_read,
        'time_values_write': time_values_write,
    }


def make_ispp_sequence(
    seq_id,
    voltages,
    *,
    base_v,
    meas_start_read,
    meas_start_write,
    meas_stop_read,
    meas_stop_write,
    meas_types_read,
    meas_types_write,
    read_v,
    time_values_read,
    time_values_write,
):
    arrays = {
        "ch1_start": [], "ch1_stop": [], "ch2_start": [], "ch2_stop": [],
        "times": [], "types": [], "starts": [], "stops": [],
    }
    for voltage in voltages:
        arrays["ch1_start"].extend([base_v, base_v, voltage, voltage, base_v])
        arrays["ch1_stop"].extend([base_v, voltage, voltage, base_v, base_v])
        arrays["ch2_start"].extend([0.0] * 5)
        arrays["ch2_stop"].extend([0.0] * 5)
        arrays["times"].extend(time_values_write)
        arrays["types"].extend(meas_types_write)
        arrays["starts"].extend(meas_start_write)
        arrays["stops"].extend(meas_stop_write)

        arrays["ch1_start"].extend([base_v, base_v, read_v, read_v, base_v])
        arrays["ch1_stop"].extend([base_v, read_v, read_v, base_v, base_v])
        arrays["ch2_start"].extend([0.0] * 5)
        arrays["ch2_stop"].extend([0.0] * 5)
        arrays["times"].extend(time_values_read)
        arrays["types"].extend(meas_types_read)
        arrays["starts"].extend(meas_start_read)
        arrays["stops"].extend(meas_stop_read)

    if len(arrays["times"]) > MAX_SEGMENTS_PER_SEQ:
        raise ValueError(
            f"ISPP seq {seq_id} has {len(arrays['times'])} segments; "
            f"limit is {MAX_SEGMENTS_PER_SEQ}."
        )
    ch1_config = (
        seq_id, arrays["ch1_start"], arrays["ch1_stop"], arrays["times"],
        arrays["types"], arrays["starts"], arrays["stops"],
    )
    ch2_config = (
        seq_id, arrays["ch2_start"], arrays["ch2_stop"], arrays["times"],
        arrays["types"], arrays["starts"], arrays["stops"],
    )
    return ch1_config, ch2_config


def preview_waveform(
    output_path=None,
    *,
    show=True,
    title_prefix='FTJ ISPP V2 CH1',
    channels=None,
    parameters=None,
    waveform=None,
):
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    return preview_sequence_configs(
        [waveform['ch1_pos_config'], waveform['ch1_neg_config']],
        output_path,
        title_prefix=title_prefix,
        show=show,
    )


def build_waveform_trace_table(*, channels=None, parameters=None, waveform=None):
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    rows = []
    elapsed = 0.0
    for polarity, voltages in (("positive", waveform['pos_voltages']), ("negative", waveform['neg_voltages'])):
        for voltage in voltages:
            rows.append(
                {
                    "Polarity": polarity,
                    "WriteVoltage_V": voltage,
                    "ReadVoltage_V": waveform['read_v'],
                    "WriteDwell_s": waveform['write_dwell'],
                    "ReadDwell_s": waveform['read_dwell'],
                    "BlockStart_s": elapsed,
                }
            )
            elapsed += sum(waveform['time_values_write']) + sum(waveform['time_values_read'])
    return pd.DataFrame(rows)


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

    if df_ch1 is None and df_ch2 is None:
        raise ValueError("No data returned from the FTJ ISPP V2 run.")

    waveform_df = build_waveform_trace_table(channels=channels, parameters=parameters, waveform=waveform)
    output_path = None
    if save_results:
        save_dir.mkdir(parents=True, exist_ok=True)
        output_stem = reserve_output_stem(
            save_dir, measurement_name(file_stem, None,
                "Vp" + voltage_tag(parameters["positive_stop_v"]),
                "Vn" + voltage_tag(parameters["negative_stop_v"]),
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
            if df_ch1 is not None and not df_ch1.empty:
                df_ch1.to_excel(writer, sheet_name="Channel_1", index=False)
            if df_ch2 is not None and not df_ch2.empty:
                df_ch2.to_excel(writer, sheet_name="Channel_2", index=False)
            waveform_df.to_excel(writer, sheet_name="Waveform", index=False)
            params_df.to_excel(writer, sheet_name="Parameters", index=False)
    result = {
        "df_ch1": df_ch1,
        "df_ch2": df_ch2,
        "waveform_df": waveform_df,
        "output_path": output_path,
    }
    result.update(params=dict(parameters), accepted_current_ranges={})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
