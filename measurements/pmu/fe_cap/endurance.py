# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: ferroelectric endurance; edit params_cycle, params_pv2, params_pund and cycle_counts.
# Instrument, channels, options and output location are INST, CH1/CH2, SEGARB_OPTIONS and SAVE_DIR.
# Flow: cumulative targets -> additional cycles -> fatigue waveform -> PV2/PUND readout -> raw data, analysis and summary.
# PREVIEW_ONLY=True previews all three waveforms; each *_params_override updates its corresponding defaults.

"""Triangular fatigue cycles followed by PV2 and triangular PUND readback."""

from pathlib import Path
import sys
import math

import matplotlib.pyplot as plt
import pandas as pd

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.pmu.preview import preview_sequence_configs
from keithley4200.output import prepare_output_dir, reserve_output_stem, measurement_name, time_tag, saved_at, reserve_summary_stem, save_summary_workbook
from keithley4200.pmu.data_processing import read_both_channels, remanent_polarization
from keithley4200.measurement_parameters import merge_parameters, remap_channel_options
from measurements.pmu.fe_cap import PV2, PUND_tri
from keithley4200.pmu.pmu_tests import validate_segment_arb_configs
from keithley4200.pmu.pmu_tests import execute_segARB_test, power_off_outputs
from keithley4200.pmu.session import PMUSession

INST = "TCPIP0::192.0.2.1::1225::SOCKET"
CH1, CH2 = 1, 2
DEVICE_AREA_CM2 = (20e-4) ** 2
# DEVICE_AREA_CM2 = (10*1e-4)**2*3.14
VP_SWEEP = 4
RISE_TIME = 2.5e-4
DELAY_TIME = 1e-3

# One bipolar triangle per cycle; delay_time=0 omits baseline holds.
params_cycle = dict(
    rise_time=RISE_TIME,
    delay_time=0,
    Vp=VP_SWEEP,
    offset=0,
    Irange1=1e-4,
    Irange2=1e-4,
)
# Same parameter meanings and waveform as the standalone PV2 entry.
params_pv2 = dict(
    rise_time=RISE_TIME,
    delay_time=DELAY_TIME,
    Vp=VP_SWEEP,
    offset=0,
    area_cm2=DEVICE_AREA_CM2,
    Irange1=1e-5,
    Irange2=1e-5,
)
# Same parameter meanings and waveform as PUND_tri; no flat-top dwell.
params_pund = dict(
    rise_time=RISE_TIME,
    delay_time=DELAY_TIME,
    offset_ramp_time=50e-6,
    Vp=VP_SWEEP,
    offset=0,
    area_cm2= DEVICE_AREA_CM2,
    Irange1=1e-5,
    Irange2=1e-5,
)
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": False,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}

# These are cumulative readback milestones, not per-step cycle increments.
cycle_counts = [1, 10, 100, 1000, 1e4, 1e5, 1e6]
SAVE_DIR = Path("data/pmu/fe_cap/endurance")


# Preview all three waveforms first; set False for acquisition.
PREVIEW_ONLY = False


# Build one unmeasured bipolar triangular fatigue cycle; omit holds when the delay is zero.
def make_cycle_seq_configs(*, channels=None, parameters=None):
    """Build one unmeasured bipolar triangle; zero delay omits the holds."""
    parameters = params_cycle if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    rise_time = parameters["rise_time"]
    delay_time = parameters["delay_time"]
    vp = parameters["Vp"]
    offset = parameters["offset"]
    start_v, stop_v, times = [], [], []
    for peak in (offset - vp, offset + vp):
        start_v.extend([offset, peak])
        stop_v.extend([peak, offset])
        times.extend([rise_time, rise_time])
        if delay_time:
            start_v.append(offset)
            stop_v.append(offset)
            times.append(delay_time)
    n = len(times)
    modes, zeros = [0] * n, [0.0] * n
    return {
        ch1: [(1, start_v, stop_v, times, modes, zeros.copy(), zeros.copy())],
        ch2: [(1, [0.0] * n, [0.0] * n, times.copy(), modes.copy(), zeros.copy(), zeros.copy())],
    }


# Convert cumulative targets to additional cycles per stage, avoiding repeated cumulative counts.
def build_cycle_schedule(target_counts):
    """Convert cumulative fatigue-cycle milestones into hardware loop counts."""
    schedule, completed = [], 0
    for raw_target in target_counts:
        if not math.isfinite(raw_target):
            raise ValueError("Cycle targets must be finite positive integers.")
        target = int(raw_target)
        if target != raw_target or target <= 0:
            raise ValueError("Cycle targets must be positive integers.")
        if target <= completed:
            raise ValueError("Cycle targets must be strictly increasing.")
        if target - completed > 1e12:
            raise ValueError("One cycle block cannot exceed the KXCI 1e12 loop limit (7-56).")
        schedule.append((target, target - completed))
        completed = target
    if not schedule:
        raise ValueError("At least one cycle target is required.")
    return schedule


# Validate each stage and restrictions related to the default 10 V source range before sending fatigue waveforms.
def validate_plan(cycle_parameters, pv2_parameters, pund_parameters, configs):
    """Preflight the default 10 V source range before applying fatigue pulses."""
    for name, parameters in (("cycle", cycle_parameters), ("PV2", pv2_parameters),
                             ("PUND_tri", pund_parameters)):
        if not math.isfinite(parameters["Vp"]) or parameters["Vp"] <= 0:
            raise ValueError(f"{name} Vp must be finite and positive.")
        if not math.isfinite(parameters["delay_time"]) or parameters["delay_time"] < 0:
            raise ValueError(f"{name} delay_time must be finite and nonnegative.")
        if name != "cycle" and (not math.isfinite(parameters["area_cm2"]) or parameters["area_cm2"] <= 0):
            raise ValueError(f"{name} area_cm2 must be finite and positive.")
        for key in ("Irange1", "Irange2"):
            if parameters[key] not in (1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.2):
                raise ValueError(f"{name} {key} must be a supported 10 V RPM fixed range (KXCI 7-15).")
    for plan in configs:
        validate_segment_arb_configs(plan)
        for sequences in plan.values():
            for config in sequences:
                if any(not math.isfinite(v) or abs(v) > 10 for v in config[1] + config[2]):
                    raise ValueError("Endurance voltage endpoints must fit the default 10 V range (KXCI 7-48/7-50).")
                if any(not math.isfinite(t) or not 20e-9 <= t <= 1.0 for t in config[3]):
                    raise ValueError("Each actual 10 V SARB segment must last 20 ns to 1 s (KXCI 7-52).")


# Apply the requested fatigue cycles through an existing connection; PV2/PUND readout is separate.
def run_cycle_block(query, n_cycles, *, parameters=None, channels=None, segarb_options=None):
    """Run only fatigue cycles; readback pulses are counted separately."""
    parameters = params_cycle if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    segarb_options = SEGARB_OPTIONS if segarb_options is None else segarb_options
    build_cycle_schedule([n_cycles])
    try:
        execute_segARB_test(
            query, channels, make_cycle_seq_configs(parameters=parameters, channels=channels),
            seq_list={ch: [(1, int(n_cycles))] for ch in channels},
            current_ranges=dict(zip(channels, (parameters["Irange1"], parameters["Irange2"]))),
            options=segarb_options,
        )
    finally:
        power_off_outputs(query, channels)


# Acquire one readout at fixed ranges and return both channels; turn outputs off before analysis and saving.
def acquire_readback(query, seq_configs, current_ranges, *, channels=None, segarb_options=None):
    """Acquire once at fixed ranges and shut down before saving or analysis."""
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    segarb_options = SEGARB_OPTIONS if segarb_options is None else segarb_options
    try:
        execute_segARB_test(query, channels, seq_configs,
                            current_ranges=current_ranges, options=segarb_options)
        return read_both_channels(query, *channels)
    finally:
        power_off_outputs(query, channels)


# Preview one fatigue cycle offline; show controls display and output_path optionally saves the image.
def preview_cycle_waveform(output_path=None, *, parameters=None, channels=None, show=True):
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    return preview_sequence_configs(make_cycle_seq_configs(parameters=parameters, channels=channels)[channels[0]],
                                    output_path, show=show, title_prefix="Endurance: one fatigue cycle")


# Preview the post-fatigue PV2 readout offline; optionally show or save the image.
def preview_pv2_waveform(output_path=None, *, parameters=None, channels=None, show=True):
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    return preview_sequence_configs(make_pv2_seq_configs(parameters=parameters, channels=channels)[channels[0]],
                                    output_path, show=show, title_prefix="Endurance PV2 readback")


# Preview the post-fatigue triangular PUND readout offline; optionally show or save the image.
def preview_pund_waveform(output_path=None, *, parameters=None, channels=None, show=True):
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    return preview_sequence_configs(make_pund_seq_configs(parameters=parameters, channels=channels)[channels[0]],
                                    output_path, show=show, title_prefix="Endurance triangular PUND readback")


# Build both PV2 channel segment waveforms and acquisition windows; no commands are sent.
def make_pv2_seq_configs(*, channels=None, parameters=None):
    """Build PV2 seq_configs directly in this script."""
    parameters = params_pv2 if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    rise_time = parameters["rise_time"]
    delay_time = parameters["delay_time"]
    vp = parameters["Vp"]
    offset = parameters["offset"]

    start_voltages = [
        0,
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        vp + offset,
        -vp + offset,
        vp + offset,
        -vp + offset,
    ]
    stop_voltages = [
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        vp + offset,
        -vp + offset,
        vp + offset,
        -vp + offset,
        offset,
    ]
    time_values = [
        rise_time,
        rise_time,
        rise_time,
        rise_time,
        delay_time,
        rise_time,
        2 * rise_time,
        2 * rise_time,
        2 * rise_time,
        rise_time,
    ]
    # Segments 0-3 are the pre/post triangle and segment 4 is the offset hold.
    # Only the main PV2 sweep in segments 5-9 is measured and integrated.
    meas_types = [0, 0, 0, 0, 0, 2, 2, 2, 2, 2]

    ch1_config = (1, start_voltages, stop_voltages, time_values, meas_types)
    ch2_config = (1, [0.0] * len(time_values), [0.0] * len(time_values), time_values, meas_types)
    return {ch1: [ch1_config], ch2: [ch2_config]}


# Build both PUND channel segment waveforms and acquisition windows; no commands are sent.
def make_pund_seq_configs(*, channels=None, parameters=None):
    """Build five triangular PUND pulses separated by unmeasured delays."""
    parameters = params_pund if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    rise_time = parameters["rise_time"]
    delay_time = parameters["delay_time"]
    offset_ramp_time = parameters["offset_ramp_time"]
    vp = parameters["Vp"]
    offset = parameters["offset"]

    start_voltages = [
        0,
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        vp + offset,
        offset,
        offset,
        vp + offset,
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        -vp + offset,
        offset,
    ]
    stop_voltages = [
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        vp + offset,
        offset,
        offset,
        vp + offset,
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
        -vp + offset,
        offset,
        offset,
    ]
    time_values = [
        offset_ramp_time,
        delay_time,
        rise_time,
        rise_time,
        delay_time,
        rise_time,
        rise_time,
        delay_time,
        rise_time,
        rise_time,
        delay_time,
        rise_time,
        rise_time,
        delay_time,
        rise_time,
        rise_time,
        delay_time,
    ]
    # Only the two slopes of each triangle contribute samples to PUND.
    measured_segments = {2, 3, 5, 6, 8, 9, 11, 12, 14, 15}
    meas_types = [2 if index in measured_segments else 0 for index in range(len(time_values))]

    ch1_config = (1, start_voltages, stop_voltages, time_values, meas_types)
    ch2_config = (1, [0.0] * len(time_values), [0.0] * len(time_values), time_values, meas_types)
    return {ch1: [ch1_config], ch2: [ch2_config]}




# Save raw channels, actual waveforms and parameters first, independently of subsequent analysis success.
def save_readback(path, frames, parameters, seq_configs, *, channels, metadata):
    """Checkpoint raw channels, exact waveforms, and all run settings first."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        writer.book.properties.creator = "ssme / Haoran Yu"
        for ch, frame in zip(channels, frames):
            if frame is not None:
                frame.to_excel(writer, sheet_name=f"Channel_{ch}", index=False)
        rows = []
        for section, values in parameters.items():
            rows.extend({"section": section, "name": key, "value": repr(value)}
                        for key, value in values.items())
        rows.extend({"section": "endurance", "name": key, "value": repr(value)}
                    for key, value in metadata.items())
        pd.DataFrame(rows).to_excel(writer, sheet_name="Parameters", index=False)
        waveform_rows = []
        for ch, sequences in seq_configs.items():
            for cfg in sequences:
                for i, (start, stop, duration, mode) in enumerate(zip(*cfg[1:5])):
                    waveform_rows.append(dict(channel=ch, sequence=cfg[0], segment=i,
                                              start_V=start, stop_V=stop, duration_s=duration,
                                              measure_type=mode))
        pd.DataFrame(waveform_rows).to_excel(writer, sheet_name="Waveform", index=False)


# Append analysis sheets to the raw-data workbook while retaining previously saved measurements.
def save_analysis(path, data, readback_name):
    """Append processed tables while retaining the raw checkpoint."""
    sheets = {"Total": data["df_total"]}
    if readback_name == "PV2":
        sheets.update(I1_Loops=data["i1_loops"], I2_Loops=data["i2_loops"])
    else:
        sheets["PUND_Diff"] = data["pund_diff"]
        sheets["AnalysisMeta"] = pd.DataFrame(
            [{"name": k, "value": repr(v)} for k, v in data["meta"].items()])
    with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        writer.book.properties.creator = "ssme / Haoran Yu"
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    fig, ax = plt.subplots(figsize=(6, 5))
    try:
        if readback_name == "PV2":
            for kind in ("delay", "no_delay"):
                frame = data[f"i2_{kind}"]
                ax.plot(frame["Voltage"], frame["Polarization"], label=kind)
        else:
            for segment, frame in data["pund_diff"].groupby("Segment", sort=False):
                ax.plot(frame["Voltage"], frame["Polarization"], label=segment)
        ax.set(xlabel="Voltage (V)", ylabel="Polarization (uC/cm^2)",
               title=f"Endurance {readback_name} from I2")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(path.with_name(f"{path.stem}_i2.png"), dpi=300)
    finally:
        plt.close(fig)


# Overlay and save PV2/PUND loops at cumulative cycle counts to compare fatigue evolution.
def save_cycle_overlay(curves, path):
    """Overlay all completed cycles separately for PV2 delay/no-delay and PUND."""
    if not any(curves.values()):
        return
    cycles = sorted({cycle for entries in curves.values() for cycle, _ in entries})
    colors = {cycle: plt.cm.viridis(index / max(len(cycles) - 1, 1))
              for index, cycle in enumerate(cycles)}
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    try:
        for axis, (name, entries) in zip(axes, curves.items()):
            for cycle, frame in entries:
                axis.plot(frame["Voltage"], frame["Polarization"],
                          color=colors[cycle], label=f"{cycle} cycles")
            axis.set(title=name + " (I2)", xlabel="Voltage (V)", ylabel="Polarization (uC/cm^2)")
            axis.grid(alpha=0.3)
            if entries:
                axis.legend()
        fig.tight_layout()
        fig.savefig(path, dpi=300)
    finally:
        plt.close(fig)


# Merge three parameter overrides, apply fatigue cycles to each cumulative target, then acquire PV2 and triangular PUND.
# preview_only=True previews only; acquisition saves raw data, analysis and summaries at each stage.
# Readouts use fixed ranges without automatic retries; readout pulses are excluded from fatigue cycle counts.
def run_test(cycle_params_override=None, pv2_params_override=None, pund_params_override=None,
             *, cycle_targets=None, channels=None, inst=None, segarb_options=None,
             save_dir=None, preview_only=None):
    """Run cumulative fatigue blocks followed by fixed-range PV2/triangle PUND.

    Each parameter override is partial; file defaults remain unchanged.
    Readback presets and read pulses affect the device but are not fatigue
    cycles in completed_cycles. No automatic range retries are performed.
    """
    cycle_parameters = merge_parameters(params_cycle, cycle_params_override)
    pv2_parameters = merge_parameters(params_pv2, pv2_params_override)
    pund_parameters = merge_parameters(params_pund, pund_params_override)
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)
    inst = INST if inst is None else inst
    save_dir = Path(SAVE_DIR if save_dir is None else save_dir)
    preview_only = PREVIEW_ONLY if preview_only is None else preview_only
    schedule = build_cycle_schedule(cycle_counts if cycle_targets is None else cycle_targets)
    cycle_digits = len(str(schedule[-1][0]))
    cycle_configs = make_cycle_seq_configs(parameters=cycle_parameters, channels=channels)
    pv2_configs = make_pv2_seq_configs(parameters=pv2_parameters, channels=channels)
    pund_configs = make_pund_seq_configs(parameters=pund_parameters, channels=channels)
    validate_plan(cycle_parameters, pv2_parameters, pund_parameters,
                  (cycle_configs, pv2_configs, pund_configs))
    parameters = {"cycle": cycle_parameters, "PV2": pv2_parameters, "PUND_tri": pund_parameters,
                  "SEGARB_OPTIONS": segarb_options}
    if preview_only:
        previews = [
            preview_cycle_waveform(parameters=cycle_parameters, channels=channels, show=False),
            preview_pv2_waveform(parameters=pv2_parameters, channels=channels, show=False),
            preview_pund_waveform(parameters=pund_parameters, channels=channels, show=False),
        ]
        plt.show()
        return {"preview": previews, "output_path": None, "params": parameters,
                "schedule": schedule}

    output_dir = prepare_output_dir(save_dir)
    summary_stem, run_time = reserve_summary_stem(output_dir, "endurance_summary")
    summary_path = Path(f"{summary_stem}.xlsx")
    rows = []
    readback_paths = []
    curves = {"PV2 delay": [], "PV2 no delay": [], "PUND": []}
    try:
        with PMUSession(inst, channels=channels) as session:
            for target, increment in schedule:
                row = {"time": run_time, "target_cycles": target, "cycle_increment": increment,
                       "stage": "cycle", "status": "running", "error": ""}
                rows.append(row)
                try:
                    run_cycle_block(session.query, increment, parameters=cycle_parameters,
                                    channels=channels, segarb_options=segarb_options)
                    row.update(status="ok", completed_cycles=target)
                    save_summary_workbook(rows, summary_path)
                    for name, read_params, configs, analyze in (
                        ("PV2", pv2_parameters, pv2_configs, PV2.analyze_pv2),
                        ("PUND_tri", pund_parameters, pund_configs, PUND_tri.analyze_pund_triangle_diff),
                    ):
                        row = {"time": run_time, "target_cycles": target, "completed_cycles": target,
                               "cycle_increment": increment, "stage": name, "status": "running",
                               "error": ""}
                        rows.append(row)
                        frames = acquire_readback(
                            session.query, configs,
                            dict(zip(channels, (read_params["Irange1"], read_params["Irange2"]))),
                            channels=channels, segarb_options=segarb_options)
                        stem = reserve_output_stem(output_dir, measurement_name(
                            "PV2" if name == "PV2" else "PUNDtri", read_params["Vp"],
                            "tr" + time_tag(read_params["rise_time"]),
                            "td" + time_tag(read_params["delay_time"]), f"cycles{target:0{cycle_digits}d}"))
                        path = Path(f"{stem}.xlsx")
                        readback_paths.append(path)
                        save_readback(path, frames, parameters, configs, channels=channels, metadata={
                            "saved_at": saved_at(), "time": run_time, "inst": inst, "channels": channels,
                            "completed_cycles": target, "cycle_increment": increment,
                            "cycle_targets": [t for t, _ in schedule], "readback": name,
                            "cycle_waveform": "triangle", "pund_waveform": "triangle",
                            "range_mode": "fixed", "cycle_counts_exclude_readback": True,
                            "Pr_reference_V": 0.0,
                            "Pr_extraction": "return_branch_linear_interpolation; zero endpoint allows at most one sample extrapolation",
                        })
                        if any(frame is None or frame.empty for frame in frames):
                            raise ValueError(f"{name} returned empty channel data; raw checkpoint saved.")
                        if len(frames[0]) != len(frames[1]):
                            raise ValueError(f"{name} channel lengths differ; raw checkpoint saved.")
                        data = analyze(*frames, channels=channels, parameters=read_params)
                        loop = data["i2_delay"] if name == "PV2" else data["pund_diff"]
                        if name == "PV2":
                            row["Pr_positive_uC_cm2"], row["Pr_negative_uC_cm2"] = remanent_polarization(
                                loop["Voltage"], loop["Polarization"], zero_endpoint=read_params["offset"] == 0)
                            no_delay = data["i2_no_delay"]
                            row["Pr_positive_no_delay_uC_cm2"], row["Pr_negative_no_delay_uC_cm2"] = remanent_polarization(
                                no_delay["Voltage"], no_delay["Polarization"], zero_endpoint=read_params["offset"] == 0)
                            curves["PV2 delay"].append((target, loop[["Voltage", "Polarization"]].copy()))
                            curves["PV2 no delay"].append((target, no_delay[["Voltage", "Polarization"]].copy()))
                        else:
                            positive = loop[(loop["Segment"] == "P-U") & (loop["Branch"] == "return")]
                            negative = loop[(loop["Segment"] == "N-D") & (loop["Branch"] == "return")]
                            row["Pr_positive_uC_cm2"] = remanent_polarization(
                                positive["Voltage"], positive["Polarization"], zero_endpoint=read_params["offset"] == 0)[0]
                            row["Pr_negative_uC_cm2"] = remanent_polarization(
                                negative["Voltage"], negative["Polarization"], zero_endpoint=read_params["offset"] == 0)[1]
                            curves["PUND"].append((target, loop[["Voltage", "Polarization"]].copy()))
                        save_analysis(path, data, name)
                        row["status"] = "ok"
                        save_summary_workbook(rows, summary_path)
                except BaseException as exc:
                    row.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                               error=str(exc))
                    raise
    finally:
        if rows:
            save_summary_workbook(rows, summary_path)
            try:
                save_cycle_overlay(curves, Path(f"{summary_stem}_loops.png"))
            except Exception as exc:
                print(f"Could not save cycle overlay; summary and measurements are retained: {exc}")
    return {"output_path": summary_path, "readback_paths": readback_paths,
            "summary": pd.DataFrame(rows), "params": parameters,
            "settings": {"inst": inst, "channels": channels, "segarb_options": segarb_options},
            "accepted_current_ranges": {}}


if __name__ == "__main__":
    run_test()
