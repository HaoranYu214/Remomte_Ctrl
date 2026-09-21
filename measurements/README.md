# Measurement entry points

[English](#english) | [中文](#中文)

## English

This directory contains directly runnable experiment scripts whose parameters are adjusted for each device. Shared communication and data-reading code lives in [src/keithley4200](../src/keithley4200/README.md).

- [pmu](pmu/README.md): pulse measurements, ferroelectric capacitors, and FTJ/FET program/read tests.
- [smu](smu/README.md): DC I-V sweeps and spot measurements.
- [workflows](../workflows/README.md): sequences of tests and parameter sweeps.

Review INST, channel assignments, physical wiring, voltages, current ranges/compliance, and SAVE_DIR before running an entry. The exact PREVIEW_ONLY=True behavior is described by each entry; normal execution may immediately apply the test waveform. The instrument's maximum output is not the device's safe test voltage.

Parameter source: [manual limits and mode reference (Chinese)](../reference/manuals/PARAMETER_LIMITS.md).

## 中文

### 测量入口

这里放可直接运行、需要按器件修改参数的实验脚本。公共通信和读数代码在 [src/keithley4200](../src/keithley4200/README.md)。

- [pmu](pmu/README.md)：脉冲、铁电电容、FTJ 和 FET 写读。
- [smu](smu/README.md)：直流 I-V 和单点测量。
- 多个测试的顺序和参数扫描在 [workflows](../workflows/README.md)。

先看脚本顶部的 INST、通道、接线、电压、电流量程/限流和 SAVE_DIR。PREVIEW_ONLY=True 的含义以各入口说明为准；普通运行可能直接输出测试波形。手册最大输出不等于当前器件的安全电压。

参数依据：[手册限制与模式速查](../reference/manuals/PARAMETER_LIMITS.md)。
