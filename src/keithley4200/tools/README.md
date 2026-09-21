# Offline development tools

[English](#english) | [中文](#中文)

## English

[dry_run.py](dry_run.py) intercepts PMU communication and generates synthetic responses from pulse/Segment Arb commands. Run it in a separate process:

~~~powershell
python src/keithley4200/tools/dry_run.py --no-save measurements/pmu/fe_cap/PV2.py
~~~

After installation, python -m keithley4200.tools.dry_run is equivalent. Explicit relative script paths use the working directory; the default RV2 target needs the source checkout.

SARB waveform segments produce 32 points, spot segments one, and unmeasured segments retain elapsed time. Averaged modes and acquisitions exceeding 65,536 synthetic points raise errors. Data exercises the normal parser, not device physics or real sample rates.

Communication, sleep and optional saving hooks affect the whole process. --no-save suppresses covered workbook/CSV/figure saves; explicit directory creation may still occur. Dry runs do not persist synthetic current ranges into real defaults.

Preview helpers belong in [pmu/preview.py](../pmu/preview.py) and [smu/preview.py](../smu/preview.py); measured plots belong in each hardware package's plotting.py.

## 中文

[dry_run.py](dry_run.py) 拦截 PMU 通信，根据脉冲/Segment Arb 命令产生模拟响应。请在独立进程执行：

~~~powershell
python src/keithley4200/tools/dry_run.py --no-save measurements/pmu/fe_cap/PV2.py
~~~

安装后也可使用 python -m keithley4200.tools.dry_run。显式相对脚本路径以当前目录为准；默认 RV2 目标需要源码仓库。

SARB 波形段生成 32 点，定点段生成一点，不采集段仍累计时间。平均模式或超过 65,536 模拟点会报错。模拟数据经过正常解析器，但不代表器件物理或真实采样率。

通信、sleep 和可选保存钩子影响整个进程。--no-save 禁止钩子覆盖的表格、CSV 和图片保存；实验显式创建的目录仍可能出现。模拟量程不会写入真实默认设置。

预览分别在 [pmu/preview.py](../pmu/preview.py) 和 [smu/preview.py](../smu/preview.py)；实测图在各硬件包的 plotting.py。
