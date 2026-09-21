# PMU FET entry points

[English](#english) | [中文](#中文)

## English

Files are named by test purpose. Each script can run directly; importing a module does not start a measurement.

| Entry | Purpose | Main parameters |
|---|---|---|
| [program_read.py](program_read.py) | Gate write train, wait, then measure at the read Vg/Vd; repeat the plan | program_levels, train_count, read_delay, cycles |
| [bipolar_program_read.py](bipolar_program_read.py) | Program, wait, and read under separately configured positive/negative write conditions | POS/NEG write settings and repeat counts, read Vg/Vd, read_delay |
| [sweeps/delay_sweep.py](sweeps/delay_sweep.py) | Calls bipolar_program_read over write-to-read delays and summarizes results | DELAY_TIMES |
| [sweeps/read_bias_delay_sweep.py](sweeps/read_bias_delay_sweep.py) | Sweeps read Vg, Vd, and delay; compares/ranks states and adds repeated program/read tests per bias pair | VG_READ_VALUES, VD_READ_VALUES, DELAY_TIMES, FEFET_REPEAT_N/T |

### Program/read order and configuration

The two base program/read entries use Segment Arb with roles selected by GATE_CH and DRAIN_CH. Generic standard pulse entries are in [pulse](../pulse/README.md).

The default program_read parameter structure provides one write-voltage setting; bipolar_program_read provides independent positive/negative write settings. This distinction does not describe channel count: both use two PMU channels.

Within each cycle, bipolar_program_read completes all positive program/read repetitions before all negative repetitions. One program/read operation contains a write train and one read. Pulses per train, program/read repetitions, and complete plan cycles are three separate settings.

Both sweep entries import configuration from bipolar_program_read and call its run_test(params_override=...). They inherit write conditions, positive/negative repetition counts, and cycle count, so a delay does not necessarily yield only one pair of readings. Every delay causes fresh programming; the sweep does not track one programmed state at multiple elapsed times.

Edit base program/read parameters at the top of the corresponding entry, and sweep values in sweeps. params is the single experiment configuration; sweeps pass each point through run_test(params_override=...) without modifying the imported module.

### Outputs

Base program/read tests save raw channel data, FET_Data, parameters, and related plots. Entry options control waveform previews. Sweeps additionally generate summary workbooks and plots. SAVE_DIR/SWEEP_NAME controls output locations, with shared naming and numbering rules.

The links above use the renamed script paths. Update any old paths in IDE run configurations or scripts outside this repository.

### Parameters and output switches

gate_current_range/drain_current_range in params (or the current_ranges override) select Gate/Drain current measurement ranges, not current compliance. source_compliance limits only the Source SMU current when that SMU is used. Allowable Gate/Drain voltages must be established for the device.

SAVE_WAVEFORM_PREVIEW controls extra waveform plots; PREVIEW_ONLY selects preview versus measurement.

Parameter source: [manual limits and mode reference (Chinese)](../../../reference/manuals/PARAMETER_LIMITS.md).

### Floating-Gate read

Both base entries expose `float_gate_during_read` (default False) and `ssr_switch_time` (default 50 us). Gate remains connected during programming and read_delay. It opens in a baseline guard segment before the Drain read pulse and closes in a guard segment after the read pulse/rest. Drain remains connected. Both channels receive the additional guard segments.

read_gate_voltage does not force the isolated Gate voltage. Gate V/I/timestamps and inferred source current are unavailable; saved Gate status is not_acquired_ssr_open. Filenames use VgFloat. Parameters record the flag and guard duration. read_delay is unchanged; the first guard adds 50 us before Drain read onset, and both guards add to total waveform time. The instrument minimum transition-segment duration is 25 us. Split software execution floats Gate only within the read waveform, not throughout the host wait. Previews show isolation as gray gaps, and waveform tables include SSR states. Sweep entries inherit these options through the base params.


Parameter API: [standalone and workflow configuration](../README.md#standalone-and-workflow-configuration).

## 中文

### PMU FET 测试入口

本目录按测试用途命名。每个脚本可以直接运行；导入模块不会启动测量。

| 入口 | 用途 | 主要参数 |
|---|---|---|
| [program_read.py](program_read.py) | Gate 写入一串脉冲，等待后设置读取 Vg/Vd 并测量，循环执行 | program_levels、train_count、read_delay、cycles |
| [bipolar_program_read.py](bipolar_program_read.py) | 分别执行正、负两组写入条件下的写入—等待—读取 | POS/NEG 写入参数及重复次数、读取 Vg/Vd、read_delay |
| [sweeps/delay_sweep.py](sweeps/delay_sweep.py) | 调用 bipolar_program_read，扫描写入至读取的等待时间并汇总 | DELAY_TIMES |
| [sweeps/read_bias_delay_sweep.py](sweeps/read_bias_delay_sweep.py) | 扫描读取 Vg、Vd、delay，比较状态电流并排序；每对偏压另做重复写读测试 | VG_READ_VALUES、VD_READ_VALUES、DELAY_TIMES、FEFET_REPEAT_N/T |

## 写读顺序与配置

两个基础写读入口使用 Segment Arb，Gate/Drain 由 GATE_CH 和 DRAIN_CH 指定。
通用普通脉冲入口已移至 [pulse](../pulse/README.md)。

program_read 的默认参数结构提供一组写入电压；bipolar_program_read 提供独立的
正、负写入配置。这一区别与使用几个 PMU 通道无关，两者都使用两路 PMU。

bipolar_program_read 在每轮中先完成所有正向写读重复，再完成所有负向写读重复。
每次写读包含一串写入脉冲和一次读取；脉冲串长度、写读重复次数、整个过程的循环
次数是三个不同参数。

两个扫描入口从 bipolar_program_read 导入配置，并调用其 run_test(params_override=...)。它们继承基础
脚本中的写入条件、正负写读重复次数和循环次数；每个 delay 不一定只得到一对读数。
每个 delay 都重新执行写入，不是对同一次写入连续跟踪不同等待时间。

修改基础写读参数应在对应入口顶部进行；扫描取值在 sweeps 中配置。
params 是唯一的实验参数配置；扫描脚本通过 run_test(params_override=...) 传入每个测点，不再修改导入模块。

## 输出

基础写读测试保存原始通道数据、FET_Data、参数及相关图形；波形预览由入口中的
选项控制。扫描另外生成汇总表和图。输出位置沿用各脚本的 SAVE_DIR/SWEEP_NAME
设置，文件继续使用公共命名和编号规则。

重命名后的脚本路径如上；IDE 运行配置或库外脚本中的旧路径需要相应更新。

## 参数与输出开关

params 内的 gate_current_range/drain_current_range（或 current_ranges 覆盖值）是 Gate/Drain 电流测量档，不是限流；source_compliance 仅在使用 Source SMU 时限制该 SMU 电流。器件允许的 Gate/Drain 电压需按器件确定。

SAVE_WAVEFORM_PREVIEW 是额外波形图开关，PREVIEW_ONLY 是预览/实测选择。

参数依据：[手册限制与模式速查](../../../reference/manuals/PARAMETER_LIMITS.md)。

参数接口：[独立运行与工作流配置](../README.md#独立运行与工作流配置)。

## Gate 浮空读取
两个基础写读入口均提供 `float_gate_during_read = False` 和 `ssr_switch_time = 50e-6`。改为 True 后，写入及原有 read_delay 期间 Gate 仍连接；随后在基线处断开 Gate，经过 50 µs 切换段后施加 Drain 读取脉冲，读取结束及原有 read idle 后重新闭合 Gate，并留出 50 µs 切换段，再开始下一轮。Drain 始终连接，两个通道使用相同分段时序。

开启后 read_gate_voltage 不作为实际栅压施加；Gate V/I/时间戳不采集并保存为空值，状态注明 `not_acquired_ssr_open`，推算源电流也为缺测。文件名使用 VgFloat，参数表保存开关及切换时间。新增两个切换段计入波形总时长；read_delay 本身不变，因此 Drain 读脉冲比原先多等待一个切换段。切换段的仪器最低要求为 25 µs，默认 50 µs。软件分次执行只在读波形内部浮空 Gate，不保证整个主机等待期间连续浮空。

预览灰色区间表示 SSR 断开，电压曲线留空；数值波形表保存 SSR 状态。两个扫描入口通过基础 params 继承此选项。
