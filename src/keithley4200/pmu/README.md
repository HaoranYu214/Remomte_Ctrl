# PMU shared helpers

[English](#english) | [中文](#中文)

## English

Experiment waveforms stay in [measurements/pmu](../../../measurements/pmu/README.md). This package shares execution and processing.

| Module | Purpose |
|---|---|
| [session.py](session.py) | PMU connection and output cleanup |
| [pmu_tests.py](pmu_tests.py) | Pulse/Segment Arb commands and execution |
| [data_processing.py](data_processing.py) | Buffer parsing and analysis |
| [current_range.py](current_range.py) | Fixed-range assessment and retry selection |
| [timing.py](timing.py) | NLS preset-to-read timing and padding |
| [preview.py](preview.py) | Offline voltage/time plots, windows, SSR and numeric tables |
| [plotting.py](plotting.py) | Measured plots and program/read current overlays |
| [fet_three_terminal_common.py](fet_three_terminal_common.py) | Shared PMU FET execution support |

A typical run builds the local waveform, opens PMUSession, executes it, reads buffers, turns outputs off, then analyzes/saves. Current-range retries replay the full waveform; measurement range is not current compliance.

Segment Arb configurations may include SSR as an eighth field:

~~~python
(seq_id, start_v, stop_v, times, meas_types, meas_start, meas_stop, ssr)
~~~

Omitting SSR retains reset defaults. SSR=0 isolates; SSR=1 connects. Relay transitions require at least 25 us per transition segment, including executed sequence/loop boundaries. Changing SSR patterns need explicitly aligned timing. Constant-channel alignment only expands a companion whose voltage is constant throughout its sequence.

The executor validates array shapes, measurement windows, segment counts and SSR transitions, not every hardware or DUT limit. Completion polling currently has no overall deadline and retries query errors; VISA timeout applies to individual calls. Ctrl+C enters session cleanup. Some legacy save helpers return False on failure, so callers must check their result.

See the [manual parameter reference](../../../reference/manuals/PARAMETER_LIMITS.md) and [entry parameter API](../../../measurements/pmu/README.md#standalone-and-workflow-configuration).

## 中文

实验波形保留在 [measurements/pmu](../../../measurements/pmu/README.md)，本包复用执行与处理能力。

| 模块 | 职责 |
|---|---|
| [session.py](session.py) | PMU 连接及输出清理 |
| [pmu_tests.py](pmu_tests.py) | Pulse/Segment Arb 命令和执行 |
| [data_processing.py](data_processing.py) | 缓冲解析与分析 |
| [current_range.py](current_range.py) | 固定档评估及重试选档 |
| [timing.py](timing.py) | NLS preset 到读出的时间与补齐 |
| [preview.py](preview.py) | 离线电压/时间图、测量窗、SSR 和数值表 |
| [plotting.py](plotting.py) | 实测图和写读电流叠图 |
| [fet_three_terminal_common.py](fet_three_terminal_common.py) | PMU FET 公共执行支持 |

通常先在实验内生成波形，再打开 PMUSession、执行、读缓冲、关输出、分析和保存。量程重试会重放完整波形；测量量程不等于限流。

Segment Arb 配置可增加第八项 SSR：

~~~python
(seq_id, start_v, stop_v, times, meas_types, meas_start, meas_stop, ssr)
~~~

不提供 SSR 时沿用复位默认值。SSR=0 隔离，SSR=1 接通。每个继电器切换段至少 25 us，检查也覆盖实际执行的序列与循环边界。变化的 SSR 阵列需要明确对齐时间。自动恒压通道对齐只扩展整个序列电压不变的伴随通道。

执行器检查数组形状、测量窗、段数和 SSR 切换，不覆盖全部硬件及器件限制。当前完成轮询没有整体截止时间，并重试查询错误；VISA 超时只约束单次调用。Ctrl+C 会进入会话清理。部分旧保存函数失败时返回 False，调用者需要检查。

参见[手册参数速查](../../../reference/manuals/PARAMETER_LIMITS.md)和[入口参数接口](../../../measurements/pmu/README.md#独立运行与工作流配置)。
