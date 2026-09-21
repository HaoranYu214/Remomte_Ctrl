# -*- coding: utf-8 -*-

# 阅读入口：SMU 单点 I–V；先改 INST、CHANNEL、SOURCE_VOLTAGE、CURRENT_COMPLIANCE 和接线。
# 流程：main → 初始化 User Mode → 施加电压 → 等待/读电流 → 打印结果 → 关闭源并恢复路由。
# SETTLE_TIME_S 是读前等待，DEVICE_AREA_CM2 用于计算电流密度；本入口不自动保存文件。

"""User Mode spot I-V example with explicit compliance and shutdown."""

from pathlib import Path
import sys
import time

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.smu.session import SMUSession
from keithley4200.smu.user_mode import (
    initialize_user_mode,
    measure_current,
    power_off_voltage_source,
    restore_user_mode_rpms,
    source_voltage,
)


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
DEVICE_AREA_CM2 = (20e-4) ** 2
CHANNEL = 1
SOURCE_VOLTAGE = 0.1
CURRENT_COMPLIANCE = 1e-3
VOLTAGE_RANGE_CODE = 0
SETTLE_TIME_S = 0.1

# Physical SMU-to-probe wiring for this 4200A.
SMU_CONNECTIONS = {
    1: "rpm:PMU1-1",
    2: "rpm:PMU1-2",
    3: "direct",
    4: "direct",
}


# 连接 SMU 施加 SOURCE_VOLTAGE，等待后读电流并打印电流密度，最后关闭源并恢复路由。
# 此入口只在终端打印单点结果，不保存工作簿。
def main():
    if DEVICE_AREA_CM2 <= 0:
        raise ValueError("DEVICE_AREA_CM2 must be positive.")
    with SMUSession(INST) as session:
        query = session.query
        rpm_targets = initialize_user_mode(
            query,
            active_channels=(CHANNEL,),
            smu_connections=SMU_CONNECTIONS,
        )
        try:
            source_voltage(
                query,
                CHANNEL,
                SOURCE_VOLTAGE,
                CURRENT_COMPLIANCE,
                range_code=VOLTAGE_RANGE_CODE,
            )
            time.sleep(SETTLE_TIME_S)
            current = measure_current(query, CHANNEL)
            current_density = current / DEVICE_AREA_CM2
            print(
                f"CH{CHANNEL}: V={SOURCE_VOLTAGE:g} V, "
                f"I={current:.6e} A, J={current_density:.6e} A/cm²"
            )
        finally:
            # Do not restore an RPM relay unless DV shutdown succeeds. If
            # shutdown raises, leave the RPM blue/SMU-routed for safe diagnosis.
            power_off_voltage_source(query, CHANNEL)
            restore_user_mode_rpms(query, rpm_targets)


if __name__ == "__main__":
    main()
