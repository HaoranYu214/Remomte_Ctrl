# FTJ program/read experiments

[English](#english) | [中文](#中文)

## English

Each base entry defines its waveform locally: write, then measure a read_v plateau to derive resistance/conductance. Edit params or call run_test(params_override=...). build_waveform(parameters=...) takes complete settings and returns sequence/execution metadata without a global cache.

| Entry | Difference |
|---|---|
| [ftj_RV1.py](ftj_RV1.py) | Write path starts at zero, positive then negative |
| [ftj_RV2.py](ftj_RV2.py) | +Vp to -Vp and back, with scan_cycles |
| [ftj_ISPP_V1.py](ftj_ISPP_V1.py) | One write sequence per level, shared read sequence |
| [ftj_ISPP_V2.py](ftj_ISPP_V2.py) | One complete ladder per polarity |
| [ftj_Identical_V1.py](ftj_Identical_V1.py) | Fixed-amplitude repeated writes/reads within SARB |
| [ftj_Identical_V2.py](ftj_Identical_V2.py) | Separate executions with host wait_after_* delays |
| [ftj_PWM.py](ftj_PWM.py) | write_base_dwell × width_multipliers |
| [ftj_MRD.py](ftj_MRD.py) | Repeated reset/read/write/read at each level |
| [ftj_endurance.py](ftj_endurance.py) | Repeated complete target runs with progress summary |

### Settings and execution

base_v is the inter-pulse level; offset_v shifts RV write levels; read_v is physically applied. *_rise/fall/dwell/idle are SARB segment durations. wait_after_* are host waits with scheduling/communication overhead. Repetition counts consume segment/sample budgets.

Use the [shared parameter API](../README.md#standalone-and-workflow-configuration) for explicit per-run overrides and preview. Instrument mode/range limits are in the [parameter reference](../../../reference/manuals/PARAMETER_LIMITS.md).

Identical V2 checkpoints after each step and on failure/interruption. Unmeasured writes may return zero points; a read missing either channel stops the run. Saving adds host overhead.

### Endurance and output

TARGET_MODULE_NAME selects RV2, Identical V1 or V2. TARGET_PARAM_OVERRIDES={} inherits the selected entry's defaults; overrides change only this call. LOOP_COUNT counts complete runs; internal sequence_cycle_count (V1), plan_repeat_count (V2), and per-polarity repetitions still apply. The runner explicitly acquires with preview_only=False. SAVE_EVERY_RUN=False retains the summary without every target's complete files.

Each invocation updates one Excel summary with status/time. Filename voltage labels precede timing: Identical/PWM use configured positive/negative levels, ISPP uses scan stops, RV uses offset_v +/- abs(vp), and MRD includes write range/reference. Vp/Vn denote ends even if offset makes both the same sign. Two-decimal labels are for display; Parameters retains full settings. Plots share the workbook stem and reserved run number.

## 中文

基础入口在本地定义波形：先写入，再测 read_v 平台，计算电阻/电导。修改 params 或调用 run_test(params_override=...)；build_waveform(parameters=...) 接收完整参数并返回序列/执行信息，不保留全局缓存。

| 入口 | 区别 |
|---|---|
| [ftj_RV1.py](ftj_RV1.py) | 写入路径从零开始，先正后负 |
| [ftj_RV2.py](ftj_RV2.py) | +Vp 到 -Vp 再返回，支持 scan_cycles |
| [ftj_ISPP_V1.py](ftj_ISPP_V1.py) | 每个电平一个写序列，共用读序列 |
| [ftj_ISPP_V2.py](ftj_ISPP_V2.py) | 每个极性打包完整阶梯 |
| [ftj_Identical_V1.py](ftj_Identical_V1.py) | SARB 内固定幅值重复写读 |
| [ftj_Identical_V2.py](ftj_Identical_V2.py) | 拆分执行，wait_after_* 为主机等待 |
| [ftj_PWM.py](ftj_PWM.py) | write_base_dwell × width_multipliers |
| [ftj_MRD.py](ftj_MRD.py) | 各电平重复 reset/read/write/read |
| [ftj_endurance.py](ftj_endurance.py) | 重复完整目标测试并更新汇总 |

### 设置与执行

base_v 为脉冲间电平，offset_v 平移 RV 写入电平，read_v 也会实际输出。*_rise/fall/dwell/idle 是 SARB 段时间；wait_after_* 是主机等待，包含调度/通信开销。重复次数会消耗段数和采样点预算。

按次覆盖与预览见[公共参数接口](../README.md#独立运行与工作流配置)，模式/量程限制见[参数速查](../../../reference/manuals/PARAMETER_LIMITS.md)。

Identical V2 每步及失败/中断时保存检查点。不采集的写入允许零点；读取缺少任一通道会停止。保存工作簿会增加主机开销。

### Endurance 与输出

TARGET_MODULE_NAME 选择 RV2、Identical V1 或 V2。TARGET_PARAM_OVERRIDES={} 继承目标默认值，覆盖只影响本次调用。LOOP_COUNT 统计完整测试次数；内部 sequence_cycle_count（V1）、plan_repeat_count（V2）及每极性重复仍然生效。外层明确用 preview_only=False 实测。SAVE_EVERY_RUN=False 仍保留汇总，但不保存每轮完整目标结果。

每次调用更新一个记录状态/时间的 Excel 汇总。文件名先电压后时间：Identical/PWM 用正负设置值，ISPP 用扫描终点，RV 用 offset_v +/- abs(vp)，MRD 保留写入范围/参考值。即使偏置使两端同号，Vp/Vn 仍表示两个端点。两位小数标签仅供显示，完整参数保存在 Parameters。图片共用表格主名和预留编号。
