# -*- coding: utf-8 -*-
"""Repeat complete segmented SMU I-V sweeps, saving each completed run."""

from datetime import datetime
from pathlib import Path
import math
import sys
import time

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents
                 if (parent / "pyproject.toml").is_file())
for path in (REPO_ROOT / "src", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from measurements.smu.iv import segmented_voltage_sweep as segmented
from keithley4200.output import reserve_summary_stem, save_summary_workbook
from keithley4200.smu.system_mode import build_segmented_voltage_path

# One run is the entire TURNING_POINTS path, not one voltage segment.
LOOP_COUNT = 20
PREVIEW_ONLY = False
INTER_RUN_DELAY_S = 0.0
SAVE_DIR = segmented.SAVE_DIR
FILE_STEM = "IVendurance"

# Start from the standalone test settings; edit this file independently.
INST = segmented.INST
SWEEP_CHANNEL = segmented.SWEEP_CHANNEL
BIAS_CHANNEL = segmented.BIAS_CHANNEL
AVAILABLE_CHANNELS = tuple(segmented.AVAILABLE_CHANNELS)
SMU_CONNECTIONS = dict(segmented.SMU_CONNECTIONS)
DEVICE_AREA_CM2 = segmented.DEVICE_AREA_CM2
TURNING_POINTS = list(segmented.TURNING_POINTS)
SEGMENT_STEP = segmented.SEGMENT_STEP
PARAMS = dict(segmented.PARAMS)
NAMES = dict(segmented.NAMES)
# Example overrides:
# TURNING_POINTS = [0.0, 4.0, 0.0, -4.0, 0.0]
# PARAMS["sweep_current_compliance"] = 1e-4
# PARAMS["sweep_delay"] = 0.02
# Hardware limits and compliance/range meanings are documented in src/keithley4200/smu.


def run_endurance(params_override=None, *, loop_count=None, turning_points=None,
                  segment_step=None, save_dir=None, preview_only=None,
                  inter_run_delay_s=None, inst=None, device_area_cm2=None,
                  sweep_channel=None, bias_channel=None, available_channels=None,
                  smu_connections=None, names=None):
    """Repeat independent acquisitions; stop and checkpoint on failure/interruption.

    Each iteration uses the segmented entry's shutdown and save behavior.
    Host transfer, saving, and reconnection add gaps between sweeps; the optional
    inter_run_delay_s is an additional sleep, not a precise total gap.
    """
    count = LOOP_COUNT if loop_count is None else loop_count
    if isinstance(count, bool) or int(count) != count or count < 1:
        raise ValueError("loop_count must be a positive integer.")
    count = int(count)
    delay = INTER_RUN_DELAY_S if inter_run_delay_s is None else float(inter_run_delay_s)
    if not math.isfinite(delay) or delay < 0:
        raise ValueError("inter_run_delay_s must be finite and nonnegative.")
    points = list(TURNING_POINTS if turning_points is None else turning_points)
    step = SEGMENT_STEP if segment_step is None else segment_step
    values = build_segmented_voltage_path(points, step)
    if len(values) > 4096:
        raise ValueError("Each segmented IV run is limited to 4096 points.")
    parameters = dict(PARAMS)
    if params_override is not None:
        unknown = set(params_override) - set(parameters)
        if unknown:
            raise ValueError(f"Unknown segmented IV parameters: {sorted(unknown)}")
        parameters.update(params_override)
    preview = PREVIEW_ONLY if preview_only is None else preview_only
    if preview:
        figure = segmented.preview_waveform(turning_points=points, segment_step=step,
                                             title=f"IV endurance: {count} repeats, {len(values)} points/run")
        return {"preview": figure, "loop_count": count, "summary_path": None}

    directory = Path(SAVE_DIR if save_dir is None else save_dir)
    summary_stem, run_time = reserve_summary_stem(directory, "iv_endurance_summary")
    summary_path = Path(f"{summary_stem}.xlsx")
    settings = dict(
        turning_points=points, segment_step=step, save_dir=directory,
        inst=INST if inst is None else inst,
        device_area_cm2=DEVICE_AREA_CM2 if device_area_cm2 is None else device_area_cm2,
        sweep_channel=SWEEP_CHANNEL if sweep_channel is None else sweep_channel,
        bias_channel=BIAS_CHANNEL if bias_channel is None else bias_channel,
        available_channels=AVAILABLE_CHANNELS if available_channels is None else available_channels,
        smu_connections=dict(SMU_CONNECTIONS if smu_connections is None else smu_connections),
        names=dict(NAMES if names is None else names),
    )
    rows = []
    output_paths = []
    digits = len(str(count))
    for index in range(1, count + 1):
        started = datetime.now()
        row = dict(time=run_time, run_index=index, requested_runs=count,
                   point_count=len(values), start_time=started, status="running", error="")
        rows.append(row)
        print(f"Segmented IV endurance: run {index}/{count}")
        try:
            result = segmented.run_test(
                params_override=parameters,
                file_stem=f"{FILE_STEM}_run{index:0{digits}d}", **settings)
            output_paths.append(result["output_path"])
            row["status"] = "ok"
        except BaseException as exc:
            row.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                       error=str(exc) or type(exc).__name__)
            raise
        finally:
            ended = datetime.now()
            row.update(end_time=ended, duration_s=(ended - started).total_seconds())
            save_summary_workbook(rows, summary_path)
        if index < count and delay:
            time.sleep(delay)
    print(f"Saved IV endurance summary: {summary_path}")
    return {"summary": rows, "summary_path": summary_path, "output_paths": output_paths}


def main():
    return run_endurance()


if __name__ == "__main__":
    main()
