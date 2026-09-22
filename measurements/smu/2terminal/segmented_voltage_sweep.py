# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.
# Select points and configure/execute here; reuse src for point algorithms, communication, and readout.

# Entry: segmented I-V; edit TURNING_POINTS, SEGMENT_STEP, PARAMS, channels, INST, and SAVE_DIR.
# Flow: main -> run_test merges settings/builds points -> SMU sweep/read -> save Excel and J-V plots.
# params_override replaces matching PARAMS entries; pass channels, wiring, and turning points as separate keywords.
# PREVIEW_ONLY selects offline preview or acquisition; preview_waveform also previews explicit paths.

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
SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\14-09-2026\04A1_2700_1200_300\L20_2\IV5_endurance")
SWEEP_CHANNEL = 1
BIAS_CHANNEL = 2
PREVIEW_ONLY = True  # True previews channel voltages without connecting or saving measurement data.
KXCI_PLOT = False  # True plots sweep voltage and both currents in KXCI; False uses list display.

# Key sweep parameters.


DEVICE_AREA_CM2 = (20e-4) ** 2
# DEVICE_AREA_CM2 = (15*1e-4)**2*3.14

# Generic device-check loop. Package/orchestration files may override these
# globals before calling ``main()`` without duplicating the SMU implementation.
POSITIVE_PEAK_V = 5
NEGATIVE_PEAK_V = -5
TURNING_POINTS = [0.0, POSITIVE_PEAK_V, 0.0, NEGATIVE_PEAK_V, 0.0]
# TURNING_POINTS = [0.0, NEGATIVE_PEAK_V, 0.0, POSITIVE_PEAK_V, 0.0]
SEGMENT_STEP = 0.1

# Electrical and sampling parameters.
PARAMS = {
    "sweep_current_compliance": 1e-4,
    "bias_voltage": 0.0,
    "bias_current_compliance": 1e-4,
    "sweep_current_range": "auto",
    "bias_current_range": "auto",
    "hold_time": 0.0,
    "sweep_delay": 0.02,
    # IT1=Fast, IT2=Normal, IT3=Quiet.
    "integration": "IT3",
    # None: no overall test deadline; keep polling SP until KXCI completes.
    # Long endurance runs may legitimately take hours or days. Use a positive
    # number only when an explicit wall-clock limit is wanted; "auto" remains
    # available as an opt-in estimate based on points/delay/integration.
    "timeout_s": None,
}


# Expand turning points through src/keithley4200/smu/points.py; preview and acquisition use the same rule.


# Preview the expanded voltage list offline; show controls display and output_path optionally saves a figure.
def preview_waveform(output_path=None, *, show=True, title=None, turning_points=None,
                     segment_step=None, sweep_channel=None, bias_channel=None, bias_voltage=None):
    """Prepare both channel paths and pass them to the common offline preview."""
    turning_points = TURNING_POINTS if turning_points is None else turning_points
    segment_step = SEGMENT_STEP if segment_step is None else segment_step
    sweep_channel = SWEEP_CHANNEL if sweep_channel is None else sweep_channel
    bias_channel = BIAS_CHANNEL if bias_channel is None else bias_channel
    normalize_channels((sweep_channel, bias_channel))
    bias_voltage = PARAMS["bias_voltage"] if bias_voltage is None else bias_voltage
    sweep_values = build_points(turning_points, segment_step)
    channel_values = {
        f"CH{sweep_channel}": sweep_values,
        f"CH{bias_channel}": [bias_voltage] * len(sweep_values),
    }
    return preview_channel_voltages(channel_values, output_path, show=show,
        title=title or f"Segmented DC I-V preview ({len(sweep_values)} points)")


# Merge run settings, then directly configure, execute, and save the list sweep.
def run_test(params_override=None, *, turning_points=None, segment_step=None,
             save_dir=None, file_stem="IV", inst=None, device_area_cm2=None,
             sweep_channel=None, bias_channel=None, available_channels=None,
             smu_connections=None, names=None, kxci_plot=None, preview_only=None):
    """Run one complete list sweep using explicit overrides without changing defaults."""
    parameters = dict(PARAMS)
    if params_override is not None:
        unknown = set(params_override) - set(parameters)
        if unknown:
            raise ValueError(f"Unknown segmented IV parameters: {sorted(unknown)}")
        parameters.update(params_override)
    inst = INST if inst is None else inst
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)
    device_area_cm2 = DEVICE_AREA_CM2 if device_area_cm2 is None else device_area_cm2
    sweep_channel = SWEEP_CHANNEL if sweep_channel is None else sweep_channel
    bias_channel = BIAS_CHANNEL if bias_channel is None else bias_channel
    available_channels = AVAILABLE_CHANNELS if available_channels is None else available_channels
    smu_connections = dict(SMU_CONNECTIONS if smu_connections is None else smu_connections)
    names = dict(NAMES if names is None else names)
    turning_points = list(TURNING_POINTS if turning_points is None else turning_points)
    segment_step = SEGMENT_STEP if segment_step is None else segment_step
    sweep_values = build_points(turning_points, segment_step)
    if len(sweep_values) > 4096:
        raise ValueError(
            f"Segmented sweep contains {len(sweep_values)} points; "
            "KXCI VL list sweeps are limited to 4096."
        )
    print(
        f"Segmented sweep: {turning_points}, "
        f"{len(sweep_values)} commanded points."
    )

    # Validate channels, then define the sweep and constant-bias channels directly.
    active = normalize_channels((sweep_channel, bias_channel))
    if not set(active) <= set(normalize_channels(available_channels)):
        raise ValueError("Active channels must be installed/mapped.")
    timeout = resolve_smu_timeout_s(parameters["timeout_s"], point_count=len(sweep_values),
        hold_time=parameters["hold_time"], sweep_delay=parameters["sweep_delay"], integration=parameters["integration"])
    plot_in_kxci = KXCI_PLOT if kxci_plot is None else kxci_plot
    if not isinstance(plot_in_kxci, bool):
        raise ValueError("KXCI_PLOT must be True or False.")
    plot_points = sweep_values
    x_min, x_max = min(plot_points), max(plot_points)
    if plot_in_kxci and x_min == x_max:
        raise ValueError("KXCI graph requires distinct X-axis limits.")
    preview = PREVIEW_ONLY if preview_only is None else preview_only
    if not isinstance(preview, bool):
        raise ValueError("preview_only must be True or False.")
    if preview:
        figure = preview_channel_voltages({
            f"CH{sweep_channel}": sweep_values,
            f"CH{bias_channel}": [parameters["bias_voltage"]] * len(sweep_values),
        }, title="Segmented IV channel voltage preview")
        return {"preview": figure, "output_path": None, "point_count": len(sweep_values)}
    with SMUSession(inst) as session:
        query = session.query
        try:
            initialize_system_mode(query, available_channels=available_channels)
            # CH: channel, voltage name, current name, source mode (1=voltage/2=current/3=Common), function (1=sweep/3=constant).
            query(f"CH{bias_channel}, '{names['bias_voltage']}', '{names['bias_current']}', 1, 3")
            # CH: channel, voltage name, current name, source mode (1=voltage/2=current/3=Common), function (1=sweep/3=constant).
            query(f"CH{sweep_channel}, '{names['sweep_voltage']}', '{names['sweep_current']}', 1, 1")
            rpm_targets = connect_smus_to_probes(query, active, smu_connections)
            query('SS')
            # Send the generated points directly to the instrument.
            # VL: physical channel, 1=master list, current compliance (A), and voltage points in measurement order.
            voltage_text = ','.join((f'{float(value):.12g}' for value in sweep_values))
            query(f"VL{sweep_channel},1,{parameters['sweep_current_compliance']},{voltage_text}")
            # VC: physical channel, constant voltage (V), and current compliance (A).
            query(f"VC{bias_channel}, {parameters['bias_voltage']}, {parameters['bias_current_compliance']}")
            # HT=initial hold (s), DT=per-point delay (s), IT1/2/3=0.1/1/10 PLC integration.
            hold_time, sweep_delay = (float(parameters['hold_time']), float(parameters['sweep_delay']))
            if not 0 <= hold_time <= 655.3 or not 0 <= sweep_delay <= 6.553:
                raise ValueError('HT must be 0..655.3 s; DT must be 0..6.553 s.')
            query(f"HT {hold_time:g}")
            query(f"DT {sweep_delay:g}")
            query(str(parameters['integration']).strip())
            # ST: automatically put active channels in standby after measurement.
            for channel in active:
                query(f"ST {channel}, 1")
            variables = [names["sweep_current"], names["sweep_voltage"], names["bias_current"], names["bias_voltage"]]
            # DM1=graph, DM2=list; RG range settings are independent of display mode.
            query("SM DM1" if plot_in_kxci else "SM DM2")
            for channel, current_range in [(sweep_channel, parameters['sweep_current_range']), (bias_channel, parameters['bias_current_range'])]:
                if current_range is not None and str(current_range).strip().lower() not in ('auto', 'default', ''):
                    range_floor = float(current_range)
                    if not math.isfinite(range_floor) or range_floor <= 0:
                        raise ValueError('Current range floor must be finite and positive.')
                    query(f"RG {channel}, {range_floor:.9g}")
            if plot_in_kxci:
                # XN=X axis; YA/YB=both currents, enabling both current measurements; 1=linear scale.
                query(f"XN '{names['sweep_voltage']}', 1, {x_min:.12g}, {x_max:.12g}")
                sweep_limit = parameters["sweep_current_compliance"]
                bias_limit = parameters["bias_current_compliance"]
                query(f"YA '{names['sweep_current']}', 1, {-sweep_limit:.12g}, {sweep_limit:.12g}")
                query(f"YB '{names['bias_current']}', 1, {-bias_limit:.12g}, {bias_limit:.12g}")
            else:
                variable_text = ", ".join(f"'{variable}'" for variable in variables)
                query(f"LI {variable_text}")
            raise_for_kxci_error(query, context="IV setup")
            execute_and_wait(query, timeout_s=timeout)
            data = retrieve_variables(query, variables, expected_point_count=len(sweep_values))
            raise_for_kxci_error(query, context="IV readout")
            restore_rpms_to_pulse(query, rpm_targets)
        finally:
            shutdown_system_mode(query, available_channels)

    # Keep the programmed path next to the measured voltage/current. Series
    # padding makes a point-count mismatch visible instead of hiding it.
    commanded = pd.DataFrame(
        {
            "PointIndex": pd.Series(range(len(sweep_values)), dtype=int),
            "CommandedVoltage": pd.Series(sweep_values, dtype=float),
        }
    )
    data = pd.concat([commanded, data.reset_index(drop=True)], axis=1)
    plot_data = build_plot_data(
        data, area_cm2=device_area_cm2,
        channel1_voltage=names["sweep_voltage"], channel1_current=names["sweep_current"],
        channel2_voltage=names["bias_voltage"], channel2_current=names["bias_current"],
    )

    output_stem = reserve_output_stem(save_dir, measurement_name(file_stem, max(abs(value) for value in turning_points)))
    output_path = Path(f"{output_stem}.xlsx")
    saved_parameters = {
        "INST": inst,
        "DEVICE_AREA_CM2": device_area_cm2,
        "SWEEP_CHANNEL": sweep_channel,
        "BIAS_CHANNEL": bias_channel,
        "KXCI_PLOT": plot_in_kxci,
        "AVAILABLE_CHANNELS": available_channels,
        "SMU_CONNECTIONS": smu_connections,
        "TURNING_POINTS": turning_points,
        "SEGMENT_STEP": segment_step,
        "POINT_COUNT": len(sweep_values),
        **names,
        **parameters,
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
            voltage_column="V1",
            current_density_column="J1_A_per_cm2",
        )
        print(f"Saved J-V plot: {jv_path.resolve()}")
        print(f"Saved log(abs(J)) plot: {log_path.resolve()}")
    except Exception as exc:
        print(f"Warning: failed to save current-density plots: {exc}")
    print(f"Saved segmented SMU sweep: {output_path.resolve()}")
    return {
        "output_path": output_path,
        "jv_plot_path": jv_path if "jv_path" in locals() else None,
        "log_plot_path": log_path if "log_path" in locals() else None,
        "point_count": len(sweep_values),
    }


# Call run_test with this file's defaults and return the segmented I-V output information.
def main():
    """Keep the standalone and existing workflow entry point."""
    return run_test()


# Internal definitions used by the experiment; ordinary parameter changes belong above.
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
