# Python source directory

[English](#english) | [中文](#中文)

## English

src is the source root used during installation; [keithley4200](keithley4200/README.md) is the actual package name. This layer keeps imports under from keithley4200... and avoids conflicts with unrelated top-level pmu/tools packages.

Run python -m pip install -e . from the repository root for an editable installation. Measurement entries add src to their import path and can usually run directly. Experiment parameters live in [measurements](../measurements/README.md), and multi-step tasks in [workflows](../workflows/README.md).

Parameter source: [manual limits and mode reference (Chinese)](../reference/manuals/PARAMETER_LIMITS.md).

## 中文

### Python 源码目录

src 是安装时的源码根目录，[keithley4200](keithley4200/README.md) 是实际包名。保留这一层后，代码统一用 from keithley4200... 导入，避免顶层 pmu/tools 与其他库重名。

在仓库根目录运行 python -m pip install -e . 可做可编辑安装。测量入口会加入 src 路径，通常也可直接运行。实际实验参数在 [measurements](../measurements/README.md)，多步任务在 [workflows](../workflows/README.md)。

参数依据：[手册限制与模式速查](../reference/manuals/PARAMETER_LIMITS.md)。
