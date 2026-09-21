# Standard PMU Pulse mode

[English](#english) | [中文](#中文)

## English

These scripts use :PMU:INIT 0 with generic CH1/CH2 roles. They do not assign Gate/Drain or control SMU3; use [FET Segment Arb entries](../fet/README.md) for program/read.

| Entry | Main settings |
|---|---|
| [pulse_train.py](pulse_train.py) | CH1/CH2 amplitudes, widths, delays and PULSE_COUNT |
| [pulse_sweep.py](pulse_sweep.py) | CH1_START/STOP/STEP, CH1_DUALSWEEP and fixed CH2_AMPLITUDE |

Edit the top settings and output directory before direct execution. Imports do not acquire; these entries have no PREVIEW_ONLY switch.

TEST_MODE selects 0=no acquisition, 1=spot, 2=waveform, 3=averaged spot or 4=averaged waveform. Current ranges select measurement sensitivity, not SMU compliance. Standard Pulse width/timing definitions differ from Segment Arb; consult the [parameter reference](../../../reference/manuals/PARAMETER_LIMITS.md).

Saved outputs use shared naming and run-number reservations. Personal launchers should point to this pulse directory.

## 中文

本目录使用 :PMU:INIT 0，以通用 CH1/CH2 配置，不指定 Gate/Drain，也不控制 SMU3。写读测试使用 [FET Segment Arb 入口](../fet/README.md)。

| 入口 | 主要参数 |
|---|---|
| [pulse_train.py](pulse_train.py) | CH1/CH2 幅值、脉宽、延迟和 PULSE_COUNT |
| [pulse_sweep.py](pulse_sweep.py) | CH1_START/STOP/STEP、CH1_DUALSWEEP、固定 CH2_AMPLITUDE |

直接执行前修改顶部参数和输出目录。导入不采集；这些入口没有 PREVIEW_ONLY 开关。

TEST_MODE：0=不采集、1=定点、2=波形、3=平均定点、4=平均波形。电流档控制测量灵敏度，不是 SMU 限流。普通 Pulse 的脉宽/时间定义与 Segment Arb 不同，参见[参数速查](../../../reference/manuals/PARAMETER_LIMITS.md)。

输出使用公共命名和编号预留。个人启动脚本应指向当前 pulse 目录。
