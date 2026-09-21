# Measurement entry points

[English](#english) | [中文](#中文)

## English

This directory contains directly runnable experiment scripts whose parameters are adjusted for each device. Shared communication and data-reading code lives in [src/keithley4200](../src/keithley4200/README.md).

- [pmu](pmu/README.md): pulse measurements, ferroelectric capacitors, and FTJ/FET program/read tests.
- [smu](smu/README.md): DC I-V sweeps and spot measurements.
- [workflows](workflows/README.md): sequences of tests and parameter sweeps.

### Choose an experiment

| Task | Start here |
|---|---|
| One PV or PUND measurement | [PV2](pmu/fe_cap/PV2.py), [triangular PUND](pmu/fe_cap/PUND_tri.py), [square PUND](pmu/fe_cap/PUND_Squr.py) |
| PV2 followed by PUND | [pv_and_pund](workflows/pv_and_pund.py) |
| FTJ characterization | [FTJ entry guide](pmu/ftj/README.md), [complete FTJ package](workflows/ftj_package1.py) |
| FeFET write/read | [single polarity](pmu/fet/program_read.py), [both polarities](pmu/fet/bipolar_program_read.py) |
| DC I–V | [segmented sweep](smu/iv/segmented_voltage_sweep.py), [repeated sweeps](smu/iv/iv_endurance.py) |
| FORC or NLS | [programmed experiments](pmu/programmed/README.md) |

### Reading an experiment file

Start with the short reading guide at the top: it names the editable settings, execution order, and preview behavior. Then read the configuration and the entry called at the bottom (`run_test`, `main`, or a named runner). Read waveform builders or analysis helpers when you need to understand that part of the experiment. Function comments explain their role; functions taking `query` use a connection supplied by their caller.

For entries supporting `params_override`, overrides replace matching defaults for that run. Waveform helpers taking `parameters` expect a complete dictionary; copy the defaults and update it. See the [parameter API](pmu/README.md#standalone-and-workflow-configuration) for details. Accepted PV/PUND current ranges are an explicit exception: acquisition can write them back to default settings.

Edit the workflow configuration when running a workflow. FeFET sweeps and FTJ endurance still inherit unspecified settings from their target experiment; their file headers identify those dependencies. Preview selection is entry-specific: some `main` functions measure directly, and some files have no `PREVIEW_ONLY` switch. Follow the reading guide in each file.

Review INST, channel assignments, physical wiring, voltages, current ranges/compliance, and SAVE_DIR before running an entry. The exact PREVIEW_ONLY=True behavior is described by each entry; normal execution may immediately apply the test waveform. The instrument's maximum output is not the device's safe test voltage.

Parameter source: [manual limits and mode reference (Chinese)](../reference/manuals/PARAMETER_LIMITS.md).

## 中文

### 测量入口

这里放可直接运行、需要按器件修改参数的实验脚本。公共通信和读数代码在 [src/keithley4200](../src/keithley4200/README.md)。

- [pmu](pmu/README.md)：脉冲、铁电电容、FTJ 和 FET 写读。
- [smu](smu/README.md)：直流 I-V 和单点测量。
- 多个测试的顺序和参数扫描在 [workflows](workflows/README.md)。

### 按实验选择入口

| 想做什么 | 打开哪个文件 |
|---|---|
| 单次 PV 或 PUND | [PV2](pmu/fe_cap/PV2.py)、[三角 PUND](pmu/fe_cap/PUND_tri.py)、[方波 PUND](pmu/fe_cap/PUND_Squr.py) |
| 先 PV2 再 PUND | [pv_and_pund](workflows/pv_and_pund.py) |
| FTJ 表征 | [FTJ 入口说明](pmu/ftj/README.md)、[FTJ 全套](workflows/ftj_package1.py) |
| FeFET 写读 | [单极性](pmu/fet/program_read.py)、[双极性](pmu/fet/bipolar_program_read.py) |
| 直流 I–V | [分段扫描](smu/iv/segmented_voltage_sweep.py)、[重复扫描](smu/iv/iv_endurance.py) |
| FORC 或 NLS | [程序化实验入口](pmu/programmed/README.md) |

### 一个实验文件怎么看

先看文件顶部的阅读指引，找到参数位置、执行顺序和预览方式；然后看配置区，以及文件末尾调用的入口（`run_test`、`main` 或对应 runner）。想了解波形时再看构建函数，想了解数据处理时再看分析函数。每个函数前的中文注释解释它在实验中的职责；接收 `query` 的函数使用调用者提供的仪器连接。

支持 `params_override` 的入口会用覆盖值替换本次运行的同名默认参数。波形辅助函数的 `parameters` 则需要完整字典，应复制默认参数后再修改，详见[参数接口](pmu/README.md#独立运行与工作流配置)。PV/PUND 自动量程是例外：实测接受的电流档会回写默认设置。

运行 workflow 时改 workflow 自己的配置；FeFET 扫描和 FTJ endurance 未覆盖的设置仍继承目标实验，具体来源见各文件顶部说明。预览分支也以各入口为准：有的 `main` 直接实测，有的文件没有 `PREVIEW_ONLY` 开关。

先看脚本顶部的 INST、通道、接线、电压、电流量程/限流和 SAVE_DIR。PREVIEW_ONLY=True 的含义以各入口说明为准；普通运行可能直接输出测试波形。手册最大输出不等于当前器件的安全电压。

参数依据：[手册限制与模式速查](../reference/manuals/PARAMETER_LIMITS.md)。
