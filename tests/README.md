# Offline regression tests

[English](#english) | [中文](#中文)

## English

Tests use unittest, fake communication, or temporary directories to check behavior without sending test commands to a real instrument.

- test_smu: SMU commands, readings, shutdown, and RPM routing.
- test_output_naming: output-group numbering, overwrite protection, and summary timestamps.
- test_review_fixes / test_tools_package: FET channel mapping, import isolation, synthetic readout, and tool-package startup.
- test_fe_cap_load_options / test_waveform_ownership: forwarding entry parameters to shared code and keeping waveforms in their owning entries.
- Other files cover endurance, FORC, NLS, FTJ, and workflow scenarios.

Run from the repository root in PowerShell:

```powershell
$env:MPLBACKEND = "Agg"
python -m unittest discover -s tests
```

Agg removes the GUI requirement for plotting tests. Passing tests does not establish a specific device's safe test range.

Parameter source: [manual limits and mode reference (Chinese)](../reference/manuals/PARAMETER_LIMITS.md).

## 中文

### 离线回归测试

这里使用 unittest、假通信或临时目录验证行为，不向真实仪器发送测试命令。

- test_smu：SMU 命令、读数、关断与 RPM 路由。
- test_output_naming：保存组编号、防覆盖及汇总时间。
- test_review_fixes / test_tools_package：FET 通道映射、导入隔离、模拟读数及工具包启动。
- test_fe_cap_load_options / test_waveform_ownership：入口参数到公共层的传递及波形归属。
- 其余按 endurance、FORC、NLS、FTJ 和 workflow 场景验证。

在仓库根目录运行（PowerShell）：

```powershell
$env:MPLBACKEND = "Agg"
python -m unittest discover -s tests
```

Agg 使绘图测试不依赖 GUI。测试通过不等同于验证了具体器件的安全测试范围。

参数依据：[手册限制与模式速查](../reference/manuals/PARAMETER_LIMITS.md)。
