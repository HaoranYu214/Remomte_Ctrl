# 参数限制：手册依据与代码约定

依据本地 [4200A-KXCI-907-01D，Rev. D，May 2024](4200A-KXCI-907-01D_May_2024.pdf)。下文页码是手册印刷页码，例如 7-52 对应 PDF 第 173 页。章节 5 是 SMU，章节 7 是 PMU/PGU；本库的 PMU 注释采用 4225-PMU 条件，不能套用 PGU 的更短时序。

这些是指令参数边界，不代表器件可以承受的测试条件。涉及模块型号、量程、前置放大器或 RPM 的项目必须按实际配置选择。本文没有改变任何实验参数，也不表示代码已校验全部边界。

## PMU 电压与电流

| 参数/命令 | 手册限制与含义 | 印刷页 |
|---|---|---|
| 通道 ch | 指令支持 1–8，实际最大值由已安装通道决定；本库主要使用 PMU1 的 1/2 通道 | 7-15、7-48 |
| SOURCE:RANGE | 10 V 或 40 V；INIT 后默认为 10 V。改实验电压数值不会自动选择 40 V | 7-24 |
| SARB STARTV/STOPV | 10 V 档端点在 -10…10 V，40 V 档在 -40…40 V；同一序列相邻段的 stop/start 电压必须连续 | 7-48、7-50 |
| PULSE:TRAIN | vbase 与 vamplitude 是基准和峰值电平；10/40 V 档的两电平跨度最多 10/40 V，不能将它理解成任意 ±10/±40 V 脉冲跨度 | 7-21 |
| MEASURE:RANGE | 0 自动、1 有下限的自动、2 固定；Segment Arb 必须用固定量程 | 7-15–7-16 |

电流测量量程（A），按 7-15 表格整理：

| 硬件/电压档 | 可用电流量程 |
|---|---|
| 10 V PMU，无 RPM | 0.2、0.01 |
| 40 V PMU，无 RPM | 0.8、0.01、0.0001 |
| 10 V RPM | 0.2、0.01、0.001、0.0001、0.00001、0.000001、0.0000001 |
| 40 V RPM | 0.8、0.01、0.0001 |

100 nA = 1e-7 A 是表中最小档，只在 10 V RPM 列中可用。本库 current_range.py 的默认候选列表是 100 nA–1 mA，是实验策略采用的子集，不是全部硬件量程。自动改档是“固定档采集 → 分析 → 换档重测”，不会把 Segment Arb 设置成仪器 autorange。过量程判据、低利用率阈值、重试次数是代码策略，不是手册限制；重测会重新施加波形。

## Segment Arb 时序、序列与数据

| 项目 | 边界/含义 | 印刷页 |
|---|---|---|
| 每个实际 TIME 段 | PMU 10 V 档 20 ns–1 s；40 V 档 50 ns–1 s；时间分辨率 10 ns | 7-52 |
| 测量 START/STOP | 单位 s，相对本段起点，10 ns 分辨率；通常 0 ≤ start < stop ≤ 段长；手册允许 start=stop=0 的特殊情形 | 7-40、7-42 |
| MEAS:TYPE | 0 不测，1 离散定点平均，2 离散波形，3 跨脉冲定点平均，4 跨脉冲波形平均 | 7-44 |
| 序列编号 | 1–512；先定义再加入执行列表 | 7-48、7-56 |
| 序列硬件 loop | 1–1e12；不等于 Python 外层循环数 | 7-56 |
| 一条 SARB 数组命令 | 最多 128 个数组值；更长数组使用对应 :ADD 命令续传 | 7-40、7-48、7-52 |
| SAMPLE:RATE | 1e3–200e6 samples/s；INIT 默认 200e6 | 7-23 |
| KXCI 采样点预算 | 最大 65536 点；可能为最短测量窗升采样率，或为总点数降采样率，两个条件必须能够同时满足 | 7-24 |
| DATA:GET | 每次请求 1–2048 点，大数据按块读取；这不是存储段数 | 7-7 |

**2048 存储段的来源边界：** 本库 MAX_SEGMENTS_PER_SEQUENCE 当前设为 2048，公共校验按每通道全部已定义序列的段数之和检查。此数字沿用项目已有约定；本地这本 KXCI 手册中查到的 2048 明确用于 DATA:GET 读取块，未找到其作为硬件存储段总数的明确条款。不可将 7-7 当作存储段上限的依据；硬件存储能力还需 Pulse Card 用户手册核对。

不同脚本的时间变量要先换算成真实段长：

- PV2 存在 2 × rise_time 的段，因此单看 rise_time ≤ 1 s 不够；这些段要求 rise_time ≤ 0.5 s。
- PUND/FTJ/FET 的 dwell 是独立平台段持续时间；段总时间包含 rise、dwell、fall、idle。
- 普通 pulse mode 的 width 采用另一种定义，不能将其公式直接用于 SARB 平台段。
- FORC 的分支时间按反转电压缩放；靠近 +Vmax 的反转点可能产生过短的真实段。
- FET 的 READ_DELAY > 1 s 时，当前实现拆分写/读执行并用 Python 等待；通信和重配置也增加间隔，不能解释成精确硬件延迟。FTJ Identical V2 的 wait_after_* 同样属于软件等待。
- TYPE=0 的段在本库被设为 start=stop=0；测量段的通用校验要求正窗口。这是库对手册特殊情形的具体处理。

## 普通 PMU 脉冲模式

仅适用于 pulse_train.py、pulse_sweep.py 等调用 PULSE:TIMES 的入口；手册 7-17–7-19。

| 参数 | PMU 10 V 档 | 40 V 档 |
|---|---|---|
| period | 60 ns–1 s | 500 ns–1 s |
| width | 40 ns…period-10 ns | 250 ns…period-10 ns |
| rise/fall | 20 ns–33 ms | 50 ns–33 ms |
| delay | 0 或非零最小 20 ns | 0 或非零最小 50 ns |
| BURST:COUNT | 1–10000 | 1–10000 |

这些独立边界必须同时满足下列组合约束（7-19）：

- 所有活动通道共用 period，最后发送的 period 对全部通道生效。
- width < period，且 width > 0.5 × (rise + fall)；rise ≤ width。
- delay < period - width - 0.5 × (rise + fall)。
- off_time = period - delay - width - 0.5 × (rise + fall) > 40 ns。

PIV 的 StartPercent/StopPercent 均为 0–1 的比例（7-32），配置时保持先后顺序。WAVEFORM 的 PrePercent/PostPercent 也是 0–1，但含义是脉冲前后采集比例，不是起止坐标；比例基准为 width + 0.5 × (rise + fall)，前置采集时长不得超过 delay（7-34）。

## PMU 公共选项

- LOAD_RESISTANCE/LOAD_RESISTANCES：设置的 DUT 负载为 1–1e7 Ω（7-11）；这是输出电平计算使用的负载估计，不是电流合规保护。
- ENABLE_LLEC：0/1 开关；启用会在正式测量前迭代施加脉冲并估算负载（7-10）。本地 KXCI 页未明确承诺每种 SARB 用法的支持性；不能只因 Python 接受此字段就认为所有波形都支持。
- ENABLE_CONNECTION_COMP：启用已保存的补偿；短路/偏移校准需按各自接线条件执行，启用开关不等于完成校准（7-5、7-12）。
- RPM 路由：0=PMU，1=CV 两线，2=SMU，3=CV 四线（7-22）；由实际线缆拓扑决定，不是通过软件任意交换仪器通道。

## SMU 扫描与单点

| 参数 | 手册含义/限制 | 印刷页 |
|---|---|---|
| 通道 | 指令编号 1–9，必须与 KCon 中已安装/映射通道一致 | 5-6、5-33 |
| VL 电压列表、DV 电压 | -210…210 V 是指令外边界；实际输出还受模块量程和输出能力约束 | 5-16、5-33 |
| VL/IL 点数 | 单次列表最多 4096 点，按展开后的实际点数计算 | 5-16 |
| 电压源电流 compliance | 4200/4201 最大幅值 0.105 A；4210/4211 最大幅值 1.05 A；必须结合模块输出能力使用 | 5-33 |
| VL 最小电流 compliance | 有前放 100 pA，无前放 100 nA；低于允许值时 KXCI 提升到允许下限 | 5-16 |
| sweep_delay / DT | 0–6.553 s，设置输出到开始测量的等待，不含全部测量耗时 | 5-10 |
| hold_time / HT | 0–655.3 s，扫描开始前保持 | 5-12 |
| integration / IT | IT1=0.1 PLC，IT2=1 PLC，IT3=10 PLC；IT4 自定义 | 5-39 |
| IT4 X/Y/Z | X 延迟因子 0–100；Y 滤波因子 0–100；Z 积分时间 0.01–10 PLC | 5-39 |
| RG 数字量程 | 指定自动量程下限，并非固定测量档；无前放最低 100 nA，有前放可到 1 pA；最大测量档按型号为 100 mA 或 1 A | 5-41 |
| DV 的 range code | 0 自动；1=20 V；2/3=200 V；4=200 mV、5=2 V 需前放 | 5-33 |

对分段 I-V，SEGMENT_STEP 是每一段内的采样电压步长；Memristor 的 POSITIVE_PEAK_STEP 是相邻循环峰值的变化，两者共同决定最终列表点数。4096 是单次完整列表的限制，不是转折点列表长度限制。

RG 与 compliance 不是同一参数；1 pA 测量档也不意味着允许 1 pA 电流合规值。timeout_s、Python SETTLE_TIME_S、重复次数和文件保存开关属于程序设置，没有可直接套用的 KXCI 硬件上限。

## 数据处理参数

area_cm2/DEVICE_AREA_CM2 为器件有效面积，单位 cm²，分析时应为正数；不是仪器量程。电流 A 除以面积得到 A/cm²；电荷 C 除以面积并乘 1e6 得到 μC/cm²。CURRENT_EPS、RES_MIN/MAX、图形比例、文件标签均属于后处理或保存规则，不应标成手册的硬限制。

## 模式数字与保存参数怎么读

同一个数字在不同参数中含义不同，应先看参数名。

| 保存的参数/指令字段 | 取值含义 |
|---|---|
| TEST_MODE / MEAS:TYPE | 0 不采集但仍可输出；1 每脉冲/段定点平均；2 每次采波形；3 跨重复脉冲定点平均；4 跨重复脉冲波形平均（7-13、7-44） |
| IRangeType | 0 自动量程；1 指定自动量程下限；2 固定档（7-15）；与上面的 TEST_MODE=2 完全不同 |
| INIT 的参数 | 0 普通脉冲；1 Segment Arb（7-9–7-10） |
| CH1_DUALSWEEP | 0 单向扫描；1 往返扫描（7-29），不是双通道开关 |
| ACQUIRE_HIGH / ACQUIRE_LOW | 是否保存脉冲高/低电平的 V、I、时间、状态；至少开一项（7-14） |
| ENABLE_LOAD_CONFIG | 本库开关：True/1 发送 LOAD 配置；False/0 跳过，不代表 DUT 电阻为 0 |
| ENABLE_LLEC / ENABLE_CONNECTION_COMP | True/1 启用对应选项；False/0 关闭/不启用，具体命令见实现 |
| PREVIEW_ONLY | True 只走入口提供的预览流程；False 走测量流程；是程序开关，不是 KXCI 模式 |
| SAVE_WAVEFORM_PREVIEW | 是否额外保存预览，不控制器件是否输出，也不等同于保存/丢弃原始测量数据 |
| SAVE_EVERY_RUN | FTJ endurance 是否逐次保存目标测试结果；关闭时仍更新汇总 |
| MeasureSquare | 是否采集方形写入段；False 不取消该写入脉冲 |
| VRange / VOLTAGE_RANGE_CODE | SMU DV 的源量程代码，见 SMU 表；0 是自动，不能按 PMU 模式表解释 |

SARB seq_id 是波形序列的编号，loop 是执行次数；r001 是文件组编号。Raw/Channel 表里的 Status 是仪器原始状态码，不是上述布尔开关，也不能将任何非零值简单当作同一种错误。数据状态格式参见 7-7–7-8；SMU 读数状态参见 5-37–5-38。

## 仪器范围与器件安全范围

仪器允许 10/40 V 或 SMU 的 ±210 V，只说明对应指令能力。器件最大允许写入电压、读取电压、脉宽、占空比、电流和累计次数，要依据该器件已有测试结果或规格确定，库内没有经过验证的通用“安全范围”。

SMU 的 CURRENT_COMPLIANCE 才是电流合规参数；PMU 的 Irange/CURRENT_RANGES 是测量量程，LOAD_RESISTANCE 是负载补偿输入，二者都不能当成器件保护限流。PREVIEW_ONLY 和 dry-run 能验证流程或波形构造，不能证明实际器件安全。
