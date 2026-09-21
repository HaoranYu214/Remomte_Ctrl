# Keithley4200Measurement

[English](#english) | [中文](#中文)

## English

Python measurement library and experiment collection for the Keithley
4200A-SCS. The repository deliberately separates reusable instrument code,
editable experiment recipes, multi-step workflows, and vendor references.

## Layout

- `src/keithley4200/pmu`: reusable PMU commands, sessions, processing, plotting.
- `src/keithley4200/smu`: reusable SMU system/user-mode commands and RPM routing.
- `measurements/pmu`: editable PMU experiment recipes grouped by device/test type.
  See the [FET entry guide](measurements/pmu/fet/README.md) for pulse, program/read, and sweep entry points.
- `measurements/smu`: editable SMU experiment recipes.
- `measurements/workflows`: multi-test measurement packages and one-click routes.
- `src/keithley4200/tools`: offline preview and dry-run helpers.
- `reference`: official examples and manuals; not maintained as production code.
- `tests`: hardware-free unit tests using fake instrument responses.

Experiment files remain directly runnable. Each one adds this repository's
`src` directory to `sys.path`, so an editable install is optional. For normal
library use, install once with `python -m pip install -e .` and import from
`keithley4200`.

Running an experiment can contact the instrument. Unit tests and waveform
preview helpers are hardware-free.


## Saved results

Automatic measurement outputs use short names, with voltage before timing:

```text
PV2_03.00V_tr250us_td1000us_r001.xlsx
PV2_03.00V_tr250us_td1000us_r001_i2.png
PV2_03.00V_tr250us_td1000us_r002.xlsx
PUNDtri_03.50V_tr250us_td1000us_r001.xlsx
PUND_03.50V_tr250us_td1000us_tw50us_r001.xlsx
```

- `tr`: rise time; `td`: delay; `tw`: dwell/pulse width. Times use microseconds,
  including fractions such as `0.1us`. PV2 and PUND always include delay.
- Voltage uses at least two integer digits and two fixed decimal places, so
  positive labels below 100 V sort as `03.00V, 03.01V, 03.02V`.
  Labels round to 0.01 V; settings that round to the same label receive different run numbers.
  Full precision remains in saved parameters. Negative bias labels retain the minus sign; alphabetical ordering is not a
  signed numerical sort, and magnitudes of 100 V or more need numeric sorting.
- Each acquisition reserves the first available `r001, r002, ...` for the entire
  workbook/image group. Existing companions count as occupied, even if the
  workbook is missing. Full parameters and an ISO `saved_at` timestamp remain in
  the parameter-bearing workbooks; display labels are not a parameter archive.
- Reservations use exclusive file creation in `.reservations/`, coordinating
  separate processes using the shared helper. Keep this internal ledger with
  the data directory. Interrupted or failed runs can leave gaps intentionally.
- Standalone measurements and batch workflows use their configured directories
  directly. No automatic time subdirectory is added; existing test/stage folders
  are retained. Summary outputs include a per-invocation time, for example
  `map_summary_20260911_103449_r001.xlsx`. The same Excel summary is updated
  after each stage and at completion; no duplicate CSV is produced. Updates
  replace the previous workbook only after the new file has been written.
  A `time` column records the same ISO timestamp. Output paths are omitted
  so summaries remain useful after moving the data. A later invocation
  reserves a new summary name, including for same-second runs.
- Existing data is not renamed. Script/module names and measurement waveforms
  are unchanged. Explicit low-level save/preview functions still honor the exact
  path supplied by their caller; automatic naming belongs at the acquisition
  entry point.

PV/PUND polarization figures show I2 only; raw I1 data and I1 analysis tables remain saved.

The common helpers live in `src/keithley4200/output.py`. Reserve a stem once with
`reserve_output_stem(directory, measurement_name(...))`, then append extensions
or plot suffixes to that same stem for every companion output.

## Offline dry runs

`python src/keithley4200/tools/dry_run.py --no-save measurements/pmu/fe_cap/PV2.py` intercepts
instrument communication and generates synthetic data from the configured
Segment Arb or pulse commands. Segment Arb skips unmeasured segments, retains
their elapsed time, returns one point per spot measurement, and samples each
waveform segment at 32 points. The ordinary data reader still parses the
responses, including block reads and pulse High/Low fields.

These data test software flow; they do not simulate device physics or the
instrument sample rate. Averaged acquisition modes and acquisitions exceeding
65,536 synthetic points raise explicit errors. Run the helper in a separate
process: its communication, sleep, and optional save hooks are process-wide.

After an editable install, the equivalent module command is
`python -m keithley4200.tools.dry_run --no-save measurements/pmu/fe_cap/PV2.py`.
Preview helpers are imported from `keithley4200.tools.waveform_preview`.
Explicit relative script paths are resolved from the current working directory;
the default RV2 script is located relative to the source checkout. A packaged
installation without the experiment files requires an explicit script path.

## Usage navigation

- [Measurement entries](measurements/README.md): choose a test and adjust device parameters.
- [Workflows](measurements/workflows/README.md): batch sweeps and multi-step measurements.
- [Shared source](src/README.md): package structure and tools.
- [Parameter and mode reference](reference/manuals/PARAMETER_LIMITS.md): voltage/current ranges, SMU compliance, mode codes such as 0/1/2, and source page numbers.
- [Tests](tests/README.md): offline verification instructions.

Parameter comments explain usage; they do not replace verification of a device's safe operating range. The documentation work does not change experiment parameters.

Parameter source: [manual limits and mode reference (Chinese)](reference/manuals/PARAMETER_LIMITS.md).

## 中文

### Keithley4200Measurement

用于 Keithley 4200A-SCS 的 Python 测量库与实验脚本集合。公共仪器代码、可编辑实验、多步工作流及厂商参考资料分别存放。

## 目录结构

- src/keithley4200/pmu：PMU 命令、会话、数据处理和绘图。
- src/keithley4200/smu：SMU System/User Mode 命令及 RPM 路由。
- measurements/pmu：按器件和测试类型组织的 PMU 实验；入口见 [FET 指南](measurements/pmu/fet/README.md)。
- measurements/smu：可编辑的 SMU 实验。
- measurements/workflows：多测试组合与参数扫描。
- src/keithley4200/tools：离线预览及 dry-run。
- reference：官方示例和手册，不作为维护中的实验代码。
- tests：使用模拟仪器响应的离线测试。

实验文件可直接运行，会把仓库 src 加入导入路径。作为库使用时，在仓库根目录执行 python -m pip install -e .，再从 keithley4200 导入。实测入口可能连接仪器；单元测试与波形预览不连接仪器。

## 保存结果

文件名优先显示电压，再显示时间参数，例如 PV2_03.00V_tr250us_td1000us_r001.xlsx；同次测量的图形沿用同一文件主名并加 _i2.png 等后缀。下一次同名测量使用 r002。

- tr 为上升时间，td 为等待时间，tw 为平台或脉宽。时间用微秒表示，允许 0.1us 等小数；PV2/PUND 始终包含 delay。
- 电压至少两位整数、固定两位小数，因此 100 V 以下正电压可按名称正确排序。标签舍入至 0.01 V，舍入后同名的测试用不同编号区分，参数表保留完整数值。负电压保留负号；负数和 100 V 以上数值需按数值排序。
- 每次采集为整组表格与图形占用首个空闲 r001/r002 编号。即使表格不存在，已有配套图形也视为占用。包含参数的表格保留完整参数和 ISO 格式 saved_at，文件名不能替代参数记录。
- .reservations/ 使用独占文件创建协调多个进程，应随数据目录保留。失败或中断可能有意留下空号。
- 独立测试和工作流直接使用设置的目录，不再额外增加时间目录，已有测试/阶段目录保留。汇总名仍包含本轮时间，例如 map_summary_20260911_103449_r001.xlsx，每个阶段及结束时更新同一 Excel，不再生成重复 CSV；新工作簿写好后才替换上一版。time 列记录同一 ISO 时间，不保存输出路径，便于移动数据。下一轮占用新编号，同秒运行也不覆盖。
- 已有数据不重命名。底层保存/预览函数仍使用调用者给定的精确路径；自动命名在采集入口完成。

PV/PUND 极化图只画 I2；I1 原始数据和分析表仍保存。

公共命名在 src/keithley4200/output.py：调用 reserve_output_stem(directory, measurement_name(...)) 一次，整组输出共享返回的主名。

## 离线模拟

在仓库根目录运行：

    python src/keithley4200/tools/dry_run.py --no-save measurements/pmu/fe_cap/PV2.py

工具拦截通信，根据配置的 Segment Arb 或普通脉冲命令产生模拟数据。SARB 不测量的段仍累计时间；定点段返回一点，波形段返回 32 点。普通读取器继续解析这些响应，包括分块读取和脉冲 High/Low 字段。

模拟用于检查软件流程，不模拟器件物理或真实采样率。平均采集模式和超过 65,536 模拟点的采集会明确报错。通信、sleep 和保存替换影响整个进程，应在独立进程运行。

可编辑安装后也可使用 python -m keithley4200.tools.dry_run --no-save 加实验路径。预览从 keithley4200.tools.waveform_preview 导入。显式相对路径以当前工作目录为准；默认 RV2 路径相对源码仓库确定。只安装包、未包含实验文件时，必须提供实验文件路径。

## 中文使用导航
- [测量入口](measurements/README.md)：选测试、改器件参数。
- [工作流](measurements/workflows/README.md)：批量扫描和多步测量。
- [公共源码](src/README.md)：包结构及工具。
- [参数与模式速查](reference/manuals/PARAMETER_LIMITS.md)：电压、电流档、SMU 限流、0/1/2 等模式码及来源页码。
- [测试说明](tests/README.md)：离线验证方式。

参数注释是使用说明，不会替代验证器件安全范围；本次文档整理不改变实验参数。

参数依据：[手册限制与模式速查](reference/manuals/PARAMETER_LIMITS.md)。
