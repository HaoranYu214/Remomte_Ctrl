# SMU I-V experiments

[English](#english) | [中文](#中文)

## English

Scripts in this folder keep experiment parameters near the top while reusing
connection, command, execution, and data helpers from
`src/keithley4200/smu` alongside the PMU library in
`src/keithley4200/pmu`.

- `linear_voltage_sweep.py`: System Mode two-channel voltage sweep.
- `segmented_voltage_sweep.py`: arbitrary turning-point path such as
  `0 -> V1 -> 0 -> V2 -> 0`.
- `user_mode_spot.py`: User Mode source-voltage/measure-current spot test.

System Mode entries expose `AVAILABLE_CHANNELS`. List every SMU installed and
mapped in KCon: the library disables that complete set before defining the
active sweep/bias channels. Completed buffers must be nonempty, equal-length,
and match the programmed point count before they are saved.

Every runnable entry also exposes `SMU_CONNECTIONS`. Use `"direct"` for an
SMU wired straight to a probe, or `"rpm:PMUN-C"` for an SMU whose probe path
passes through the RPM attached to that PMU channel. The current instrument
uses RPM paths for SMU1/SMU2 (`PMU1-1`/`PMU1-2`) and direct paths for
SMU3/SMU4.

The two-terminal sweep workbooks use three worksheets in a stable order:

1. `Raw`: commanded values, every measured buffer, and the original KXCI
   status columns.
2. `PlotData`: `CommandedVoltage`, then `V1`, `I1`, `J1_A_per_cm2`,
   `AbsI1`, `AbsJ1_A_per_cm2`, followed by the corresponding V2/I2/J2
   columns. It contains no status columns and is intended for plotting and
   scripted extraction.
3. `Parameters`: the complete experiment configuration.

The two-terminal sweep entries expose `DEVICE_AREA_CM2`. FET entries instead save Id/Ig in amperes; see their own guide for workbook sheets. Raw current remains in amperes; the
processed current density is `J = I / DEVICE_AREA_CM2` in A/cm². Default PNGs
plot J-V and log(abs(J))-V. Major log tick labels display physical values such
as `1e-2` and `1e-1` A/cm² rather than their numerical log10 exponents.

## Segmented memristor sweep

[segmented_voltage_sweep_Memristor.py](segmented_voltage_sweep_Memristor.py) changes the positive peak between cycles while using a fixed negative peak. POSITIVE_PEAK_STEP controls the change between peaks; SEGMENT_STEP controls sampling steps within each segment. The fully expanded list is limited to 4096 points per execution.

Parameter source: [manual limits and mode reference (Chinese)](../../../reference/manuals/PARAMETER_LIMITS.md).

### IV endurance

[iv_endurance.py](iv_endurance.py) repeats the full segmented_voltage_sweep path LOOP_COUNT times. Edit TURNING_POINTS, SEGMENT_STEP, PARAMS, DEVICE_AREA_CM2, and SAVE_DIR at the top; initial values are copied from the standalone segmented script. PREVIEW_ONLY=True shows one path without connecting or saving; set it to False for acquisition. Each run saves Raw/PlotData/Parameters plus both current-density plots under a run-numbered filename. One Excel summary is updated after every attempt, including failures/interruption, without output paths. Errors stop subsequent runs. Each list remains limited to 4096 points; loops are separate acquisitions with transfer/save/reconnection gaps. INTER_RUN_DELAY_S adds an optional host sleep between completed runs. Workflow callers can use run_endurance(loop_count=..., params_override=..., turning_points=..., save_dir=..., preview_only=False). The standalone segmented entry now also accepts explicit run_test overrides; main() remains compatible.

## 中文

### SMU I-V 实验

脚本顶部保留实验参数，复用 src/keithley4200/smu 的连接、命令、执行和数据辅助，与 PMU 库并列。

- linear_voltage_sweep.py：System Mode 双通道线性电压扫描。
- segmented_voltage_sweep.py：任意转折点路径，例如 0 → V1 → 0 → V2 → 0。
- user_mode_spot.py：User Mode 电压源、电流单点测量。

System Mode 的 AVAILABLE_CHANNELS 必须列出 KCon 中全部已安装和映射的 SMU，库先关闭这些通道，再定义活动扫描/偏置通道。保存前确认缓冲非空、长度一致并等于设定点数。

SMU_CONNECTIONS 描述实际接线：direct 为直接连接探针；rpm:PMUN-C 为经过指定 PMU 通道的 RPM。当前系统 SMU1/2 经 PMU1-1/2，SMU3/4 直连。

上述两端扫描的工作簿包含（FET 的工作表见 3terminal 指南）：

1. Raw：设定电压、全部测量缓冲及原始 KXCI 状态。
2. PlotData：CommandedVoltage，然后 V1、I1、J1_A_per_cm2、AbsI1、AbsJ1_A_per_cm2，随后为通道 2 对应列；不含状态，供绘图/提取。
3. Parameters：完整实验配置。

两端扫描的 DEVICE_AREA_CM2 为器件面积；FET 入口直接保存 Id/Ig，不做面积归一化。原始电流单位 A，电流密度 J=I/DEVICE_AREA_CM2，单位 A/cm²。默认 PNG 绘制 J-V 和 log(abs(J))-V；对数刻度显示实际 1e-2、1e-1 A/cm² 等值，不是 log10 指数。

## Memristor 分段扫描
[segmented_voltage_sweep_Memristor.py](segmented_voltage_sweep_Memristor.py) 逐次改变正峰值，配合固定负峰值。POSITIVE_PEAK_STEP 决定峰值之间的变化，SEGMENT_STEP 决定每段内的采样步长。最终展开列表每次最多 4096 点。

参数依据：[手册限制与模式速查](../../../reference/manuals/PARAMETER_LIMITS.md)。

### IV endurance

[iv_endurance.py](iv_endurance.py) 将 segmented_voltage_sweep 的完整路径重复 LOOP_COUNT 次。顶部 TURNING_POINTS、SEGMENT_STEP、PARAMS、DEVICE_AREA_CM2、SAVE_DIR 初始复制独立 segmented 文件的配置，可在本文件单独修改。PREVIEW_ONLY=True 只预览一轮、不连接或保存，改为 False 实测。每轮分别保存 Raw/PlotData/Parameters 和两张电流密度图，文件名带轮次；每次尝试后更新同一份 Excel 汇总，失败或中断也记录，不保存路径列。失败停止后续轮次。每轮最多 4096 点，轮次间包含传输、保存和重新连接的停顿；INTER_RUN_DELAY_S 是额外的软件等待。workflow 可调用 run_endurance(loop_count=..., params_override=..., turning_points=..., save_dir=..., preview_only=False)。独立 segmented 另提供显式传参的 run_test，原 main() 保持兼容。
