# Copyright (c) 2026 ssme / Haoran Yu.
"""Shared PMU helpers for two-channel plus grounded-source FET pulse tests."""

from __future__ import annotations

from pathlib import Path
import time

import numpy as np
from keithley4200.output import saved_at

import pandas as pd

from .data_processing import read_both_channels, read_channel_data
from .pmu_tests import execute_segARB_test, power_off_outputs


def source_smu_on(query, channel, voltage, compliance):
    """Put one independent SMU in User Mode and force the source potential."""
    query("US")
    query(f"DV{channel}, 0, {voltage}, {compliance}")


def source_smu_off(query, channel):
    """Best-effort shutdown for a User Mode voltage source."""
    try:
        query("US")
        query(f"DV{channel}")
    except Exception:
        pass


def read_fet_channels(query, gate_channel, drain_channel, *, float_gate=False):
    """Read Drain only when Gate is isolated; NaNs are explicit missing data.

    Floating Gate voltage is not the PMU programmed voltage. Do not acquire
    or infer Gate V/I from a disconnected PMU channel (KXCI SSR, 7-46).
    """
    if not float_gate:
        return read_both_channels(query, gate_channel, drain_channel)
    drain = read_channel_data(query, drain_channel)
    if drain is None or drain.empty:
        return None, drain
    gate = pd.DataFrame({
        f"Voltage {gate_channel}": np.full(len(drain), np.nan),
        f"Current {gate_channel}": np.full(len(drain), np.nan),
        f"Timestamp {gate_channel}": np.full(len(drain), np.nan),
        f"Status {gate_channel}": ["not_acquired_ssr_open"] * len(drain),
    })
    return gate, drain


def add_derived_fet_columns(data, gate_channel=1, drain_channel=2):
    """Add inferred source current and conventional FET aliases."""
    data = data.copy()
    aliases = {
        f"Voltage {gate_channel}": "MeasuredVg",
        f"Current {gate_channel}": "Ig",
        f"Voltage {drain_channel}": "MeasuredVd",
        f"Current {drain_channel}": "Id",
    }
    for source, target in aliases.items():
        if source in data:
            data[target] = pd.to_numeric(data[source], errors="coerce")
    if "Ig" in data and "Id" in data:
        data["InferredIs"] = -(data["Ig"] + data["Id"])
    return data


def save_fet_workbook(path, data, parameters, channel_frames=None):
    """Save aligned FET results, raw PMU channels, and parameters."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    parameters = {**parameters, "saved_at": saved_at()}
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        writer.book.properties.creator = "ssme / Haoran Yu"
        data.to_excel(writer, sheet_name="FET_Data", index=False)
        for channel, frame in (channel_frames or {}).items():
            if frame is not None and not frame.empty:
                frame.to_excel(writer, sheet_name=f"PMU_CH{channel}", index=False)
        pd.DataFrame(
            [{"name": key, "value": repr(value)} for key, value in parameters.items()]
        ).to_excel(writer, sheet_name="Parameters", index=False)
    return path


def save_waveform_data_sheets(workbook_path, real_time_data, schematic_data):
    """Add numeric real-time and compressed waveform plotting data sheets."""
    workbook_path = Path(workbook_path)
    with pd.ExcelWriter(
        workbook_path,
        engine="openpyxl",
        mode="a",
        if_sheet_exists="replace",
    ) as writer:
        writer.book.properties.creator = "ssme / Haoran Yu"
        real_time_data.to_excel(writer, sheet_name="Waveform_RealTime", index=False)
        schematic_data.to_excel(writer, sheet_name="Waveform_Schematic", index=False)
    return workbook_path


def report_last_error(query):
    """Print and return the last KXCI error without masking shutdown."""
    try:
        response = query(":ERROR:LAST:GET").strip()
    except Exception as exc:
        print(f"Could not query KXCI error queue: {exc}")
        return ""
    if response and not response.startswith("0"):
        print(f"KXCI error: {response}")
    return response


def execute_program_read_with_software_delay(
    query,
    plan,
    seq_configs,
    delay,
    gate_channel,
    drain_channel,
    current_ranges,
    options,
    *, float_gate=False,
):
    """Execute each write and read separately with a host-side delay."""
    sequence_ids = sorted(config[0] for config in seq_configs[gate_channel])
    read_sequence_id = sequence_ids[-1]
    program_sequence_ids = sequence_ids[:-1]
    if not program_sequence_ids:
        raise ValueError("No program sequence is available for split-delay execution.")

    config_lookup = {
        channel: {config[0]: config for config in configs}
        for channel, configs in seq_configs.items()
    }
    raw_gate, raw_drain = [], []
    channels = (gate_channel, drain_channel)

    for point_index in range(len(plan)):
        if "ProgramSequenceID" in plan.columns:
            program_sequence_id = int(plan.iloc[point_index]["ProgramSequenceID"])
        else:
            program_sequence_id = program_sequence_ids[
                point_index % len(program_sequence_ids)
            ]
        # Every split execution begins with PMU INIT. Define its sole sequence
        # as ID 1; an isolated original ID (for example read sequence 3) is not
        # recognized by the PMU and causes KXCI -961 "Unknown sequence".
        write_configs = {
            channel: [(1, *config_lookup[channel][program_sequence_id][1:])]
            for channel in channels
        }
        write_list = {
            channel: [(1, int(plan.iloc[point_index]["TrainCount"]))]
            for channel in channels
        }
        execute_segARB_test(
            query,
            list(channels),
            write_configs,
            seq_list=write_list,
            current_ranges=current_ranges,
            options=options,
        )
        power_off_outputs(query, channels)
        print(
            f"Software delay {float(delay):g} s before read "
            f"({point_index + 1}/{len(plan)})..."
        )
        time.sleep(float(delay))

        read_configs = {
            channel: [(1, *config_lookup[channel][read_sequence_id][1:])]
            for channel in channels
        }
        read_list = {channel: [(1, 1)] for channel in channels}
        execute_segARB_test(
            query,
            list(channels),
            read_configs,
            seq_list=read_list,
            current_ranges=current_ranges,
            options=options,
        )
        gate_df, drain_df = read_fet_channels(query, gate_channel, drain_channel, float_gate=float_gate)
        if gate_df is None or drain_df is None or gate_df.empty or drain_df.empty:
            report_last_error(query)
            raise ValueError(f"Split read {point_index + 1} returned empty PMU data.")
        if len(gate_df) != 1 or len(drain_df) != 1:
            raise ValueError(
                f"Split read {point_index + 1} expected one point, received "
                f"CH{gate_channel}={len(gate_df)}, CH{drain_channel}={len(drain_df)}."
            )
        raw_gate.append(gate_df.reset_index(drop=True))
        raw_drain.append(drain_df.reset_index(drop=True))
        power_off_outputs(query, channels)

    return (
        pd.concat(raw_gate, ignore_index=True),
        pd.concat(raw_drain, ignore_index=True),
    )
