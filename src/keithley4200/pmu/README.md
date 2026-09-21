# PMU reusable layer

[English](#english) | [中文](#中文)

## English

- `session.py`: safe PMU connection and output shutdown lifecycle.
- `pmu_tests.py`: reusable 4225-PMU and Segment Arb commands.
- `current_range.py`: fixed-range assessment and automatic retry helpers.
- `data_processing.py`: PMU buffer parsing and analysis helpers.
- `plotting_utils.py`: common PMU plotting utilities.
- `fet_three_terminal_common.py`: shared execution helpers for three-terminal
  FET pulse experiments.

The PMU package imports the common VISA implementation from
`keithley4200.transport`. Experiment-specific pulse sequences stay in
runnable entries under `measurements/pmu`.

## Usage and parameters

The usual call sequence is: open PMUSession → construct sequences → execute_segARB_test → wait for completion/read data → turn outputs off → save and analyze. Automatic current_range retries reapply the entire waveform. A current measurement range is not current compliance, and segment-count validation does not imply that all voltage/timing bounds have been checked. The reference below explains mode codes, hardware conditions, and software limits.

Parameter source: [manual limits and mode reference (Chinese)](../../../reference/manuals/PARAMETER_LIMITS.md).

### NLS timing

[`timing.py`](timing.py) documents and validates the fixed preset-to-read interval and baseline padding. NLS waveform definitions remain in the measurement entries.

### Optional SSR

`configure_segARB_sequence(..., ssr=None)` accepts an optional 0/1 array. Omit it to send no SSR commands and retain the reset default (closed). For execution configs append SSR as the eighth tuple field:

`(seq_id, start_v, stop_v, times, meas_types, meas_start, meas_stop, ssr)`

Unused measurement arrays may be None. SSR=0 isolates the channel; SSR=1 connects it. KXCI 7-46/7-47 requires at least 25 us for each segment where the relay changes state. Internal transitions and executed sequence/loop boundaries are checked. Constant-channel alignment preserves a constant SSR state; changing SSR arrays require explicit aligned timing. Arrays longer than 128 values use SSR:ADD.


### Validation and failure behavior

SARB time and measurement-window commands retain 12 significant digits; hardware timing resolution still applies. Automatic alignment only expands a companion whose voltage is constant across the entire sequence. Different plateau levels must be aligned explicitly.

The executor checks array shapes, measurement windows, stored segment counts, and SSR transitions. It does not validate every voltage, timing, sequence-plan, or DUT limit. Its completion polling currently has no total timeout and retries query errors; the VISA timeout only limits each communication call. Stop an unresponsive run with Ctrl+C to enter session cleanup.

Legacy save helpers return False on failure instead of raising. Standard Pulse callers currently do not check that flag, so a completion message alone does not confirm a workbook was saved.

## 中文

### PMU 公共层

- session.py：PMU 连接及输出关闭的生命周期。
- pmu_tests.py：4225-PMU 与 Segment Arb 公共命令。
- current_range.py：固定电流档评估与自动重测。
- data_processing.py：PMU 缓冲读取、解析与分析。
- plotting_utils.py：公共绘图工具。
- fet_three_terminal_common.py：三端 FET 脉冲实验的公共执行辅助。

通信统一使用 keithley4200.transport。具体实验脉冲仍放在 measurements/pmu 的可运行入口中。

## 使用与参数
推荐调用顺序是建立 PMUSession → 构造序列 → execute_segARB_test → 等待结束/读取 → 关输出 → 保存分析。current_range 的自动重试会重新输出整个波形。电流测量档不是限流；段数校验也不代表全部电压/时间边界已经校验。模式码、硬件条件及代码限制见下方速查。

参数依据：[手册限制与模式速查](../../../reference/manuals/PARAMETER_LIMITS.md)。

## NLS 时间参数

[`timing.py`](timing.py) 集中说明并校验 NLS 从 preset 到读取的固定总间隔及补偿等待；波形定义仍保留在实验入口。

## 可选逐段继电器控制

不传 `ssr` 时不额外发送 SSR 指令，初始化后的默认值为 1（闭合）。启用时把 0/1 数组作为序列元组第八项：

`(seq_id, start_v, stop_v, times, meas_types, meas_start, meas_stop, ssr)`

未使用的测量数组可填 None。SSR=0 断开通道，SSR=1 闭合。KXCI 7-46/7-47 要求继电器切换所在段至少 25 µs；执行器校验内部、跨序列和循环边界的切换。恒压通道自动对齐仅保留恒定 SSR，变化的 SSR 需要显式对齐时序。超过 128 项用 SSR:ADD 续传。浮空不等于驱动 0 V。

### 校验与异常行为

SARB 时间和测量窗指令保留 12 位有效数字，实际仍受硬件时间分辨率限制。自动对齐只扩展整条序列电压恒定的伴随通道；各平台电平不同的波形需显式对齐。

执行器校验数组形状、测量窗、存储段数和 SSR 切换，但不覆盖全部电压、时序、执行计划或器件边界。目前结束状态轮询没有总超时，并会重试查询异常；VISA timeout 仅限制单次通信。不响应时可 Ctrl+C 进入会话清理。

旧保存函数失败时返回 False，不抛异常。普通 Pulse 入口目前没有检查这个返回值，因此完成提示本身不能证明工作簿已保存。
