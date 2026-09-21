# Keithley 4200A SMU tests

[English](#english) | [中文](#中文)

## English

The runnable experiments are in `iv/`. Their reusable KXCI implementation
lives in `src/keithley4200/smu/`.

Layout:

- `iv/`: editable experiment entries with parameters, safe session handling,
  validated data retrieval, and result saving.
- `../../reference/manuals/smu/`: the local Keithley KXCI programming manual.
- `../../reference/official_examples/smu/`: vendor examples retained for command-format
  comparison only. They are not production-safe experiment entries.

Runtime PMU and SMU connections use `src/keithley4200/transport.py`. The
vendor `instrcomms.py` in `reference/official_examples/smu/System Mode/` is kept
as an unmodified reference and is not imported by runnable experiments.

Before running an experiment, set `AVAILABLE_CHANNELS` to every SMU installed
and mapped in KCon. The library disables all of those channels first, then
defines only the requested sweep and bias channels.

Set `SMU_CONNECTIONS` to the physical probe wiring. On the current system,
SMU1 and SMU2 pass through the RPMs on PMU1 channels 1 and 2, while SMU3 and
SMU4 go directly to probes:

```python
SMU_CONNECTIONS = {
    1: "rpm:PMU1-1",
    2: "rpm:PMU1-2",
    3: "direct",
    4: "direct",
}
```

For active `rpm:` entries, the reusable layer selects RPM mode 2 after
`*RST` and before source setup (blue LED). It returns those RPMs to pulse mode
0 only after the SMUs enter standby or are explicitly powered off. Direct
entries do not send any RPM commands.

RPM safety rule: never switch the relay while an attached source may be
energized. A normally completed System Mode run uses `ST channel,1`, waits for
completion, then restores the RPM to pulse mode. User Mode explicitly powers
off with `DVchannel` before restoration. On timeout, command error, interrupt,
or failed shutdown, the library deliberately leaves the RPM in SMU mode rather
than risk switching an active source; inspect the instrument before recovery.

Manual locations in `reference/manuals/smu/4200A-KXCI-907-01D_May_2024.pdf`:

- Printed pages 7-67 to 7-68: `RP HRID, mode`, blue-SMU example, and the
  instruction to set outputs to 0 V before returning the RPM to pulse.
- Printed pages 7-22 to 7-23: equivalent `:PMU:RPM:CONFIGURE HRID, mode`
  command and all accepted modes (`0` PMU, `1` CV 2-wire, `2` SMU,
  `3` CV 4-wire).
- Printed page 5-14: `ST channel,1` automatic standby behavior.

Changing physical RPM/PMU cables is different from electronic `RP` switching:
power down the 4200A and disconnect mains before plugging or unplugging RPM
hardware, as required by the 4225-RPM hardware instructions.

For Ethernet KXCI, configure the command/string terminator to `None` in KCon;
the Python session sends and reads the required null (`\0`) terminator. Keep
the KXCI reading delimiter consistent with the comma-separated buffer format
used by `DO`.

## Parameters to check first

AVAILABLE_CHANNELS and SMU_CONNECTIONS must match the installed equipment and physical wiring. Select voltage, CURRENT_COMPLIANCE, and integration settings for the specific SMU model. Do not treat the instrument's maximum range as the device's safe test range.

Parameter source: [manual limits and mode reference (Chinese)](../../reference/manuals/PARAMETER_LIMITS.md).

## 中文

### Keithley 4200A SMU 测试

可运行实验在 iv/，公共 KXCI 实现在 src/keithley4200/smu/。reference/manuals/smu 保存本地编程手册，reference/official_examples/smu 保存用于对照的官方示例。正式入口不导入参考目录的 instrcomms.py，PMU/SMU 统一使用 src/keithley4200/transport.py。

AVAILABLE_CHANNELS 要列出 KCon 中全部已安装和映射的 SMU。库先关闭这些通道，再配置本次扫描和偏置通道。SMU_CONNECTIONS 必须匹配探针接线；当前系统 SMU1/2 经 PMU1 的两路 RPM，SMU3/4 直接连接：

    SMU_CONNECTIONS = {
        1: "rpm:PMU1-1",
        2: "rpm:PMU1-2",
        3: "direct",
        4: "direct",
    }

活动 rpm: 通道在 *RST 之后、输出配置之前切至模式 2（蓝灯），确认 SMU standby 或关闭输出后才恢复模式 0（Pulse）。direct 通道不发送 RPM 切换指令。

不要在相关源可能输出时切换继电器。正常 System Mode 使用 ST channel,1 自动 standby，等待完成后恢复 RPM；User Mode 用 DVchannel 关闭源再恢复。超时、错误、中断或关断失败时，库保留 SMU 路由，应先检查仪器。

本地 reference/manuals/smu/4200A-KXCI-907-01D_May_2024.pdf 的印刷页码：

- 7-67–7-68：RP HRID, mode、SMU 蓝灯示例，以及恢复 Pulse 前输出需置 0 V 的要求。
- 7-22–7-23：等价 :PMU:RPM:CONFIGURE；0=PMU、1=CV 两线、2=SMU、3=CV 四线。
- 5-14：ST channel,1 的自动 standby 行为。

物理插拔 RPM/PMU 电缆不同于电子 RP 切换；按 4225-RPM 硬件说明，插拔前关闭 4200A 并断开市电。

Ethernet KXCI 在 KCon 中把命令/字符串终止符设为 None，Python 会话负责 null 终止符。读取分隔符需与 DO 使用的逗号分隔缓冲格式一致。

## 参数先看什么
AVAILABLE_CHANNELS 和 SMU_CONNECTIONS 必须匹配实际设备/接线。电压、CURRENT_COMPLIANCE 和积分参数按具体 SMU 型号选择。不要把硬件最大范围直接当作器件的安全测试范围。

参数依据：[手册限制与模式速查](../../reference/manuals/PARAMETER_LIMITS.md)。
