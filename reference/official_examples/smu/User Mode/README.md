# SMU

[English](#english) | [中文](#中文)

## English

These examples are for external control of the 4200A SMU in user mode with the KXCI application running on it and using a PC.

Requirements

* Software: Any Clarius version
* KXCI terminal setup: String Terminator = None, Reading Delimiter= String Terminator, Set to ethernet mode
* KXCI Configuration (set within KCON): TH, String Terminator = None, Reading Terminator = String Terminator
* Python: Version 3.6 or later
* Dependencies:  **[instrcomms.py](../System%20Mode/instrcomms.py)**, time, pyVISA
* Optional dependencies (Need for the code to run, but can be modified to run with it. All lines are marked where these can be removed) plotly.express, pandas

## Directory

* **Combined user mode example.py** This example uses the SMU KXCI's user mode to source a 100 nA current on SMU1, and sets SMU2 to be a voltage source, sourcing 5 volts.50 voltage readings are then taken on channel 1.
* **Source current and measure voltage.py** This example uses SMU KXCI's user mode to set SMU1 to source current, outputting 1 nA and measures one reading of voltage on SMU1.
* **Source voltage and measure current.py** This example uses SMU KXCI's user mode to set SMU1 to source voltage, ouputting 5 V and measures one reading of current on SMU1.
* **Source voltage from voltage source.py** This example uses SMU KXCI's user mode to set SMU1 to be a voltage source,outputting 5 V, and measures one reading of voltage on SMU1.

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

- Combined user mode example.py：SMU1 输出 100 nA，SMU2 输出 5 V，在通道 1 读取 50 次电压。
- Source current and measure voltage.py：SMU1 输出 1 nA，读取一次电压。
- Source voltage and measure current.py：SMU1 输出 5 V，读取一次电流。
- Source voltage from voltage source.py：SMU1 配成 5 V 电压源，读取一次电压。

通信依赖位于 [System Mode/instrcomms.py](../System%20Mode/instrcomms.py)。

## 本库中的位置
此处保留官方示例说明。实际维护入口见 [SMU I-V](../../../../measurements/smu/iv/README.md)，参数含义见 [手册速查](../../../manuals/PARAMETER_LIMITS.md)。示例代码未因本次注释整理而修改。
