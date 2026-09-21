# -*- coding: utf-8 -*-

# 阅读入口：ftj_ISPP_V1；先改本文件的 INST、CH1/CH2、params、CURRENT_RANGES 和 SAVE_DIR。
# 流程：run_test 合并本次参数 → build_waveform 构造波形 → PMU 执行/读回 → 整理并保存结果。
# PREVIEW_ONLY=True 时只预览；run_test 的显式参数优先于文件默认值。
# 查看波形定义从 build_waveform 开始；一般改实验条件不需要修改下方辅助函数。

"""FTJ ISPP V1: one write sequence per voltage, followed by a common read."""

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
    execute_segARB_test,
    power_off_outputs,
    validate_segment_arb_configs,
)
from keithley4200.pmu.session import PMUSession
from keithley4200.measurement_parameters import merge_parameters, remap_channel_options
from keithley4200.tools.waveform_preview import preview_sequence_configs


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2
SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\07-07-2026\FTJ")
FILE_STEM = "ISPP1"

CURRENT_RANGES = {CH1: 1e-5, CH2: 1e-5}
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": False,
    "LOAD_RESISTANCE": 1e6,
    # LLEC is not available for Segment Arb measurements.
    "ENABLE_LLEC": False,
}

params = {
    # Voltage held during pre-delay and after every write/read pulse.
    "base_v": 0.0,
    "read_v": 0.1,
    "positive_start_v": 0.5,
    "positive_stop_v": 2.0,
    "positive_steps": 15,
    "negative_start_v": -0.5,
    "negative_stop_v": -2.0,
    "negative_steps": 15,
    "write_dwell": 1e-6,
    "read_dwell": 1e-5,
    "pre_delay": 1e-3,
    "rise_time": 2e-7,
    "fall_time": 2e-7,
    "idle_time": 0.1,
}

READ_SEQ_ID = 1
WRITE_POSITIVE_SEQ_START_ID = 2
PREVIEW_ONLY = True


# 生成含端点的等间隔写入电压列表；steps 为 1 时仅使用 stop。
def voltage_steps(start, stop, steps):
    if int(steps) <= 0:
        raise ValueError("ISPP step count must be positive.")
    if int(steps) == 1:
        return [float(stop)]
    step = (float(stop) - float(start)) / (int(steps) - 1)
    return [float(start) + index * step for index in range(int(steps))]


# 根据 parameters 和 channels 生成本次波形配置、执行顺序及关联信息。
# 返回供测量和预览共用的字典；只计算波形，不连接仪器。
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
    write_negative_seq_start_id = WRITE_POSITIVE_SEQ_START_ID + pos_steps
    time_values_write = [pre_delay, rise_time, write_dwell, fall_time, idle_time]
    time_values_read = [pre_delay, rise_time, read_dwell, fall_time, idle_time]
    meas_types_write = [0, 0, 0, 0, 0]
    meas_start_write = [0.0] * 5
    meas_stop_write = [0.0] * 5
    meas_types_read = [0, 0, 1, 0, 0]
    meas_start_read = [0.0, 0.0, read_dwell * 0.5, 0.0, 0.0]
    meas_stop_read = [0.0, 0.0, read_dwell * 0.9, 0.0, 0.0]
    pos_voltages = voltage_steps(pos_v_start, pos_v_stop, pos_steps)
    neg_voltages = voltage_steps(neg_v_start, neg_v_stop, neg_steps)
    ch1_read_config, ch2_read_config = make_read_configs(base_v=base_v, meas_start_read=meas_start_read, meas_stop_read=meas_stop_read, meas_types_read=meas_types_read, read_v=read_v, time_values_read=time_values_read)
    ch1_pos_configs, ch2_pos_configs = make_write_configs(
        WRITE_POSITIVE_SEQ_START_ID, pos_voltages,
        base_v=base_v,
        meas_start_write=meas_start_write,
        meas_stop_write=meas_stop_write,
        meas_types_write=meas_types_write,
        time_values_write=time_values_write,
    )
    ch1_neg_configs, ch2_neg_configs = make_write_configs(
        write_negative_seq_start_id, neg_voltages,
        base_v=base_v,
        meas_start_write=meas_start_write,
        meas_stop_write=meas_stop_write,
        meas_types_write=meas_types_write,
        time_values_write=time_values_write,
    )
    seq_configs = {
        ch1: [ch1_read_config] + ch1_pos_configs + ch1_neg_configs,
        ch2: [ch2_read_config] + ch2_pos_configs + ch2_neg_configs,
    }
    seq_plan = (
        make_ispp_plan(WRITE_POSITIVE_SEQ_START_ID, pos_steps)
        + make_ispp_plan(write_negative_seq_start_id, neg_steps)
    )
    seq_list = {ch1: list(seq_plan), ch2: list(seq_plan)}
    validate_segment_arb_configs(seq_configs)
    return {
        'seq_list': seq_list,
        'ch1_neg_configs': ch1_neg_configs,
        'ch1_pos_configs': ch1_pos_configs,
        'ch1_read_config': ch1_read_config,
        'seq_configs': seq_configs,
    }


# 生成两通道共用的读脉冲序列配置，供每次递增写入后重复调用。
def make_read_configs(*, base_v, meas_start_read, meas_stop_read, meas_types_read, read_v, time_values_read):
    ch1_start_v = [base_v, base_v, read_v, read_v, base_v]
    ch1_stop_v = [base_v, read_v, read_v, base_v, base_v]
    zeros = [0.0] * 5
    ch1_config = (
        READ_SEQ_ID, ch1_start_v, ch1_stop_v, time_values_read,
        meas_types_read, meas_start_read, meas_stop_read,
    )
    ch2_config = (
        READ_SEQ_ID, zeros.copy(), zeros.copy(), time_values_read,
        meas_types_read, meas_start_read, meas_stop_read,
    )
    return ch1_config, ch2_config


# 为每个写入电压分配序列编号并生成双通道配置，返回两组序列列表。
def make_write_configs(
    seq_start_id,
    voltages,
    *,
    base_v,
    meas_start_write,
    meas_stop_write,
    meas_types_write,
    time_values_write,
):
    ch1_configs = []
    ch2_configs = []
    for index, voltage in enumerate(voltages):
        seq_id = seq_start_id + index
        ch1_start_v = [base_v, base_v, voltage, voltage, base_v]
        ch1_stop_v = [base_v, voltage, voltage, base_v, base_v]
        zeros = [0.0] * 5
        ch1_configs.append(
            (
                seq_id, ch1_start_v, ch1_stop_v, time_values_write,
                meas_types_write, meas_start_write, meas_stop_write,
            )
        )
        ch2_configs.append(
            (
                seq_id, zeros.copy(), zeros.copy(), time_values_write,
                meas_types_write, meas_start_write, meas_stop_write,
            )
        )
    return ch1_configs, ch2_configs


# 生成执行顺序：每个递增电压的写入序列后紧接一次公共读序列。
def make_ispp_plan(seq_start_id, steps):
    return [
        item
        for index in range(int(steps))
        for item in ((seq_start_id + index, 1), (READ_SEQ_ID, 1))
    ]


# 根据本次参数生成波形图；不连接仪器，指定 output_path 时保存预览图片。
def preview_waveform(
    output_path=None,
    *,
    show=True,
    title_prefix='FTJ ISPP V1 CH1',
    channels=None,
    parameters=None,
    waveform=None,
):
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    return preview_sequence_configs(
        [waveform['ch1_read_config']] + waveform['ch1_pos_configs'] + waveform['ch1_neg_configs'],
        output_path,
        title_prefix=title_prefix,
        show=show,
    )


# 合并 params_override 并生成波形，执行独立写序列与公共读序列交替执行的递增电压测试。
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
        raise ValueError("No data returned from the FTJ ISPP V1 run.")

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
            params_df.to_excel(writer, sheet_name="Parameters", index=False)

    result = {"df_ch1": df_ch1, "df_ch2": df_ch2, "output_path": output_path}
    result.update(params=dict(parameters), accepted_current_ranges={})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
