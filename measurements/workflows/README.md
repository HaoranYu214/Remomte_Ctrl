# Measurement workflows

[English](#english) | [中文](#中文)

## English

Workflows define batch settings and call the experiment entries. Keep waveforms in their owning experiments.

| Entry | Plan |
|---|---|
| [pv_and_pund.py](pv_and_pund.py) | PV2 followed by triangular PUND |
| [pv2_pund_map.py](pv2_pund_map.py) | Amplitude × triangular frequency × delay |
| [FEcap_package1.py](FEcap_package1.py) | RUN_ORDER combines PV/PUND, parameter mapping and segmented SMU I-V |
| [ftj_package1.py](ftj_package1.py) | RUN_ORDER combines RV2/PWM/Identical/MRD |

Edit workflow tables for batch runs. STOP_ON_ERROR controls whether later stages run after failure; SETTLE_TIME_S adds a host wait between stages, not a pulse segment.

pv_and_pund, FEcap_package1 and ftj_package1 check PREVIEW_ONLY in main; their run_* functions acquire directly. pv2_pund_map has no preview switch. The FEcap I-V stage explicitly requests acquisition even if the standalone segmented script is set to preview.

The map uses rise_time=1/(4f); added delays/conditioning increase total duration beyond the nominal triangular period. Accepted PV/PUND ranges can be written back to the active workflow and leaf defaults; other overrides are not persisted this way. See the [parameter API](../pmu/README.md#standalone-and-workflow-configuration).

Each invocation reserves its own Excel summary and updates it after stages and at completion. It records status/time without duplicate CSV or output-path columns; return values may still contain paths. Run numbers distinguish output groups. Workflows require the source checkout, including measurements.

## 中文

工作流定义批量配置并调用实验入口，波形仍保留在所属实验中。

| 入口 | 执行计划 |
|---|---|
| [pv_and_pund.py](pv_and_pund.py) | PV2 后执行三角 PUND |
| [pv2_pund_map.py](pv2_pund_map.py) | 幅值 × 三角频率 × 等待时间 |
| [FEcap_package1.py](FEcap_package1.py) | RUN_ORDER 组合 PV/PUND、参数扫描、分段 SMU I-V |
| [ftj_package1.py](ftj_package1.py) | RUN_ORDER 组合 RV2/PWM/Identical/MRD |

批量运行时修改工作流参数表。STOP_ON_ERROR 控制失败后是否继续后续阶段；SETTLE_TIME_S 是阶段间的软件等待，不是脉冲段。

pv_and_pund、FEcap_package1、ftj_package1 在 main 检查 PREVIEW_ONLY，run_* 函数直接实测。pv2_pund_map 没有预览开关。FEcap 的 I-V 阶段明确请求实测，不受独立分段脚本预览默认值影响。

参数图使用 rise_time=1/(4f)，附加等待和预处理使总时长超过名义三角周期。接受的 PV/PUND 量程可以回写当前工作流及底层入口默认值；其他覆盖参数不会这样持久化。详见[参数接口](../pmu/README.md#独立运行与工作流配置)。

每次调用预留自己的 Excel 汇总表，在各阶段后和结束时更新；记录状态、时间，不再重复输出 CSV 或路径列，函数返回值仍可包含路径。运行编号区分输出组。工作流需要包含 measurements 的源码仓库。
