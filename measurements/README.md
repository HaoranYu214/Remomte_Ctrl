# Experiment entry points

[English](#english) | [中文](#中文)

## English

Choose an experiment here; shared mechanisms live in [src](../src/README.md).

| Task | Entry |
|---|---|
| Learn two/three-channel DC testing | [2terminal example](smu/2terminal/README.md), [3terminal example](smu/3terminal/README.md) |
| FET output/transfer curves | [SMU three-terminal tests](smu/3terminal/FET.md) |
| PV, PUND, retention or fatigue | [Ferroelectric capacitors](pmu/fe_cap/README.md) |
| FTJ program/read | [FTJ](pmu/ftj/README.md) |
| FeFET pulse program/read | [PMU FET](pmu/fet/README.md) |
| Standard pulse trains | [Pulse](pmu/pulse/README.md) |
| FORC/NLS sweeps | [Programmed experiments](pmu/programmed/README.md) |
| Combine tests or map parameters | [Workflows](workflows/README.md) |

Read each header, edit the top settings, then follow main/run_test into waveform construction and acquisition. Imports do not start measurements. Direct execution may do so: not every entry supports PREVIEW_ONLY, and some run_* functions explicitly acquire regardless of a standalone preview setting.

Use a supported params_override argument for per-run changes. Waveform/preview helpers taking parameters usually expect a complete dictionary. The [PMU API](pmu/README.md#standalone-and-workflow-configuration) lists the supported entries and accepted-range persistence exception.

SMU examples expose commands directly and share point algorithms. PMU entries own their pulse sequences. Workflows own batch settings; some wrappers inherit unspecified settings from a selected experiment. Source checkout paths must remain available when importing experiments.

## 中文

在这里选择实验；公共机制在 [src](../src/README.md)。

| 任务 | 入口 |
|---|---|
| 学习两路/三路 SMU 直流测试 | [2terminal 示例](smu/2terminal/README.md)、[3terminal 示例](smu/3terminal/README.md) |
| FET output/transfer 曲线 | [SMU 三端测试](smu/3terminal/FET.md) |
| PV、PUND、retention 或疲劳 | [铁电电容](pmu/fe_cap/README.md) |
| FTJ 写读 | [FTJ](pmu/ftj/README.md) |
| FeFET 脉冲写读 | [PMU FET](pmu/fet/README.md) |
| 普通脉冲串 | [Pulse](pmu/pulse/README.md) |
| FORC/NLS 扫描 | [程序化实验](pmu/programmed/README.md) |
| 组合测试或扫描参数 | [工作流](workflows/README.md) |

先读文件头部、修改顶部参数，再沿 main/run_test 阅读波形生成和采集。导入不会启动测量，直接执行可能会。并非所有入口都有 PREVIEW_ONLY；部分 run_* 函数明确实测，不受独立运行的预览开关控制。

支持 params_override 的入口可以按次覆盖参数；接收 parameters 的波形/预览函数通常需要完整字典。[PMU 参数接口](pmu/README.md#独立运行与工作流配置)列出了适用入口及接受量程回写这一例外。

SMU 示例直接展示命令并共用取点算法，PMU 实验自己定义脉冲序列。工作流拥有批量配置，部分外层脚本会继承目标实验中未覆盖的设置。导入实验时需要保留源码仓库路径。
