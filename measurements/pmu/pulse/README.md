# Standard PMU pulse tests

[English](#english) | [中文](#中文)

## English

These entries use standard Pulse mode (`:PMU:INIT 0`) with generic CH1/CH2 settings. They do not assign fixed Gate/Drain roles or control SMU3. See [fet](../fet/README.md) for three-terminal SegArb program/read tests.

| Entry | Purpose | Main parameters |
|---|---|---|
| [pulse_train.py](pulse_train.py) | Two fixed-amplitude pulse trains; channel delays can stagger the pulses | CH1/CH2 amplitude, width, delay, PULSE_COUNT |
| [pulse_sweep.py](pulse_sweep.py) | Sweeps CH1 pulse amplitude while CH2 produces a fixed-amplitude train | CH1_START/STOP/STEP, CH1_DUALSWEEP, CH2_AMPLITUDE |

Edit parameters near the top of each script, then run it directly. Importing a module does not start a measurement. Output locations are configured in each script; saves use shared naming and automatic numbering rules.

TEST_MODE selects instrument acquisition: 0 no acquisition, 1 spot, 2 waveform, 3 averaged spot, and 4 averaged waveform. Current measurement ranges are not SMU-style current compliance. Standard Pulse timing definitions differ from SegArb. See the [shared parameter guide (Chinese)](../../../reference/manuals/PARAMETER_LIMITS.md) for range and timing limits.

These scripts previously lived in measurements/pmu/fet/. Update old paths in IDE run configurations or scripts outside this repository.

## 中文

### PMU 普通脉冲测试

本目录使用普通 Pulse 模式（`:PMU:INIT 0`），通过 CH1/CH2 配置双通道脉冲；不固定 Gate/Drain 角色，也不控制 SMU3。三端 SegArb 写读测试见 [fet](../fet/README.md)。

| 入口 | 用途 | 主要参数 |
|---|---|---|
| [pulse_train.py](pulse_train.py) | 两路固定幅值脉冲串，可通过通道延迟错开脉冲 | CH1/CH2 幅值、脉宽、延迟、PULSE_COUNT |
| [pulse_sweep.py](pulse_sweep.py) | CH1 扫描脉冲幅值，CH2 输出固定幅值脉冲串 | CH1_START/STOP/STEP、CH1_DUALSWEEP、CH2_AMPLITUDE |

在脚本顶部修改参数后直接运行；导入模块不会启动测量。输出目录在各脚本中设置，保存使用公共命名和自动编号规则。

TEST_MODE 是仪器采集模式：0 不采集，1 定点，2 波形，3 平均定点，4 平均波形。电流测量档不是 SMU 式限流；普通 Pulse 模式的时间定义与 SegArb 不同。范围和时间限制见[公共参数说明](../../../reference/manuals/PARAMETER_LIMITS.md)。

这两个脚本原位于 measurements/pmu/fet/；IDE 运行配置或库外脚本中的旧路径需要更新。
