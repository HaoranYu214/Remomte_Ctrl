# -*- coding: utf-8 -*-

# 阅读入口：ftj_Identical_V1；先改本文件的 INST、CH1/CH2、params、CURRENT_RANGES 和 SAVE_DIR。
# 流程：run_test 合并本次参数 → build_waveform 构造波形 → PMU 执行/读回 → 整理并保存结果。
# PREVIEW_ONLY=True 时只预览；run_test 的显式参数优先于文件默认值。
# 查看波形定义从 build_waveform 开始；一般改实验条件不需要修改下方辅助函数。

"""FTJ identical-pulse test with fixed write and read levels.

Physical purpose:
    Apply the same write pulse repeatedly and read the FTJ state after every
    pulse. Unlike ISPP, the write amplitude does not increase. The changing
    variable is cumulative pulse count.

    This reveals pulse-to-pulse evolution at fixed programming conditions:
    gradual resistance change, switching probability, saturation, and the
    number of identical pulses required to reach a target state. Because the
    FTJ response is nonlinear, identical pulses may initially cause little
    change and then produce an abrupt jump or rapid saturation.

Difference from ISPP (Incremental Step Pulse Programming):
    ISPP increases write amplitude step by step to make resistance/conductance
    updates more controlled and approximately linear. Identical-pulse testing
    keeps amplitude fixed and exposes the device's nonlinear accumulation
    versus pulse number.
"""

from pathlib import Path

import pandas as pd

import sys
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
from keithley4200.tools.waveform_preview import preview_sequence_configs
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
SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\14-09-2026\04A1_2700_1200_300\L30_2\FTJ\Identical")
# SAVE_DIR = Path(r"D:\Code\data\20260620")
FILE_STEM = "Identical1"

CURRENT_RANGES = {CH1: 1e-6, CH2: 1e-6}
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": False,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}

# PREVIEW_ONLY = True
PREVIEW_ONLY = True
SAVE_WAVEFORM_PREVIEW = False

params = {
    # Voltage held before/after every write and read pulse.
    "base_v": 0.0,
    "write_positive_v": 6,
    "write_negative_v": -6,
    "read_v": -1.5,
    "write_positive_dwell": 5e-5,
    "write_negative_dwell": 5e-5,
    "read_dwell": 5e-5,
    "write_positive_trf": 1e-6,
    "write_negative_trf": 1e-6,
    "read_trf": 1e-6,
    "write_positive_idle": 1e-2,
    "write_negative_idle": 1e-2,
    "read_idle": 1e-2,
    "positive_repeat_count": 100,
    "negative_repeat_count": 100,
    "sequence_cycle_count": 1,
}


# 按执行计划展开序列列表，拼成一个可下发的 PMU 序列配置。
def build_sequence_plan_config(configs, seq_plan, *, seq_id):
    """Flatten a sequence-list plan into one PMU sequence."""
    config_by_id = {config[0]: config for config in configs}
    start_v = []
    stop_v = []
    time_values = []
    meas_types = []
    meas_start = []
    meas_stop = []

    for plan_seq_id, repeat_count in seq_plan:
        config = config_by_id[plan_seq_id]
        for _ in range(repeat_count):
            start_v.extend(config[1])
            stop_v.extend(config[2])
            time_values.extend(config[3])
            meas_types.extend(config[4])
            meas_start.extend(config[5])
            meas_stop.extend(config[6])

    return (seq_id, start_v, stop_v, time_values, meas_types, meas_start, meas_stop)

# 检查生成的序列配置是否符合本脚本要求，在发送到 PMU 前发现参数错误。
def validate_sequence_configs(configs_by_channel, seq_list_by_channel):
    """Catch common parameter edit mistakes before sending configs to the PMU."""
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
            if any(time_value <= 0 for time_value in times):
                raise ValueError(f"CH{channel} seq {seq_id} has non-positive segment time.")
            if len(times) > MAX_SEGMENTS_PER_SEQUENCE:
                raise ValueError(
                    f"CH{channel} seq {seq_id} has {len(times)} segments; "
                    f"limit is {MAX_SEGMENTS_PER_SEQUENCE}."
                )

        missing_seq_ids = [
            seq_id
            for seq_id, _repeat_count in seq_list_by_channel[channel]
            if seq_id not in config_by_id
        ]
        if missing_seq_ids:
            raise ValueError(f"CH{channel} SEQ_LIST references missing seq IDs: {missing_seq_ids}")


# 向时间—电压端点列表追加一个波形块，用于重建指令波形图。
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


# 根据 parameters 和 channels 生成本次波形配置、执行顺序及关联信息。
# 返回供测量和预览共用的字典；只计算波形，不连接仪器。
def build_waveform(*, parameters=None, channels=None):
    """Build pulse arrays and execution metadata from this run's parameters."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    base_v = float(parameters["base_v"])
    write_positive_v = float(parameters["write_positive_v"])
    write_negative_v = float(parameters["write_negative_v"])
    read_v = float(parameters["read_v"])
    reverse_read_v = -read_v
    write_positive_dwell = float(parameters["write_positive_dwell"])
    write_negative_dwell = float(parameters["write_negative_dwell"])
    read_dwell = float(parameters["read_dwell"])
    write_positive_trf = float(parameters["write_positive_trf"])
    write_negative_trf = float(parameters["write_negative_trf"])
    read_trf = float(parameters["read_trf"])
    write_positive_idle = float(parameters["write_positive_idle"])
    write_negative_idle = float(parameters["write_negative_idle"])
    read_idle = float(parameters["read_idle"])
    positive_repeat_count = int(parameters["positive_repeat_count"])
    negative_repeat_count = int(parameters["negative_repeat_count"])
    seq_cycle_count = int(parameters["sequence_cycle_count"])
    time_values_write_positive = [
        write_positive_trf,
        write_positive_dwell,
        write_positive_trf,
        write_positive_idle,
    ]
    time_values_read = [read_trf, read_dwell, read_trf, read_idle]
    time_values_write_negative = [
        write_negative_trf,
        write_negative_dwell,
        write_negative_trf,
        write_negative_idle,
    ]
    meas_start_read = [0.0, read_dwell * 0.5, 0.0, 0.0]
    meas_stop_read = [0.0, read_dwell * 0.9, 0.0, 0.0]
    ch1_start_v_write_positive = [base_v, write_positive_v, write_positive_v, base_v]
    ch1_stop_v_write_positive = [write_positive_v, write_positive_v, base_v, base_v]
    ch1_start_v_read = [base_v, read_v, read_v, base_v]
    ch1_stop_v_read = [read_v, read_v, base_v, base_v]
    ch1_start_v_reverse_read = [base_v, reverse_read_v, reverse_read_v, base_v]
    ch1_stop_v_reverse_read = [reverse_read_v, reverse_read_v, base_v, base_v]
    ch1_start_v_write_negative = [base_v, write_negative_v, write_negative_v, base_v]
    ch1_stop_v_write_negative = [write_negative_v, write_negative_v, base_v, base_v]
    write_positive_seq_id = 1
    meas_start_write_positive = [0.0, 0.0, 0.0, 0.0]
    meas_stop_write_positive = [0.0, 0.0, 0.0, 0.0]
    meas_types_write_positive = [0, 0, 0, 0]
    ch1_write_positive_config = (
        write_positive_seq_id, ch1_start_v_write_positive, ch1_stop_v_write_positive,
        time_values_write_positive, meas_types_write_positive,
        meas_start_write_positive, meas_stop_write_positive,
    )
    ch2_start_v_write_positive = [0] * 4
    ch2_stop_v_write_positive = [0] * 4
    ch2_write_positive_config = (
        write_positive_seq_id, ch2_start_v_write_positive, ch2_stop_v_write_positive,
        time_values_write_positive, meas_types_write_positive,
        meas_start_write_positive, meas_stop_write_positive,
    )
    read_seq_id = 2
    meas_types_read = [0, 1, 0, 0]
    ch1_read_config = (
        read_seq_id, ch1_start_v_read, ch1_stop_v_read, time_values_read,
        meas_types_read, meas_start_read, meas_stop_read,
    )
    ch2_start_v_read = [0] * 4
    ch2_stop_v_read = [0] * 4
    ch2_read_config = (
        read_seq_id, ch2_start_v_read, ch2_stop_v_read, time_values_read,
        meas_types_read, meas_start_read, meas_stop_read,
    )
    reverse_read_seq_id = 4
    ch1_reverse_read_config = (
        reverse_read_seq_id, ch1_start_v_reverse_read, ch1_stop_v_reverse_read,
        time_values_read, meas_types_read, meas_start_read, meas_stop_read,
    )
    ch2_reverse_read_config = (
        reverse_read_seq_id, ch2_start_v_read, ch2_stop_v_read, time_values_read,
        meas_types_read, meas_start_read, meas_stop_read,
    )
    write_negative_seq_id = 3
    meas_start_write_negative = [0.0, 0.0, 0.0, 0.0]
    meas_stop_write_negative = [0.0, 0.0, 0.0, 0.0]
    meas_types_write_negative = [0, 0, 0, 0]
    ch1_write_negative_config = (
        write_negative_seq_id, ch1_start_v_write_negative, ch1_stop_v_write_negative,
        time_values_write_negative, meas_types_write_negative,
        meas_start_write_negative, meas_stop_write_negative,
    )
    ch2_start_v_write_negative = [0] * 4
    ch2_stop_v_write_negative = [0] * 4
    ch2_write_negative_config = (
        write_negative_seq_id, ch2_start_v_write_negative, ch2_stop_v_write_negative,
        time_values_write_negative, meas_types_write_negative,
        meas_start_write_negative, meas_stop_write_negative,
    )
    base_seq_configs = {
        ch1: [ch1_write_positive_config, ch1_read_config, ch1_reverse_read_config, ch1_write_negative_config],
        ch2: [ch2_write_positive_config, ch2_read_config, ch2_reverse_read_config, ch2_write_negative_config],
    }
    single_cycle_plan = (
        [(write_positive_seq_id, 1), (read_seq_id, 1)] * positive_repeat_count
        + [(write_negative_seq_id, 1), (read_seq_id, 1)] * negative_repeat_count
    )
    seq_plan = single_cycle_plan * seq_cycle_count
    first_expanded_seq_id = 1
    expanded_seq_ids = [first_expanded_seq_id + index for index in range(seq_cycle_count)]
    ch1_expanded_configs = [
        build_sequence_plan_config(base_seq_configs[ch1], single_cycle_plan, seq_id=seq_id)
        for seq_id in expanded_seq_ids
    ]
    ch2_expanded_configs = [
        build_sequence_plan_config(base_seq_configs[ch2], single_cycle_plan, seq_id=seq_id)
        for seq_id in expanded_seq_ids
    ]
    seq_configs = {ch1: ch1_expanded_configs, ch2: ch2_expanded_configs}
    seq_list = {
        ch1: [(seq_id, 1) for seq_id in expanded_seq_ids],
        ch2: [(seq_id, 1) for seq_id in expanded_seq_ids],
    }
    ch1_sequence_plan_preview_config = build_sequence_plan_config(
        base_seq_configs[ch1], seq_plan, seq_id=0
    )
    validate_segment_arb_configs(seq_configs)
    return {
        'read_seq_id': read_seq_id,
        'reverse_read_seq_id': reverse_read_seq_id,
        'seq_list': seq_list,
        'seq_plan': seq_plan,
        'write_negative_seq_id': write_negative_seq_id,
        'write_positive_seq_id': write_positive_seq_id,
        'base_seq_configs': base_seq_configs,
        'ch1_sequence_plan_preview_config': ch1_sequence_plan_preview_config,
        'seq_configs': seq_configs,
    }


# 根据本次参数生成波形图；不连接仪器，指定 output_path 时保存预览图片。
def preview_waveform(
    output_path=None,
    *,
    show=True,
    title_prefix='FTJ Identical CH1',
    channels=None,
    parameters=None,
    waveform=None,
):
    """Preview the generated identical-pulse waveform on CH1."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    return preview_sequence_configs(
        [waveform['ch1_sequence_plan_preview_config']],
        output_path,
        title_prefix=title_prefix,
        show=show,
    )


# 把指令波形整理成时间—电压表，供导出和绘图；它不是仪器采集数据。
def build_waveform_trace_table(*, channels=None, parameters=None, waveform=None):
    """Return one wide t-V table for plotting write/read command waveforms."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    config_by_id = {config[0]: config for config in waveform['base_seq_configs'][ch1]}
    write_points = []
    read_points = []
    reverse_read_points = []
    cursor = 0.0

    for seq_id, repeat_count in waveform['seq_plan']:
        config = config_by_id[seq_id]
        if seq_id in (waveform['write_positive_seq_id'], waveform['write_negative_seq_id']):
            points = write_points
        elif seq_id == waveform['read_seq_id']:
            points = read_points
        elif seq_id == waveform['reverse_read_seq_id']:
            points = reverse_read_points
        else:
            points = []

        for _ in range(repeat_count):
            cursor = _extend_trace_points(
                points,
                config[1],
                config[2],
                config[3],
                cursor,
            )

    trace_columns = {
        "Time_Write_s": [time for time, _voltage in write_points],
        "Voltage_Write_V": [voltage for _time, voltage in write_points],
        "Time_Read_s": [time for time, _voltage in read_points],
        "Voltage_Read_V": [voltage for _time, voltage in read_points],
        "Time_ReverseRead_s": [time for time, _voltage in reverse_read_points],
        "Voltage_ReverseRead_V": [voltage for _time, voltage in reverse_read_points],
    }
    return pd.DataFrame({name: pd.Series(values) for name, values in trace_columns.items()})


# 合并 params_override 并生成波形，执行固定幅值的重复写入与读回。
# preview_only=True 时只预览；实测返回数据及输出路径，save_results 控制结果文件保存。
# 未覆盖参数沿用本文件默认值；电流量程和通道可通过关键字参数单独指定。
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
    """Run the FTJ segARB sequence list and optionally save raw data."""
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

    if df_ch1 is None and df_ch2 is None:
        raise ValueError("No data returned from the FTJ segARB run.")

    waveform_df = build_waveform_trace_table(channels=channels, parameters=parameters, waveform=waveform)
    output_path = None
    preview_path = None
    if save_results:
        save_dir.mkdir(parents=True, exist_ok=True)
        output_stem = reserve_output_stem(
            save_dir, measurement_name(file_stem, None,
                "Vp" + voltage_tag(parameters["write_positive_v"]),
                "Vn" + voltage_tag(parameters["write_negative_v"]),
                "tw" + time_tag(parameters["write_positive_dwell"])),
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

        if save_waveform_preview:
            preview_path = Path(f"{output_stem}_waveform.png")
            preview_waveform(preview_path, channels=channels, parameters=parameters, waveform=waveform)

    result = {
        "df_ch1": df_ch1,
        "df_ch2": df_ch2,
        "waveform_df": waveform_df,
        "output_path": output_path,
        "preview_path": preview_path,
    }
    result.update(params=dict(parameters), accepted_current_ranges={})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
