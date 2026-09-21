# SMU reusable layer

[English](#english) | [中文](#中文)

## English

This folder separates the two KXCI SMU command families:

- `system_mode.py`: Clarius-style sweeps using `DE`, `CH`, `SS`, `VR/IR`,
  `HT`, `DT`, `IT`, `ME`, `SP`, and `DO`.
- `user_mode.py`: direct spot control using `US`, `DV/DI`, and `TI/TV`.

SMU and PMU sessions share the maintained VISA implementation in
`../transport.py`; the vendor `instrcomms.py` remains under `reference` only.

Do not mix CVU `:CVU:SPEED` commands with SMU `IT` commands. Ethernet tests
poll `SP`; `DR` is for GPIB Data Ready service requests.

The initialization helpers send `EM 1,0`, clear the KXCI error queue, reset the
instrument, and disable every explicitly configured available channel before
defining active channels. Active System Mode channels use automatic standby;
exceptions and interrupts trigger best-effort `ME4` abort and channel disable.

`routing.py` validates explicit per-channel probe connections. RPM-backed
channels are selected with `RP PMUN-C, 2` only after `*RST`; direct channels
are untouched. After output standby/shutdown, switched RPMs are returned with
`RP PMUN-C, 0`. Runnable experiments expose this map as `SMU_CONNECTIONS` so
the physical topology is not hidden in the reusable layer.

Do not restore an RPM after an uncertain shutdown. The run helpers restore
Pulse mode only after successful completion with automatic SMU standby. Error,
timeout, and interrupt paths abort/disable best-effort but intentionally leave
the RPM routed to the SMU for diagnosis.

The API remains close to the official examples while adding the validation and
cleanup behavior needed for real experiments. Runnable entries remain under
`measurements/smu/iv`.

Completed System Mode data is downloaded with `DO`. `RD` is reserved for
real-time retrieval when the expected point count is already known; a returned
`0` means that point is not ready, not that the data buffer has ended.

Numeric `RG` values specify the lowest autoranged measurement range, not a
fixed range. Use `"auto"` or `None` when preamplifier availability is unknown.

`data_processing.py` saves untouched measurements/statuses to `Raw` and a
fixed numeric extraction table to `PlotData`. `plotting.py` plots absolute
current on a true logarithmic axis so tick labels remain physical amperes.

## Frequently adjusted parameters

In System Mode, DT is the per-point delay, HT is the hold before the sweep, and IT is integration time. RG selects the autorange floor; current compliance is a separate parameter. The User Mode DV range argument is a range code, not a voltage entered directly in volts. See the manual reference below.

Parameter source: [manual limits and mode reference (Chinese)](../../../reference/manuals/PARAMETER_LIMITS.md).

## 中文

### SMU 公共层

两个 KXCI 命令族分别实现：

- system_mode.py：使用 DE、CH、SS、VR/IR、HT、DT、IT、ME、SP 和 DO 完成扫描。
- user_mode.py：使用 US、DV/DI 和 TI/TV 直接控制单点输出与测量。

SMU 和 PMU 共用 ../transport.py 的 VISA 实现；厂商 instrcomms.py 仅保留在 reference 中。CVU 的 :CVU:SPEED 不能与 SMU 的 IT 混用。Ethernet 轮询 SP；DR 用于 GPIB Data Ready 服务请求。

初始化发送 EM 1,0、清除错误并复位。System Mode 在定义活动通道前关闭 AVAILABLE_CHANNELS 指定的所有通道，并为活动通道设置自动 standby；异常或中断时尽力 ME4 中止并关闭通道。

routing.py 根据显式接线映射校验通道。RPM 通道在 *RST 后使用 RP PMUN-C, 2 接入 SMU，直连通道不切换。确认 standby/关闭输出后才用 RP PMUN-C, 0 恢复 Pulse。关断状态不确定时不能恢复 RPM；错误、超时、中断时保持 SMU 路由供检查。实验通过 SMU_CONNECTIONS 暴露接线拓扑。

接口贴近官方示例，并增加实测所需校验和清理。可运行入口在 measurements/smu/iv。完成后用 DO 下载；RD 用于已知点数的实时读取，返回 0 表示该点尚未就绪，不代表缓冲结束。

RG 数值表示自动量程下限，并非固定测量档。前放配置不确定时使用 auto 或 None。data_processing.py 把原始读数及状态保存到 Raw，把数值提取表保存到 PlotData；plotting.py 在真实对数轴上绘制绝对电流，刻度仍以安培表示。

## 常改参数
System Mode 的 DT 是每点等待，HT 是整次扫描前等待，IT 是积分时间。RG 是自动量程下限，电流 compliance 是另一个参数。user_mode 的 DV range 参数是代码编号，不是直接填伏特值。详见下方手册速查。

参数依据：[手册限制与模式速查](../../../reference/manuals/PARAMETER_LIMITS.md)。
