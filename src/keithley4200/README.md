# Shared Keithley source library

[English](#english) | [中文](#中文)

## English

The reusable instrument code is divided by hardware command family:

- `pmu/`: 4225-PMU sessions, Segment Arb execution, data processing,
  current-range helpers, plotting, and shared FET pulse helpers.
- `smu/`: SMU System Mode, User Mode, RPM routing, data processing, plotting,
  and sessions.
- `transport.py`: the single shared PyVISA communication implementation used
  by both packages.

Runnable experiment parameters and waveforms remain outside `src`; this
directory contains reusable mechanisms rather than experiment protocols.

## Other shared modules

- [output.py](output.py): shared filename labels, atomic run-number reservations, and summary timestamps.
- [tools](tools/README.md): waveform previews and dry-run helpers, included in the installed package.

__init__.py marks an importable package and normally does not need to be run directly. Experiment entries combine these shared capabilities, while measurements owns the experiment-specific waveforms.

Parameter source: [manual limits and mode reference (Chinese)](../../reference/manuals/PARAMETER_LIMITS.md).


Parameter API: [standalone and workflow configuration](../../measurements/pmu/README.md#standalone-and-workflow-configuration).


### Parameter helpers

- [measurement_parameters.py](measurement_parameters.py): copy/merge run overrides and remap channel-specific options; it does not define experiment classes.
- [parameter_defaults.py](parameter_defaults.py): update only accepted current-range literals in source defaults while retaining comments and other settings.

## 中文

### Keithley 公共源码库

公共代码按仪器命令族分组：

- pmu/：4225-PMU 会话、Segment Arb 执行、处理、量程辅助、绘图及 FET 通用执行辅助。
- smu/：SMU System/User Mode、RPM 路由、处理、绘图及会话。
- transport.py：PMU 与 SMU 共用的 PyVISA 通信实现。

可运行实验的参数和波形保留在 src 外；此处实现公共机制，实验协议由 measurements 定义。

## 其他公共模块
- [output.py](output.py)：统一文件标签、原子占号和汇总时间。
- [tools](tools/README.md)：波形预览与 dry-run，已包含在安装包内。

__init__.py 标记可导入的包；一般不需要直接运行。实验入口只组合这些公共能力，具体波形仍由 measurements 定义。

参数依据：[手册限制与模式速查](../../reference/manuals/PARAMETER_LIMITS.md)。

### 参数辅助

- [measurement_parameters.py](measurement_parameters.py)：复制/合并单次参数并重映射通道选项，不定义实验类。
- [parameter_defaults.py](parameter_defaults.py)：仅回写接受的电流档数值，保留注释和其他设置。

参数接口：[独立运行与工作流配置](../../measurements/pmu/README.md#独立运行与工作流配置)。
