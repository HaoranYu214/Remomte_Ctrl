# Three-terminal FET tests / 三端 FET 测试

[output.py](output.py)：固定 Vgs，扫描 Vds；[transfer.py](transfer.py)：固定 Vds，扫描 Vgs。
通道定义、测试点、配置命令和采集步骤直接写在各文件中；基础教学见 [example.py](example.py)。

## Source 使用电压源

Gate→SMU1，Drain→SMU2，Source→SMU3。三个端子都使用电压源模式。
Source 默认固定 0 V，并且同时测量、保存 VS 和 IS：

~~~python
query("CH3, 'VS', 'IS', 1, 3")
query("SS")
query("VC3, 0.0, 0.001")  # Source 0 V，独立限流 1 mA。
~~~

PARAMS 中各端子参数独立：

| 参数 | 默认值 | 含义 |
|---|---|---|
| source_voltage | 0.0 | Source 固定电压，V |
| gate_compliance | 1e-6 | Gate 电流限值，A |
| drain_compliance | 1e-3 | Drain 电流限值，A |
| source_compliance | 1e-3 | Source 电流限值，A |
| gate_current_range | auto | Gate 自动量程下限 |
| drain_current_range | auto | Drain 自动量程下限 |
| source_current_range | auto | Source 自动量程下限 |

current_range 可为 auto 或正数（A）；它不是固定量程，也不是 compliance。
Source 的限流需要覆盖预期回流；达到限流时实际 VS 可能偏离设定值，保留原始状态。
原始读数为 VG/IG、VD/ID、VS/IS。处理后的 VGS=VG−VS、VDS=VD−VS。

扫描路径和固定偏置按 Vgs/Vds 定义。若修改 source_voltage，程序给 Gate/Drain 指令加上 Source 偏置，
使相对电压设置保持一致；实测相对电压仍由读回值相减得到。

## 扫描与运行

| 设置 | output 默认 | transfer 默认 |
|---|---|---|
| MODE | output | transfer |
| TURNING_POINTS | [0, 1] | [-1, 1, -1] |
| STEP | 0.05 V | 0.05 V |
| FIXED_BIASES | [0, 0.5, 1] Vgs | [0.1] Vds |

共享转折点只测一次，单条列表最多 4096 点。每个固定偏置独立测一条曲线，期间包含关断、保存和重连。
修改 INST、通道和 SMU_CONNECTIONS 对应实际接线。PREVIEW_ONLY=True 只预览相对电压计划；
改成 False 才连接仪器。SHOW_RESULTS 控制完成后显示 Python 图，PNG 仍保存。

~~~powershell
python measurements/smu/3terminal/output.py
python measurements/smu/3terminal/transfer.py
~~~

hold_time 是首点保持；sweep_delay 是每点读前等待（均为 s）。integration 为 IT1/2/3，
对应 0.1/1/10 PLC。timeout_s 可为 None、auto 或正秒数。

## 六变量采集与显示

默认 KXCI_PLOT=False，使用 DM2 + LI，明确启用 VG、IG、VD、ID、VS、IS 六个变量。
保留 True 供以后实机试验：先 LI 六列，再切 DM1，横轴为扫描端 VG 或 VD，两个纵轴为 IG、IS。
仍读取并检查六列的点数，缺列或点数不符会报错，不保存为完整曲线。
尚未验证切换后额外缓冲是否保留测量；点数通过也不等于确认数据有效，实机还需核对未画出的 ID 等读数。
不能据此断言仪器在 DM1 下最多只能采集三个变量。
DM1/DM2 是显示及测量选择设置；VR/VL 是线性/列表扫描设置，不能混为一谈。
KXCI_IG_LIMITS 控制 IG 图轴（None 使用 ±gate_compliance）；IS 轴使用 ±source_compliance。
改画其他变量可直接编辑 XN/YA/YB；不再保留未参与绘图的 ID 轴配置。
Python 仍保存 Id、log(abs(Id))、Ig 三联图；Is 原始数据在 Excel 中。

依据：[KXCI 手册](../../../reference/manuals/4200A-KXCI-907-01D_May_2024.pdf) 的 CH（5-7）、
LI（5-23）和 DO（5-37 至 5-38）；LI 只启用列出的测量量。

## 输出和中断

每次保存带运行编号的 Excel 和 PNG。Excel 包括：

- Raw：CurveIndex、点序号、指令 Vgs/Vds/Vs、三端电压电流、状态、VGS/VDS。
- Curves：偏置、起止时间、完成/失败/中断、点数、任意通道限流的点数。
- SweepPlan：所有曲线的完整指令点和 Source 偏置。
- Parameters：仪器、接线、三端独立参数和 Source 电压源配置。

每条曲线更新一次工作簿，失败时保留之前完成的数据。未完整读回的当前曲线不会作为完成结果保存。
保留带符号电流和限流状态，不自动提取阈值/迁移率，不做面积归一化。

## English

Source now uses voltage-source constant bias (0 V by default), with independent compliance and current
range floor. All six voltage/current buffers are acquired in list mode; measured VGS and VDS subtract VS.
KXCI_PLOT defaults to False. True enables an unverified hardware trial: LI all six variables, then DM1
with IG and IS against the swept voltage. All six buffers are still requested and their lengths checked.
Python plots and Excel output remain available, including raw IS and its status.

## 公共模块职责

[points.py](../../../src/keithley4200/smu/points.py) 负责线性、分段、对数和自定义列表的通用规则。
[fet.py](../../../src/keithley4200/smu/fet.py) 保留 output/transfer 共用的参数检查与曲线族表结构；原子写入复用 output.py。
FET 离线预览位于 smu/preview.py，结果图位于 smu/plotting.py；这些函数不发送仪器命令。
CH、VL、VC、时序、量程、采集和可选 KXCI 图形配置均在实验文件中直接展开。
