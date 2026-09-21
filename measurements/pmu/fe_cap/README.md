# Ferroelectric capacitor tests

[English](#english) | [中文](#中文)

## English

| File | Purpose and parameters to adjust |
|---|---|
| [PV2.py](PV2.py) | Two triangular P-V loops after conditioning; Vp, rise_time, delay_time, offset, area_cm2 |
| [PUND_tri.py](PUND_tri.py) | Triangular P/U/N/D subtraction; rise_time is one edge's duration and delay_time is the interval between pulses |
| [PUND_Squr.py](PUND_Squr.py) | Square/trapezoidal PUND; dwell_time is the plateau segment duration |
| [NLS_manually.py](NLS_manually.py) | Square write pulse with triangular readout; Vsquare, Dwell, Rt_s, MeasureSquare |
| [endurance.py](endurance.py) | Unmeasured endurance cycles, with PV2/PUND readback at cumulative cycle_counts milestones |

PV2, PUND_tri, and PUND_Squr use automatic range retries: each acquisition uses a fixed current range; an unsuitable range triggers a new acquisition at another range. Irange1/2 are the initial ranges, and the accepted ranges are saved with the measurement. The default candidate ranges target a 10 V RPM.

Some PV2 segments last 2 × rise_time. Since an individual segment is limited to 1 s, rise_time is also constrained to at most 0.5 s. PUND dwell is a plateau duration, not the width parameter of standard PULSE:TIMES.

area_cm2 is the effective device area in cm². It controls charge/polarization conversion, not instrument output. MeasureSquare=False disables acquisition of the square segment without removing the square pulse.

Parameter source: [manual limits and mode reference (Chinese)](../../../reference/manuals/PARAMETER_LIMITS.md).

### Fixed NLS readout interval

`TotalDelay` (seconds, default 0.11) runs from the end of the preset/prepost falling edge to the start of the first half-PUND read rising edge. `Dwell` is the disturb flat-top duration. An unmeasured baseline hold is inserted after the disturb pulse: `PaddingDelay = TotalDelay - 2*Delaytime - 2*Rt_s - Dwell`. The baseline is `offset` (currently 0 V). Both existing waits and disturb edges count toward the total; `Delaytime` between the two half-PUND read pulses is unchanged.

Insufficient total time is rejected before measurement. Zero padding is omitted; nonzero padding must meet the default 10 V range segment duration limit of 20 ns–1 s. Hardware timing is limited by its 10 ns resolution. Parameter sheets and the batch summary save `TotalDelay` and `PaddingDelay`. Fixing this interval controls elapsed time since preset, while the time from the end of disturbance to readout still varies with pulse width.

### Retention: split executions
- [retentionPV.py](retentionPV.py): preset, output-off wait, then two continuous PV loops; two executions.
- [retentionPUND.py](retentionPUND.py): separate Preset/P/U/N/D executions with `delay_time` between successive pulses; five executions.
- Waveforms remain in each entry. [_retention.py](_retention.py) supplies local execution, timing, checkpoint and preview support without changes to src.

These dedicated entries always split; they do not switch modes at 0.1 s. Defaults are a 1 s delay and preview-only mode. Review voltage, fixed current ranges, area and save directory before setting `PREVIEW_ONLY=False`. There is no automatic range retry. This version requires zero offset; waiting uses output-off, not guaranteed 0 V drive or verified SSR isolation.

Deadlines use the previous EXECUTE send time plus programmed duration. Transfer and configuration consume the wait budget. Unknown communication/startup latency remains: `estimated_delay_s` and `EstimatedGlobalTime_s` are host estimates, not measured hardware timing. `overrun_s` records known lateness. Raw local timestamps and Stage/Execution labels remain intact. Raw data and execution logs are checkpointed before analysis, including data already retrieved before failure/interruption. Preview shows separate executions and software gaps. PV retains PV2 integration; PUND pairs labeled branches and interpolates unequal sample counts in normalized time.


Parameter API: [standalone and workflow configuration](../README.md#standalone-and-workflow-configuration).

### Endurance: triangular cycle and readback

[endurance.py](endurance.py) keeps three editable dictionaries: params_cycle, params_pv2, and params_pund. All use Vp, offset, rise_time, delay_time, and Irange1/Irange2. The readback dictionaries also contain area_cm2; triangular PUND adds offset_ramp_time. The old rise_time_cycle/Vc/offset_c keys are now rise_time/Vp/offset.

- Fatigue: one cycle is offset → offset-Vp → offset → offset+Vp → offset. Each slope lasts rise_time. delay_time holds the baseline after each triangle; zero omits both holds. Period is 4*rise_time + 2*delay_time. These pulses are unmeasured.
- PV2: the same preset, independent delay, and two triangular loops as standalone PV2.
- PUND: the same Preset/P/U/N/D triangles as PUND_tri. delay_time sets independent unmeasured waits; offset_ramp_time sets the initial ramp. There is no dwell parameter. Only the triangle edges are measured, using the current standalone branch analysis.

cycle_counts contains cumulative fatigue milestones: [1, 10, 100] executes blocks of 1, 9, 90 cycles. PV/PUND presets and reads also affect the device but are excluded from this fatigue count. Readback uses fixed ranges without retries or range-default rewriting. Waveforms remain local to endurance and are regression-checked against the standalone entries; their analysis functions are reused with explicit parameters.

PREVIEW_ONLY=True displays one fatigue cycle plus both readback waveforms without opening hardware or creating output directories. Set it to False to measure. Workflow callers use run_test(cycle_params_override=..., pv2_params_override=..., pund_params_override=..., cycle_targets=..., save_dir=..., preview_only=False); overrides do not change file defaults.

Each readback workbook contains raw channels, Waveform, Parameters, and processed tables; filenames include voltage, rise, delay, cumulative cycles and a reserved run number. Cycle labels use the largest scheduled target to choose padding: a 1000-cycle maximum gives cycles0001 through cycles1000, for example PUNDtri_04.00V_tr50us_td50us_cycles1000_r001.xlsx. Raw data is checkpointed before analysis. One Excel summary is updated after each stage and on completion, recording status and time without output paths. Failure stops later stages and records the failed/interrupted stage. The 10 V segment/voltage/range preflight runs before fatigue starts; long-delay retention splitting is not enabled in this entry.

### Polarization figures and endurance Pr

PV2, triangular/square PUND, retention PV/PUND, and NLS now plot only I2 polarization. Raw I1/I2 measurements and both channels' analysis tables remain saved. Differential-current and raw waveform plots keep their existing data.

Endurance also saves one combined figure with three panels: PV2 delay, PV2 no delay, and triangular PUND. Each panel overlays the completed cycle counts, using the same color per cycle. A failed or interrupted run can still plot the successfully analyzed curves.

The summary stores signed Pr_positive_uC_cm2 and Pr_negative_uC_cm2 for PV2's delayed loop and triangular PUND. PV2 additionally saves Pr_positive_no_delay_uC_cm2 and Pr_negative_no_delay_uC_cm2. These are I2-based remanent polarization values on the return branches at 0 V, not peak polarization or values at offset. Bracketing samples are linearly interpolated. If the programmed branch ends exactly at zero but sampling omits that endpoint, the last two adjacent points may extrapolate by at most one voltage sample interval. Missing crossings beyond this bound remain blank. The extraction convention is recorded in Parameters.

## 中文

### 铁电电容测试

| 文件 | 用途及应修改的参数 |
|---|---|
| [PV2.py](PV2.py) | 预处理后测两圈三角 P-V；Vp、rise_time、delay_time、offset、area_cm2 |
| [PUND_tri.py](PUND_tri.py) | 三角脉冲 P/U/N/D 差分；rise_time 为单边时间，delay_time 为脉冲间等待 |
| [PUND_Squr.py](PUND_Squr.py) | 方波/梯形脉冲 PUND；额外的 dwell_time 是平台段时间 |
| [NLS_manually.py](NLS_manually.py) | 方形写入脉冲配合三角读出；Vsquare、Dwell、Rt_s、MeasureSquare |
| [endurance.py](endurance.py) | 无测量的疲劳循环，到累计 cycle_counts 节点执行 PV2/PUND 读回 |

PV2、PUND_tri、PUND_Squr 调用自动改档：每次用固定电流档采集，不合适时换档重测。Irange1/2 是初始档，实际接受的档位随测量记录保存。其候选范围默认面向 10 V RPM。

PV2 的部分实际段长为 2×rise_time，单段最长 1 s，因此 rise_time 上限还受 0.5 s 约束。PUND 的 dwell 是平台段，不是普通 PULSE:TIMES 的 width。

area_cm2 是器件有效面积，单位 cm²；它决定电荷/极化换算，不改变仪器输出。MeasureSquare=False 仅关闭方形段的采集，不取消方形脉冲。

参数依据：[手册限制与模式速查](../../../reference/manuals/PARAMETER_LIMITS.md)。

### NLS 固定读出间隔

`TotalDelay`（秒，默认 0.11）从 preset/prepost 下降沿结束计时，到 half-PUND 第一个读取上升沿开始。方波平台为 `Dwell`；在方波后增加不采集的基线等待段：`PaddingDelay = TotalDelay - 2*Delaytime - 2*Rt_s - Dwell`。基线为 `offset`，当前为 0 V；原有两段等待和扰动边沿均计入总间隔，half-PUND 两次读取之间的 `Delaytime` 不变。

总间隔不足会在测试前报错；补偿为零时省略新增段，非零补偿须满足默认 10 V 档 20 ns–1 s 段长限制。实际仪器时间精度受 10 ns 分辨率限制。参数表保存 `TotalDelay` 和 `PaddingDelay`；批量扫描汇总表也保存这两项。固定此间隔可控制 preset 后的总等待时间，但不同脉宽仍会对应不同的扰动结束后等待时间。

参数接口：[独立运行与工作流配置](../README.md#独立运行与工作流配置)。

## Retention：分次执行
- [retentionPV.py](retentionPV.py)：Preset → 关闭输出等待 → 连续双 PV 回线，共两次执行。
- [retentionPUND.py](retentionPUND.py)：Preset、P、U、N、D 分别执行，共五次；每对相邻脉冲之间按 `delay_time` 等待。
- 波形仍在各入口中定义；[_retention.py](_retention.py) 仅为这两个入口提供配置、计时、原始数据保存和预览支持，不改变 src。

独立入口固定采用软件拆分，不按 0.1 s 阈值逐点切换。默认 `delay_time=1.0` 秒、`PREVIEW_ONLY=True`；确认电压、量程、面积及输出目录后，将 `PREVIEW_ONLY=False` 运行。量程固定，不自动重测。初版要求 `offset=0`，两次执行之间为 `output_off`，不承诺驱动 0 V 或已验证的 SSR 浮空。

等待基准是上一次 EXECUTE 发送时刻加该次波形时长，至下一次 EXECUTE 发送时刻；数据读取、关闭输出和配置耗时计入等待预算。通信与硬件启动延迟无法消除，因此 `ExecutionTiming` 中的 `estimated_delay_s` 是主机估计，`overrun_s` 记录已知超时量，不能作为精确硬件时间。每批原始 `Timestamp` 保持局部值，`Stage`/`Execution` 标记来源，`EstimatedGlobalTime_s` 单独标注估计全局时间。

原始通道、参数及执行记录先保存，再进行分析；中断或失败时保留已经读回的数据。预览将各次执行分开显示，并标注软件等待。PV 使用原 PV2 的回线分析；PUND 按脉冲标签和分支配对，对点数不同的分支使用归一化时间插值。

### Endurance：三角循环与读回

[endurance.py](endurance.py) 顶部保留 params_cycle、params_pv2、params_pund 三组可编辑参数，统一使用 Vp、offset、rise_time、delay_time、Irange1/Irange2。读回另有 area_cm2，三角 PUND 另有 offset_ramp_time。旧 rise_time_cycle/Vc/offset_c 已改名为 rise_time/Vp/offset。

- 疲劳循环：每圈为 offset → offset-Vp → offset → offset+Vp → offset，每个斜坡持续 rise_time。delay_time 在每个三角后保持基线，设为 0 时省略两个等待段；周期为 4*rise_time + 2*delay_time，全程不采集。
- PV2：与独立 PV2 一致的预处理、独立 delay 和连续双圈三角读回。
- PUND：与 PUND_tri 一致的 Preset/P/U/N/D 三角脉冲。delay_time 控制独立、不采集的等待，offset_ramp_time 控制初始爬坡，没有 dwell 平台参数；只采集三角边沿，使用当前独立测试的分支分析。

cycle_counts 是累计疲劳节点：[1, 10, 100] 对应执行 1、9、90 圈。PV/PUND 的预处理与读取也会作用于器件，但不计入此疲劳圈数。读回固定量程，不自动重测或回写量程。波形保留在 endurance 文件中，并用回归测试检查与独立入口一致；分析函数通过显式参数复用。

PREVIEW_ONLY=True 时展示单个疲劳循环和两种读回波形，不连接仪器、不创建输出目录；改为 False 实测。workflow 调用 run_test(cycle_params_override=..., pv2_params_override=..., pund_params_override=..., cycle_targets=..., save_dir=..., preview_only=False)，覆盖值不会改写默认文件。

每次读回工作簿含原始通道、Waveform、Parameters 和分析表；文件名含电压、rise、delay、累计圈数及自动编号。圈数按本次最大节点的位数补零：最大 1000 圈时使用 cycles0001 到 cycles1000，例如 PUNDtri_04.00V_tr50us_td50us_cycles1000_r001.xlsx。先保存原始数据再分析。每个阶段及结束时更新同一份 Excel 汇总，记录阶段、状态和 time，不保存输出路径；失败即停止后续阶段并记录失败/中断。开始疲劳前校验 10 V 档的电压、实际段长和量程；本入口未启用长 delay 的 retention 拆分。

### 极化图与 endurance Pr

PV2、三角/方波 PUND、retention PV/PUND 和 NLS 现在只画 I2 极化图。I1/I2 原始测量数据及两个通道的分析表均保留；差分电流图和原始波形图维持原有数据。

endurance 另保存一张总图，包含 PV2 有 delay、PV2 无 delay、三角 PUND 三个面板，每个面板叠加已完成的不同 cycle，同一 cycle 使用相同颜色。失败或中断时仍可画出已成功分析的曲线。

summary 的 Pr_positive_uC_cm2、Pr_negative_uC_cm2 保存 PV2 有 delay 回线及三角 PUND 的带符号正负 Pr；PV2 另保存 Pr_positive_no_delay_uC_cm2、Pr_negative_no_delay_uC_cm2。这些值来自 I2，在返回支路的 0 V 处提取，不是峰值极化，也不是 offset 处的值。跨过 0 V 的相邻采样点做线性插值；若设定支路明确结束在 0 V，而采样未包含端点，则允许用最后两个相邻点做不超过一个电压采样间隔的外推。超出范围或数据缺失时留空，Parameters 中记录提取规则。
