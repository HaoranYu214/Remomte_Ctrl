# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.
# Select points and configure/execute here; reuse src for point algorithms, communication, and readout.

# Entry: multiple-loop memristor I-V; edit POSITIVE_PEAK_*, NEGATIVE_PEAK, SEGMENT_STEP, and PARAMS.
# TURNING_POINTS derives from the peak list; set instrument, wiring, and output through INST, SMU_CONNECTIONS, and SAVE_DIR.
# Flow: main -> full voltage list -> SMU sweep/read -> save commanded/measured values and J-V plots; PREVIEW_ONLY selects preview or acquisition.

"""Segmented SMU voltage sweep: 0 -> V1 -> 0 -> V2 -> 0."""

from pathlib import Path
import sys
import math

import pandas as pd

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.output import measurement_name, reserve_output_stem
from keithley4200.smu.data_processing import build_plot_data, retrieve_variables, save_workbook
from keithley4200.smu.plotting import save_current_density_plots
from keithley4200.smu.preview import preview_channel_voltages
from keithley4200.smu.points import build_segmented_voltage_path as build_points
from keithley4200.smu.session import SMUSession
from keithley4200.smu.common import normalize_channels, raise_for_kxci_error
from keithley4200.smu.routing import connect_smus_to_probes, restore_rpms_to_pulse
from keithley4200.smu.system_mode import initialize_system_mode, shutdown_system_mode, execute_and_wait, resolve_smu_timeout_s


# Instrument and wiring defaults: check when changing hardware or connections.
INST = "TCPIP0::129.125.87.80::1225::SOCKET"
# All installed/mapped channels; direct means a direct connection and rpm means routing through an RPM.
AVAILABLE_CHANNELS = (1, 2, 3, 4)
SMU_CONNECTIONS = {
    1: "rpm:PMU1-1",
    2: "rpm:PMU1-2",
    3: "direct",
    4: "direct",
}

# Run settings: output directory, active channels, offline preview, and KXCI plots.
SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\10-09-2026\04A1_2700_1200_300\R10_1\IV")
SWEEP_CHANNEL = 1
BIAS_CHANNEL = 2
PREVIEW_ONLY = True  # True previews channel voltages without connecting or saving measurement data.
KXCI_PLOT = False  # True plots sweep voltage and both currents in KXCI; False uses list display.

# Key sweep parameters.


DEVICE_AREA_CM2 = (20e-4) ** 2
# Positive peak shrinks from +5 V to 0 V in 0.2 V increments. After every
# positive excursion, the negative excursion remains fixed at -5 V:
# 0 -> +5.0 -> 0 -> -5 -> 0 -> +4.8 -> 0 -> -5 -> 0 -> ... -> -5 -> 0.
POSITIVE_PEAK_START = 6
POSITIVE_PEAK_STOP = 0.0
POSITIVE_PEAK_STEP = 0.5
NEGATIVE_PEAK = -6.0

# One value applies to every segment. A per-segment version is also valid:
# SEGMENT_STEP = [0.05, 0.05, 0.1, 0.1]
SEGMENT_STEP = 0.1

# Electrical and sampling parameters.
PARAMS = {
    "sweep_current_compliance": 1e-3,
    "bias_voltage": 0.0,
    "bias_current_compliance": 1e-3,
    "sweep_current_range": "auto",
    "bias_current_range": "auto",
    "hold_time": 0.0,
    "sweep_delay": 0.02,
    # IT1=Fast, IT2=Normal, IT3=Quiet.
    "integration": "IT2",
    # None: no overall test deadline; keep polling SP until KXCI completes.
    # Long endurance runs may legitimately take hours or days. Use a positive
    # number only when an explicit wall-clock limit is wanted; "auto" remains
    # available as an opt-in estimate based on points/delay/integration.
    "timeout_s": None,
}

# Accepted values for sweep_current_range and bias_current_range:
# - None, "auto", "default", or "": skip RG and use the *RST default
#   autorange floor (1 nA with a preamp; 100 nA without a preamp).
# - A positive int/float, for example 1e-9 or 100e-9: send
#   "RG channel, value" after "SM DM2".
# - A positive numeric string, for example "1e-9": converted to float and
#   handled exactly like the numeric form.
# - Zero, negative values, or any other string: rejected with ValueError.
# Common RG floors are 1e-12, 10e-12, 100e-12, 1e-9, 10e-9, 100e-9,
# 1e-6, 10e-6, 100e-6, 1e-3, 10e-3, and 100e-3 A; 1e-12 through
# 10e-9 require a preamp, and 1 A is available only on 4210/4211 SMUs.
# RG sets the LOWEST range autoranging may select; it does not fix the range.
# Expand turning points through src/keithley4200/smu/points.py; preview and acquisition use the same rule.


# Acquire the multiple-loop TURNING_POINTS path and save data, parameters, and J-V plots.
def main():
    """Run the segmented list sweep and save measured plus commanded values."""
    sweep_values = build_points(TURNING_POINTS, SEGMENT_STEP)
    print(
        f"Segmented sweep: {TURNING_POINTS}, "
        f"{len(sweep_values)} commanded points."
    )

    # Validate channels, then define the sweep and constant-bias channels directly.
    active = normalize_channels((SWEEP_CHANNEL, BIAS_CHANNEL))
    if not set(active) <= set(normalize_channels(AVAILABLE_CHANNELS)):
        raise ValueError("Active channels must be installed/mapped.")
    timeout = resolve_smu_timeout_s(PARAMS["timeout_s"], point_count=len(sweep_values),
        hold_time=PARAMS["hold_time"], sweep_delay=PARAMS["sweep_delay"], integration=PARAMS["integration"])
    plot_in_kxci = KXCI_PLOT
    if not isinstance(plot_in_kxci, bool):
        raise ValueError("KXCI_PLOT must be True or False.")
    plot_points = sweep_values
    x_min, x_max = min(plot_points), max(plot_points)
    if plot_in_kxci and x_min == x_max:
        raise ValueError("KXCI graph requires distinct X-axis limits.")
    if not isinstance(PREVIEW_ONLY, bool):
        raise ValueError("PREVIEW_ONLY must be True or False.")
    if PREVIEW_ONLY:
        return preview_channel_voltages({
            f"CH{SWEEP_CHANNEL}": sweep_values,
            f"CH{BIAS_CHANNEL}": [PARAMS["bias_voltage"]] * len(sweep_values),
        }, title="IV channel voltage preview")
    with SMUSession(INST) as session:
        query = session.query
        try:
            initialize_system_mode(query, available_channels=AVAILABLE_CHANNELS)
            # CH: channel, voltage name, current name, source mode (1=voltage/2=current/3=Common), function (1=sweep/3=constant).
            query(f"CH{BIAS_CHANNEL}, '{NAMES['bias_voltage']}', '{NAMES['bias_current']}', 1, 3")
            # CH: channel, voltage name, current name, source mode (1=voltage/2=current/3=Common), function (1=sweep/3=constant).
            query(f"CH{SWEEP_CHANNEL}, '{NAMES['sweep_voltage']}', '{NAMES['sweep_current']}', 1, 1")
            rpm_targets = connect_smus_to_probes(query, active, SMU_CONNECTIONS)
            query('SS')
            # Send the generated points directly to the instrument.
            # VL: physical channel, 1=master list, current compliance (A), and voltage points in measurement order.
            voltage_text = ','.join((f'{float(value):.12g}' for value in sweep_values))
            query(f"VL{SWEEP_CHANNEL},1,{PARAMS['sweep_current_compliance']},{voltage_text}")
            # VC: physical channel, constant voltage (V), and current compliance (A).
            query(f"VC{BIAS_CHANNEL}, {PARAMS['bias_voltage']}, {PARAMS['bias_current_compliance']}")
            # HT=initial hold (s), DT=per-point delay (s), IT1/2/3=0.1/1/10 PLC integration.
            hold_time, sweep_delay = (float(PARAMS['hold_time']), float(PARAMS['sweep_delay']))
            if not 0 <= hold_time <= 655.3 or not 0 <= sweep_delay <= 6.553:
                raise ValueError('HT must be 0..655.3 s; DT must be 0..6.553 s.')
            query(f"HT {hold_time:g}")
            query(f"DT {sweep_delay:g}")
            query(str(PARAMS['integration']).strip())
            # ST: automatically put active channels in standby after measurement.
            for channel in active:
                query(f"ST {channel}, 1")
            variables = [NAMES["sweep_current"], NAMES["sweep_voltage"], NAMES["bias_current"], NAMES["bias_voltage"]]
            # DM1=graph, DM2=list; RG range settings are independent of display mode.
            query("SM DM1" if plot_in_kxci else "SM DM2")
            for channel, current_range in [(SWEEP_CHANNEL, PARAMS['sweep_current_range']), (BIAS_CHANNEL, PARAMS['bias_current_range'])]:
                if current_range is not None and str(current_range).strip().lower() not in ('auto', 'default', ''):
                    range_floor = float(current_range)
                    if not math.isfinite(range_floor) or range_floor <= 0:
                        raise ValueError('Current range floor must be finite and positive.')
                    query(f"RG {channel}, {range_floor:.9g}")
            if plot_in_kxci:
                # XN=X axis; YA/YB=both currents, enabling both current measurements; 1=linear scale.
                query(f"XN '{NAMES['sweep_voltage']}', 1, {x_min:.12g}, {x_max:.12g}")
                sweep_limit = PARAMS["sweep_current_compliance"]
                bias_limit = PARAMS["bias_current_compliance"]
                query(f"YA '{NAMES['sweep_current']}', 1, {-sweep_limit:.12g}, {sweep_limit:.12g}")
                query(f"YB '{NAMES['bias_current']}', 1, {-bias_limit:.12g}, {bias_limit:.12g}")
            else:
                variable_text = ", ".join(f"'{variable}'" for variable in variables)
                query(f"LI {variable_text}")
            raise_for_kxci_error(query, context="IV setup")
            execute_and_wait(query, timeout_s=timeout)
            data = retrieve_variables(query, variables, expected_point_count=len(sweep_values))
            raise_for_kxci_error(query, context="IV readout")
            restore_rpms_to_pulse(query, rpm_targets)
        finally:
            shutdown_system_mode(query, AVAILABLE_CHANNELS)

    # Keep the programmed path next to the measured voltage/current. Series
    # padding makes a point-count mismatch visible instead of hiding it.
    commanded = pd.DataFrame(
        {
            "PointIndex": pd.Series(range(len(sweep_values)), dtype=int),
            "CommandedVoltage": pd.Series(sweep_values, dtype=float),
        }
    )
    data = pd.concat([commanded, data.reset_index(drop=True)], axis=1)
    plot_data = build_plot_data(data, area_cm2=DEVICE_AREA_CM2)

    output_stem = reserve_output_stem(SAVE_DIR, measurement_name("IVmem", max(abs(value) for value in TURNING_POINTS)))
    output_path = Path(f"{output_stem}.xlsx")
    saved_parameters = {
        "INST": INST,
        "DEVICE_AREA_CM2": DEVICE_AREA_CM2,
        "SWEEP_CHANNEL": SWEEP_CHANNEL,
        "BIAS_CHANNEL": BIAS_CHANNEL,
        "KXCI_PLOT": plot_in_kxci,
        "AVAILABLE_CHANNELS": AVAILABLE_CHANNELS,
        "SMU_CONNECTIONS": SMU_CONNECTIONS,
        "TURNING_POINTS": TURNING_POINTS,
        "SEGMENT_STEP": SEGMENT_STEP,
        "POINT_COUNT": len(sweep_values),
        **NAMES,
        **PARAMS,
    }
    save_workbook(
        output_path,
        data,
        saved_parameters,
        plot_data=plot_data,
    )
    try:
        jv_path, log_path = save_current_density_plots(
            plot_data,
            output_path,
            voltage_column=NAMES["sweep_voltage"],
            current_density_column=NAMES["sweep_current_density"],
        )
        print(f"Saved J-V plot: {jv_path.resolve()}")
        print(f"Saved log(abs(J)) plot: {log_path.resolve()}")
    except Exception as exc:
        print(f"Warning: failed to save current-density plots: {exc}")
    print(f"Saved segmented SMU sweep: {output_path.resolve()}")


# Internal definitions used by the experiment; ordinary parameter changes belong above.
# Derive turning points from the peak parameters above; usually no manual changes are needed.
_positive_peak_count = int(
    round((POSITIVE_PEAK_START - POSITIVE_PEAK_STOP) / POSITIVE_PEAK_STEP)
)
POSITIVE_PEAKS = [
    round(POSITIVE_PEAK_START - index * POSITIVE_PEAK_STEP, 12)
    for index in range(_positive_peak_count + 1)
]

TURNING_POINTS = [0.0]
for positive_peak in POSITIVE_PEAKS:
    # At the final 0 V level there is no positive excursion, but the matching
    # fixed negative excursion is retained.
    if positive_peak > 0:
        TURNING_POINTS.extend([positive_peak, 0.0])
    TURNING_POINTS.extend([NEGATIVE_PEAK, 0.0])

# Instrument variables and result column names; usually unchanged.
NAMES = {
    "sweep_voltage": "V1",
    "sweep_current": "I1",
    "sweep_current_density": "J1_A_per_cm2",
    "bias_voltage": "V2",
    "bias_current": "I2",
    "bias_current_density": "J2_A_per_cm2",
}


if __name__ == "__main__":
    main()
