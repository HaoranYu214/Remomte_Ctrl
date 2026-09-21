# Python source

[English](#english) | [中文](#中文)

## English

[keithley4200](keithley4200/README.md) is the installed package; src is its source root. Install from the repository root with:

~~~powershell
python -m pip install -e .
~~~

Use imports beginning with keithley4200. Experiment settings belong in [measurements](../measurements/README.md), and batch plans in [workflows](../measurements/workflows/README.md). Those directories are part of the checkout, not the installed package.

## 中文

[keithley4200](keithley4200/README.md) 是安装包名，src 是源码根目录。在仓库根目录安装：

~~~powershell
python -m pip install -e .
~~~

导入路径以 keithley4200 开头。实验设置放在 [measurements](../measurements/README.md)，批量计划放在 [workflows](../measurements/workflows/README.md)。这两个目录属于源码仓库，不随公共库安装。
