# Offline tools

[English](#english) | [中文](#中文)

## English

- [waveform_preview.py](waveform_preview.py): converts actual seq_configs to preview plots/numeric tables and provides program/read current overlays. It does not connect to the instrument.
- [dry_run.py](dry_run.py): intercepts communication commands and generates synthetic data from configured waveforms to check software flow.

Run from the repository root:

```powershell
python src/keithley4200/tools/dry_run.py --no-save measurements/pmu/fe_cap/PV2.py
```

After an editable installation, python -m keithley4200.tools.dry_run is also available. --no-save disables the Excel/CSV/figure saves covered by the hooks; explicit mkdir calls in an entry can still create directories.

Synthetic data does not represent device response or instrument sampling accuracy. SARB waveform segments use 32 samples and spot segments use one. Averaged modes and acquisitions exceeding the synthetic-point budget raise explicit errors. Communication/save/sleep replacements affect the whole process, so run dry-run in a separate process.

Parameter source: [manual limits and mode reference (Chinese)](../../../reference/manuals/PARAMETER_LIMITS.md).

## 中文

### 离线工具

- [waveform_preview.py](waveform_preview.py)：将实际 seq_configs 转成预览图/数值表，也提供写读电流叠图。它不连接仪器。
- [dry_run.py](dry_run.py)：拦截通信命令，根据已配置的波形产生模拟数据，供检查软件流程。

在仓库根目录运行：

```powershell
python src/keithley4200/tools/dry_run.py --no-save measurements/pmu/fe_cap/PV2.py
```

可编辑安装后也可使用 python -m keithley4200.tools.dry_run。--no-save 关闭工具覆盖的 Excel/CSV/图形保存；入口自身显式 mkdir 仍可能创建目录。

模拟数据不代表器件响应或仪器采样精度。SARB 波形段使用 32 点，定点测量使用 1 点；平均模式及超出模拟点预算会明确报错。通信/保存/sleep 替换是进程级的，使用独立进程运行 dry-run。

参数依据：[手册限制与模式速查](../../../reference/manuals/PARAMETER_LIMITS.md)。
