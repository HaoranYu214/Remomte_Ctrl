# Multi-step measurement workflows

[English](#english) | [中文](#中文)

## English

| File | Execution plan |
|---|---|
| [pv_and_pund.py](pv_and_pund.py) | Runs PV2 followed by triangular PUND; supports repeated calls |
| [pv2_pund_map.py](pv2_pund_map.py) | Sweeps combinations of amplitude, triangular-wave frequency, and delay |
| [package1.py](package1.py) | Uses RUN_ORDER to combine PV/PUND, a parameter map, and segmented SMU I-V |
| [ftj_package1.py](ftj_package1.py) | Configures and runs RV2/PWM/Identical/MRD in RUN_ORDER |

Workflow parameter tables override the corresponding lower-level entry settings, so edit these tables first for batch measurements. STOP_ON_ERROR=True stops later stages after an error; False allows the workflow to continue and record failures. SETTLE_TIME_S is a Python wait between stages, not an instrument pulse delay.

The map converts frequency to rise_time=1/(4f). This describes the nominal triangular-wave frequency only; delay and conditioning segments increase the actual total duration. All expanded segments must still respect the manual's timing limits.

Outputs use configured directories and summaries include time. r001/r002 identifies output groups sharing the same base name. Boolean RUN_* and PREVIEW_ONLY parameters are switches, distinct from instrument mode codes.

Parameter source: [manual limits and mode reference (Chinese)](../reference/manuals/PARAMETER_LIMITS.md).


Parameter API: [standalone and workflow configuration](../measurements/pmu/README.md#standalone-and-workflow-configuration).

Summary output uses one Excel workbook per invocation, updated as progress is recorded. No duplicate live CSV or output-path columns are saved; runtime return values can still provide paths to callers.

## 中文

### 多步测量工作流

| 文件 | 执行内容 |
|---|---|
| [pv_and_pund.py](pv_and_pund.py) | 顺序执行 PV2 和三角 PUND，可重复调用 |
| [pv2_pund_map.py](pv2_pund_map.py) | 扫描幅值、三角波频率和 delay 的组合 |
| [package1.py](package1.py) | 按 RUN_ORDER 串联 PV/PUND、map 和 SMU 分段 I-V |
| [ftj_package1.py](ftj_package1.py) | 按 RUN_ORDER 配置并运行 RV2/PWM/Identical/MRD |

工作流自己的参数表会覆盖下层入口的相应设置；批量测量时优先改这里的配置。STOP_ON_ERROR=True 表示遇到错误停止后续阶段，False 表示允许按流程继续并记录失败。SETTLE_TIME_S 是 Python 阶段间等待，不是仪器脉冲延迟。

map 中 frequency 转换为 rise_time=1/(4f)，仅表示三角波的标称频率；delay 和其他预处理段会增加实际总时间。所有展开后的真实时间段仍受手册边界约束。

保存按配置目录执行，汇总表含 time；r001/r002 是同名输出组编号。RUN_*、PREVIEW_ONLY 等布尔值在参数表中表示开关，不能和仪器模式码混为一谈。

参数依据：[手册限制与模式速查](../reference/manuals/PARAMETER_LIMITS.md)。

参数接口：[独立运行与工作流配置](../measurements/pmu/README.md#独立运行与工作流配置)。

每轮只保存一份 Excel 汇总，随进度更新，不再保存重复的实时 CSV 或输出路径列；函数返回值仍可向调用方提供运行时路径。
