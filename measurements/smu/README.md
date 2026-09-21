# SMU DC experiments

[English](#english) | [中文](#中文)

## English

SMU experiments sit directly in this directory; there is no extra iv folder.

| Directory | Start with | Existing experiments |
|---|---|---|
| [2terminal](2terminal/README.md) | Generic two-channel example | Linear/segmented/memristor I-V, endurance, User Mode spot |
| [3terminal](3terminal/README.md) | Generic three-channel example | FET output and transfer families |

Both examples start in offline preview mode. Top-level settings expose hardware defaults, output directory, physical channels, PREVIEW_ONLY, KXCI_PLOT, point rules and per-channel parameters. Result names and internal definitions follow later.

Voltage paths use shared [point algorithms](../../src/keithley4200/smu/points.py). Every voltage sweep sends VL; linear/segments describe how Python generates points. CH, VL, VC, timing, ranges and display commands remain in each experiment. Connection, routing, polling, readout and saving use shared code.

PREVIEW_ONLY plots commanded voltages against point index. KXCI_PLOT controls the instrument's live graph during acquisition. Neither switch replaces the other; Python result plots are separate.

The directory names start with digits, so workflow imports use importlib:

~~~python
from importlib import import_module
iv = import_module("measurements.smu.2terminal.segmented_voltage_sweep")
result = iv.run_test(preview_only=False)
~~~

That call acquires real data. Run from the source checkout; measurements is not part of the installed library.

## 中文

SMU 实验直接放在本目录下，不再增加 iv 层。

| 目录 | 入门 | 已有实验 |
|---|---|---|
| [2terminal](2terminal/README.md) | 通用两通道示例 | 线性/分段/忆阻器 I-V、endurance、User Mode 单点 |
| [3terminal](3terminal/README.md) | 通用三通道示例 | FET output、transfer 曲线族 |

两个 example 都默认离线预览。顶部依次暴露硬件默认值、输出目录、物理通道、PREVIEW_ONLY、KXCI_PLOT、取点规则及各通道参数；结果命名和内部定义放在后面。

电压路径使用公共[取点算法](../../src/keithley4200/smu/points.py)。电压扫描统一下发 VL；linear/segments 表示 Python 如何生成点。CH、VL、VC、时间、量程及显示命令保留在实验里，连接、路由、轮询、读数和保存复用公共代码。

PREVIEW_ONLY 按点序号画指令电压。KXCI_PLOT 控制实测时仪器窗口画图。两个开关互不替代，Python 实测结果图也独立处理。

目录名以数字开头，工作流使用 importlib 导入：

~~~python
from importlib import import_module
iv = import_module("measurements.smu.2terminal.segmented_voltage_sweep")
result = iv.run_test(preview_only=False)
~~~

此调用会实测。请保留源码仓库；measurements 不属于安装包。
