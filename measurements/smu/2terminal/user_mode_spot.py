# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Entry: SMU spot I-V; edit INST, CHANNEL, SOURCE_VOLTAGE, CURRENT_COMPLIANCE, and wiring.
# Flow: main -> initialize User Mode -> force voltage -> wait/read current -> print -> turn off source and restore routing.
# SETTLE_TIME_S is the wait before reading; DEVICE_AREA_CM2 converts current density. This entry does not save files.

"""User Mode spot I-V example with explicit compliance and shutdown."""

from pathlib import Path
import sys
import time
import operator

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.smu.session import SMUSession
from keithley4200.smu.common import validate_channel, raise_for_kxci_error
from keithley4200.smu.user_mode import (
    initialize_user_mode,
    measure_current,
    restore_user_mode_rpms,
)


INST = "TCPIP0::192.0.2.1::1225::SOCKET"
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


# Force SOURCE_VOLTAGE, wait, read current, print current density, then turn off the source and restore routing.
# Print the spot result to the terminal without saving a workbook.
def main():
    if DEVICE_AREA_CM2 <= 0:
        raise ValueError("DEVICE_AREA_CM2 must be positive.")
    validate_channel(CHANNEL)
    range_code = operator.index(VOLTAGE_RANGE_CODE)
    if range_code not in range(6):
        raise ValueError("Voltage range code must be 0..5.")
    with SMUSession(INST) as session:
        query = session.query
        rpm_targets = initialize_user_mode(
            query,
            active_channels=(CHANNEL,),
            smu_connections=SMU_CONNECTIONS,
        )
        try:
            # DV: channel, voltage-source range (0=auto), voltage (V), and current compliance (A).
            query(f"DV{CHANNEL}, {range_code}, {SOURCE_VOLTAGE}, {CURRENT_COMPLIANCE}")
            raise_for_kxci_error(query, context="Spot voltage setup")
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
            query(f"DV{CHANNEL}")  # DV without arguments turns off the voltage source.
            restore_user_mode_rpms(query, rpm_targets)


if __name__ == "__main__":
    main()
