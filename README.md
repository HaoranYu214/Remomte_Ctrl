# Keithley 4200A-SCS measurements

[English](#english) | [中文](#中文)

## English

Editable PMU and SMU experiments with a shared Python library. Experiment files show the waveform or voltage path and instrument configuration; src handles reusable communication, validation, readout, and saving.

### Start here

Requires Python 3.10 or newer. From the repository root:

~~~powershell
python -m pip install -e .
python measurements/smu/2terminal/example.py
~~~

The two-terminal example defaults to PREVIEW_ONLY=True: it prints configuration commands and plots commanded voltages without connecting or saving. Copy it to build a new test; use the [three-terminal example](measurements/smu/3terminal/README.md) for three SMUs. Check the current file settings before running other entries: preview behavior is entry-specific. Real acquisition requires the instrument's VISA connection and KXCI setup.

### Local instrument settings

Public examples use TCPIP0::192.0.2.1::1225::SOCKET and relative data/<experiment> output directories, resolved from the working directory. Replace the example resource before acquisition. The data/ and .local/ directories are ignored by Git. Private settings backups, when present, live in .local/private-config/ and are never loaded automatically. Restoring settings into source files makes those files private again.

### Repository map

| Directory | What belongs here |
|---|---|
| [measurements/pmu](measurements/pmu/README.md) | Pulse waveforms, PV/PUND, FTJ and FeFET experiments |
| [measurements/smu](measurements/smu/README.md) | 2terminal / 3terminal DC experiments and examples |
| [measurements/workflows](measurements/workflows/README.md) | Ordered tests, parameter maps and batch settings |
| [src/keithley4200](src/keithley4200/README.md) | Shared PMU/SMU mechanisms and output utilities |
| [tests](tests/README.md) | Hardware-free regression tests; retained in Git |
| [reference](reference/README.md) | Manuals and original vendor examples |

Only src/keithley4200 is installed as a package. Experiment entries bootstrap the source path when run directly; workflows also need the measurements directory from the checkout.

### Reading and editing a test

Read the file header, editable settings, then the runner at the bottom. SMU examples order settings as hardware defaults → directory/channels/preview switches → sweep definition → electrical and sampling parameters. Internal result-column names appear later.

SMU linear, segmented, logarithmic and explicit paths all produce VL lists. Point algorithms live in smu/points.py; CH/VL/VC/timing/range commands remain visible in each experiment. PMU pulse sequences remain in their experiment files. PMU preview uses time; SMU preview uses point index. Neither is a measured result.

### Results and offline checks

Excel workbooks record "ssme / Haoran Yu" in the creator document property. This metadata travels with the workbook; it adds no cells or measurement columns.

Output groups share a reserved stem, for example PV2_03.00V_tr250us_td1000us_r001.xlsx and its plot companions. tr/td/tw are rise/delay/width in microseconds. Labels round voltage to two decimals; full settings remain in parameter sheets. Existing workbooks or companion plots occupy a run number. Keep the .reservations directory with the data; interrupted runs may leave gaps.

Configured output directories are used directly. Progress summaries are updated as one Excel workbook per invocation, using atomic replacement after successful writing. Low-level helpers still honor explicit output paths. PV/PUND polarization figures show I2; raw I1 and its analysis remain saved.

~~~powershell
$env:MPLBACKEND = "Agg"
python -m unittest discover -s tests
python src/keithley4200/tools/dry_run.py --no-save measurements/pmu/fe_cap/PV2.py
~~~

The [PMU dry-run tool](src/keithley4200/tools/README.md) checks software flow with synthetic responses. It does not simulate device physics. Instrument display and buffer behavior still require hardware verification.

See the [parameter and mode reference](reference/manuals/PARAMETER_LIMITS.md) for documented limits and source pages.

## 中文

本仓库提供可直接修改的 PMU、SMU 实验及公共 Python 库。实验文件展示波形或电压路径、仪器配置；src 负责复用通信、校验、读数和保存。

### 从哪里开始

需要 Python 3.10 或更新版本。在仓库根目录执行：

~~~powershell
python -m pip install -e .
python measurements/smu/2terminal/example.py
~~~

两端示例默认 PREVIEW_ONLY=True：只打印配置命令、绘制指令电压，不连接或保存。可以复制它新建实验；三路 SMU 从[三端示例](measurements/smu/3terminal/README.md)开始。其他入口的预览行为各不相同，运行前查看文件当前设置。实测需要配置仪器 VISA 连接与 KXCI。

### 本地仪器设置

公开示例使用 TCPIP0::192.0.2.1::1225::SOCKET 和相对输出目录 data/<实验路径>，相对当前工作目录解析。实测前替换示例资源地址。data/、.local/ 已加入 Git 忽略；本地配置备份放在 .local/private-config/，不会自动加载。把原配置恢复到源码后，这些源码会再次包含私人设置。

### 目录导航

| 目录 | 内容 |
|---|---|
| [measurements/pmu](measurements/pmu/README.md) | 脉冲波形、PV/PUND、FTJ、FeFET 实验 |
| [measurements/smu](measurements/smu/README.md) | 2terminal / 3terminal 直流实验和示例 |
| [measurements/workflows](measurements/workflows/README.md) | 顺序测试、参数扫描及批量配置 |
| [src/keithley4200](src/keithley4200/README.md) | PMU/SMU 公共机制与输出工具 |
| [tests](tests/README.md) | 不连接硬件的回归测试，保留在 Git 中 |
| [reference](reference/README.md) | 手册和原始官方示例 |

安装范围只有 src/keithley4200。实验入口直接运行时会加入源码路径；工作流还需要源码仓库中的 measurements 目录。

### 如何阅读和修改实验

先看文件头部说明和参数，再看底部调用的执行函数。SMU 示例按“硬件默认设置 → 目录、通道、预览开关 → 扫描定义 → 电气与采样参数”排列；内部结果列名放在后面。

SMU 的 linear、segments、log、list 都生成 VL 列表。取点算法放在 smu/points.py，CH/VL/VC、时间和量程命令直接写在实验里。PMU 的脉冲序列也保留在各实验文件。PMU 预览横轴是时间，SMU 是点序号；两者都是指令预览。

### 结果与离线检查

Excel 工作簿在 creator 文档属性中记录 "ssme / Haoran Yu"。署名随文件分享，不增加单元格或测量列。

同次输出共用预留主名，例如 PV2_03.00V_tr250us_td1000us_r001.xlsx 及其配套图片。tr/td/tw 表示上升、等待、脉宽，单位微秒。文件名电压保留两位小数，完整设置保存在参数表。已有表格或配套图片都会占用编号；.reservations 应随数据目录保留，中断可能留下空号。

输出直接使用配置目录。每次调用使用一个 Excel 汇总表持续更新，新文件写成功后才原子替换旧版。底层辅助函数仍尊重显式路径。PV/PUND 极化图展示 I2，I1 原始数据和分析仍保存。

~~~powershell
$env:MPLBACKEND = "Agg"
python -m unittest discover -s tests
python src/keithley4200/tools/dry_run.py --no-save measurements/pmu/fe_cap/PV2.py
~~~

[PMU dry-run](src/keithley4200/tools/README.md) 使用模拟响应检查软件流程，不模拟器件物理。仪器窗口显示与缓冲区行为仍需实机验证。

参数限制及出处见[参数与模式速查](reference/manuals/PARAMETER_LIMITS.md)。
