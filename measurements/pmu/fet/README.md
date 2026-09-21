# PMU FeFET program/read

[English](#english) | [中文](#中文)

## English

Gate and Drain use two coordinated PMU channels; Source SMU settings are handled separately. These pulse tests differ from [SMU DC FET curves](../../smu/3terminal/README.md).

| Entry | What to edit |
|---|---|
| [program_read.py](program_read.py) | Write levels/train count, read biases/delay and cycles |
| [bipolar_program_read.py](bipolar_program_read.py) | Independent positive/negative write settings and repetition counts |
| [sweeps](sweeps/README.md) | Delay or read-bias/delay grids and extra repetitions |

In each bipolar cycle, all positive program/read repetitions precede all negative repetitions. Pulses per write train, program/read repetitions and complete cycles are different settings. Both base entries use two PMU channels; their names describe write conditions, not channel count.

Edit params and the hardware/output settings, preview the local sequence, then use run_test with preview_only=False for acquisition. Partial overrides are copied for that run; see the [parameter API](../README.md#standalone-and-workflow-configuration). Outputs include raw channels, FET_Data, parameters and plots; SAVE_WAVEFORM_PREVIEW controls extra command previews.

gate_current_range/drain_current_range are measurement ranges. source_compliance limits the Source SMU when used. Inferred Source current is derived from Gate/Drain currents, not a separate measured Is.

### Floating Gate and long waits

float_gate_during_read defaults to False. When enabled, Gate stays connected during programming/read_delay, opens in a baseline guard before Drain reading, and reconnects after the read/rest. ssr_switch_time defaults to 50 us; transition segments need at least 25 us. Drain stays connected.

An isolated Gate is not forced to read_gate_voltage. Gate V/I/time and inferred Source current are unavailable; saved status is not_acquired_ssr_open. Names use VgFloat, tables record SSR, and preview shows isolation. Guards add time beyond read_delay.

For read_delay above 1 s, program/read uses split execution with a host wait and outputs off. Timing includes configuration overhead. Floating Gate applies within the read waveform, not throughout the host wait.

Each sweep point programs the device again, inheriting unspecified base settings; it does not follow one programmed state continuously.

## 中文

Gate、Drain 使用两路协同 PMU，Source SMU 单独配置。这些脉冲测试与 [SMU 直流 FET 曲线](../../smu/3terminal/README.md)不同。

| 入口 | 主要调整项 |
|---|---|
| [program_read.py](program_read.py) | 写入电平/脉冲串长度、读偏置/等待、循环次数 |
| [bipolar_program_read.py](bipolar_program_read.py) | 独立正负写入条件及重复次数 |
| [sweeps](sweeps/README.md) | 等待或读偏置/等待网格，以及附加重复 |

双极性测试每轮先完成全部正向写读，再完成全部负向写读。每串脉冲数、写读重复次数和完整循环次数是不同设置。两个基础入口均使用两路 PMU，名称区别表示写入条件，不表示通道数量。

修改 params、硬件和输出设置，先预览本地序列，再用 run_test(preview_only=False) 实测。部分覆盖仅复制到本次调用，见[参数接口](../README.md#独立运行与工作流配置)。输出含原始通道、FET_Data、参数和图；SAVE_WAVEFORM_PREVIEW 控制额外指令预览图。

gate_current_range/drain_current_range 是测量档。source_compliance 限制所用 Source SMU 的电流。推算 Source 电流来自 Gate/Drain 电流，并非单独测得的 Is。

### 浮栅和长等待

float_gate_during_read 默认 False。启用后，Gate 在写入及 read_delay 中接通，在 Drain 读取前的基线保护段断开，读出/休息结束后重新接通。ssr_switch_time 默认 50 us，切换段至少 25 us；Drain 始终接通。

隔离的 Gate 不受 read_gate_voltage 强制。Gate V/I/时间及推算 Source 电流不可用，保存状态为 not_acquired_ssr_open。文件名使用 VgFloat，表格记录 SSR，预览显示隔离。保护段在 read_delay 之外增加时间。

read_delay 超过 1 s 时拆分写/读执行，中间关闭输出并由主机等待，实际时间含重配置开销。浮栅只发生在读波形内，不贯穿主机等待。

扫描中每个点重新写入并继承基础脚本未覆盖的设置，不是连续追踪同一已写状态。
