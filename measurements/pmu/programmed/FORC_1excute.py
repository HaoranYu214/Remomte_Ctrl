# -*- coding: utf-8 -*-
"""Run the complete ferroelectric FORC family in one PMU execution.

Unlike ``FORC.py``, this entry initializes and enables the PMU only once. The
waveform ramps from zero to positive saturation, executes every
``+Vmax -> Vr -> +Vmax`` reversal pair continuously, then returns to zero.
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

from measurements.pmu.programmed import FORC as separate_forc
from keithley4200.output import measurement_name, reserve_output_stem
from keithley4200.pmu.data_processing import read_both_channels
from keithley4200.pmu.pmu_tests import (
    KXCI_DEFAULT_SAMPLE_RATE,
    KXCI_MAX_DATA_POINTS,
    MAX_SEGMENTS_PER_SEQUENCE,
    execute_segARB_test,
    power_off_outputs,
)
from keithley4200.pmu.session import PMUSession


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2

PARAMS = dict(
    Vmax=5.0,
    offset=0.0,
    # Time for a complete -Vmax -> +Vmax sweep. Every reversal ramp uses the
    # corresponding fraction, keeping dV/dt constant.
    full_sweep_time=5e-4,
    saturation_hold=5e-4,
    offset_ramp_time=1e-4,
    Irange1=1e-4,
    Irange2=1e-4,
    area_cm2=(20 * 1e-4) ** 2 * np.pi,
)

REVERSAL_START = 4.0
REVERSAL_STOP = -4.0
REVERSAL_COUNT = 10
REVERSAL_VOLTAGES = np.linspace(REVERSAL_START, REVERSAL_STOP, REVERSAL_COUNT)

SEGARB_OPTIONS = dict(
    ENABLE_CONNECTION_COMP=False,
    ENABLE_LOAD_CONFIG=True,
    LOAD_RESISTANCE=1e3,
    ENABLE_LLEC=False,
)

SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\FORC")
PREVIEW_ONLY = True


def _branch_time(params, reversal_voltage):
    return separate_forc._branch_time(params, reversal_voltage)


def build_combined_forc_layout(
    ch1=CH1,
    ch2=CH2,
    params=PARAMS,
    reversal_voltages=REVERSAL_VOLTAGES,
):
    """Build and validate one sequence containing the complete FORC family."""
    separate_forc._validate_params(params)
    reversal_voltages = separate_forc._validated_reversal_voltages(
        params,
        reversal_voltages,
    )
    vmax = float(params["Vmax"])
    offset = float(params["offset"])
    positive_saturation = offset + vmax
    saturation_hold = float(params["saturation_hold"])
    offset_ramp_time = float(params["offset_ramp_time"])
    preset_time = 0.5 * float(params["full_sweep_time"])

    starts = []
    stops = []
    durations = []
    measure_types = []
    measured_segments = []

    def add_segment(start, stop, duration, measure_type, metadata=None):
        starts.append(float(start))
        stops.append(float(stop))
        durations.append(float(duration))
        measure_types.append(int(measure_type))
        if metadata is not None:
            measured_segments.append(
                {
                    **metadata,
                    "segment_index": len(durations) - 1,
                    "duration": float(duration),
                }
            )

    if not np.isclose(offset, 0.0, atol=1e-15):
        add_segment(0.0, offset, offset_ramp_time, 0)
    add_segment(offset, positive_saturation, preset_time, 0)

    for curve_index, reversal_voltage in enumerate(reversal_voltages):
        reversal_level = offset + float(reversal_voltage)
        branch_time = _branch_time(params, reversal_voltage)

        # Returning to +Vmax from the previous curve already sets the voltage;
        # this hold supplies the same saturation dwell before every reversal.
        add_segment(positive_saturation, positive_saturation, saturation_hold, 0)
        add_segment(
            positive_saturation,
            reversal_level,
            branch_time,
            2,
            {
                "curve_index": curve_index,
                "reversal_voltage": float(reversal_voltage),
                "branch": "Descending",
            },
        )
        add_segment(
            reversal_level,
            positive_saturation,
            branch_time,
            2,
            {
                "curve_index": curve_index,
                "reversal_voltage": float(reversal_voltage),
                "branch": "Return",
            },
        )

    add_segment(positive_saturation, offset, preset_time, 0)
    if not np.isclose(offset, 0.0, atol=1e-15):
        add_segment(offset, 0.0, offset_ramp_time, 0)

    segment_count = len(durations)
    if segment_count > MAX_SEGMENTS_PER_SEQUENCE:
        raise ValueError(
            f"Combined FORC requires {segment_count} segments, above the "
            f"4225-PMU limit of {MAX_SEGMENTS_PER_SEQUENCE}."
        )

    measurement_time = sum(item["duration"] for item in measured_segments)
    shortest_measurement = min(item["duration"] for item in measured_segments)
    minimum_usable_sample_rate = 1.0 / shortest_measurement
    automatic_sample_rate = min(
        KXCI_DEFAULT_SAMPLE_RATE,
        KXCI_MAX_DATA_POINTS / measurement_time,
    )
    if minimum_usable_sample_rate > automatic_sample_rate:
        raise ValueError(
            "The combined FORC timing cannot satisfy both the shortest measured "
            f"segment ({shortest_measurement:g} s) and the KXCI "
            f"{KXCI_MAX_DATA_POINTS}-point limit."
        )
    estimated_samples = min(
        KXCI_MAX_DATA_POINTS,
        int(np.ceil(measurement_time * automatic_sample_rate)),
    )

    ch1_config = (1, starts, stops, durations, measure_types)
    ch2_config = (
        1,
        [0.0] * segment_count,
        [0.0] * segment_count,
        list(durations),
        list(measure_types),
    )
    return {
        "seq_configs": {ch1: [ch1_config], ch2: [ch2_config]},
        "measured_segments": measured_segments,
        "segment_count": segment_count,
        "measurement_time": measurement_time,
        "shortest_measurement": shortest_measurement,
        "minimum_usable_sample_rate": minimum_usable_sample_rate,
        "automatic_sample_rate": automatic_sample_rate,
        "estimated_samples": estimated_samples,
    }


def make_forc_seq_configs(
    ch1=CH1,
    ch2=CH2,
    params=PARAMS,
    reversal_voltages=REVERSAL_VOLTAGES,
):
    """Return the one-sequence configuration used by preview and execution."""
    return build_combined_forc_layout(
        ch1=ch1,
        ch2=ch2,
        params=params,
        reversal_voltages=reversal_voltages,
    )["seq_configs"]


def preview_forc_waveforms(
    output_path=None,
    *,
    params=PARAMS,
    reversal_voltages=REVERSAL_VOLTAGES,
    ch1=CH1,
    ch2=CH2,
):
    """Preview the exact continuous waveform without connecting to the PMU."""
    reversal_voltages = separate_forc._validated_reversal_voltages(
        params,
        reversal_voltages,
    )
    layout = build_combined_forc_layout(
        ch1=ch1,
        ch2=ch2,
        params=params,
        reversal_voltages=reversal_voltages,
    )
    config = layout["seq_configs"][ch1][0]
    _sequence_id, starts, stops, durations, measure_types = config[:5]
    annotation_stride = max(1, int(np.ceil(len(reversal_voltages) / 10)))
    markers = {
        item["segment_index"]: item
        for item in layout["measured_segments"]
        if item["branch"] == "Descending"
        and (
            item["curve_index"] % annotation_stride == 0
            or item["curve_index"] == len(reversal_voltages) - 1
        )
    }

    figure, axis = plt.subplots(figsize=(16, 6))
    elapsed = 0.0
    for segment_index, (start, stop, duration, measure_type) in enumerate(
        zip(starts, stops, durations, measure_types)
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
        marker = markers.get(segment_index)
        if marker is not None:
            axis.text(
                next_time * 1e3,
                float(params["offset"]) + float(params["Vmax"]) + 0.15,
                f"Vr={marker['reversal_voltage']:g}",
                rotation=90,
                ha="center",
                va="bottom",
                fontsize=7,
            )
        elapsed = next_time

    axis.plot([], [], color="tab:blue", linewidth=1, label="Programmed voltage")
    axis.plot([], [], color="tab:orange", linewidth=2.2, label="Measured ramps")
    axis.set_xlabel("Time within one PMU execution (ms)")
    axis.set_ylabel("Voltage (V)")
    axis.set_title(
        f"FORC waveform preview - one execution, "
        f"{len(reversal_voltages)} curves, {layout['segment_count']} segments",
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
    print(f"Saved single-execution FORC preview to {output_path}")
    return output_path


def _allocate_measured_segment_counts(point_count, measured_segments):
    """Allocate returned points using the common sample rate and window times."""
    if point_count < 3 * len(measured_segments):
        raise ValueError(
            "Combined FORC returned too few points for all measured segments."
        )
    weights = np.asarray(
        [item["duration"] for item in measured_segments],
        dtype=float,
    )
    ideal = point_count * weights / weights.sum()
    counts = np.floor(ideal).astype(int)
    remainder = point_count - int(counts.sum())
    fractional_order = np.argsort(-(ideal - counts), kind="stable")
    counts[fractional_order[:remainder]] += 1
    if np.any(counts < 3):
        raise ValueError("At least one FORC branch contains fewer than three points.")
    return counts.tolist()


def _analyze_curve_segments(
    descending_ch1,
    return_ch1,
    descending_ch2,
    return_ch2,
    metadata,
    *,
    params,
    ch1,
    ch2,
):
    """Integrate one exactly split descending/return pair."""
    frames = (descending_ch1, return_ch1, descending_ch2, return_ch2)
    if any(frame is None or frame.empty for frame in frames):
        raise ValueError("FORC branch returned empty data.")
    descending_count = min(len(descending_ch1), len(descending_ch2))
    return_count = min(len(return_ch1), len(return_ch2))
    duration = float(metadata[0]["duration"])

    voltage = np.concatenate(
        (
            descending_ch1[f"Voltage {ch1}"].to_numpy()[:descending_count]
            - descending_ch2[f"Voltage {ch2}"].to_numpy()[:descending_count],
            return_ch1[f"Voltage {ch1}"].to_numpy()[:return_count]
            - return_ch2[f"Voltage {ch2}"].to_numpy()[:return_count],
        )
    )
    current_i1 = np.concatenate(
        (
            descending_ch1[f"Current {ch1}"].to_numpy()[:descending_count],
            return_ch1[f"Current {ch1}"].to_numpy()[:return_count],
        )
    )
    current_i2 = -np.concatenate(
        (
            descending_ch2[f"Current {ch2}"].to_numpy()[:descending_count],
            return_ch2[f"Current {ch2}"].to_numpy()[:return_count],
        )
    )
    raw_time = np.concatenate(
        (
            descending_ch1[f"Timestamp {ch1}"].to_numpy()[:descending_count],
            return_ch1[f"Timestamp {ch1}"].to_numpy()[:return_count],
        )
    )
    local_time = np.concatenate(
        (
            np.linspace(0.0, duration, descending_count),
            duration + np.linspace(0.0, duration, return_count),
        )
    )
    charge_i1 = separate_forc._cumulative_trapezoid(current_i1, local_time)
    charge_i2 = separate_forc._cumulative_trapezoid(current_i2, local_time)
    area_cm2 = float(params["area_cm2"])
    curve_index = int(metadata[0]["curve_index"])
    reversal_voltage = float(metadata[0]["reversal_voltage"])

    return pd.DataFrame(
        {
            "CurveIndex": curve_index,
            "ReversalVoltage": reversal_voltage,
            "Branch": ["Descending"] * descending_count
            + ["Return"] * return_count,
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


def split_combined_forc_data(
    df_ch1,
    df_ch2,
    measured_segments,
    *,
    params=PARAMS,
    ch1=CH1,
    ch2=CH2,
):
    """Split the single PMU buffer back into its 80 reversal curves."""
    if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
        raise ValueError("Combined FORC returned empty channel data.")
    if len(df_ch1) != len(df_ch2):
        raise ValueError(
            f"FORC channel lengths differ: CH{ch1}={len(df_ch1)}, "
            f"CH{ch2}={len(df_ch2)}."
        )

    counts = _allocate_measured_segment_counts(len(df_ch1), measured_segments)
    ch1_segments = []
    ch2_segments = []
    cursor = 0
    for count, metadata in zip(counts, measured_segments):
        segment_ch1 = df_ch1.iloc[cursor : cursor + count].copy()
        segment_ch2 = df_ch2.iloc[cursor : cursor + count].copy()
        for frame in (segment_ch1, segment_ch2):
            frame.insert(0, "Branch", metadata["branch"])
            frame.insert(0, "ReversalVoltage", metadata["reversal_voltage"])
            frame.insert(0, "CurveIndex", metadata["curve_index"])
        ch1_segments.append(segment_ch1)
        ch2_segments.append(segment_ch2)
        cursor += count

    raw_ch1_frames = []
    raw_ch2_frames = []
    forc_frames = []
    for curve_index in range(len(measured_segments) // 2):
        first = 2 * curve_index
        metadata = measured_segments[first : first + 2]
        raw_ch1_frames.append(
            pd.concat(ch1_segments[first : first + 2], ignore_index=True)
        )
        raw_ch2_frames.append(
            pd.concat(ch2_segments[first : first + 2], ignore_index=True)
        )
        forc_frames.append(
            _analyze_curve_segments(
                ch1_segments[first],
                ch1_segments[first + 1],
                ch2_segments[first],
                ch2_segments[first + 1],
                metadata,
                params=params,
                ch1=ch1,
                ch2=ch2,
            )
        )
    return raw_ch1_frames, raw_ch2_frames, forc_frames


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
    """Execute, read, split, and save the complete FORC family once."""
    reversal_voltages = separate_forc._validated_reversal_voltages(
        params,
        reversal_voltages,
    )
    layout = build_combined_forc_layout(
        ch1=ch1,
        ch2=ch2,
        params=params,
        reversal_voltages=reversal_voltages,
    )
    print(
        f"Running {len(reversal_voltages)} FORCs in one execution: "
        f"{layout['segment_count']} segments, "
        f"{layout['measurement_time'] * 1e3:.3f} ms measured, "
        f"KXCI automatic rate up to "
        f"{layout['automatic_sample_rate'] / 1e6:.4g} MSa/s "
        f"({layout['estimated_samples']} points/channel maximum)."
    )

    current_ranges = {
        ch1: float(params["Irange1"]),
        ch2: float(params["Irange2"]),
    }
    try:
        execute_segARB_test(
            query,
            [ch1, ch2],
            layout["seq_configs"],
            current_ranges=current_ranges,
            options=segarb_options,
        )
        df_ch1, df_ch2 = read_both_channels(query, ch1, ch2)
    finally:
        power_off_outputs(query, (ch1, ch2))

    raw_ch1_frames, raw_ch2_frames, forc_frames = split_combined_forc_data(
        df_ch1,
        df_ch2,
        layout["measured_segments"],
        params=params,
        ch1=ch1,
        ch2=ch2,
    )
    forc_data = pd.concat(forc_frames, ignore_index=True)
    save_dir = Path(save_dir)
    output_stem = reserve_output_stem(save_dir, measurement_name("FORCsingle", params["Vmax"]))
    workbook_path = Path(f"{output_stem}.xlsx")
    separate_forc.save_forc_workbook(
        workbook_path,
        raw_ch1_frames,
        raw_ch2_frames,
        forc_frames,
        params=params,
        reversal_voltages=reversal_voltages,
        segarb_options=segarb_options,
    )
    polarization_path, current_path = separate_forc.save_forc_plots(
        forc_data,
        output_stem,
    )
    print(f"Saved single-execution FORC workbook: {workbook_path.resolve()}")
    return {
        "data": forc_data,
        "workbook_path": workbook_path,
        "polarization_path": polarization_path,
        "current_path": current_path,
        "completed_curves": len(forc_frames),
        "segment_count": layout["segment_count"],
        "automatic_sample_rate": layout["automatic_sample_rate"],
        "estimated_samples": layout["estimated_samples"],
    }


def main():
    with PMUSession(INST, channels=(CH1, CH2)) as session:
        run_forc_test(session.query)


if __name__ == "__main__":
    if PREVIEW_ONLY:
        preview_forc_waveforms()
    else:
        main()
