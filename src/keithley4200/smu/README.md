# SMU shared helpers

[English](#english) | [中文](#中文)

## English

Runnable examples live in [measurements/smu](../../../measurements/smu/README.md). Their CH, VL, VC, timing, RG and display commands remain directly readable.

| Module | Purpose |
|---|---|
| [session.py](session.py) | Connection lifecycle |
| [system_mode.py](system_mode.py) | Initialization, execution polling, abort handling and command support |
| [user_mode.py](user_mode.py) | User Mode support for spot measurements |
| [routing.py](routing.py) | Direct/RPM routing and cleanup |
| [common.py](common.py) | Shared SMU validation |
| [points.py](points.py) | Linear, segmented, log and explicit voltage lists |
| [data_processing.py](data_processing.py) | Parse readings/statuses, check point counts and prepare results |
| [preview.py](preview.py) | Commanded channel voltages and FET family previews |
| [plotting.py](plotting.py) | Measured J-V and FET plots |
| [fet.py](fet.py) | FET plan validation and family checkpoint tables |

Point generation is hardware-free. All current voltage-sweep entries send explicit VL lists, limited to 4096 points. Linear/segmented paths include endpoints; explicit lists retain repeats. Preview uses point index rather than elapsed time.

timeout_s=None removes the overall sweep deadline; positive seconds set one, and "auto" opts into an estimate. A VISA call still has its own timeout. Completion and failure handling remain shared so each experiment does not duplicate polling or abort logic.

The Source/bias channel is a voltage source, default 0 V, with independent compliance and autorange floor. RG is not compliance. FET plotting support is separate from the six-variable acquisition plan; KXCI graph mode with all six buffers remains a hardware trial.

## 中文

可运行示例在 [measurements/smu](../../../measurements/smu/README.md)，CH、VL、VC、时间、RG 和显示命令直接写在实验文件里。

| 模块 | 职责 |
|---|---|
| [session.py](session.py) | 连接生命周期 |
| [system_mode.py](system_mode.py) | 初始化、执行轮询、中止及命令支持 |
| [user_mode.py](user_mode.py) | User Mode 单点测试支持 |
| [routing.py](routing.py) | 直连/RPM 路由与清理 |
| [common.py](common.py) | SMU 公共校验 |
| [points.py](points.py) | 线性、分段、对数及显式电压列表 |
| [data_processing.py](data_processing.py) | 解析读数和状态、检查点数、整理结果 |
| [preview.py](preview.py) | 各通道指令电压及 FET 曲线族预览 |
| [plotting.py](plotting.py) | 实测 J-V、FET 图 |
| [fet.py](fet.py) | FET 计划校验及曲线族检查点表格 |

取点不需要仪器。当前电压扫描入口统一下发 VL 列表，每条最多 4096 点。线性和分段路径包含终点，显式列表保留重复点。预览横轴是点序号，不是实际时间。

timeout_s=None 不设整次扫描截止时间；正数指定秒数，"auto" 使用估算。单次 VISA 调用仍有自己的超时。完成轮询和异常中止共用公共处理。

Source/固定偏置端使用电压源，默认 0 V，并独立设置限流和自动量程下限。RG 不是限流。FET 画图与六变量采集计划分开；KXCI 图形模式下六列缓冲有效性仍需实机试验。
