# FeFET parameter sweeps

[English](#english) | [中文](#中文)

## English

Both runners call [bipolar_program_read.py](../bipolar_program_read.py) with per-run overrides.

| Entry | Grid and outputs |
|---|---|
| [delay_sweep.py](delay_sweep.py) | DELAY_TIMES; summary and current-versus-delay plots |
| [read_bias_delay_sweep.py](read_bias_delay_sweep.py) | VG_READ_VALUES × VD_READ_VALUES × DELAY_TIMES; state-window/contrast rankings, plots and FEFET_REPEAT_N/T repetitions |

Set the base entry to acquisition mode before launching these measurement runners. They inherit write conditions, repeat/cycle counts, hardware, output root and floating-Gate options. Every grid point programs again, and inherited repetitions can yield more than one positive/negative pair.

Delays must be positive. Above 1 s the base test uses a host-wait branch with configuration overhead. Select read biases within the instrument and device limits. See the [base guide](../README.md) for ordering, floating Gate and saved data.

## 中文

两个执行器均通过按次覆盖调用 [bipolar_program_read.py](../bipolar_program_read.py)。

| 入口 | 网格及输出 |
|---|---|
| [delay_sweep.py](delay_sweep.py) | DELAY_TIMES；汇总及电流随等待时间变化图 |
| [read_bias_delay_sweep.py](read_bias_delay_sweep.py) | VG_READ_VALUES × VD_READ_VALUES × DELAY_TIMES；状态窗口/对比度排名、绘图及 FEFET_REPEAT_N/T 重复测试 |

启动这些实测入口前，将基础入口设为采集模式。写入条件、重复/循环次数、硬件、输出根目录和浮栅选项均继承基础设置。每个网格点重新写入，继承的重复次数可能产生多对正负读数。

等待时间必须为正；超过 1 s 时基础测试使用主机等待分支，实际时间包含重配置开销。读偏置需符合仪器和器件限制。执行顺序、浮栅及输出见[基础指南](../README.md)。
