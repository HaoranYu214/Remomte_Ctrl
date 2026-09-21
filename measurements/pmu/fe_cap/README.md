# Ferroelectric capacitor experiments

[English](#english) | [中文](#中文)

## English

Edit the top parameters and hardware/output settings, then preview the local waveform before acquisition. See the [run_test API](../README.md#standalone-and-workflow-configuration) for per-run overrides.

| Entry | Measurement |
|---|---|
| [PV2.py](PV2.py) | Conditioning followed by two triangular P-V loops |
| [PUND_tri.py](PUND_tri.py) | Triangular P/U/N/D subtraction |
| [PUND_Squr.py](PUND_Squr.py) | Square/trapezoidal PUND with dwell plateau |
| [NLS_manually.py](NLS_manually.py) | Square disturb and triangular readout |
| [retentionPV.py](retentionPV.py) | Preset, output-off wait, then two continuous PV loops |
| [retentionPUND.py](retentionPUND.py) | Separate Preset/P/U/N/D executions with waits |
| [endurance.py](endurance.py) | Fatigue blocks and PV2/PUND readback at cumulative milestones |

### Ranges, timing and analysis

Standalone PV2 and triangular/square PUND can retry the entire waveform at another fixed range. Irange1/2 are starting ranges; accepted ranges are saved and may be persisted to defaults. Default candidates target a 10 V RPM.

Some PV2 segments last 2*rise_time; the 1 s segment ceiling therefore limits rise_time to 0.5 s. PUND dwell is a plateau, not standard Pulse width. area_cm2 controls charge/polarization conversion, not output. Polarization figures show I2 only; raw I1/I2 and both analysis tables remain saved.

### NLS timing

TotalDelay runs from the end of the preset/prepost falling edge to the first half-PUND read rising edge. Dwell is the disturb plateau. Add an unmeasured baseline hold:

~~~text
PaddingDelay = TotalDelay - 2*Delaytime - 2*Rt_s - Dwell
~~~

Both waits and disturb edges count; the wait between half-PUND reads remains unchanged. Reject insufficient time before acquisition. Omit zero padding; nonzero padding must meet the configured segment limits (default 10 V: 20 ns to 1 s, with 10 ns hardware resolution). Save TotalDelay/PaddingDelay in parameters and batch summaries. This fixes time since preset; disturb-to-read time still varies with pulse width.

MeasureSquare=False disables acquisition of the square segment, not the applied pulse.

### Retention

Retention entries always split executions and default to preview with a 1 s delay. They use fixed ranges with no retry and require zero offset. Output-off waiting is neither a guaranteed 0 V drive nor verified SSR isolation. Waveforms remain local; [_retention.py](_retention.py) supplies timing/execution/checkpoint support.

Deadlines use the previous EXECUTE send time plus programmed duration. Transfer/configuration consumes the wait budget. estimated_delay_s and EstimatedGlobalTime_s are host estimates; overrun_s records known lateness. Raw timestamps and Stage/Execution labels are preserved. Raw data/logs are checkpointed before analysis, including retrieved data on failure/interruption. PUND pairs branches and interpolates unequal counts in normalized time; PV retains PV2 integration.

### Endurance

Three dictionaries configure params_cycle, params_pv2 and params_pund. Each uses Vp, offset, rise_time, delay_time and Irange1/2; readback also uses area_cm2 and triangular PUND uses offset_ramp_time.

One fatigue cycle is offset → offset-Vp → offset → offset+Vp → offset. Each slope lasts rise_time, with baseline holds after each triangle; period=4*rise_time+2*delay_time. Fatigue is unmeasured. cycle_counts is cumulative: [1, 10, 100] executes blocks of 1, 9, 90. PV/PUND conditioning/readout also affects the device but is excluded from that count.

PREVIEW_ONLY previews one cycle and both readback waveforms. Acquisition uses fixed readback ranges, no retry/default rewriting, and no long-delay retention split. run_test accepts cycle_params_override, pv2_params_override, pund_params_override, cycle_targets, save_dir and preview_only. Validate the 10 V plan before fatigue starts.

Each readback saves raw/processed tables, Waveform and Parameters; raw data is checkpointed before analysis. One summary updates after stages and at completion; failure stops later stages. Filenames include cumulative cycles and run number. A combined three-panel figure overlays completed PV2 delayed/no-delay and PUND curves.

Summary Pr values are signed I2 remanent polarization on return branches at 0 V, not peak polarization or values at offset. Bracketing samples interpolate linearly. If a branch ends exactly at zero but misses that sample, at most one voltage interval may be extrapolated from the last two points; otherwise leave missing. Parameters records the convention.

See the [manual reference](../../../reference/manuals/PARAMETER_LIMITS.md) for parameter limits.

## 中文

先修改顶部参数及硬件/输出设置，再预览本地波形。按次覆盖见 [run_test 接口](../README.md#独立运行与工作流配置)。

| 入口 | 测量 |
|---|---|
| [PV2.py](PV2.py) | 预处理后两圈三角 P-V |
| [PUND_tri.py](PUND_tri.py) | 三角 P/U/N/D 差分 |
| [PUND_Squr.py](PUND_Squr.py) | 含 dwell 平台的方波/梯形 PUND |
| [NLS_manually.py](NLS_manually.py) | 方形扰动加三角读取 |
| [retentionPV.py](retentionPV.py) | Preset、关闭输出等待、连续双 PV |
| [retentionPUND.py](retentionPUND.py) | Preset/P/U/N/D 分别执行并等待 |
| [endurance.py](endurance.py) | 疲劳块及累计节点的 PV2/PUND 读回 |

### 量程、时间与分析

独立 PV2、三角/方波 PUND 可换固定档重放整个波形。Irange1/2 是起始档，接受档位保存并可能回写默认值。默认候选针对 10 V RPM。

PV2 部分段长为 2*rise_time，受单段 1 s 上限影响，rise_time 最多 0.5 s。PUND dwell 是平台，不是普通 Pulse 的 width。area_cm2 影响电荷/极化换算，不影响输出。极化图只画 I2；I1/I2 原始数据及两路分析表仍保存。

### NLS 时间定义

TotalDelay 从 preset/prepost 下降沿结束计时，到第一个 half-PUND 读取上升沿开始。Dwell 为扰动平台时间，额外加入不采集的基线保持：

~~~text
PaddingDelay = TotalDelay - 2*Delaytime - 2*Rt_s - Dwell
~~~

两段等待及扰动边沿均计入，half-PUND 两次读取间等待不变。总时间不足会在采集前拒绝；补齐为零时省略，非零时需符合所用段长限制（默认 10 V 档为 20 ns 到 1 s，硬件分辨率 10 ns）。参数和批量汇总保存 TotalDelay/PaddingDelay。固定的是 preset 后经过时间，扰动结束至读取的时间仍随脉宽变化。

MeasureSquare=False 只关闭方形段采集，不取消实际脉冲。

### Retention

Retention 始终拆分执行，默认 1 s 等待并只预览。使用固定量程，不重试，要求零 offset。关闭输出等待不保证强制 0 V，也不代表已验证的 SSR 隔离。波形留在本地，[_retention.py](_retention.py) 提供时间、执行和检查点支持。

截止时间由上次 EXECUTE 发送时刻加编程时长得到，传输/配置消耗等待预算。estimated_delay_s、EstimatedGlobalTime_s 为主机估算，overrun_s 记录已知超时。保留原始时间及 Stage/Execution 标签。分析前保存原始数据/日志检查点，失败或中断时也保存已读数据。PUND 配对分支并按归一化时间插值不同点数；PV 沿用 PV2 积分。

### Endurance

params_cycle、params_pv2、params_pund 三个字典独立配置，均使用 Vp、offset、rise_time、delay_time、Irange1/2；读回还含 area_cm2，三角 PUND 含 offset_ramp_time。

一个疲劳周期为 offset → offset-Vp → offset → offset+Vp → offset。每个斜坡持续 rise_time，每个三角后保持基线；周期=4*rise_time+2*delay_time。疲劳不采集。cycle_counts 是累计值：[1, 10, 100] 实际执行 1、9、90 个周期。PV/PUND 的预处理和读取同样影响器件，但不计入疲劳数。

PREVIEW_ONLY 预览一个疲劳周期和两种读回波形。实测使用固定读回档，不重试或回写，不启用长等待 retention 拆分。run_test 接收 cycle_params_override、pv2_params_override、pund_params_override、cycle_targets、save_dir、preview_only，疲劳前校验 10 V 计划。

各次读回保存原始/分析表、Waveform、Parameters，分析前先存原始检查点。一个汇总表在阶段后和结束时更新，失败停止后续阶段。文件名包含累计周期和运行号。三联图叠加已完成的 PV2 延迟/无延迟及 PUND 曲线。

汇总 Pr 是 I2 在返回分支 0 V 处的有符号剩余极化，不是峰值或 offset 处的值。跨零样本线性插值；若分支恰好结束于零却漏采端点，允许最后两点在一个电压间隔内外推，否则留空。Parameters 记录约定。

参数限制见[手册速查](../../../reference/manuals/PARAMETER_LIMITS.md)。
