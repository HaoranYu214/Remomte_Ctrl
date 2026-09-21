# SMU

[English](#english) | [中文](#中文)

## English

These examples are for external control of the 4200A SMU in system mode with the KXCI application running on it and using a PC.

Requirements

* Software: Any Clarius version
* KXCI terminal setup: String Terminator = None, Reading Delimiter= String Terminator, Set to ethernet mode
* KXCI Configuration (set within KCON): TH, String Terminator = None, Reading Terminator = String Terminator
* Python: Version 3.6 or later
* Dependencies:  **[instrcomms.py](instrcomms.py)**, time, pyVISA
* Optional dependencies (Need for the code to run, but can be modified to run with it. All lines are marked where these can be removed) plotly.express, pandas

## Directory

* **2 SMUs 0V.py** This example performs a static bias test using the 4200A-SCS.Both SMU1 and SMU2 are set to 0 V to monitor baseline current behavior. It measures current on both SMUs over time and logs the data to CSV.
* **4 SMUs 0V.py** This example configures all four SMUs on a 4200A-SCS to source 0 V with 1 µA compliance. It performs a fixed current measurement (100 nA) on each channel, takes 3 readings, and saves the results with timestamps to a CSV file.
* **Current sweep without plotting.py** This example performs a current sweep using the 4200A-SCS in list display mode. SMU2 sources current from 1 µA to 10 µA in 1 µA steps, while SMU1 holds constant current. It measures voltage and current on both SMUs and logs the data to CSV.
* **Current sweep.py** This example performs a current sweep using the 4200A-SCS in list display mode. SMU2 sources current from 1 µA to 10 µA in 1 µA steps, while SMU1 holds constant current. It measures voltage and current on both SMUs and logs the data to CSV. It outputs a Drain Current vs Drain Voltage graph.
* **family_of_curves data retrival GPIB.py** *This example requires a GPIB connection. Settings within KCON: String Terminator = LF, Reading Delimiter = Comma.* This example performs a family of curves measurement using the 4200A-SCS. It sweeps drain voltage (0-5 V) and steps gate voltage (1-4 V) using SMU2 and SMU3, while SMU1 holds source at 0 V. Data is segmented and saved in a Clarius-like format.
* **family_of_curves data retrival.py** This example performs a family of curves measurement using the 4200A-SCS. It sweeps drain voltage (0-5 V) and steps gate voltage (1-4 V) using SMU2 and SMU3, while SMU1 holds source at 0 V. Data is segmented and saved in a Clarius-like format.
* **Linear sweep without plotting.py** This example performs a VAR1 linear sweep using the 4200A-SCS in list display mode. SMU2 sweeps from 1 V to 5 V in 0.1 V steps while SMU1 holds 0 V. It measures voltage and current on both SMUs and logs the data to CSV.
* **Linear sweep.py** This example performs a VAR1 linear sweep using the 4200A-SCS in list display mode. SMU2 sweeps from 1 V to 5 V in 0.1 V steps while SMU1 holds 0 V. It measures voltage and current on both SMUs and logs the data to CSV. It outputs a Drain Current vs Drain Voltage graph.
* **List sweep.py** This example performs a custom list sweep using the 4200A-SCS. SMU1 sweeps from 0 to 1 V in 100 linear steps (defined via NumPy), while SMU2 holds 0 V. It measures voltage on both SMUs and logs the data to CSV.
* **Log sweep without plotting.py** This example performs a log-scale VAR1 sweep using the 4200A-SCS in list display mode. SMU2 sweeps from 1 V to 10 V (log10 scale) while SMU1 holds 0 V. It measures voltage and current on both SMUs and logs the data to CSV.
* **Log sweep.py** This example performs a log-scale VAR1 sweep using the 4200A-SCS in list display mode. SMU2 sweeps from 1 V to 10 V (log10 scale) while SMU1 holds 0 V.It measures voltage and current on both SMUs and logs the data to CSV. It outputs a Diode Forward I-V Sweep graph.
* **Multi-channel sweep without plotting.py** This example performs a multi-channel sweep using the 4200A-SCS. SMU1 performs a linear VAR1 sweep from 0 to 1 V, while SMU2 and SMU3 follow the same sweep using VAR1' ratio mode. It measures voltage and current on all three SMUs and logs the data to CSV.
* **Multi-channel sweep.py** This example performs a multi-channel sweep using the 4200A-SCS. SMU1 performs a linear VAR1 sweep from 0 to 1 V, while SMU2 and SMU3 follow the same sweep using VAR1' ratio mode. It measures voltage and current on all three SMUs and logs the data to CSV. It outputs a Drain Voltage vs Gate Current graph.
* **res2t.py** This example recreates the Clarius res2t test by performing a 2-terminal resistance sweep using the 4200A-SCS. It sweeps voltage from -1 V to 1 V on SMU1 while SMU2 holds 0 V, measures current, and calculates average resistance.

## Location in this repository

The official example descriptions above are retained. Maintained entries are under [SMU I-V](../../../../measurements/smu/iv/README.md), and parameter meanings are covered by the [manual reference](../../../manuals/PARAMETER_LIMITS.md). The example code was not changed by the documentation work.

Parameter source: [manual limits and mode reference (Chinese)](../../../manuals/PARAMETER_LIMITS.md).

## 中文

### SMU 官方示例

这些示例在 PC 上通过运行 KXCI 的 4200A 控制 SMU。

## 环境要求

- 软件：任意 Clarius 版本；Python 3.6 或以上。
- KXCI 终端：String Terminator=None，Reading Delimiter=String Terminator，Ethernet 模式。
- KCon 中 KXCI 配置：TH，String Terminator=None，Reading Terminator=String Terminator。
- 依赖：instrcomms.py、time、PyVISA。绘图/表格代码还用 plotly.express、pandas；原示例标注了可移除这些依赖的代码行。

## 示例目录

- 2 SMUs 0V.py：SMU1/2 置 0 V，随时间监测基线电流并保存 CSV。
- 4 SMUs 0V.py：四路置 0 V、限流 1 µA，固定 100 nA 测量档，每路读取 3 次并保存带时间的 CSV。
- Current sweep without plotting.py / Current sweep.py：SMU2 从 1 µA 扫至 10 µA、步长 1 µA，SMU1 保持恒流；测两路电压/电流并保存 CSV。绘图版另画漏电流与漏电压。
- family_of_curves data retrival GPIB.py / family_of_curves data retrival.py：SMU2 扫漏压 0–5 V，SMU3 阶梯栅压 1–4 V，SMU1 源极置 0 V；数据按类似 Clarius 的格式分段保存。GPIB 版要求 GPIB 连接，并在 KCon 设置 String Terminator=LF、Reading Delimiter=Comma。
- Linear sweep without plotting.py / Linear sweep.py：SMU2 用 VAR1 从 1 V 扫至 5 V、步长 0.1 V，SMU1 置 0 V；保存两路电压/电流 CSV，绘图版另画漏电流与漏电压。
- List sweep.py：SMU1 用 NumPy 定义 0–1 V 的 100 点列表，SMU2 置 0 V，测两路电压并保存 CSV。
- Log sweep without plotting.py / Log sweep.py：SMU2 用对数 VAR1 从 1 V 扫至 10 V，SMU1 置 0 V，保存两路电压/电流 CSV；绘图版另画二极管正向 I-V。
- Multi-channel sweep without plotting.py / Multi-channel sweep.py：SMU1 用 VAR1 从 0 V 扫至 1 V，步长 0.1 V；SMU2/3 用 VAR1' 比例跟随，保存全部通道电压/电流 CSV；绘图版另画漏压与栅压。
- res2t.py：复现 Clarius res2t 双端电阻测试，SMU1 从 -1 V 扫至 1 V，SMU2 置 0 V，测电流并计算平均电阻。

通信依赖：[instrcomms.py](instrcomms.py)。

## 本库中的位置
此处保留官方示例说明。实际维护入口见 [SMU I-V](../../../../measurements/smu/iv/README.md)，参数含义见 [手册速查](../../../manuals/PARAMETER_LIMITS.md)。示例代码未因本次注释整理而修改。
