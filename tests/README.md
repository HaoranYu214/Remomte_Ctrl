# Offline regression tests

[English](#english) | [中文](#中文)

## English

Keep these tests in Git: they protect command generation, cleanup, waveform ownership and saved-data behavior as experiments change. They use unittest, fake communication and temporary directories without instrument acquisition.

Run from the repository root:

~~~powershell
$env:MPLBACKEND = "Agg"
python -m unittest discover -s tests
~~~

Agg avoids GUI requirements. Install project dependencies first with python -m pip install -e ..

Coverage includes SMU point generation/readout/routing, PMU waveform and timing rules, parameter forwarding, import/tool startup, workflow/endurance behavior, output numbering and atomic workbook replacement. Test names describe the scenario; use an individual file while changing that area, then run the suite.

These are software checks. KXCI display/buffer behavior, actual instrument timing and device response require separate hardware verification. Test fixtures containing non-English text intentionally check encoding and should retain that data.

## 中文

测试保留在 Git 中，用于在实验变化时检查命令生成、清理、波形归属和保存行为。使用 unittest、模拟通信和临时目录，不执行仪器采集。

在仓库根目录运行：

~~~powershell
$env:MPLBACKEND = "Agg"
python -m unittest discover -s tests
~~~

Agg 避免依赖图形窗口。先执行 python -m pip install -e . 安装项目依赖。

覆盖 SMU 取点/读数/路由、PMU 波形和时间规则、参数传递、导入/工具启动、工作流/endurance、文件编号及工作簿原子替换。测试名对应场景；修改局部时先运行对应文件，再运行整套测试。

这些检查验证软件。KXCI 显示/缓冲、真实时间和器件响应仍需硬件验证。测试数据中的非英文文本用于检查编码，应保留。
