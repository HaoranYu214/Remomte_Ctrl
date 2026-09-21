# FORC and NLS sweeps

[English](#english) | [中文](#中文)

## English

| File | Purpose |
|---|---|
| [FORC.py](FORC.py) | Executes a separate first-order reversal curve for each reversal voltage |
| [FORC_1excute.py](FORC_1excute.py) | Combines multiple reversal curves into one SARB execution and separates them for analysis |
| [NLS_1C_switch.py](NLS_1C_switch.py) | Configurable single NLS program/read test and preview |
| [NLS_1C_switch_list.py](NLS_1C_switch_list.py) | Calls the single-test entry over Dwell_list × Vsquare_list |

FORC Vmax is relative to offset. The reversal condition -Vmax ≤ Vr < Vmax is an algorithmic constraint. full_sweep_time is scaled to each voltage excursion, so reversal levels close to +Vmax can create very short actual segments. The combined version must also fit a single execution's segment and sampling-point budgets.

For NLS, Dwell is the square write plateau duration and Vsquare is the write level. MeasureSquare selects whether that part is acquired; disabling acquisition still outputs the pulse.

Parameter source: [manual limits and mode reference (Chinese)](../../../reference/manuals/PARAMETER_LIMITS.md).

### Fixed NLS readout interval

`TotalDelay` (seconds, default 0.11) runs from the end of the preset/prepost falling edge to the start of the first half-PUND read rising edge. `Dwell` is the disturb flat-top duration. An unmeasured baseline hold is inserted after the disturb pulse: `PaddingDelay = TotalDelay - 2*Delaytime - 2*Rt_s - Dwell`. The baseline is `offset` (currently 0 V). Both existing waits and disturb edges count toward the total; `Delaytime` between the two half-PUND read pulses is unchanged.

Insufficient total time is rejected before measurement. Zero padding is omitted; nonzero padding must meet the default 10 V range segment duration limit of 20 ns–1 s. Hardware timing is limited by its 10 ns resolution. Parameter sheets and the batch summary save `TotalDelay` and `PaddingDelay`. Fixing this interval controls elapsed time since preset, while the time from the end of disturbance to readout still varies with pulse width.

## 中文

### FORC 与 NLS 扫描

| 文件 | 用途 |
|---|---|
| [FORC.py](FORC.py) | 每个反转电压单独执行一条一阶反转曲线 |
| [FORC_1excute.py](FORC_1excute.py) | 将多条反转曲线合并为一次 SARB 执行，再分离分析 |
| [NLS_1C_switch.py](NLS_1C_switch.py) | 提供可配置的单次 NLS 写入/读回及预览 |
| [NLS_1C_switch_list.py](NLS_1C_switch_list.py) | 调用前者扫描 Dwell_list × Vsquare_list |

FORC 的 Vmax 是相对 offset 的幅值；反转电压满足 -Vmax ≤ Vr < Vmax 是算法约束。full_sweep_time 按电压跨度换算分支时间，所以靠近 +Vmax 的曲线可能出现很短的实际段。合并版本还须符合单次段数与采样点预算。

NLS 的 Dwell 是方形写入平台时间，Vsquare 为写入电平；MeasureSquare 控制这部分是否采集，关闭采集仍输出脉冲。

参数依据：[手册限制与模式速查](../../../reference/manuals/PARAMETER_LIMITS.md)。

### NLS 固定读出间隔

`TotalDelay`（秒，默认 0.11）从 preset/prepost 下降沿结束计时，到 half-PUND 第一个读取上升沿开始。方波平台为 `Dwell`；在方波后增加不采集的基线等待段：`PaddingDelay = TotalDelay - 2*Delaytime - 2*Rt_s - Dwell`。基线为 `offset`，当前为 0 V；原有两段等待和扰动边沿均计入总间隔，half-PUND 两次读取之间的 `Delaytime` 不变。

总间隔不足会在测试前报错；补偿为零时省略新增段，非零补偿须满足默认 10 V 档 20 ns–1 s 段长限制。实际仪器时间精度受 10 ns 分辨率限制。参数表保存 `TotalDelay` 和 `PaddingDelay`；批量扫描汇总表也保存这两项。固定此间隔可控制 preset 后的总等待时间，但不同脉宽仍会对应不同的扰动结束后等待时间。
