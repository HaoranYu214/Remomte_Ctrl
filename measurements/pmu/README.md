# PMU experiments

[English](#english) | [中文](#中文)

## English

Pulse definitions stay in these experiment files. Shared execution, parsing, preview and plotting live in [src/keithley4200/pmu](../../src/keithley4200/pmu/README.md).

| Directory | Experiments |
|---|---|
| [fe_cap](fe_cap/README.md) | PV, PUND, retention, NLS and fatigue |
| [ftj](ftj/README.md) | Program/read voltage, width and pulse-count tests |
| [fet](fet/README.md) | Coordinated Gate/Drain FeFET Segment Arb program/read |
| [programmed](programmed/README.md) | FORC and NLS sweeps |
| [pulse](pulse/README.md) | Standard Pulse trains and amplitude sweeps |

Most entries use Segment Arb; pulse uses standard Pulse timing. PMU current ranges are measurement ranges, not SMU current compliance. Available ranges depend on RPM and source range; see the [parameter reference](../../reference/manuals/PARAMETER_LIMITS.md).

### Standalone and workflow configuration

Base FTJ/FET tests, PV2, triangular/square PUND and retention PV/PUND expose plain run_test functions. Edit top-level params for standalone use; pass partial params_override for a single call. Defaults are copied, unknown keys rejected, and parameters passed explicitly to local waveform builders. Waveform helpers taking parameters expect a complete dictionary.

~~~python
from measurements.pmu.fet import program_read

parameters = {**program_read.params, "read_delay": 0.01}
program_read.preview_waveform(parameters=parameters)

# Real acquisition:
result = program_read.run_test(
    params_override={"read_delay": 0.01},
    save_dir="data/example",
    preview_only=False,
)
~~~

FTJ build_waveform returns a dictionary containing seq_configs and execution/analysis metadata; no global waveform cache is kept. Hardware/output keywords include inst, channels, segarb_options and save_dir where supported. FET channel order is Gate, Drain.

Acquisition returns output_path, final params, accepted_current_ranges and settings. Preview returns its result/parameters with output_path=None, without acquisition settings. Function signatures and workbook sheets remain experiment-specific: FTJ uses current_ranges, FET also has gate_current_range/drain_current_range, PV/PUND uses Irange1/2. Endurance has separate cycle/PV2/PUND overrides. Standard Pulse, FORC and NLS retain their own runners.

### Accepted-range persistence

PV2 and triangular/square PUND may retry the entire waveform at another fixed current range. Accepted Irange1/2 values are written back to the entry and active workflow starting settings; other run overrides are not persisted. Failed candidates, preview and dry-run do not update real ranges. Source updates preserve other settings/comments; a write failure warns while allowing data saving.

The leaf entry persists accepted ranges after acquisition. The workflow receives them only after run_test returns successfully, so later analysis/save failure may leave leaf defaults updated but workflow defaults unchanged.

Measurements remain sequential. Calling a preview-capable entry does not make every wrapper preview-capable; check each runner.

## 中文

脉冲定义保留在各实验文件；公共执行、解析、预览和绘图在 [src/keithley4200/pmu](../../src/keithley4200/pmu/README.md)。

| 目录 | 实验 |
|---|---|
| [fe_cap](fe_cap/README.md) | PV、PUND、retention、NLS、疲劳 |
| [ftj](ftj/README.md) | 写读电压、脉宽和脉冲数测试 |
| [fet](fet/README.md) | Gate/Drain 协同的 FeFET Segment Arb 写读 |
| [programmed](programmed/README.md) | FORC、NLS 扫描 |
| [pulse](pulse/README.md) | 普通 Pulse 脉冲串与幅值扫描 |

大部分入口使用 Segment Arb；pulse 使用普通 Pulse 的时间定义。PMU 电流档是测量量程，不是 SMU 限流。可选档位取决于 RPM 和源电压档，见[参数速查](../../reference/manuals/PARAMETER_LIMITS.md)。

### 独立运行与工作流配置

基础 FTJ/FET、PV2、三角/方波 PUND、retention PV/PUND 使用普通 run_test 函数。独立运行修改顶部 params；单次调用使用部分 params_override。默认值会被复制，未知参数会报错，参数显式传给本地波形生成函数。接收 parameters 的波形函数需要完整字典。

~~~python
from measurements.pmu.fet import program_read

parameters = {**program_read.params, "read_delay": 0.01}
program_read.preview_waveform(parameters=parameters)

# Real acquisition:
result = program_read.run_test(
    params_override={"read_delay": 0.01},
    save_dir="data/example",
    preview_only=False,
)
~~~

FTJ 的 build_waveform 返回包含 seq_configs 和执行/分析信息的字典，不保留全局波形缓存。支持的硬件/输出关键字包括 inst、channels、segarb_options、save_dir，具体看函数签名。FET 通道顺序为 Gate、Drain。

实测返回 output_path、最终 params、accepted_current_ranges、settings；预览返回预览结果和参数，output_path=None，不返回实测 settings。各实验的签名和表格不必完全一样：FTJ 用 current_ranges，FET 还有 gate_current_range/drain_current_range，PV/PUND 用 Irange1/2。Endurance 有独立 cycle/PV2/PUND 覆盖项；普通 Pulse、FORC、NLS 保留自己的入口。

### 接受量程的持久化

PV2、三角/方波 PUND 可能换固定档重放完整波形。接受的 Irange1/2 回写实验和当前工作流起始设置，其他覆盖参数不持久化。失败候选、预览、dry-run 都不改真实量程默认值。源码更新保留其他参数和注释，写失败会警告但允许继续保存数据。

底层入口在采集后保存接受量程；工作流只有在 run_test 成功返回后才收到它。因此后续分析/保存失败时，可能底层已更新而工作流尚未更新。

测试仍顺序执行。底层支持预览不意味着所有外层调用也支持，需查看各自执行函数。
