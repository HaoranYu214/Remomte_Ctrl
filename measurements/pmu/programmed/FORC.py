# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: separately executed FORC curves; edit PARAMS, REVERSAL_*, INST, channels and SAVE_DIR.
# Flow: validate/build curves -> acquire each curve -> integrate -> checkpoint each curve -> save family plots.
# The file entry point handles PREVIEW_ONLY; main and run_forc_test both acquire data.

"""Ferroelectric first-order reversal-curve (FORC) measurement.

Each curve starts from the positive saturation voltage, descends to one
reversal voltage, and returns to positive saturation. Both moving branches are
measured. Polarization is reported relative to the common positive-saturation
starting point; an absolute saturation-polarization offset is not assumed.
"""

from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.output import measurement_name, reserve_output_stem, saved_at
from keithley4200.output import set_workbook_author
from keithley4200.pmu.data_processing import read_both_channels
from keithley4200.pmu.pmu_tests import execute_segARB_test, power_off_outputs
from keithley4200.pmu.session import PMUSession


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2

PARAMS = dict(
    # Voltages are relative to offset. Vmax must be positive.
    Vmax=5.0,
    offset=0.0,
    # Time for a complete -Vmax -> +Vmax span. Shorter reversal excursions
    # are scaled proportionally so every FORC uses the same dV/dt.
    full_sweep_time=5e-4,
    saturation_hold=5e-4,
    offset_ramp_time=1e-4,
    Irange1=1e-4,
    Irange2=1e-4,
    area_cm2=(20 * 1e-4) ** 2 * np.pi,
)

# Do not include +Vmax itself: that curve would have zero descending/return
# span and therefore carries no FORC information.
REVERSAL_START = 4.0
REVERSAL_STOP = -4.0
REVERSAL_COUNT = 80
REVERSAL_VOLTAGES = np.linspace(REVERSAL_START, REVERSAL_STOP, REVERSAL_COUNT)

SEGARB_OPTIONS = dict(
    ENABLE_CONNECTION_COMP=False,
    ENABLE_LOAD_CONFIG=True,
    LOAD_RESISTANCE=1e3,
    ENABLE_LLEC=False,
)

SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\FORC")
PREVIEW_ONLY = True


# Check finite reversal voltages within allowed bounds and return the FORC voltage list.
def _validated_reversal_voltages(params, reversal_voltages):
    """Return finite reversal levels inside [-Vmax, +Vmax)."""
    vmax = float(params["Vmax"])
    if not np.isfinite(vmax) or vmax <= 0:
        raise ValueError("Vmax must be a finite positive voltage.")

    values = np.asarray(list(reversal_voltages), dtype=float)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("reversal_voltages must contain at least one value.")
    if not np.all(np.isfinite(values)):
        raise ValueError("reversal_voltages must contain only finite values.")
    if np.any(values < -vmax) or np.any(values >= vmax):
        raise ValueError("Every reversal voltage must satisfy -Vmax <= Vr < Vmax.")
    if len(np.unique(values)) != len(values):
        raise ValueError("reversal_voltages must not contain duplicates.")
    return values


# Validate FORC timing, current ranges, offsets and device area without hardware access.
def _validate_params(params):
    """Validate timing, current-range, offset, and device-area parameters."""
    _validated_reversal_voltages(params, (0.0,))
    positive_keys = (
        "full_sweep_time",
        "saturation_hold",
        "offset_ramp_time",
        "Irange1",
        "Irange2",
        "area_cm2",
    )
    for key in positive_keys:
        value = float(params[key])
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be finite and positive.")
    if not np.isfinite(float(params["offset"])):
        raise ValueError("offset must be finite.")


# Calculate branch duration from reversal voltage to keep the same voltage ramp rate across curves.
def _branch_time(params, reversal_voltage):
    """Keep dV/dt constant for all reversal excursions."""
    vmax = float(params["Vmax"])
    return (
        float(params["full_sweep_time"])
        * (vmax - float(reversal_voltage))
        / (2.0 * vmax)
    )


# Build two-channel FORC configurations for each reversal voltage; curves execute separately.
def make_forc_seq_configs(
    ch1=CH1,
    ch2=CH2,
    params=PARAMS,
    reversal_voltages=REVERSAL_VOLTAGES,
):
    """Build one aligned Segment Arb sequence for every reversal voltage."""
    _validate_params(params)
    reversal_voltages = _validated_reversal_voltages(params, reversal_voltages)

    vmax = float(params["Vmax"])
    offset = float(params["offset"])
    positive_saturation = offset + vmax
    saturation_hold = float(params["saturation_hold"])
    offset_ramp_time = float(params["offset_ramp_time"])
    preset_time = 0.5 * float(params["full_sweep_time"])

    ch1_configs = []
    ch2_configs = []
    for sequence_id, reversal_voltage in enumerate(reversal_voltages, start=1):
        reversal_level = offset + float(reversal_voltage)
        branch_time = _branch_time(params, reversal_voltage)

        start_voltages = [
            offset,
            positive_saturation,
            positive_saturation,
            reversal_level,
            positive_saturation,
        ]
        stop_voltages = [
            positive_saturation,
            positive_saturation,
            reversal_level,
            positive_saturation,
            offset,
        ]
        time_values = [
            preset_time,
            saturation_hold,
            branch_time,
            branch_time,
            preset_time,
        ]
        # Measure the descending and return ramps. Measuring the descending
        # branch gives every curve the same Q=0 positive-saturation reference.
        meas_types = [0, 0, 2, 2, 0]

        # Only add real offset transitions. With offset=0 this avoids the
        # misleading 0 V platforms that the previous preview displayed.
        if not np.isclose(offset, 0.0, atol=1e-15):
            start_voltages = [0.0, *start_voltages, offset]
            stop_voltages = [offset, *stop_voltages, 0.0]
            time_values = [offset_ramp_time, *time_values, offset_ramp_time]
            meas_types = [0, *meas_types, 0]

        ch1_configs.append(
            (
                sequence_id,
                start_voltages,
                stop_voltages,
                time_values,
                meas_types,
            )
        )
        ch2_configs.append(
            (
                sequence_id,
                [0.0] * len(time_values),
                [0.0] * len(time_values),
                time_values,
                meas_types,
            )
        )
    return {ch1: ch1_configs, ch2: ch2_configs}


# Preview separate FORC waveforms offline; their placement does not imply one continuous hardware execution.
def preview_forc_waveforms(
    output_path=None,
    *,
    params=PARAMS,
    reversal_voltages=REVERSAL_VOLTAGES,
    ch1=CH1,
    ch2=CH2,
):
    """Preview every configured independent FORC run on one time axis."""
    reversal_voltages = _validated_reversal_voltages(params, reversal_voltages)
    configs = make_forc_seq_configs(
        ch1=ch1,
        ch2=ch2,
        params=params,
        reversal_voltages=reversal_voltages,
    )[ch1]
    figure, axis = plt.subplots(figsize=(16, 6))
    gap = max(float(params["offset_ramp_time"]) * 0.15, 1e-7)
    elapsed = 0.0
    annotation_stride = max(1, int(np.ceil(len(configs) / 10)))

    for index, (config, reversal_voltage) in enumerate(
        zip(configs, reversal_voltages)
    ):
        _sequence_id, starts, stops, durations, meas_types = config[:5]
        run_start = elapsed
        for start, stop, duration, measure_type in zip(
            starts,
            stops,
            durations,
            meas_types,
        ):
            next_time = elapsed + float(duration)
            axis.plot(
                [elapsed * 1e3, next_time * 1e3],
                [start, stop],
                color="tab:blue",
                linewidth=0.8,
            )
            if measure_type != 0:
                axis.plot(
                    [elapsed * 1e3, next_time * 1e3],
                    [start, stop],
                    color="tab:orange",
                    linewidth=2.2,
                )
            elapsed = next_time

        run_end = elapsed
        axis.axvline(run_start * 1e3, color="0.82", linewidth=0.45)
        if index % annotation_stride == 0 or index == len(configs) - 1:
            axis.text(
                0.5 * (run_start + run_end) * 1e3,
                float(params["offset"]) + float(params["Vmax"]) + 0.15,
                f"Vr={reversal_voltage:g}",
                rotation=90,
                ha="center",
                va="bottom",
                fontsize=7,
            )
        elapsed += gap

    axis.axvline((elapsed - gap) * 1e3, color="0.82", linewidth=0.45)
    axis.plot([], [], color="tab:blue", linewidth=1, label="Programmed voltage")
    axis.plot([], [], color="tab:orange", linewidth=2.2, label="Measured ramps")
    axis.set_xlabel("Concatenated time across separate runs (ms)")
    axis.set_ylabel("Voltage (V)")
    axis.set_title(
        f"FORC waveform preview — {len(configs)} separate runs",
        pad=55,
    )
    axis.grid(alpha=0.2)
    axis.legend(loc="lower left")
    figure.tight_layout()

    if output_path is None:
        plt.show()
        return None
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=200)
    plt.close(figure)
    print(f"Saved FORC waveform preview to {output_path}")
    return output_path


# Cumulatively integrate current over time with the trapezoidal rule, returning charge starting at zero.
def _cumulative_trapezoid(current, time_values):
    current = np.asarray(current, dtype=float)
    time_values = np.asarray(time_values, dtype=float)
    if len(current) != len(time_values):
        raise ValueError("Current and time arrays must have the same length.")
    charge = np.zeros(len(current), dtype=float)
    if len(current) > 1:
        charge[1:] = np.cumsum(
            0.5 * (current[:-1] + current[1:]) * np.diff(time_values)
        )
    return charge


# Process one descending/return curve and integrate from positive saturation into relative polarization.
def analyze_forc_curve(
    df_ch1,
    df_ch2,
    reversal_voltage,
    params=PARAMS,
    curve_index=0,
    ch1=CH1,
    ch2=CH2,
):
    """Build one descending/return curve and integrate from positive saturation."""
    _validate_params(params)
    if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
        raise ValueError("FORC returned empty channel data.")

    point_count = min(len(df_ch1), len(df_ch2))
    if point_count < 6:
        raise ValueError("FORC curve has too few points to split into two branches.")
    descending_count = point_count // 2
    return_count = point_count - descending_count

    voltage = (
        df_ch1[f"Voltage {ch1}"].to_numpy(dtype=float)[:point_count]
        - df_ch2[f"Voltage {ch2}"].to_numpy(dtype=float)[:point_count]
    )
    current_i1 = df_ch1[f"Current {ch1}"].to_numpy(dtype=float)[:point_count]
    # Existing Fe-cap tests use current entering the device from grounded CH2.
    current_i2 = -df_ch2[f"Current {ch2}"].to_numpy(dtype=float)[:point_count]
    raw_time = df_ch1[f"Timestamp {ch1}"].to_numpy(dtype=float)[:point_count]

    duration = _branch_time(params, reversal_voltage)
    descending_time = np.linspace(0.0, duration, descending_count)
    return_time = duration + np.linspace(0.0, duration, return_count)
    local_time = np.concatenate((descending_time, return_time))
    charge_i1 = _cumulative_trapezoid(current_i1, local_time)
    charge_i2 = _cumulative_trapezoid(current_i2, local_time)
    area_cm2 = float(params["area_cm2"])

    return pd.DataFrame(
        {
            "CurveIndex": int(curve_index),
            "ReversalVoltage": float(reversal_voltage),
            "Branch": ["Descending"] * descending_count + ["Return"] * return_count,
            "LocalTime": local_time,
            "RawTimestamp": raw_time,
            "Voltage": voltage,
            "CurrentI1": current_i1,
            "CurrentI2": current_i2,
            "ChargeI1": charge_i1,
            "ChargeI2": charge_i2,
            "PolarizationRelativeI1": charge_i1 / area_cm2 * 1e6,
            "PolarizationRelativeI2": charge_i2 / area_cm2 * 1e6,
        }
    )


# Build a parameter table from this run's settings and instrument options without acquiring data.
def build_params_table(params, reversal_voltages, segarb_options):
    rows = [{"name": name, "value": repr(value)} for name, value in params.items()]
    rows.append({"name": "REVERSAL_VOLTAGES", "value": repr(list(reversal_voltages))})
    rows.extend(
        {"name": name, "value": repr(value)}
        for name, value in segarb_options.items()
    )
    rows.append(
        {
            "name": "POLARIZATION_REFERENCE",
            "value": repr("Q=0 at the start of each positive-saturation descent"),
        }
    )
    rows.append({"name": "saved_at", "value": saved_at()})
    return pd.DataFrame(rows)


# Checkpoint completed FORC curves, raw data and parameters in a workbook.
def save_forc_workbook(
    output_path,
    raw_ch1_frames,
    raw_ch2_frames,
    forc_frames,
    *,
    params,
    reversal_voltages,
    segarb_options,
):
    """Write a restart-safe checkpoint after every completed FORC curve."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        set_workbook_author(writer.book)
        pd.concat(raw_ch1_frames, ignore_index=True).to_excel(
            writer, sheet_name="Raw_CH1", index=False
        )
        pd.concat(raw_ch2_frames, ignore_index=True).to_excel(
            writer, sheet_name="Raw_CH2", index=False
        )
        pd.concat(forc_frames, ignore_index=True).to_excel(
            writer, sheet_name="FORC_Data", index=False
        )
        build_params_table(params, reversal_voltages, segarb_options).to_excel(
            writer, sheet_name="Parameters", index=False
        )
    return output_path


# Save polarization and current families for FORC return branches.
def save_forc_plots(forc_data, output_stem):
    """Save return-branch polarization and current families."""
    output_stem = Path(output_stem)
    return_data = forc_data[forc_data["Branch"] == "Return"]
    curve_groups = list(return_data.groupby("CurveIndex", sort=True))
    colors = plt.cm.viridis(np.linspace(0.0, 1.0, len(curve_groups)))

    figure_p, axis_p = plt.subplots(figsize=(7, 5))
    figure_i, axis_i = plt.subplots(figsize=(7, 5))
    for color, (_curve_index, curve) in zip(colors, curve_groups):
        reversal_voltage = curve["ReversalVoltage"].iloc[0]
        label = f"Vr={reversal_voltage:g} V"
        axis_p.plot(
            curve["Voltage"],
            curve["PolarizationRelativeI2"],
            color=color,
            linewidth=1,
            label=label,
        )
        axis_i.plot(
            curve["Voltage"],
            curve["CurrentI2"],
            color=color,
            linewidth=1,
            label=label,
        )

    for axis in (axis_p, axis_i):
        axis.set_xlabel("Voltage (V)")
        axis.grid(alpha=0.3)
    axis_p.set_ylabel("Relative polarization (uC/cm^2)")
    axis_p.set_title("FORC Return Branches")
    axis_i.set_ylabel("Current I2 (A)")
    axis_i.set_title("FORC Return-Branch Current")
    if len(curve_groups) <= 12:
        axis_p.legend(fontsize=7)
        axis_i.legend(fontsize=7)

    figure_p.tight_layout()
    figure_i.tight_layout()
    polarization_path = Path(f"{output_stem}_polarization.png")
    current_path = Path(f"{output_stem}_current.png")
    figure_p.savefig(polarization_path, dpi=300)
    figure_i.savefig(current_path, dpi=300)
    plt.close(figure_p)
    plt.close(figure_i)
    return polarization_path, current_path


# Acquire FORC curves through the existing connection, checkpoint each curve and save final plots.
# Return curve data and output information; params and reversal_voltages specify this run.
def run_forc_test(
    query,
    *,
    ch1=CH1,
    ch2=CH2,
    params=PARAMS,
    reversal_voltages=REVERSAL_VOLTAGES,
    save_dir=SAVE_DIR,
    segarb_options=SEGARB_OPTIONS,
):
    """Acquire the FORC family one curve at a time and checkpoint each curve."""
    _validate_params(params)
    reversal_voltages = _validated_reversal_voltages(params, reversal_voltages)
    save_dir = Path(save_dir)
    output_stem = reserve_output_stem(save_dir, measurement_name("FORC", params["Vmax"]))
    workbook_path = Path(f"{output_stem}.xlsx")

    all_configs = make_forc_seq_configs(
        ch1=ch1,
        ch2=ch2,
        params=params,
        reversal_voltages=reversal_voltages,
    )
    raw_ch1_frames = []
    raw_ch2_frames = []
    forc_frames = []
    interrupted = False

    try:
        for curve_index, reversal_voltage in enumerate(reversal_voltages):
            print(
                f"FORC {curve_index + 1}/{len(reversal_voltages)}: "
                f"Vr={reversal_voltage:g} V"
            )
            # Configure only one curve per acquisition. This bounds each PMU
            # buffer and makes the two measured branches explicit.
            ch1_config = (1, *all_configs[ch1][curve_index][1:])
            ch2_config = (1, *all_configs[ch2][curve_index][1:])
            seq_configs = {ch1: [ch1_config], ch2: [ch2_config]}
            current_ranges = {
                ch1: float(params["Irange1"]),
                ch2: float(params["Irange2"]),
            }

            try:
                execute_segARB_test(
                    query,
                    [ch1, ch2],
                    seq_configs,
                    current_ranges=current_ranges,
                    options=segarb_options,
                )
                df_ch1, df_ch2 = read_both_channels(query, ch1, ch2)
            finally:
                power_off_outputs(query, (ch1, ch2))

            curve = analyze_forc_curve(
                df_ch1,
                df_ch2,
                reversal_voltage,
                params=params,
                curve_index=curve_index,
                ch1=ch1,
                ch2=ch2,
            )
            tagged_ch1 = df_ch1.copy()
            tagged_ch2 = df_ch2.copy()
            for frame in (tagged_ch1, tagged_ch2):
                frame.insert(0, "ReversalVoltage", float(reversal_voltage))
                frame.insert(0, "CurveIndex", curve_index)
            raw_ch1_frames.append(tagged_ch1)
            raw_ch2_frames.append(tagged_ch2)
            forc_frames.append(curve)

            save_forc_workbook(
                workbook_path,
                raw_ch1_frames,
                raw_ch2_frames,
                forc_frames,
                params=params,
                reversal_voltages=reversal_voltages,
                segarb_options=segarb_options,
            )
    except KeyboardInterrupt:
        interrupted = True
        print(f"FORC interrupted after {len(forc_frames)} completed curves.")

    if not forc_frames:
        raise RuntimeError("FORC ended before any complete curve was acquired.")

    forc_data = pd.concat(forc_frames, ignore_index=True)
    polarization_path, current_path = save_forc_plots(forc_data, output_stem)
    status = "interrupted" if interrupted else "complete"
    print(f"FORC {status}: {len(forc_frames)}/{len(reversal_voltages)} curves.")
    print(f"Saved FORC workbook: {workbook_path.resolve()}")
    print(f"Saved FORC polarization plot: {polarization_path.resolve()}")
    print(f"Saved FORC current plot: {current_path.resolve()}")
    return {
        "data": forc_data,
        "workbook_path": workbook_path,
        "polarization_path": polarization_path,
        "current_path": current_path,
        "completed_curves": len(forc_frames),
        "interrupted": interrupted,
    }


# Create a PMU session and acquire via run_forc_test; the file entry point selects preview or measurement.
def main():
    with PMUSession(INST, channels=(CH1, CH2)) as session:
        run_forc_test(session.query)


if __name__ == "__main__":
    if PREVIEW_ONLY:
        preview_forc_waveforms()
    else:
        main()
