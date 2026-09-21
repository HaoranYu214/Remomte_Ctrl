# PMU experiments

[English](#english) | [中文](#中文)

## English

| Directory | Purpose |
|---|---|
| [fe_cap](fe_cap/README.md) | PV, triangular/square PUND, NLS, and endurance cycling |
| [ftj](ftj/README.md) | Read resistance after programming; vary write voltage, pulse width, or pulse count |
| [pulse](pulse/README.md) | Standard Pulse mode: two-channel pulse trains and amplitude sweeps |
| [fet](fet/README.md) | Coordinated Gate/Drain SegArb FeFET program/read tests |
| [programmed](programmed/README.md) | FORC and NLS parameter sweeps |

Most entries use Segment Arb. pulse/pulse_train.py and pulse/pulse_sweep.py use standard pulse mode, which has different timing definitions. Irange/CURRENT_RANGES specifies a current measurement range, not SMU-style current compliance. Select ranges according to the RPM configuration and 10/40 V source range; INIT defaults to the 10 V range.

The shared parameter guide also explains modes 0-4, LOAD/LLEC, save switches, and software waits.

Parameter source: [manual limits and mode reference (Chinese)](../../reference/manuals/PARAMETER_LIMITS.md).

### Standalone and workflow configuration

The eight base FTJ tests, both base FET program/read tests, PV2, triangular/square PUND, retentionPV, and retentionPUND use plain functions. Each file keeps its editable params, hardware/output settings, waveform builder, analysis, and run_test. There is no Measurement class, configuration factory, or duplicate forwarding function. Pulse design remains in the measurement file.

    from measurements.pmu.fet import program_read

    # Execute with partial overrides. Missing keys use the file defaults.
    result = program_read.run_test(
        params_override={"read_delay": 0.01, "float_gate_during_read": True},
        save_dir="data/example",
        preview_only=False,
    )
    print(result["output_path"])
    print(result["params"])

    # Preview using a complete parameter dictionary, without opening hardware.
    parameters = {**program_read.params, "read_delay": 0.01}
    program_read.preview_waveform(parameters=parameters)

Standalone: edit top-level params and run the file. Workflow: call run_test(params_override=...) directly with partial or complete overrides. run_test copies defaults and explicitly passes this run's parameters to subsequent functions. Unknown parameter names raise an error. Helpers accept a complete parameters dictionary, or use file defaults when it is omitted.

FTJ build_waveform(parameters=...) returns a plain dictionary containing seq_configs and execution/analysis metadata. A run builds it once and passes it to execution, preview, or saving; no global waveform cache is retained. FET channel order is Gate, Drain. Use inst, channels, segarb_options, and save_dir for run settings.

Acquisition returns output_path, final params, accepted_current_ranges, and settings (instrument, channels, and Segment Arb options). Preview returns the preview result and parameters with output_path=None; it does not return acquisition settings. PREVIEW_ONLY selects preview; pass preview_only=False to acquire. Accepted range persistence is the explicit exception described below; other overrides do not rewrite file defaults.

The instrument still runs sequentially. This API covers the entries above and their workflow/sweep callers. Standard Pulse, FORC, NLS, and SMU retain their existing entrypoints.

### Remember accepted current ranges

After PV2, triangular PUND, or square PUND accepts automatic current ranges, Irange1/Irange2 are written back to that test file's top-level params. The active PV/PUND workflow also updates its own starting-range fields, for subsequent points and future launches. Voltage, timing, area, and other parameters are not written back. Explicit range overrides still select the starting ranges.

Only accepted ranges are remembered; failed or unstable acquisitions do not persist candidate ranges. Preview does not write defaults. dry_run never rewrites real starting ranges, even when synthetic data saving is enabled. Updates preserve comments and other code. A write failure reports a warning and allows measurement data saving to continue.


### API boundaries

The shared structure is file defaults → waveform construction → session/execution → readout/analysis → saved parameters. It does not mean every entry has identical keyword names or workbook sheets. FTJ fixed ranges use current_ranges; FET also exposes gate_current_range/drain_current_range in params; PV/PUND uses Irange1/Irange2. Analysis sheets remain specific to each experiment. Endurance now exposes run_test with three parameter-override dictionaries. Its local PV2/triangular PUND waveforms match the standalone entries, and it reuses their analysis with fixed-range acquisitions.

A leaf PV/PUND entry persists accepted ranges immediately after acquisition. Its workflow receives those ranges only when run_test returns successfully. If later analysis or saving raises, the leaf defaults may already be updated while workflow defaults retain their previous values.

## 中文

### PMU 实验

| 目录 | 实验用途 |
|---|---|
| [fe_cap](fe_cap/README.md) | PV、三角/方波 PUND、NLS、疲劳循环 |
| [ftj](ftj/README.md) | 写入后读阻，改变写电压、脉宽或脉冲次数 |
| [pulse](pulse/README.md) | 普通 Pulse 模式的双通道脉冲串与幅值扫描 |
| [fet](fet/README.md) | Gate/Drain 配合的 SegArb FeFET 写读 |
| [programmed](programmed/README.md) | FORC、NLS 参数扫描 |

大部分入口使用 Segment Arb；pulse/pulse_train.py 和 pulse/pulse_sweep.py 使用普通脉冲模式，两者的时间定义不同。Irange/CURRENT_RANGES 是电流测量档，不是 SMU 式电流限流。需要按 RPM 和 10/40 V 档选择；默认 INIT 为 10 V 档。

公共参数表还解释了模式 0–4、LOAD/LLEC、保存开关和软件等待。

参数依据：[手册限制与模式速查](../../reference/manuals/PARAMETER_LIMITS.md)。

## 独立运行与工作流配置

FTJ 的 8 个基础测试、FET 的两个基础写读测试，以及 PV2、三角/方波 PUND、retentionPV、retentionPUND 都使用普通函数。每个文件保留顶部 params、设备与保存设置、波形构建、分析和 run_test。没有 Measurement 类、配置工厂或同名转发函数；脉冲设计仍在测试文件中。

    from measurements.pmu.fet import program_read

    # Execute with partial overrides. Missing keys use the file defaults.
    result = program_read.run_test(
        params_override={"read_delay": 0.01, "float_gate_during_read": True},
        save_dir="data/example",
        preview_only=False,
    )
    print(result["output_path"])
    print(result["params"])

    # Preview using a complete parameter dictionary, without opening hardware.
    parameters = {**program_read.params, "read_delay": 0.01}
    program_read.preview_waveform(parameters=parameters)

单独运行：编辑文件顶部 params，然后直接运行该文件。workflow：直接调用 run_test(params_override=...)，可以覆盖部分或全部参数。run_test 复制默认参数，后续函数显式接收本次 parameters；参数拼写错误会报错。辅助函数的 parameters 应传完整字典，省略时使用文件默认值。

FTJ 的 build_waveform(parameters=...) 返回普通字典，包含 seq_configs 和执行/分析所需的信息。运行时构建一次，再传给执行、预览或保存函数，不保留全局波形缓存。FET 的 channels 顺序为 Gate、Drain。设备、通道、选项、路径等用 inst、channels、segarb_options、save_dir 关键字传入。

实测返回 output_path、最终 params、accepted_current_ranges 和 settings（设备、通道、Segment Arb 选项）。预览返回预览结果和参数，output_path=None，不返回实测 settings；PREVIEW_ONLY 为真时只预览，可传 preview_only=False 执行测量。量程的文件回写是下面说明的明确例外，其余覆盖参数不改写默认文件。

仪器仍按单台设备顺序执行。此次接口覆盖上述测试及其 workflow/扫描调用；普通 Pulse、FORC、NLS 和 SMU 保持原有入口。

## 自动量程回写

PV2、三角 PUND、方波 PUND 在自动量程检查接受后，将 Irange1/Irange2 写回各自测试文件顶部的 params。当前运行的 PV/PUND workflow 也会更新自己的默认量程字段，后续测点和重新启动都会沿用。电压、时序、面积等其他参数不会回写。显式传入新的量程仍可覆盖起始值。

只有被接受的量程会保存；未稳定或采集失败不会写入候选档位。预览不回写；dry_run 即使允许保存模拟数据，也不会修改真实测试文件的量程。回写保留注释和其他代码；写入失败时提示，并继续保存测量数据。

### 接口边界

共同结构是“文件默认参数 → 构建波形 → 会话与执行 → 读回/分析 → 保存参数”，不代表每个入口的关键字或工作表完全同名。FTJ 固定档通过 current_ranges 传入；FET 的 params 还提供 gate_current_range/drain_current_range；PV/PUND 使用 Irange1/Irange2。分析工作表按实验需要保留。endurance 现在提供 run_test 和三组参数覆盖入口；本地 PV2/三角 PUND 波形与独立测试一致，固定量程采集并复用其分析。

独立 PV/PUND 在采集接受量程后立即回写；workflow 要等 run_test 成功返回才收到量程。因此后续分析或保存抛错时，独立文件可能已更新，而 workflow 默认量程仍是旧值。
