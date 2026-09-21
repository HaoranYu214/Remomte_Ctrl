# Copyright (c) 2026 ssme / Haoran Yu.
"""Three-terminal FET validation and curve-family checkpoint tables.

KXCI manual Rev. D: CH 5-7; VL 5-16; DM/XN/YA/YB 5-22--5-26.
Source uses constant voltage bias; all three terminal voltages and currents are recorded.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from .common import normalize_channels
from .routing import normalize_smu_connections
from .system_mode import resolve_smu_timeout_s
from ..output import saved_at, save_atomic_workbook


# Check finite numbers and convert to float before constructing instrument commands.
def _finite(value, name):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")
    return number


# Validate and normalize one curve configuration for preview and acquisition; no connection is opened.
def validate_fet_sweep(
    *, values, sweep_terminal, bias_voltage,
    gate_channel=1, drain_channel=2, source_channel=3,
    available_channels=(1, 2, 3, 4), smu_connections=None,
    gate_compliance=1e-6, drain_compliance=1e-3, source_compliance=1e-3, source_voltage=0.0,
    gate_current_range="auto", drain_current_range="auto", source_current_range="auto",
    hold_time=0.0, sweep_delay=0.02, integration="IT2", timeout_s=None,
    kxci_plot=False, kxci_ig_limits=None,
):
    if sweep_terminal not in ("gate", "drain"):
        raise ValueError("sweep_terminal must be 'gate' or 'drain'.")
    active = (gate_channel, drain_channel, source_channel)
    if any(isinstance(c, bool) for c in active):
        raise ValueError("Gate, drain, and source must be distinct integer SMU channels.")
    gate_channel, drain_channel, source_channel = normalize_channels(active)
    available = normalize_channels(available_channels, name="available_channels")
    if not set(active) <= set(available):
        raise ValueError("Every FET channel must be included in available_channels.")
    connections = normalize_smu_connections(smu_connections, active_channels=active)
    values = [_finite(v, "sweep voltage") for v in values]
    if not 2 <= len(values) <= 4096 or min(values) == max(values):
        raise ValueError("A FET sweep requires 2..4096 points and distinct voltage levels.")
    bias = _finite(bias_voltage, "bias_voltage")
    source_voltage = _finite(source_voltage, "source_voltage")
    if any(abs(v) > 210 for v in [source_voltage, bias + source_voltage, *[v + source_voltage for v in values]]):
        raise ValueError("FET voltages must be within -210..210 V (module limits also apply).")
    gate_compliance = _finite(gate_compliance, "gate_compliance")
    drain_compliance = _finite(drain_compliance, "drain_compliance")
    source_compliance = _finite(source_compliance, "source_compliance")
    if gate_compliance <= 0 or drain_compliance <= 0 or source_compliance <= 0:
        raise ValueError("Gate/drain/source current compliance must be positive.")
    hold_time = _finite(hold_time, "hold_time")
    sweep_delay = _finite(sweep_delay, "sweep_delay")
    if not 0 <= hold_time <= 655.3 or not 0 <= sweep_delay <= 6.553:
        raise ValueError("HT must be 0..655.3 s and DT must be 0..6.553 s.")
    integration = str(integration).strip().upper()
    if integration not in ("IT1", "IT2", "IT3"):
        raise ValueError("FET integration must be IT1, IT2, or IT3.")
    for name, value in (("gate_current_range", gate_current_range),
                        ("drain_current_range", drain_current_range),
                        ("source_current_range", source_current_range)):
        if value is not None and str(value).strip().lower() not in ("", "auto", "default"):
            if _finite(value, name) <= 0:
                raise ValueError(f"{name} must be positive, 'auto', or None.")
    resolved_timeout = resolve_smu_timeout_s(
        timeout_s, point_count=len(values), hold_time=hold_time,
        sweep_delay=sweep_delay, integration=integration)
    if resolved_timeout is not None:
        _finite(resolved_timeout, "timeout_s")
    if not isinstance(kxci_plot, bool):
        raise ValueError("kxci_plot must be True or False.")
    ig_limits = tuple(kxci_ig_limits) if kxci_ig_limits is not None else (-gate_compliance, gate_compliance)
    if len(ig_limits) != 2:
        raise ValueError("kxci_ig_limits requires two limits.")
    low, high = [_finite(v, "kxci_ig_limits") for v in ig_limits]
    if not -999 <= low < high <= 999:
        raise ValueError("kxci_ig_limits must be increasing and within -999..999 A.")
    ig_limits = (low, high)
    return dict(
        values=values, sweep_terminal=sweep_terminal, bias_voltage=bias,
        gate_channel=gate_channel, drain_channel=drain_channel, source_channel=source_channel,
        available_channels=available, smu_connections=connections,
        gate_compliance=gate_compliance, drain_compliance=drain_compliance,
        source_voltage=source_voltage, source_compliance=source_compliance, source_current_range=source_current_range,
        gate_current_range=gate_current_range, drain_current_range=drain_current_range,
        hold_time=hold_time, sweep_delay=sweep_delay, integration=integration,
        timeout_s=resolved_timeout, kxci_plot=kxci_plot,
        kxci_ig_limits=tuple(float(v) for v in ig_limits),
    )




# Update the same workbook after each curve; replace it only after the temporary file is complete.
def save_fet_checkpoint(path, frames, curves, parameters):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    records = {k: v for k, v in parameters.items() if k != "curve_configs"}
    records.update(saved_at=saved_at(), source_mode="Voltage bias (CH mode 1, function 3)")
    planned = []
    for index, config in enumerate(parameters.get("curve_configs", []), 1):
        for key, value in config.items():
            if key != "values":
                records[f"curve_{index}.{key}"] = value
        records[f"curve_{index}.point_count"] = len(config["values"])
        for point, value in enumerate(config["values"]):
            planned.append({"CurveIndex": index, "PointIndex": point,
                            "CommandedVGS_V": value if config["sweep_terminal"] == "gate" else config["bias_voltage"],
                            "CommandedVDS_V": config["bias_voltage"] if config["sweep_terminal"] == "gate" else value,
                            "CommandedVS_V": config["source_voltage"]})
    save_atomic_workbook({
        "Raw": raw,
        "Curves": pd.DataFrame(curves),
        "SweepPlan": pd.DataFrame(planned),
        "Parameters": pd.DataFrame([{"name": k, "value": repr(v)} for k, v in records.items()]),
    }, path)
    return path
