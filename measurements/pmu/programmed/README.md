# FORC and NLS sweeps

[English](#english) | [中文](#中文)

## English

These entries define their own waveforms and sweep plans, sharing PMU execution/analysis.

| Entry | Plan |
|---|---|
| [FORC.py](FORC.py) | One execution per reversal voltage |
| [FORC_1excute.py](FORC_1excute.py) | Multiple reversal curves in one SARB execution, separated for analysis |
| [NLS_1C_switch.py](NLS_1C_switch.py) | Single NLS write/read and preview |
| [NLS_1C_switch_list.py](NLS_1C_switch_list.py) | Dwell_list × Vsquare_list through the single entry |

FORC Vmax is relative to offset and requires -Vmax <= Vr < Vmax. full_sweep_time scales with excursion, so reversal levels near +Vmax may yield very short segments. Combined curves must fit the segment/sample budget.

Edit each entry's top settings and check its preview behavior before running. NLS Dwell is a plateau duration; Vsquare is the write level.

### NLS timing

TotalDelay runs from the end of the preset/prepost falling edge to the first half-PUND read rising edge. Dwell is the disturb plateau. Add an unmeasured baseline hold:

~~~text
PaddingDelay = TotalDelay - 2*Delaytime - 2*Rt_s - Dwell
~~~

Both waits and disturb edges count; the wait between half-PUND reads remains unchanged. Reject insufficient time before acquisition. Omit zero padding; nonzero padding must meet the configured segment limits (default 10 V: 20 ns to 1 s, with 10 ns hardware resolution). Save TotalDelay/PaddingDelay in parameters and batch summaries. This fixes time since preset; disturb-to-read time still varies with pulse width.

MeasureSquare=False disables acquisition of the square segment, not the applied pulse.

See the [manual reference](../../../reference/manuals/PARAMETER_LIMITS.md) for mode and timing limits.

## 中文

这些入口自己定义波形与扫描计划，共用 PMU 执行/分析。

| 入口 | 计划 |
|---|---|
| [FORC.py](FORC.py) | 每个反转电压单独执行 |
| [FORC_1excute.py](FORC_1excute.py) | 多条反转曲线合并一次 SARB，分析时拆分 |
| [NLS_1C_switch.py](NLS_1C_switch.py) | 单次 NLS 写读及预览 |
| [NLS_1C_switch_list.py](NLS_1C_switch_list.py) | 调用单次入口扫描 Dwell_list × Vsquare_list |

FORC 的 Vmax 相对 offset，反转电压要求 -Vmax <= Vr < Vmax。full_sweep_time 随跨度换算，因此接近 +Vmax 的反转点可能产生很短的段。合并曲线还需满足段数/采样预算。

运行前修改顶部设置并确认各入口预览行为。NLS 的 Dwell 是平台时间，Vsquare 是写入电平。

### NLS 时间定义

TotalDelay 从 preset/prepost 下降沿结束计时，到第一个 half-PUND 读取上升沿开始。Dwell 为扰动平台时间，额外加入不采集的基线保持：

~~~text
PaddingDelay = TotalDelay - 2*Delaytime - 2*Rt_s - Dwell
~~~

两段等待及扰动边沿均计入，half-PUND 两次读取间等待不变。总时间不足会在采集前拒绝；补齐为零时省略，非零时需符合所用段长限制（默认 10 V 档为 20 ns 到 1 s，硬件分辨率 10 ns）。参数和批量汇总保存 TotalDelay/PaddingDelay。固定的是 preset 后经过时间，扰动结束至读取的时间仍随脉宽变化。

MeasureSquare=False 只关闭方形段采集，不取消实际脉冲。

模式和时间限制见[手册速查](../../../reference/manuals/PARAMETER_LIMITS.md)。
