# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.
"""Generic two-terminal SMU example: define channels -> outputs -> sampling -> execute -> read."""
# Terminals are named CH1/CH2; their roles depend on the physical wiring.
# By default, CH1 sweeps voltage and CH2 holds 0 V; read voltage and current on both.
# Start at configure(): configuration commands are local; communication, waiting, and readout use shared helpers.

from pathlib import Path
import sys
import math

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT / "src"))

from keithley4200.output import reserve_output_stem
from keithley4200.smu.common import raise_for_kxci_error, normalize_channels
from keithley4200.smu.data_processing import retrieve_variables
from keithley4200.smu.routing import connect_smus_to_probes, restore_rpms_to_pulse
from keithley4200.smu.points import (
    build_linear_voltage_path, build_segmented_voltage_path,
    build_log_voltage_path, validate_list_points,
)
from keithley4200.smu.preview import preview_channel_voltages
from keithley4200.smu.session import SMUSession
from keithley4200.smu.system_mode import initialize_system_mode, execute_and_wait, shutdown_system_mode, resolve_smu_timeout_s

# 1. Instrument and wiring defaults: check when changing hardware or connections.
INST = "TCPIP0::192.0.2.1::1225::SOCKET"
AVAILABLE_CHANNELS = (1, 2, 3, 4)  # All installed SMUs mapped in KCon.
SMU_CONNECTIONS = {1: "rpm:PMU1-1", 2: "rpm:PMU1-2", 3: "direct", 4: "direct"}

# 2. Run settings: output directory, physical channels, offline preview, and instrument plots.
SAVE_DIR = Path("data/smu/2terminal/example")
CHANNEL_1 = 1  # Master voltage list.
CHANNEL_2 = 2  # Constant voltage bias.
PREVIEW_ONLY = True  # Plot commanded channel voltages and print commands without connecting or saving.
KXCI_PLOT = False  # True plots sweep voltage and both currents in KXCI; this is separate from offline preview.

# 3. Key sweep parameters: select a point rule; all paths use VL voltage lists.
POINT_METHOD = "linear"  # linear / list / segments / log
START, STOP, STEP = 0.0, 1.0, 0.05  # V; use a negative STEP for a reverse linear sweep.
LIST_POINTS = [0.0, 0.2, 0.5, 1.0, 0.5, 0.0]  # Preserve order and repeated points.
TURNING_POINTS = [0.0, 1.0, -1.0, 0.0]  # For segments, STEP is positive or a list of positive per-segment steps.
LOG_START, LOG_STOP, LOG_COUNT = 0.01, 1.0, 21  # Nonzero endpoints of the same sign, with geometric spacing.
# Linear/segment paths include endpoints; the last step may be shorter. Maximum 4096 points per sweep.

# 4. Electrical and sampling parameters: independent compliance and autorange floor per channel.
PARAMS = {
    "ch1_current_compliance": 1e-3,  # A; current compliance for the VL voltage source.
    "ch2_voltage": 0.0,  # V; a constant bias needs no list.
    "ch2_current_compliance": 1e-3,
    "ch1_current_range": "auto",  # auto: keep reset defaults; a positive number sets the RG floor in A.
    "ch2_current_range": "auto",
    "hold_time": 0.1,  # Hold before the first point, in seconds.
    "sweep_delay": 0.02,  # Wait after each output update, in seconds; this is not a fixed sampling period.
    "integration": "IT2",  # IT1 / IT2 / IT3 = 0.1 / 1 / 10 PLC。
    "timeout_s": None,  # Overall test timeout: None for no deadline, positive seconds, or "auto".
}


# All four point-generation choices are here; list order is measurement order.
def build_points():
    # Select the point rule here; shared helpers generate lists without configuring the instrument.
    if POINT_METHOD == "linear":
        return build_linear_voltage_path(START, STOP, STEP)
    if POINT_METHOD == "list":
        return validate_list_points(LIST_POINTS)
    if POINT_METHOD == "segments":
        return build_segmented_voltage_path(TURNING_POINTS, STEP)
    if POINT_METHOD == "log":
        return build_log_voltage_path(LOG_START, LOG_STOP, LOG_COUNT)
    raise ValueError("POINT_METHOD must be linear, list, segments, or log.")

# Configuration stays in this file; query uses the connection, or print for offline preview.
def configure(query, values):
    # Validate before sending commands; V/I variable names derive from physical channel numbers.
    values = validate_list_points(values)
    active = normalize_channels((CHANNEL_1, CHANNEL_2))
    if not set(active) <= set(normalize_channels(AVAILABLE_CHANNELS)):
        raise ValueError("Active channels must be installed/mapped.")
    if not isinstance(KXCI_PLOT, bool):
        raise ValueError("KXCI_PLOT must be True or False.")
    if KXCI_PLOT and min(values) == max(values):
        raise ValueError("KXCI graph requires distinct X limits.")
    if not 0 <= PARAMS["hold_time"] <= 655.3 or not 0 <= PARAMS["sweep_delay"] <= 6.553:
        raise ValueError("HT must be 0..655.3 s; DT must be 0..6.553 s.")
    if PARAMS["integration"] not in ("IT1", "IT2", "IT3"):
        raise ValueError("Choose IT1, IT2 or IT3.")
    for index in range(1, 3):
        limit = float(PARAMS[f"ch{index}_current_compliance"])
        floor = PARAMS[f"ch{index}_current_range"]
        if not math.isfinite(limit) or limit <= 0:
            raise ValueError("Current compliance must be finite and positive.")
        if str(floor).lower() != "auto" and (not math.isfinite(float(floor)) or float(floor) <= 0):
            raise ValueError("Current range must be 'auto' or a positive floor in A.")
    if any(not math.isfinite(float(v)) or abs(float(v)) > 210
           for v in [*values, PARAMS["ch2_voltage"]]):
        raise ValueError("Voltages must be finite and within +/-210 V; module limits also apply.")

    # CH: physical channel, voltage name, current name, source mode, function.
    # Source modes: 1=voltage, 2=current, 3=Common; functions: 1=VAR1, 2=VAR2, 3=constant, 4=follow.
    # This example uses a voltage list plus constant voltage; VAR2/follow require additional configuration.
    query("DE")
    query(f"CH{CHANNEL_1}, 'V{CHANNEL_1}', 'I{CHANNEL_1}', 1, 1")
    query(f"CH{CHANNEL_2}, 'V{CHANNEL_2}', 'I{CHANNEL_2}', 1, 3")
    query("SS")
    voltage_text = ",".join(f"{value:.12g}" for value in values)
    # VL takes the physical channel, then 1=master or 0=subordinate, followed by compliance in A.
    query(f"VL{CHANNEL_1},1,{PARAMS['ch1_current_compliance']},{voltage_text}")
    query(f"VC{CHANNEL_2}, {PARAMS['ch2_voltage']}, {PARAMS['ch2_current_compliance']}")

    # For multiple VL channels, select master/subordinate lists and validate equal lengths and pointwise alignment in Python.
    # For example, master [0, .5, 1] and subordinate [0, .1, .2] form three joint measurement points.
    # assert len(subordinate_values) == len(values)
    # subordinate_text = ",".join(f"{v:.12g}" for v in subordinate_values)
    # query(f"VL{CHANNEL_2},0,{PARAMS['ch2_current_compliance']},{subordinate_text}")
    # This illustrates VL syntax, not an example switch; multiple lists also require channel definitions, preview changes, and hardware verification.
    # Keep VC for constant bias; repeated preview values only draw a horizontal line.
    # Clarius aligns lists; KXCI documentation does not specify unequal-length behavior. Do not rely on padding/truncation.

    # Use IL for current lists (CH source mode 2, compliance in V), or IC for constant current.
    # Current sourcing also requires appropriate units, preview axes, and readout settings; changing VL alone is insufficient.
    # Common uses CH source mode/function 3,3; this example uses a voltage source for independent compliance and measurement.

    query(f"HT {PARAMS['hold_time']}")
    query(f"DT {PARAMS['sweep_delay']}")
    query(PARAMS["integration"])
    for channel in active:
        query(f"ST {channel}, 1")  # Automatically enter standby after completion.

    # RG sets the autorange floor, not compliance or a fixed measurement range.
    query("SM DM2")
    for index, channel in enumerate(active, 1):
        floor = PARAMS[f"ch{index}_current_range"]
        if str(floor).lower() != "auto":
            query(f"RG {channel}, {float(floor):.9g}")
    variables = [f"{kind}{channel}" for channel in active for kind in ("V", "I")]
    variable_text = ", ".join(f"'{name}'" for name in variables)
    query(f"LI {variable_text}")
    if KXCI_PLOT:
        # DM1/DM2 control display mode independently of VL list sweeping.
        # Enable both current axes and still read and check all four variables.
        query("SM DM1")
        query(f"XN 'V{CHANNEL_1}', 1, {min(values):g}, {max(values):g}")
        limit1 = PARAMS["ch1_current_compliance"]
        limit2 = PARAMS["ch2_current_compliance"]
        query(f"YA 'I{CHANNEL_1}', 1, {-limit1:g}, {limit1:g}")
        query(f"YB 'I{CHANNEL_2}', 1, {-limit2:g}, {limit2:g}")
    return variables


# Share connection, completion polling, abort handling, and parsing; keep configuration commands here.
def main():
    values = build_points()
    expected_points = len(values)
    if not isinstance(PREVIEW_ONLY, bool):
        raise ValueError("PREVIEW_ONLY must be True or False.")
    timeout = resolve_smu_timeout_s(PARAMS["timeout_s"], point_count=expected_points,
        hold_time=PARAMS["hold_time"], sweep_delay=PARAMS["sweep_delay"], integration=PARAMS["integration"])
    if PREVIEW_ONLY:
        print("Commanded points:", values)
        configure(print, values)
        print(f"Preview only: {expected_points} points; no instrument connection.")
        return preview_channel_voltages({
            f"CH{CHANNEL_1}": values,
            f"CH{CHANNEL_2}": [PARAMS["ch2_voltage"]] * expected_points,
        }, title="2terminal channel voltage preview")

    configure(lambda command: None, values)  # Run the same parameter checks before connecting.
    with SMUSession(INST) as session:
        query = session.query
        try:
            initialize_system_mode(query, available_channels=AVAILABLE_CHANNELS)
            rpm_targets = connect_smus_to_probes(query, (CHANNEL_1, CHANNEL_2), SMU_CONNECTIONS)
            variables = configure(query, values)
            raise_for_kxci_error(query, context="Two-terminal setup")
            execute_and_wait(query, timeout_s=timeout)
            data = retrieve_variables(query, variables, expected_point_count=expected_points)
            raise_for_kxci_error(query, context="Two-terminal readout")
            restore_rpms_to_pulse(query, rpm_targets)
        finally:
            shutdown_system_mode(query, AVAILABLE_CHANNELS)

    stem = reserve_output_stem(SAVE_DIR, "2terminal")
    output_path = Path(f"{stem}.csv")
    data.to_csv(output_path, index=False)
    print(f"Saved: {output_path}")
    return data


if __name__ == "__main__":
    main()
