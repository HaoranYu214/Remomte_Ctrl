# Two-terminal SMU examples

[English](#english) | [中文](#中文)

## English

[example.py](example.py) starts with CH1 sweeping voltage and CH2 holding 0 V. It reads both voltages and currents, with statuses. Terminal roles are generic and follow your wiring.

### Build a test

Copy example.py and edit these sections in order:

1. INST, AVAILABLE_CHANNELS and SMU_CONNECTIONS describe the instrument and all installed/mapped SMUs.
2. SAVE_DIR, CHANNEL_* and PREVIEW_ONLY/KXCI_PLOT select this run.
3. POINT_METHOD and its range/step/list/count define the sweep.
4. PARAMS defines independent compliance/range per channel and shared sampling settings.

CHANNEL_1 is a role whose value is a physical SMU number; ch1_* parameters follow that role. V/I readout names follow the physical number. The example defaults to PREVIEW_ONLY=True: print commands and plot voltages without connecting or saving. Set False to acquire. Existing recipes have their own current defaults.

configure() keeps the commands together in the same file for both preview and acquisition. Read CH → VL/VC → HT/DT/IT → ST → RG/LI/display. Shared helpers handle point algorithms, connection, routing, polling/abort, parsing and saving.

### Point rules

| POINT_METHOD | Settings | Behavior |
|---|---|---|
| linear | START, STOP, STEP | Direction matches step sign |
| list | LIST_POINTS | Retains order and repeated points |
| segments | TURNING_POINTS, STEP | Positive scalar or per-segment steps; shared turns appear once |
| log | LOG_START, LOG_STOP, LOG_COUNT | Geometric spacing; nonzero endpoints of the same sign |

All four send VL lists, at most 4096 points. Linear/segmented paths include endpoints; a final interval may be shorter. For example, 0 to 1 by 0.05 gives 21 points; reversing linear uses 1 to 0 by -0.05. These are point rules, not the full set of Clarius test modes.

### Source modes, range and sampling

CH specifies physical channel, V name, I name, source mode and function. Source modes are 1=voltage, 2=current, 3=Common; functions are 1=VAR1, 2=VAR2, 3=constant, 4=follow. The example uses voltage sourcing with VAR1 and constant channels. VAR2/follow need additional configuration.

VL selects a voltage list with current compliance in A; VC selects constant voltage. Current lists use IL and constant current uses IC, with voltage compliance and CH source mode 2. Changing source mode also requires appropriate parameter units, preview axes and readout settings.

Each channel has independent current compliance and current_range. "auto" keeps reset defaults; a positive range value sends an RG autorange floor in A, not a fixed measurement range. A constant 0 V voltage source can still measure terminal current; it is not Common.

HT holds before the first point; DT waits after each output update; IT1/2/3 integrate for 0.1/1/10 PLC. DT is not a fixed sample period. timeout_s=None has no overall deadline; a positive number sets seconds and "auto" requests an estimate.

### Multiple lists and displays

VL takes physical channel, then 1=master or 0=subordinate. A multi-list extension should validate equal lengths and pointwise alignment in Python: [0, .5, 1] with [0, .1, .2] gives three joint points. VC channels need no list. Clarius aligns subordinate lengths, but KXCI's unequal-list behavior is unspecified; do not rely on automatic padding/trimming. The example comments explain the extension, not a complete multi-list switch: channel definitions, preview and hardware verification also need updating.

DM2 is list display, DM1 is graph display; this choice is independent of VL. PREVIEW_ONLY is an offline command preview. KXCI_PLOT is a separate acquisition-time option.

### Existing recipes

- [linear_voltage_sweep.py](linear_voltage_sweep.py): linear voltage path.
- [segmented_voltage_sweep.py](segmented_voltage_sweep.py): turning-point path; run_test accepts per-run overrides.
- [segmented_voltage_sweep_Memristor.py](segmented_voltage_sweep_Memristor.py): multiple loops with changing peaks.
- [iv_endurance.py](iv_endurance.py): repeat complete segmented runs, save each and update a summary.
- [user_mode_spot.py](user_mode_spot.py): one active SMU using User Mode DV; prints results without a workbook.

KXCI_PLOT=True selects sweep voltage as X and the two currents as Y axes. Readback still requests and checks four variables. Endurance displays only the current round. Real window/buffer behavior needs hardware confirmation. Python result plots and saving are separate.

The fixed-bias channel has its own bias_voltage, bias_current_compliance and bias_current_range. Current density uses DEVICE_AREA_CM2. See [EXPERIMENTS.md](EXPERIMENTS.md) for recipe details and the [manual reference](../../../reference/manuals/PARAMETER_LIMITS.md) for documented limits.

## 中文

[example.py](example.py) 默认 CH1 扫电压、CH2 固定 0 V，读取两端电压、电流及状态。端子不绑定器件名称，用途由接线决定。

### 新建测试

复制 example.py，按以下顺序修改：

1. INST、AVAILABLE_CHANNELS、SMU_CONNECTIONS：仪器及全部已安装、映射的 SMU。
2. SAVE_DIR、CHANNEL_*、PREVIEW_ONLY/KXCI_PLOT：本次运行设置。
3. POINT_METHOD 及对应范围、步长、列表或点数：扫描路径。
4. PARAMS：各通道独立限流和量程，以及公共采样设置。

CHANNEL_1 是通道角色，值为物理 SMU 编号；ch1_* 参数跟随这一角色，V/I 读数名字跟随物理编号。example 默认 PREVIEW_ONLY=True，只打印命令、画指令电压，不连接或保存。设为 False 后实测；其他现成实验查看各自当前默认值。

configure() 将命令集中写在同一文件中，供预览和实测共用。按 CH → VL/VC → HT/DT/IT → ST → RG/LI/显示阅读即可。公共函数负责取点算法、连接、路由、轮询/中止、解析和保存。

### 取点规则

| POINT_METHOD | 参数 | 行为 |
|---|---|---|
| linear | START、STOP、STEP | 步长正负与扫描方向一致 |
| list | LIST_POINTS | 保留顺序和重复点 |
| segments | TURNING_POINTS、STEP | 正步长或逐段正步长；相邻段共用转折点只保留一次 |
| log | LOG_START、LOG_STOP、LOG_COUNT | 几何间隔，端点同号且非零 |

四种方式都下发 VL，每次最多 4096 点。线性/分段包含终点，最后一步可能缩短。例如 0 到 1、步长 0.05 共 21 点；反向线性扫描用 1 到 0、步长 -0.05。这些是取点规则，并非 Clarius 全部测试模式。

### 源模式、量程与采样

CH 指定物理通道、V 名、I 名、源模式和功能。源模式：1=电压、2=电流、3=Common；功能：1=VAR1、2=VAR2、3=固定、4=跟随。示例使用电压源，配合 VAR1 和固定端；VAR2/跟随需要额外配置。

VL 是电压列表，限流单位 A；VC 是固定电压。电流列表用 IL，固定电流用 IC，限压单位 V，并将 CH 源模式设为 2。更换源模式时还要修改参数单位、预览坐标和读数设置。

每路独立配置 current_compliance 和 current_range。"auto" 沿用复位默认；正数通过 RG 设置自动量程下限，单位 A，不是固定测量档。固定 0 V 的电压源仍可测量端子电流，与 Common 不同。

HT 是首点保持，DT 是每点输出后的等待，IT1/2/3 对应 0.1/1/10 PLC 积分。DT 不代表固定采样周期。timeout_s=None 不设整体截止时间，正数表示秒数，"auto" 使用估算。

### 多列表与显示

VL 先指定物理通道，再用 1=主列表、0=从列表。扩展多列表时应在 Python 校验等长且逐点对应：[0, .5, 1] 和 [0, .1, .2] 共三个联合测点。VC 固定端不需要列表。Clarius 会对齐从列表长度，但 KXCI 未明确不等长行为，因此不依赖自动补齐或截断。示例注释说明扩展方法，并未提供完整多列表开关，还需调整通道定义、预览并实机验证。

DM2 是列表显示，DM1 是图形显示，与 VL 扫描方式独立。PREVIEW_ONLY 是离线指令预览，KXCI_PLOT 是实测时的另一项设置。

### 已有实验

- [linear_voltage_sweep.py](linear_voltage_sweep.py)：线性电压路径。
- [segmented_voltage_sweep.py](segmented_voltage_sweep.py)：转折点路径，run_test 支持按次覆盖。
- [segmented_voltage_sweep_Memristor.py](segmented_voltage_sweep_Memristor.py)：变化峰值的多回线。
- [iv_endurance.py](iv_endurance.py)：重复完整分段测试，逐轮保存并更新汇总。
- [user_mode_spot.py](user_mode_spot.py)：一个活动 SMU 的 User Mode DV 单点测试，只打印、不保存表格。

KXCI_PLOT=True 时 X 为扫描电压，两路电流分别作为纵轴；仍读取并检查四个变量。Endurance 只显示当前轮次。实际窗口与缓冲行为需要实机确认。Python 结果图和保存独立处理。

固定端有独立的 bias_voltage、bias_current_compliance、bias_current_range。电流密度通过 DEVICE_AREA_CM2 换算。现成实验细节见 [EXPERIMENTS.md](EXPERIMENTS.md)，参数限制见[手册速查](../../../reference/manuals/PARAMETER_LIMITS.md)。
