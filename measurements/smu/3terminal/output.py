# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.
"""Three-terminal FET output curves."""

# MODE="output": sweep drain at fixed gate bias; MODE="transfer": sweep gate at fixed drain bias.
# Read from top-level settings to build_plan, then run_test for per-curve acquisition, readback, and saving.
# Wiring: Gate=SMU1, Drain=SMU2, Source=SMU3 voltage source, holding 0 V by default while reading VS/IS.
# PREVIEW_ONLY=True plots the voltage plan; False connects. Most edits belong in the configuration section.
# Point selection, channel definitions, sweep commands, and readback stay here, using the same basic helpers as example.py.

from datetime import datetime
from pathlib import Path
import sys
import warnings
import math

import pandas as pd

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents
                 if (parent / "pyproject.toml").is_file())
for location in (REPO_ROOT / "src", REPO_ROOT):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from keithley4200.output import measurement_name, reserve_output_stem
from keithley4200.smu.fet import save_fet_checkpoint, validate_fet_sweep
from keithley4200.smu.preview import preview_fet_family
from keithley4200.smu.plotting import save_fet_plot
from keithley4200.smu.points import build_segmented_voltage_path as build_points
from keithley4200.smu.session import SMUSession
from keithley4200.smu.common import normalize_channels, raise_for_kxci_error
from keithley4200.smu.routing import connect_smus_to_probes, restore_rpms_to_pulse
from keithley4200.smu.system_mode import initialize_system_mode, shutdown_system_mode, execute_and_wait, resolve_smu_timeout_s
from keithley4200.smu.data_processing import retrieve_variables


# -------------------- User configuration --------------------
# Instrument and wiring defaults: check when changing hardware or connections.
INST = "TCPIP0::192.0.2.1::1225::SOCKET"
# All installed/mapped channels; direct means a direct connection and rpm means routing through an RPM.
AVAILABLE_CHANNELS = (1, 2, 3, 4)  # All installed SMUs mapped in KCon.
SMU_CONNECTIONS = {
    1: "rpm:PMU1-1",  # Route to Gate through an RPM; use "direct" if physically wired directly.
    2: "rpm:PMU1-2",  # Route to Drain through an RPM.
    3: "direct",     # Source connects to SMU3.
    4: "direct",
}

# Run settings: output directory, active channels, offline preview, and KXCI plots.
SAVE_DIR = Path("data/smu/3terminal/output")
GATE_CHANNEL = 1
DRAIN_CHANNEL = 2
SOURCE_CHANNEL = 3  # Independent voltage source, default 0 V; compliance and range are set in PARAMS.
PREVIEW_ONLY = True
# Acquire VG/IG/VD/ID/VS/IS in DM2 list mode; Python plots are still saved.
# True is for hardware trials: select six LI variables before DM1; additional buffer acquisition remains unverified.
KXCI_PLOT = False
SHOW_RESULTS = True  # Show Python plots after all curves; PNG files are always saved.

# Key sweep parameters.

# Turning points may have either sign; STEP is positive. Shared endpoints appear once and scan order is preserved.
MODE = "output"  # "output" or "transfer".
TURNING_POINTS = [0.0, 1.0]  # output: Vds path; transfer: Vgs path.
STEP = 0.05  # V; at most 4096 expanded points per curve.
FIXED_BIASES = [0.0, 0.5, 1.0]  # output: fixed Vgs; transfer: fixed Vds.
# Transfer example: MODE="transfer", TURNING_POINTS=[-1, 1, -1],
# STEP=0.05, FIXED_BIASES=[0.1]. Check both path and biases when changing modes.

# compliance limits current; current_range sets the RG autorange floor.
# Electrical and sampling parameters.
PARAMS = {
    "gate_compliance": 1e-6,       # A
    "drain_compliance": 1e-3,      # A
    "source_voltage": 0.0,         # V; constant Source voltage. Sweep/bias values are defined as Vgs/Vds.
    "source_compliance": 1e-3,     # A; independent Source current compliance.
    "gate_current_range": "auto",
    "drain_current_range": "auto",
    "source_current_range": "auto", # RG autorange floor, separate from compliance.
    "hold_time": 0.1,             # s; hold at the start of the sweep.
    "sweep_delay": 0.02,          # s; wait after setting each point's voltage.
    "integration": "IT2",        # IT1/IT2/IT3 = 0.1/1/10 PLC。
    "timeout_s": None,            # Per-curve timeout: None for no deadline, seconds, or "auto".
}

KXCI_IG_LIMITS = None   # IG graph-axis bounds; None uses +/-gate_compliance.


# Shared point algorithms live in src; define the path, channels, and all test commands here.


# Build and validate every curve configuration offline.
def build_plan(parameters=None):
    parameters = dict(PARAMS if parameters is None else parameters)

    # Mode selects the swept terminal; the other terminal holds a constant bias.
    if MODE == "output":
        sweep_terminal = "drain"
    elif MODE == "transfer":
        sweep_terminal = "gate"
    else:
        raise ValueError('MODE must be "output" or "transfer".')

    # For example, path [0, 1] with step 0.5 expands to [0, 0.5, 1] V.
    values = build_points(TURNING_POINTS, STEP)
    if not FIXED_BIASES:
        raise ValueError("FIXED_BIASES must contain at least one voltage.")

    # Each fixed bias defines one complete curve; validate all curves before acquisition.
    plan = []
    for bias in FIXED_BIASES:
        config = validate_fet_sweep(
            values=values, sweep_terminal=sweep_terminal, bias_voltage=bias,
            gate_channel=GATE_CHANNEL, drain_channel=DRAIN_CHANNEL,
            source_channel=SOURCE_CHANNEL, available_channels=AVAILABLE_CHANNELS,
            smu_connections=SMU_CONNECTIONS, kxci_plot=KXCI_PLOT,
            kxci_ig_limits=KXCI_IG_LIMITS, **parameters,
        )
        plan.append(config)
    return plan


# Preview gate/drain command lists offline; the X axis is point index, not actual measurement time.
def preview_waveform(*, parameters=None, show=True):
    return preview_fet_family(build_plan(parameters), show=show)


# Merge overrides and acquire the family; checkpoint after each curve and record failure/interruption status.
# Return data, curve status, and paths; preview_only=True neither connects nor creates result files.
def run_test(params_override=None, *, preview_only=None, save_dir=None, show=None):
    parameters = dict(PARAMS)
    if params_override is not None:
        unknown = set(params_override) - set(parameters)
        if unknown:
            raise ValueError(f"Unknown FET parameters: {sorted(unknown)}")
        parameters.update(params_override)
    configs = build_plan(parameters)  # Validate every bias before connecting.
    preview = PREVIEW_ONLY if preview_only is None else preview_only
    show = SHOW_RESULTS if show is None else show
    if preview:
        return {"preview": preview_fet_family(configs, show=show), "output_path": None}

    directory = Path(SAVE_DIR if save_dir is None else save_dir)
    stem = reserve_output_stem(directory, measurement_name(
        f"FET{MODE.title()}", max(abs(v) for v in configs[0]["values"]), f"n{len(configs)}"))
    workbook = Path(f"{stem}.xlsx")
    frames, curves = [], []
    settings = {"INST": INST, "test": MODE, "curve_configs": configs,
                "source_reference_V": parameters["source_voltage"], "source_reference_is_measured": True}
    for index, config in enumerate(configs, 1):
        fixed_terminal = "VGS" if MODE == "output" else "VDS"
        print(f"FET {MODE}: curve {index}/{len(configs)}, fixed {fixed_terminal}={config['bias_voltage']:g} V")
        row = {"CurveIndex": index, "BiasVoltage_V": config["bias_voltage"],
               "StartTime": datetime.now().isoformat(), "Status": "running", "Error": ""}
        curves.append(row)
        try:
            with SMUSession(INST) as session:
                # Keep configuration and acquisition explicit so each curve's measurement flow is visible.
                query = session.query
                gate, drain, source = (config[k] for k in ("gate_channel", "drain_channel", "source_channel"))
                gate_sweep = config["sweep_terminal"] == "gate"
                sweep, bias = (gate, drain) if gate_sweep else (drain, gate)
                sweep_compliance = config["gate_compliance" if gate_sweep else "drain_compliance"]
                bias_compliance = config["drain_compliance" if gate_sweep else "gate_compliance"]
                variables = ["VG", "IG", "VD", "ID", "VS", "IS"]
                try:
                    initialize_system_mode(query, available_channels=config["available_channels"])
                    # CH: channel, voltage name, current name, source mode (1=voltage/2=current/3=Common), function (1=sweep/3=constant).
                    query(f"CH{gate}, 'VG', 'IG', 1, {(1 if gate_sweep else 3)}")
                    # CH: channel, voltage name, current name, source mode (1=voltage/2=current/3=Common), function (1=sweep/3=constant).
                    query(f"CH{drain}, 'VD', 'ID', 1, {(3 if gate_sweep else 1)}")
                    # CH: channel, voltage name, current name, source mode (1=voltage/2=current/3=Common), function (1=sweep/3=constant).
                    query(f"CH{source}, 'VS', 'IS', 1, 3")
                    rpm_targets = connect_smus_to_probes(query, (gate, drain, source), config["smu_connections"])
                    query('SS')
                    # VL: physical channel, 1=master list, current compliance (A), and voltage points in measurement order.
                    voltage_text = ','.join((f"{float(value) + config['source_voltage']:.12g}" for value in config['values']))
                    query(f"VL{sweep},1,{sweep_compliance},{voltage_text}")
                    # VC: physical channel, constant voltage (V), and current compliance (A).
                    query(f"VC{bias}, {config['bias_voltage'] + config['source_voltage']}, {bias_compliance}")
                    # Source voltage source: constant voltage (V) and independent current compliance (A).
                    query(f"VC{source}, {config['source_voltage']}, {config['source_compliance']}")
                    # HT=initial hold (s), DT=per-point delay (s), IT1/2/3=0.1/1/10 PLC integration.
                    hold_time, sweep_delay = (float(config['hold_time']), float(config['sweep_delay']))
                    if not 0 <= hold_time <= 655.3 or not 0 <= sweep_delay <= 6.553:
                        raise ValueError('HT must be 0..655.3 s; DT must be 0..6.553 s.')
                    query(f"HT {hold_time:g}")
                    query(f"DT {sweep_delay:g}")
                    query(str(config['integration']).strip())
                    # ST: automatically put active channels in standby after measurement.
                    for channel in (gate, drain, source):
                        query(f"ST {channel}, 1")
                    ranges = [(gate, config["gate_current_range"]), (drain, config["drain_current_range"]), (source, config["source_current_range"])]
                    # DM2=list display; RG=range floor (A); LI selects requested voltage/current variables.
                    query('SM DM2')
                    for channel, current_range in ranges:
                        if current_range is not None and str(current_range).strip().lower() not in ('auto', 'default', ''):
                            range_floor = float(current_range)
                            if not math.isfinite(range_floor) or range_floor <= 0:
                                raise ValueError('Current range floor must be finite and positive.')
                            query(f"RG {channel}, {range_floor:.9g}")
                    variable_text = ', '.join((f"'{variable}'" for variable in variables))
                    query(f"LI {variable_text}")
                    if config["kxci_plot"]:
                        # Hardware trial: still attempt to read all six variables after switching to graph mode.
                        # X is measured sweep-terminal voltage; YA/YB select IG/IS and can be edited here.
                        query("SM DM1")
                        x_name = "VG" if gate_sweep else "VD"
                        x_low = min(config["values"]) + config["source_voltage"]
                        x_high = max(config["values"]) + config["source_voltage"]
                        query(f"XN '{x_name}', 1, {x_low:g}, {x_high:g}")
                        ig_low, ig_high = config["kxci_ig_limits"]
                        query(f"YA 'IG', 1, {ig_low:g}, {ig_high:g}")
                        is_limit = config["source_compliance"]
                        query(f"YB 'IS', 1, {-is_limit:g}, {is_limit:g}")
                    raise_for_kxci_error(query, context="Three-terminal FET setup")
                    execute_and_wait(query, timeout_s=config["timeout_s"])
                    # ST puts outputs in standby before buffers are transferred or relays restored.
                    frame = retrieve_variables(query, variables, expected_point_count=len(config["values"]))
                    raise_for_kxci_error(query, context="Three-terminal FET readout")
                    restore_rpms_to_pulse(query, rpm_targets)
                except BaseException:
                    shutdown_system_mode(query, config["available_channels"])
                    # Do not restore RPMs after failed/aborted execution with uncertain outputs.
                    raise
                frame.insert(0, "PointIndex", range(len(frame)))
                frame.insert(1, "CommandedVGS_V", config["values"] if gate_sweep else config["bias_voltage"])
                frame.insert(2, "CommandedVDS_V", config["bias_voltage"] if gate_sweep else config["values"])
                frame.insert(3, "CommandedVS_V", config["source_voltage"])
                frame["VGS"] = frame["VG"] - frame["VS"]
                frame["VDS"] = frame["VD"] - frame["VS"]
            frame.insert(0, "CurveIndex", index)
            frames.append(frame)
            status_columns = [c for c in frame if c.endswith("_Status")]
            hits = frame[status_columns].eq("C").any(axis=1).sum() if status_columns else 0
            row.update(Status="complete", PointCount=len(frame), CompliancePoints=int(hits))
        except BaseException as exc:
            row.update(Status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                       Error=str(exc) or type(exc).__name__, EndTime=datetime.now().isoformat())
            try:
                save_fet_checkpoint(workbook, frames, curves, settings)
            except Exception as save_error:
                warnings.warn(f"Could not save FET failure checkpoint: {save_error}", RuntimeWarning)
            raise
        row["EndTime"] = datetime.now().isoformat()
        save_fet_checkpoint(workbook, frames, curves, settings)

    data = pd.concat(frames, ignore_index=True)
    plot_path = Path(f"{stem}_curves.png")
    save_fet_plot(data, plot_path, sweep_terminal=configs[0]["sweep_terminal"], show=show)
    print(f"Saved FET {MODE}: {workbook}")
    return {"data": data, "curves": pd.DataFrame(curves),
            "output_path": workbook, "plot_path": plot_path}


# Standalone entry follows the PREVIEW_ONLY setting above.
def main():
    return run_test()


if __name__ == "__main__":
    main()
