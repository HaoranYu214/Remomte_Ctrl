# FET parameter sweeps

[English](#english) | [中文](#中文)

## English

- [delay_sweep.py](delay_sweep.py): calls the base bipolar program/read test for each DELAY_TIMES value, programs the device again, and summarizes Id versus delay.
- [read_bias_delay_sweep.py](read_bias_delay_sweep.py): sweeps Vg, Vd, and delay, adds repeated program/read tests for each Vg/Vd pair, and calculates state-separation metrics and rankings.

Both call [bipolar_program_read.py](../bipolar_program_read.py), inheriting its write voltages, positive/negative repetition counts, and cycle count. These are not continuous readbacks of a single programmed state, and each delay need not produce only one pair of readings.

DELAY_TIMES values above 1 s use the base entry's software-wait branch; the actual interval includes reconfiguration overhead. VG_READ_VALUES/VD_READ_VALUES must also respect the PMU voltage range and the device's allowable read conditions.

Parameter source: [manual limits and mode reference (Chinese)](../../../../reference/manuals/PARAMETER_LIMITS.md).

## 中文

### FET 参数扫描

- [delay_sweep.py](delay_sweep.py)：逐个 DELAY_TIMES 调用基础正负写读测试，每次重新写入，汇总 Id 随等待时间的变化。
- [read_bias_delay_sweep.py](read_bias_delay_sweep.py)：组合扫描 Vg、Vd、delay，并对每组 Vg/Vd 追加重复写读，再生成状态区分指标及排序。

两者调用 [bipolar_program_read.py](../bipolar_program_read.py)，写入电压、正负重复次数、循环次数继承自该入口。扫描不是对同一次写入状态持续读回；不应把每个 delay 自动理解为只有一对数据。

DELAY_TIMES > 1 s 会走基础入口的软件等待分支；精确间隔还含重配置开销。VG_READ_VALUES/VD_READ_VALUES 同样受 PMU 电压档和器件允许读取条件限制。

参数依据：[手册限制与模式速查](../../../../reference/manuals/PARAMETER_LIMITS.md)。
