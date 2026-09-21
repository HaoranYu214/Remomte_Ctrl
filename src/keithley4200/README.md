# Shared measurement library

[English](#english) | [中文](#中文)

## English

Keep reusable mechanisms here and experiment definitions in [measurements](../../measurements/README.md).

| Responsibility | PMU | SMU |
|---|---|---|
| Connection and cleanup | pmu/session.py | smu/session.py |
| Command support | pmu/pmu_tests.py | smu/system_mode.py, user_mode.py, routing.py |
| Readout and processing | pmu/data_processing.py | smu/data_processing.py |
| Offline preview | pmu/preview.py: time, segments, windows, SSR | smu/preview.py: point index and channel voltages |
| Measured plots | pmu/plotting.py | smu/plotting.py |
| Shared specialization | FET pulse execution, timing and current ranges | smu/points.py and smu/fet.py |

The two previews have different axes and inputs. Plotting modules handle measured results. smu/fet.py only validates FET plans and saves family checkpoints; it does not hide the sweep commands.

Package-wide helpers:

- [transport.py](transport.py): shared PyVISA communication.
- [output.py](output.py): labels, output-group reservations, timestamps and atomic workbook saving.
- [measurement_parameters.py](measurement_parameters.py): copy/merge run settings and remap channel options.
- [parameter_defaults.py](parameter_defaults.py): persist accepted current-range literals while preserving other source settings.
- [tools](tools/README.md): PMU dry-run command-line tool.

See [PMU](pmu/README.md) and [SMU](smu/README.md) for boundaries and limitations. Current imports use pmu.preview and pmu.plotting; update personal scripts still using tools.waveform_preview or pmu.plotting_utils.

## 中文

这里保留公共机制，实验定义放在 [measurements](../../measurements/README.md)。

| 职责 | PMU | SMU |
|---|---|---|
| 连接与清理 | pmu/session.py | smu/session.py |
| 命令支持 | pmu/pmu_tests.py | smu/system_mode.py、user_mode.py、routing.py |
| 读取与处理 | pmu/data_processing.py | smu/data_processing.py |
| 离线预览 | pmu/preview.py：时间、分段、测量窗、SSR | smu/preview.py：点序号与各通道电压 |
| 实测绘图 | pmu/plotting.py | smu/plotting.py |
| 专用公共能力 | FET 脉冲执行、时间和电流量程 | smu/points.py、smu/fet.py |

两种预览的横轴和输入不同；plotting 模块负责实测结果。smu/fet.py 只校验 FET 计划和保存曲线族检查点，不封装整套扫描命令。

跨仪器公共模块：

- [transport.py](transport.py)：PyVISA 通信。
- [output.py](output.py)：文件标签、输出组占号、时间戳和工作簿原子保存。
- [measurement_parameters.py](measurement_parameters.py)：复制、合并单次配置，重映射通道选项。
- [parameter_defaults.py](parameter_defaults.py)：回写接受的电流档字面量，保留其他源码设置。
- [tools](tools/README.md)：PMU dry-run 命令行工具。

具体边界见 [PMU](pmu/README.md) 和 [SMU](smu/README.md)。当前导入使用 pmu.preview、pmu.plotting；个人脚本若仍使用 tools.waveform_preview、pmu.plotting_utils，需要更新。
