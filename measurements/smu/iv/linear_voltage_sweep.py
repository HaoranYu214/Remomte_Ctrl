# -*- coding: utf-8 -*-
"""Two-channel SMU linear voltage sweep using the reusable System Mode layer."""

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
from keithley4200.smu.system_mode import linear_sweep_point_count, run_linear_voltage_sweep


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
DEVICE_AREA_CM2 = (20e-4) ** 2
SWEEP_CHANNEL = 2
BIAS_CHANNEL = 1
AVAILABLE_CHANNELS = (1, 2, 3, 4)

# Physical SMU-to-probe wiring for this 4200A:
# - SMU1/SMU2 pass through the RPMs attached to PMU1 channels 1/2.
# - SMU3/SMU4 connect directly to their probes.
# Every active channel must have an explicit entry. "direct" sends no RP
# command; "rpm:PMUN-C" switches that RPM to SMU (blue LED) after *RST.
SMU_CONNECTIONS = {
    1: "rpm:PMU1-1",
    2: "rpm:PMU1-2",
    3: "direct",
    4: "direct",
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
PARAMS = {
    "start": 0.0,
    "stop": 1.0,
    "step": 0.1,
    "sweep_current_compliance": 1e-3,
    "bias_voltage": 0.0,
    "bias_current_compliance": 1e-3,
    "sweep_current_range": "auto",
    "bias_current_range": "auto",
    "hold_time": 0.0,
    "sweep_delay": 0.02,
    # IT1=Fast/0.1 PLC, IT2=Normal/1 PLC, IT3=Quiet/10 PLC.
    # Custom example: "IT4, delay_factor, filter_factor, aperture_plc"
    "integration": "IT2",
    # None: no overall test deadline; keep polling SP until KXCI completes.
    # Use a positive number only for an explicit limit; "auto" remains an
    # opt-in estimate based on points, delay, and integration time.
    "timeout_s": None,
}

NAMES = {
    "sweep_voltage": "V2",
    "sweep_current": "I2",
    "sweep_current_density": "J2_A_per_cm2",
    "bias_voltage": "V1",
    "bias_current": "I1",
    "bias_current_density": "J1_A_per_cm2",
}

SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\06-07-2026\03C6\R20um1\FE\frequency")


def main():
    """Run the sweep and save data plus the complete parameter table."""
    with SMUSession(INST) as session:
        variables = run_linear_voltage_sweep(
            session.query,
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
        expected_points = linear_sweep_point_count(
            PARAMS["start"],
            PARAMS["stop"],
            PARAMS["step"],
        )
        data = retrieve_variables(
            session.query,
            variables,
            expected_point_count=expected_points,
        )

    commanded_values = [
        float(PARAMS["start"]) + index * float(PARAMS["step"])
        for index in range(expected_points)
    ]
    commanded = pd.DataFrame(
        {
            "PointIndex": pd.Series(range(expected_points), dtype=int),
            "CommandedVoltage": pd.Series(commanded_values, dtype=float),
        }
    )
    data = pd.concat([commanded, data.reset_index(drop=True)], axis=1)
    plot_data = build_plot_data(data, area_cm2=DEVICE_AREA_CM2)

    output_stem = reserve_output_stem(SAVE_DIR, measurement_name("IVlinear", max(abs(PARAMS["start"]), abs(PARAMS["stop"]))))
    output_path = Path(f"{output_stem}.xlsx")
    saved_parameters = {
        "INST": INST,
        "DEVICE_AREA_CM2": DEVICE_AREA_CM2,
        "SWEEP_CHANNEL": SWEEP_CHANNEL,
        "BIAS_CHANNEL": BIAS_CHANNEL,
        "AVAILABLE_CHANNELS": AVAILABLE_CHANNELS,
        "SMU_CONNECTIONS": SMU_CONNECTIONS,
        "EXPECTED_POINT_COUNT": expected_points,
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
    print(f"Saved SMU sweep: {output_path.resolve()}")


if __name__ == "__main__":
    main()
