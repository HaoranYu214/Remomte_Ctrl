
# 阅读说明：retentionPV/retentionPUND 的共用执行辅助文件，不是独立实验入口。
# 实验参数和波形在两个入口中修改；这里负责检查、配置、等待、执行和原始数据保存。
# prepare_stage/execute_plan 使用调用者的仪器连接；preview_plan 只做离线绘图。

"""Local execution support for the two retention entries; no waveform design."""

import math
import time

import numpy as np
import pandas as pd

from keithley4200.pmu.data_processing import read_both_channels
from keithley4200.pmu.pmu_tests import (
    _apply_common_pmu_options, configure_segARB_sequence,
    power_off_outputs, validate_segment_arb_configs,
)


# 在连接仪器或预留输出文件前检查所有阶段的波形、通道和参数。
def validate_plan(plan, channels, params):
    """Check every stage before opening a session or reserving output files."""
    if len(set(channels)) != 2:
        raise ValueError("Retention requires two distinct PMU channels.")
    for key in ("rise_time", "area_cm2", "Irange1", "Irange2"):
        value = float(params[key])
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be finite and positive.")
    if float(params["offset"]) != 0:
        raise ValueError("These output-off retention entries require offset=0.")
    labels = set()
    for stage in plan:
        if stage["label"] in labels:
            raise ValueError("Retention stage labels must be unique.")
        labels.add(stage["label"])
        delay = float(stage["delay_before_s"])
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("delay_time must be finite and nonnegative.")
        configs = stage["configs"]
        if set(configs) != set(channels):
            raise ValueError("Stage channel mapping is incomplete.")
        validate_segment_arb_configs(configs)
        times = configs[channels[0]][0][3]
        for channel in channels:
            if len(configs[channel]) != 1 or configs[channel][0][0] != 1:
                raise ValueError("Each isolated execution must use sequence 1.")
            cfg = configs[channel][0]
            if cfg[3] != times:
                raise ValueError("Retention channels must use identical segment times.")
            if any(not math.isfinite(float(t)) or not 20e-9 <= t <= 1 for t in cfg[3]):
                raise ValueError("Each hardware segment must be 20 ns to 1 s (10 V range).")
            if any(not math.isfinite(float(v)) or abs(v) > 10 for v in cfg[1] + cfg[2]):
                raise ValueError("Retention voltages must fit the default +/-10 V range.")
            if cfg[1][0] != 0 or cfg[2][-1] != 0:
                raise ValueError("Each output-off execution must start and end at 0 V.")


# 通过已有连接在输出关闭时配置下一阶段，供后续等待到期后执行。
def prepare_stage(query, configs, channels, params, options):
    """Configure with outputs off, before waiting for the next deadline."""
    query(":PMU:INIT 1")
    for channel in channels:
        query(f":PMU:RPM:CONFIGURE PMU1-{channel}, 0")
    _apply_common_pmu_options(query, channels, options=options)
    for channel, key in zip(channels, ("Irange1", "Irange2")):
        query(f":PMU:MEASURE:RANGE {channel}, 2, {params[key]}")
        configure_segARB_sequence(query, channel, *configs[channel][0])
        query(f":PMU:SARB:WFM:SEQ:LIST {channel}, 1, 1")
        query(f":PMU:OUTPUT:STATE {channel}, 1")


# 按计划配置并执行各阶段，在阶段间关闭输出并由主机计时等待。
# 更新 frames/timing；记录的时序是主机估计值，不是仪器实测脉冲时间。
def execute_plan(query, plan, channels, params, options, frames, timing,
                 *, clock=time.perf_counter, sleep=time.sleep, poll_s=0.005,
                 timeout_s=30.0):
    """Execute stages; clocks estimate hardware timing and never measure it directly.

    End estimate = EXECUTE send time + programmed waveform duration. Command
    latency and hardware startup latency remain unknown. The first observed
    completion and its lateness are recorded separately. No full delay is
    added after transfer/configuration: those operations consume the budget.
    OUTPUT:STATE 1 takes effect at EXECUTE; inter-stage state is output_off.
    """
    validate_plan(plan, channels, params)
    previous_end = None
    origin = None
    try:
        for index, stage in enumerate(plan):
            record = {"stage": stage["label"], "execution": index + 1,
                      "target_delay_s": stage["delay_before_s"],
                      "wait_state": "output_off", "status": "preparing"}
            timing.append(record)
            duration = sum(stage["configs"][channels[0]][0][3])
            prepare_stage(query, stage["configs"], channels, params, options)
            target = None if previous_end is None else previous_end + stage["delay_before_s"]
            if target is not None:
                while True:
                    remaining = target - clock()
                    if remaining <= 0:
                        break
                    sleep(min(remaining, 0.05))
            sent = clock()
            if origin is None:
                origin = sent
            record.update(command_sent_s=sent-origin, programmed_duration_s=duration,
                          estimated_delay_s=None if previous_end is None else sent-previous_end,
                          overrun_s=0.0 if target is None else max(0.0, sent-target),
                          status="executing")
            query(":PMU:EXECUTE")
            record["command_return_s"] = clock()-origin
            while True:
                status = str(query(":PMU:TEST:STATUS?")).replace("ACK", "").strip()
                if status == "0":
                    break
                if clock() - sent > duration + timeout_s:
                    raise TimeoutError(f"Retention stage {stage['label']} did not complete.")
                sleep(poll_s)
            observed = clock()
            previous_end = sent + duration
            record.update(completion_observed_s=observed-origin,
                          estimated_end_s=previous_end-origin,
                          completion_lag_s=observed-previous_end)
            power_off_outputs(query, channels)
            if any(mode != 0 for mode in stage["configs"][channels[0]][0][4]):
                pair = read_both_channels(query, *channels)
                if any(df is None or df.empty for df in pair):
                    raise ValueError(f"Empty retention data for {stage['label']}.")
                if len(pair[0]) != len(pair[1]):
                    raise ValueError("Retention channel sample counts differ.")
                for channel, df in zip(channels, pair):
                    df = df.copy()
                    df["Stage"] = stage["label"]
                    df["Execution"] = index + 1
                    df["EstimatedGlobalTime_s"] = df[f"Timestamp {channel}"] + sent-origin
                    frames[channel].append(df)
                    record[f"CH{channel}_points"] = len(df)
            record["status"] = "complete"
            if record["overrun_s"] > 0.001:
                print(f"{stage['label']}: estimated delay overrun {record['overrun_s']:.6g} s")
    except BaseException as exc:
        if timing:
            timing[-1].update(status="failed", error=str(exc))
        try:
            query(":PMU:ABORT")
        except Exception:
            pass
        raise
    finally:
        power_off_outputs(query, channels)
    return tuple(pd.concat(frames[ch], ignore_index=True) for ch in channels)


# 将已获取的原始数据、阶段计时和参数保存到工作簿，支持失败或中断后的记录。
def save_raw(path, frames, timing, parameters):
    """Checkpoint raw data before analysis, including interrupted/failed runs."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for channel, parts in frames.items():
            if parts:
                pd.concat(parts, ignore_index=True).to_excel(writer, sheet_name=f"Channel_{channel}", index=False)
        pd.DataFrame(timing).to_excel(writer, sheet_name="ExecutionTiming", index=False)
        parameters.to_excel(writer, sheet_name="Parameters", index=False)


# 离线画出双通道执行阶段与等待间隔；输出关闭期间不假定器件电压。
def preview_plan(plan, channel, *, show=True, compress_delay=True, title_prefix="Retention"):
    """Preview both channels; output-off gaps have no assigned DUT voltage."""
    import matplotlib.pyplot as plt
    channels = [channel] + [ch for ch in plan[0]["configs"] if ch != channel]
    durations = [sum(stage["configs"][channel][0][3]) for stage in plan]
    gap_width = max(durations) * 0.6
    fig = plt.figure(figsize=(max(12, 3*len(plan)), 8))
    grid = fig.add_gridspec(3, len(plan), height_ratios=(1, 1, 1.2))
    overview = [fig.add_subplot(grid[row, :]) for row in range(2)]
    detail = [fig.add_subplot(grid[2, index]) for index in range(len(plan))]
    cursor = 0.0
    for index, (stage, duration) in enumerate(zip(plan, durations)):
        delay = float(stage["delay_before_s"])
        displayed_delay = min(delay, gap_width) if compress_delay else delay
        if index and delay:
            for axis in overview:
                axis.axvspan(cursor*1e3, (cursor+displayed_delay)*1e3,
                             color="gray", alpha=0.15)
                axis.text((cursor+displayed_delay/2)*1e3, 0.97,
                          f"Output off\n{delay:g} s" + (" (compressed)" if displayed_delay < delay else ""),
                          transform=axis.get_xaxis_transform(), ha="center", va="top", fontsize=8)
            cursor += displayed_delay
        for row, ch in enumerate(channels):
            cfg = stage["configs"][ch][0]
            modes = cfg[4]
            starts = cfg[5] if len(cfg) > 5 else [0.0]*len(cfg[3])
            stops = cfg[6] if len(cfg) > 6 else cfg[3]
            elapsed, times, volts = 0.0, [], []
            for a, b, dt, mode, ms, me in zip(cfg[1], cfg[2], cfg[3], modes, starts, stops):
                times.extend([elapsed, elapsed+dt]); volts.extend([a, b])
                if mode:
                    x = np.asarray([elapsed+ms, elapsed+me])
                    y = [a+(b-a)*ms/dt, a+(b-a)*me/dt]
                    for axis, tx in ((overview[row], (cursor+x)*1e3), (detail[index], x*1e6)):
                        axis.plot(tx, y, color="tab:orange", linewidth=4, alpha=0.6,
                                  label="Acquisition" if "Acquisition" not in axis.get_legend_handles_labels()[1] else None)
                elapsed += dt
            color = ("tab:blue", "tab:red")[row]
            overview[row].plot((cursor+np.asarray(times))*1e3, volts, color=color)
            overview[row].axvline(cursor*1e3, color="black", linestyle=":", linewidth=0.8)
            overview[row].text((cursor+duration/2)*1e3, 0.04, f"#{index+1} {stage['label']}",
                               transform=overview[row].get_xaxis_transform(), ha="center", fontsize=8)
            detail[index].plot(np.asarray(times)*1e6, volts, color=color, label=f"CH{ch}")
        detail[index].set_title(f"EXECUTE {index+1}: {stage['label']}")
        detail[index].set_xlabel("Local time (us)")
        detail[index].set_ylabel("Voltage (V)")
        detail[index].grid(alpha=0.3)
        detail[index].legend(fontsize=8)
        cursor += duration
    for axis, ch in zip(overview, channels):
        axis.set_ylabel(f"CH{ch} voltage (V)")
        axis.set_xlabel("Displayed time (ms; long waits compressed)" if compress_delay
                        else "Planned elapsed time (ms)")
        axis.margins(y=0.4)
        axis.grid(alpha=0.3)
    fig.suptitle(f"{title_prefix}: split executions / output-off waits\n"
                 "Planned timing only; communication overruns are not shown. Gap voltage is unspecified.")
    fig.canvas.manager.set_window_title(title_prefix)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    if show:
        plt.show()
    return fig
