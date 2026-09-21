# -*- coding: utf-8 -*-

# 阅读入口：双极性 FeFET 写读；先改 params、INST、GATE_CH/DRAIN_CH 和 SAVE_DIR。
# 流程：run_test → 校验参数/生成写读计划 → PMU 执行 → 读回并整理 Id → 保存数据和图。
# PREVIEW_ONLY=True 时只预览；params_override 覆盖同名默认参数，其余沿用本文件设置。
# 读前等待超过 1 s 时分开执行写入和读回；源极设置在 USE_SOURCE_SMU/SOURCE_SMU。

"""Dual-polarity FeFET program/read test using one synchronized Segment Arb run."""

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

from keithley4200.output import measurement_name, reserve_output_stem, voltage_tag, time_tag
from keithley4200.pmu.fet_three_terminal_common import (
    add_derived_fet_columns,
    read_fet_channels,
    execute_program_read_with_software_delay,
    report_last_error,
    save_fet_workbook,
    save_waveform_data_sheets,
    source_smu_off,
    source_smu_on,
)
from keithley4200.tools.waveform_preview import (
    preview_sequence_configs,
    save_ids_dual_axis_plot,
    sequence_configs_to_dataframe,
)
from keithley4200.pmu.data_processing import read_both_channels
from keithley4200.pmu.pmu_tests import (
    MAX_SEGMENTS_PER_SEQUENCE, execute_segARB_test, power_off_outputs,
)
from keithley4200.pmu.session import PMUSession
from keithley4200.measurement_parameters import merge_parameters, remap_channel_options


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
GATE_CH, DRAIN_CH, SOURCE_SMU = 1, 2, 3
PREVIEW_ONLY = False
SAVE_WAVEFORM_PREVIEW = False
# Optional semantic filename supplied by wrapper scripts. None keeps the
# standalone parameter-based filename behavior.
OUTPUT_TAG = None


# False: connect Source to GNDU FORCE and leave SMU3 physically disconnected.
# True: connect Source to SMU3 only; do not connect it to GNDU at the same time.
USE_SOURCE_SMU = False

SEGARB_OPTIONS = {
    "ENABLE_LLEC": False,
    "LLEC_CHANNELS": (DRAIN_CH,),
    "ENABLE_LOAD_CONFIG": False,
    "LOAD_RESISTANCES": {GATE_CH: 1e6, DRAIN_CH: 1e6},
    "ENABLE_CONNECTION_COMP": False,
    "CONNECTION_COMP_CHANNELS": (GATE_CH, DRAIN_CH),
}

# Edit experiment parameters here. Workflow overrides are copied for each run.
params = {
    'cycles': 3,
    'positive_write_voltage': 4,
    'positive_train_count': 1,
    'positive_program_read_repeats': 20,
    'positive_write_base': 0.0,
    'positive_write_rise': 1e-07,
    'positive_write_plateau': 0.0001,
    'positive_write_fall': 1e-07,
    'positive_write_rest': 1e-05,
    'negative_write_voltage': -4,
    'negative_train_count': 1,
    'negative_program_read_repeats': 20,
    'negative_write_base': 0.0,
    'negative_write_rise': 1e-07,
    'negative_write_plateau': 0.0001,
    'negative_write_fall': 1e-07,
    'negative_write_rest': 1e-05,
    'float_gate_during_read': False,
    'ssr_switch_time': 50e-6,  # SSR transition guard; hardware minimum is 25 us.
    'read_gate_voltage': 0.5,
    'read_drain_voltage': -2,
    'read_base': 0.0,
    'read_delay': 5,
    'read_rise': 0.0001,
    'read_plateau': 0.001,
    'read_fall': 0.0001,
    'read_rest': 0.0001,
    'measure_start_fraction': 0.2,
    'measure_stop_fraction': 0.9,
    'gate_current_range': 1e-07,
    'drain_current_range': 1e-06,
    'source_voltage': 0.0,
    'source_compliance': 0.001,
    'max_segments_per_sequence': MAX_SEGMENTS_PER_SEQUENCE,
}

SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\06-08-2026\03C5_FET\FeFET 2\D40-5um gap circular 2\Vg0.5 Vd-2")


# 向波形数组追加不采集数据的等待段；超过 1 s 时拆成多个段。
def append_constant_delay(arrays, level, duration):
    """Append an unmeasured delay, split at the 1 s segment-time limit."""
    remaining = float(duration)
    while remaining > 0:
        segment_time = min(remaining, 1.0)
        arrays["start"].append(level)
        arrays["stop"].append(level)
        arrays["time"].append(segment_time)
        arrays["mode"].append(0)
        arrays["meas_start"].append(0.0)
        arrays["meas_stop"].append(0.0)
        remaining -= segment_time

# 把序列循环展开为预览配置，便于画完整时序；不改变实际硬件执行计划。
def build_sequence_plan_preview_config(configs, sequence_plan, sequence_id):
    """Expand hardware loops into one config solely for waveform preview."""
    config_by_id = {config[0]: config for config in configs}
    has_ssr = any(len(cfg) > 7 and cfg[7] is not None for cfg in configs)
    arrays = [[] for _ in range(7 if has_ssr else 6)]
    for seq_id, repeat_count in sequence_plan:
        config = config_by_id[seq_id]
        for _ in range(int(repeat_count)):
            sources = list(config[1:7])
            if has_ssr:
                sources.append(config[7] if len(config) > 7 and config[7] is not None else [1]*len(config[3]))
            for target, source in zip(arrays, sources):
                target.extend(source)
    return (sequence_id, *arrays)


# 向数组追加脉冲的上升、平台、下降和休息段，并设置采集窗口。
def append_pulse(arrays, base, level, timing, measure=False, *, parameters=None):
    """Append seamless rise, plateau, fall, and rest segments."""
    parameters = params if parameters is None else parameters

    rise, plateau, fall, rest = timing
    arrays["start"].extend([base, level, level, base])
    arrays["stop"].extend([level, level, base, base])
    arrays["time"].extend([rise, plateau, fall, rest])
    arrays["mode"].extend([0, 1 if measure else 0, 0, 0])
    if measure:
        m_start = plateau * parameters["measure_start_fraction"]
        m_stop = plateau * parameters["measure_stop_fraction"]
    else:
        m_start = m_stop = 0.0
    arrays["meas_start"].extend([0.0, m_start, 0.0, 0.0])
    arrays["meas_stop"].extend([0.0, m_stop, 0.0, 0.0])


# 生成正/负极性各自的写脉冲串及读回计划，返回读点表、双通道配置和执行列表。
def build_program_read_sequence(include_delay=True, *, channels=None, parameters=None):
    """Build independent positive/negative trains, each followed by a read."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (GATE_CH, DRAIN_CH)
    gate_ch, drain_ch = channels

    p = parameters
    plan = []
    configs = {gate_ch: [], drain_ch: []}
    execution_list = []
    read_timing = (p["read_rise"], p["read_plateau"], p["read_fall"], p["read_rest"])

    write_states = (
        {
            "name": "Positive",
            "voltage": p["positive_write_voltage"],
            "count": int(p["positive_train_count"]),
            "repeats": int(p["positive_program_read_repeats"]),
            "base": p["positive_write_base"],
            "timing": (
                p["positive_write_rise"], p["positive_write_plateau"],
                p["positive_write_fall"], p["positive_write_rest"],
            ),
        },
        {
            "name": "Negative",
            "voltage": p["negative_write_voltage"],
            "count": int(p["negative_train_count"]),
            "repeats": int(p["negative_program_read_repeats"]),
            "base": p["negative_write_base"],
            "timing": (
                p["negative_write_rise"], p["negative_write_plateau"],
                p["negative_write_fall"], p["negative_write_rest"],
            ),
        },
    )

    # Define one four-segment sequence for each polarity. CH2 gets a matching
    # zero-volt hold waveform so both PMU channels use the same time stamps.
    program_sequence_ids = []
    for sequence_id, state in enumerate(write_states, start=1):
        program_sequence_ids.append((sequence_id, state))
        for channel, base, level in (
            (gate_ch, state["base"], state["voltage"]),
            (drain_ch, p["read_base"], p["read_base"]),
        ):
            arrays = {
                key: [] for key in ("start", "stop", "time", "mode", "meas_start", "meas_stop")
            }
            append_pulse(arrays, base, level, state["timing"], measure=False, parameters=parameters)
            configs[channel].append((
                sequence_id,
                arrays["start"], arrays["stop"], arrays["time"], arrays["mode"],
                arrays["meas_start"], arrays["meas_stop"],
            ))

    # A shared four-segment read sequence follows each completed train.
    read_sequence_id = len(program_sequence_ids) + 1
    for channel, base, level in (
        (gate_ch, p["read_base"], p["read_gate_voltage"]),
        (drain_ch, p["read_base"], p["read_drain_voltage"]),
    ):
        arrays = {
            key: [] for key in ("start", "stop", "time", "mode", "meas_start", "meas_stop")
        }
        if include_delay:
            append_constant_delay(arrays, base, p["read_delay"])
        float_gate = p.get("float_gate_during_read", False)
        delay_segments = len(arrays["time"])
        if float_gate:
            append_constant_delay(arrays, base, p["ssr_switch_time"])
        append_pulse(arrays, base, base if float_gate and channel == gate_ch else level,
                     read_timing, measure=not (float_gate and channel == gate_ch), parameters=parameters)
        if float_gate:
            append_constant_delay(arrays, base, p["ssr_switch_time"])
        configs[channel].append((
            read_sequence_id,
            arrays["start"], arrays["stop"], arrays["time"], arrays["mode"],
            arrays["meas_start"], arrays["meas_stop"],
        ))
        if float_gate and channel == gate_ch:
            configs[channel][-1] += ([1]*delay_segments + [0]*5 + [1],)

    # Both channels receive this exact same ordered list. Looping the program
    # sequence produces N pulses without defining 4*N segments.
    for cycle in range(1, int(p["cycles"]) + 1):
        for program_sequence_id, state in program_sequence_ids:
            for polarity_repeat in range(1, state["repeats"] + 1):
                execution_list.extend([
                    (program_sequence_id, state["count"]),
                    (read_sequence_id, 1),
                ])
                plan.append(
                    {
                        "Cycle": cycle,
                        "WritePolarity": state["name"],
                        "PolarityRepeat": polarity_repeat,
                        "ProgramVoltage": state["voltage"],
                        "TrainCount": state["count"],
                        "ProgramSequenceID": program_sequence_id,
                    }
                )

    for channel_configs in configs.values():
        for config in channel_configs:
            segment_count = len(config[3])
            if segment_count > int(p["max_segments_per_sequence"]):
                raise ValueError(
                    f"Sequence {config[0]} needs {segment_count} segments, above "
                    f"max_segments_per_sequence={p['max_segments_per_sequence']}."
                )
            if any(duration > 1.0 for duration in config[3]):
                raise ValueError(f"Sequence {config[0]} contains a segment longer than 1 s.")
    seq_lists = {
        gate_ch: list(execution_list),
        drain_ch: list(execution_list),
    }
    return pd.DataFrame(plan), configs, seq_lists


# 检查脉冲次数、时间、采集窗口及悬空读栅极的 SSR 设置；不连接仪器。
def validate_parameters(*, parameters=None):
    parameters = params if parameters is None else parameters

    if parameters.get("float_gate_during_read", False):
        if not 25e-6 <= parameters["ssr_switch_time"] <= 1.0:
            raise ValueError("SSR_SWITCH_TIME must be between 25 us and 1 s.")
    if int(parameters["cycles"]) < 1:
        raise ValueError("cycles must be a positive integer.")
    for name in (
        "positive_train_count", "negative_train_count",
        "positive_program_read_repeats", "negative_program_read_repeats",
    ):
        if int(parameters[name]) < 1:
            raise ValueError(f"{name} must be a positive integer.")
    if parameters["read_delay"] < 0:
        raise ValueError("READ_DELAY must be non-negative.")
    for name in (
        "positive_write_rise", "positive_write_plateau",
        "positive_write_fall", "positive_write_rest",
        "negative_write_rise", "negative_write_plateau",
        "negative_write_fall", "negative_write_rest",
        "read_rise", "read_plateau", "read_fall", "read_rest",
    ):
        if parameters[name] <= 0:
            raise ValueError(f"{name} must be positive.")
    if not 0 <= parameters["measure_start_fraction"] < parameters["measure_stop_fraction"] <= 1:
        raise ValueError("Measurement fractions must satisfy 0 <= start < stop <= 1.")


# 返回展开循环后的 Gate/Drain 波形配置，供预览和数值导出使用。
def expanded_preview_configs(*, channels=None, parameters=None):
    """Return fully expanded Gate and Drain configs for plotting/export."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (GATE_CH, DRAIN_CH)
    gate_ch, drain_ch = channels

    _plan, seq_configs, seq_lists = build_program_read_sequence(channels=channels, parameters=parameters)
    gate_preview = build_sequence_plan_preview_config(
        seq_configs[gate_ch], seq_lists[gate_ch], gate_ch
    )
    drain_preview = build_sequence_plan_preview_config(
        seq_configs[drain_ch], seq_lists[drain_ch], drain_ch
    )
    return [gate_preview, drain_preview]


# 根据本次参数生成波形图；不连接仪器，指定 output_path 时保存预览图片。
def preview_waveform(output_path=None, *, compress_delay=True, channels=None, parameters=None):
    """Preview the expanded plan using compressed or real-time delay scaling."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (GATE_CH, DRAIN_CH)
    gate_ch, drain_ch = channels

    return preview_sequence_configs(
        expanded_preview_configs(channels=channels, parameters=parameters),
        output_path,
        title_prefix="FeFET program/read",
        channel_labels=("CH1 Gate", "CH2 Drain"),
        compress_constant_segments_above=0.1 if compress_delay else None,
    )


# 返回真实时间轴和压缩等待时间轴的波形表，供 Excel 保存和绘图使用。
def waveform_data_frames(*, channels=None, parameters=None):
    """Return real-time and compressed numeric waveform plotting tables."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (GATE_CH, DRAIN_CH)
    gate_ch, drain_ch = channels

    configs = expanded_preview_configs(channels=channels, parameters=parameters)
    labels = ("CH1", "CH2")
    return (
        sequence_configs_to_dataframe(configs, channel_labels=labels),
        sequence_configs_to_dataframe(
            configs,
            channel_labels=labels,
            compress_constant_segments_above=0.1,
        ),
    )


# 合并 params_override 后执行写入—等待—读回，保存工作簿及结果图。
# preview_only=True 时只预览；实测返回含 output_path、params 和 settings 的字典。
# 超过 1 s 的读前等待采用分开执行和主机等待；未覆盖的参数沿用本文件默认值。
def run_test(
    params_override=None,
    *,
    channels=None,
    current_ranges=None,
    inst=None,
    output_tag=None,
    preview_only=None,
    save_dir=None,
    save_waveform_preview=None,
    segarb_options=None,
    source_smu=None,
    use_source_smu=None,
):
    parameters = merge_parameters(params, params_override)
    channels = tuple(channels) if channels is not None else (GATE_CH, DRAIN_CH)
    gate_ch, drain_ch = channels
    current_ranges = dict(current_ranges) if current_ranges is not None else {gate_ch: parameters["gate_current_range"], drain_ch: parameters["drain_current_range"]}
    parameters.update(gate_current_range=current_ranges[gate_ch], drain_current_range=current_ranges[drain_ch])
    inst = INST if inst is None else inst
    output_tag = OUTPUT_TAG if output_tag is None else output_tag
    preview_only = PREVIEW_ONLY if preview_only is None else preview_only
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)
    save_waveform_preview = SAVE_WAVEFORM_PREVIEW if save_waveform_preview is None else save_waveform_preview
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (GATE_CH, DRAIN_CH), channels, segarb_options)
    source_smu = SOURCE_SMU if source_smu is None else source_smu
    use_source_smu = USE_SOURCE_SMU if use_source_smu is None else use_source_smu

    if preview_only:
        return {"preview": preview_waveform(channels=channels, parameters=parameters), "output_path": None, "params": dict(parameters), "accepted_current_ranges": {}}

    validate_parameters(parameters=parameters)
    split_delay = parameters["read_delay"] > 1.0
    plan, seq_configs, seq_lists = build_program_read_sequence(
        include_delay=not split_delay,
        channels=channels,
        parameters=parameters,
    )
    defined_segments = sum(len(config[3]) for config in seq_configs[gate_ch])
    print(
        f"Segment Arb FeFET plan: {len(plan)} program/read states, "
        f"{defined_segments} defined segments/channel; gate trains use sequence loops"
    )
    print(
        "Delay execution: "
        + ("separate write/read executions" if split_delay else "one synchronized execution")
    )
    print(plan.to_string(index=False))

    with PMUSession(inst, channels=(gate_ch, drain_ch)) as session:
        query = session.query
        try:
            query(":ERROR:LAST:CLEAR")
            if use_source_smu:
                source_smu_on(
                    query,
                    source_smu,
                    parameters["source_voltage"],
                    parameters["source_compliance"],
                )
            current_ranges = {
                gate_ch: parameters["gate_current_range"],
                drain_ch: parameters["drain_current_range"],
            }
            options = segarb_options
            if split_delay:
                gate_df, drain_df = execute_program_read_with_software_delay(
                    query, plan, seq_configs, parameters["read_delay"],
                    gate_ch, drain_ch, current_ranges, options,
                    float_gate=parameters.get("float_gate_during_read", False),
                )
            else:
                execute_segARB_test(
                    query, [gate_ch, drain_ch], seq_configs,
                    seq_list=seq_lists, current_ranges=current_ranges, options=options,
                )
                gate_df, drain_df = read_fet_channels(query, gate_ch, drain_ch,
                    float_gate=parameters.get("float_gate_during_read", False))
            if gate_df is None or drain_df is None or gate_df.empty or drain_df.empty:
                report_last_error(query)
                raise ValueError("Segment Arb FeFET read returned empty PMU data.")
            measured = pd.concat(
                [gate_df.reset_index(drop=True), drain_df.reset_index(drop=True)], axis=1
            )
            if len(measured) != len(plan):
                raise ValueError(
                    f"Expected {len(plan)} drain-read points, received {len(measured)}."
                )
            data = add_derived_fet_columns(
                pd.concat([plan, measured], axis=1),
                gate_channel=gate_ch, drain_channel=drain_ch,
            )
            name = measurement_name(
                "FETdual", parameters["positive_write_voltage"],
                "VgFloat" if parameters.get("float_gate_during_read", False) else "Vg" + voltage_tag(parameters["read_gate_voltage"]),
                "Vd" + voltage_tag(parameters["read_drain_voltage"]),
                "td" + time_tag(parameters["read_delay"]),
            )
            if output_tag:
                name += "_" + output_tag
            output_stem = reserve_output_stem(save_dir, name)
            path = Path(f"{output_stem}.xlsx")
            save_fet_workbook(
                path,
                data,
                {
                    "mode": "dual_polarity_segment_arb_program_then_read",
                    "delay_execution": "software_split" if split_delay else "single_execution",
                    "source_connection": f"SMU{source_smu}" if use_source_smu else "GNDU",
                    **parameters,
                    "CURRENT_RANGES": current_ranges,
                    "inst": inst,
                    "channels": (gate_ch, drain_ch),
                    "source_smu": source_smu,
                    **segarb_options,
                },
                {gate_ch: gate_df, drain_ch: drain_df},
            )
            try:
                save_ids_dual_axis_plot(
                    expanded_preview_configs(channels=channels, parameters=parameters),
                    data["Id"],
                    path.with_name(f"{path.stem}_Ids.png"),
                    read_gate_voltage=float("nan") if parameters.get("float_gate_during_read", False) else parameters["read_gate_voltage"],
                    read_drain_voltage=parameters["read_drain_voltage"],
                    read_delay=parameters["read_delay"],
                )
            except Exception as exc:
                print(f"Warning: Ids plot could not be saved; measurement data is safe: {exc}")
            if save_waveform_preview:
                real_time_data, schematic_data = waveform_data_frames(channels=channels, parameters=parameters)
                save_waveform_data_sheets(path, real_time_data, schematic_data)
                real_time_path = path.with_name(f"{path.stem}_waveform_real_time.png")
                schematic_path = path.with_name(f"{path.stem}_waveform_compressed.png")
                preview_waveform(
                    real_time_path,
                    compress_delay=False,
                    channels=channels,
                    parameters=parameters,
                )
                preview_waveform(
                    schematic_path,
                    compress_delay=True,
                    channels=channels,
                    parameters=parameters,
                )
            print(f"Saved: {path.resolve()}")
            result = {"output_path": path}
            result.update(params=dict(parameters), accepted_current_ranges={})
            result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
            return result
        finally:
            power_off_outputs(query, (gate_ch, drain_ch))
            if use_source_smu:
                source_smu_off(query, source_smu)


if __name__ == "__main__":
    run_test()
