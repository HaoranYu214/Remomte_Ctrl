# -*- coding: utf-8 -*-
"""Segmented SMU voltage sweep: 0 -> V1 -> 0 -> V2 -> 0."""

from pathlib import Path
import sys

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
from keithley4200.smu.session import SMUSession
from keithley4200.smu.system_mode import build_segmented_voltage_path, run_list_voltage_sweep


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
DEVICE_AREA_CM2 = (20e-4) ** 2
SWEEP_CHANNEL = 1
BIAS_CHANNEL = 2
# List every installed/mapped SMU so initialization explicitly disables all
# unused channels before defining the active sweep and bias pair.
AVAILABLE_CHANNELS = (1, 2, 3, 4)

# Physical SMU-to-probe wiring for this 4200A. SMU1 and SMU2 pass through
# the RPMs attached to PMU1 channels 1 and 2; SMU3/SMU4 (when used by future
# experiments) are direct probe connections.
SMU_CONNECTIONS = {
    1: "rpm:PMU1-1",
    2: "rpm:PMU1-2",
    3: "direct",
    4: "direct",
}

# Positive peak shrinks from +5 V to 0 V in 0.2 V increments. After every
# positive excursion, the negative excursion remains fixed at -5 V:
# 0 -> +5.0 -> 0 -> -5 -> 0 -> +4.8 -> 0 -> -5 -> 0 -> ... -> -5 -> 0.
POSITIVE_PEAK_START = 6
POSITIVE_PEAK_STOP = 0.0
POSITIVE_PEAK_STEP = 0.5
NEGATIVE_PEAK = -6.0

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

# One value applies to every segment. A per-segment version is also valid:
# SEGMENT_STEP = [0.05, 0.05, 0.1, 0.1]
SEGMENT_STEP = 0.1

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

NAMES = {
    "sweep_voltage": "V1",
    "sweep_current": "I1",
    "sweep_current_density": "J1_A_per_cm2",
    "bias_voltage": "V2",
    "bias_current": "I2",
    "bias_current_density": "J2_A_per_cm2",
}

SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\10-09-2026\04A1_2700_1200_300\R10_1\IV")


def main():
    """Run the segmented list sweep and save measured plus commanded values."""
    sweep_values = build_segmented_voltage_path(TURNING_POINTS, SEGMENT_STEP)
    print(
        f"Segmented sweep: {TURNING_POINTS}, "
        f"{len(sweep_values)} commanded points."
    )

    with SMUSession(INST) as session:
        variables = run_list_voltage_sweep(
            session.query,
            values=sweep_values,
            sweep_channel=SWEEP_CHANNEL,
            bias_channel=BIAS_CHANNEL,
            sweep_voltage_name=NAMES["sweep_voltage"],
            sweep_current_name=NAMES["sweep_current"],
            bias_voltage_name=NAMES["bias_voltage"],
            bias_current_name=NAMES["bias_current"],
            available_channels=AVAILABLE_CHANNELS,
            smu_connections=SMU_CONNECTIONS,
            **PARAMS,
        )
        data = retrieve_variables(
            session.query,
            variables,
            expected_point_count=len(sweep_values),
        )

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


if __name__ == "__main__":
    main()
