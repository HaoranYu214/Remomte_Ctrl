# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: repeat one FTJ test; choose TARGET_MODULE_NAME, then set LOOP_COUNT and SAVE_DIR.
# TARGET_PARAM_OVERRIDES replaces only specified parameters; others come from the target module's params.
# None for TARGET_INST/CHANNELS/CURRENT_RANGES/SEGARB_OPTIONS retains the corresponding target setting.
# Flow: main -> run_endurance -> target run_test each cycle -> checkpoint status after each run.
# This entry forces acquisition regardless of the target PREVIEW_ONLY; SAVE_EVERY_RUN controls per-run data files.

"""External-loop endurance runner for any maintained FTJ measurement.

The target measurement owns its waveform. This runner configures that module,
runs it repeatedly, and saves a live summary after every attempt. Keeping each
iteration as a separate target run avoids building an unbounded Segment Arb
sequence while still allowing long endurance experiments.
"""

from __future__ import annotations

from datetime import datetime
import importlib
from pathlib import Path
import sys
import traceback

import pandas as pd

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from keithley4200.output import prepare_output_dir, reserve_summary_stem, save_summary_workbook

# =============================================================================
# USER CONFIGURATION
# =============================================================================

# Select ONE target by uncommenting its assignment. Each outer run executes
# the target's complete plan, including its own repeat counts.
# TARGET_MODULE_NAME = "measurements.pmu.ftj.ftj_RV2"
TARGET_MODULE_NAME = "measurements.pmu.ftj.ftj_Identical_V1"
# TARGET_MODULE_NAME = "measurements.pmu.ftj.ftj_Identical_V2"

# Empty means use the selected test file's params. Only use keys belonging
# to that target; changing targets does not translate parameter names.
# Identical V1: sequence_cycle_count repeats the packed SARB plan.
# Identical V2: plan_repeat_count repeats separate executions and Python waits.
# Both accept write_positive_v, write_negative_v, read_v,
# positive_repeat_count, and negative_repeat_count.
TARGET_PARAM_OVERRIDES = {}

# Leave these as None to retain the target module's own settings.
TARGET_INST = None
TARGET_CHANNELS = None
TARGET_CURRENT_RANGES = None
TARGET_SEGARB_OPTIONS = None

SAVE_DIR = Path(
    "data/pmu/ftj/ftj_endurance"
)
# Number of complete target runs, not individual write-pulse pairs.
LOOP_COUNT = 1000
SAVE_EVERY_RUN = True
STOP_ON_ERROR = True
FILE_STEM_PREFIX = "ftj_endurance"


# Load and return the FTJ experiment module without connecting to hardware.
def load_ftj_module(module_name=None):
    """Import one maintained FTJ measurement module without opening VISA."""
    module_name = TARGET_MODULE_NAME if module_name is None else module_name
    module = importlib.import_module(module_name)
    if not callable(getattr(module, "run_test", None)):
        raise TypeError(f"{module_name} does not provide run_test(...).")
    return module


# Build a summary record with run index, status, start/end times and error details.
def make_summary_row(run_index, status, start_time, end_time, error_text):
    return {
        "run_index": run_index,
        "status": status,
        "start_time": start_time,
        "end_time": end_time,
        "duration_s": (end_time - start_time).total_seconds(),
        "error": error_text,
    }


# Merge target defaults with TARGET_PARAM_OVERRIDES (or param_overrides), then call acquisition repeatedly.
# Update the status summary each run; return summary_df/summary_path; save_every_run controls per-run data files.
# Explicit preview_only=False bypasses the target script's preview switch.
def run_endurance(
    *,
    module_name=None,
    param_overrides=None,
    inst=None,
    channels=None,
    current_ranges=None,
    segarb_options=None,
    save_dir=None,
    loop_count=None,
    save_every_run=None,
    stop_on_error=None,
    file_stem_prefix=None,
    module=None,
):
    """Configure one FTJ test once, then execute it in an external loop."""
    module_name = TARGET_MODULE_NAME if module_name is None else module_name
    inst = TARGET_INST if inst is None else inst
    channels = TARGET_CHANNELS if channels is None else channels
    current_ranges = (
        TARGET_CURRENT_RANGES if current_ranges is None else current_ranges
    )
    segarb_options = (
        TARGET_SEGARB_OPTIONS if segarb_options is None else segarb_options
    )
    save_dir = SAVE_DIR if save_dir is None else save_dir
    loop_count = LOOP_COUNT if loop_count is None else loop_count
    save_every_run = SAVE_EVERY_RUN if save_every_run is None else save_every_run
    stop_on_error = STOP_ON_ERROR if stop_on_error is None else stop_on_error
    file_stem_prefix = (
        FILE_STEM_PREFIX if file_stem_prefix is None else file_stem_prefix
    )
    module = load_ftj_module(module_name) if module is None else module
    save_dir = prepare_output_dir(save_dir)
    summary_stem, run_time = reserve_summary_stem(save_dir, "endurance_summary")
    summary_path = Path(f"{summary_stem}.xlsx")
    configured_params = dict(module.params)
    configured_params.update(TARGET_PARAM_OVERRIDES if param_overrides is None else param_overrides)

    summary_rows = []
    for run_index in range(1, int(loop_count) + 1):
        start_time = datetime.now()
        print(
            f"FTJ endurance run {run_index}/{loop_count} started at "
            f"{start_time:%Y-%m-%d %H:%M:%S}"
        )
        error_text = ""
        status = "ok"
        try:
            module.run_test(
                params_override=configured_params, inst=inst, channels=channels,
                current_ranges=current_ranges, segarb_options=segarb_options,
                preview_only=False,
                save_results=bool(save_every_run),
                save_dir=save_dir,
                file_stem=file_stem_prefix,
            )
        except KeyboardInterrupt:
            end_time = datetime.now()
            summary_rows.append(
                make_summary_row(
                    run_index,
                    "interrupted",
                    start_time,
                    end_time,
                    "KeyboardInterrupt",
                )
            )
            save_summary_workbook(pd.DataFrame(summary_rows).assign(time=run_time), summary_path)
            raise
        except Exception:
            status = "failed"
            error_text = traceback.format_exc()
            print(error_text)

        end_time = datetime.now()
        summary_rows.append(
            make_summary_row(
                run_index, status, start_time, end_time, error_text
            )
        )
        save_summary_workbook(pd.DataFrame(summary_rows).assign(time=run_time), summary_path)
        print(
            f"FTJ endurance run {run_index}/{loop_count} finished "
            f"with status={status}"
        )
        if status != "ok" and stop_on_error:
            break

    summary_df = pd.DataFrame(summary_rows).assign(time=run_time)
    save_summary_workbook(summary_df, summary_path)
    print(f"Saved FTJ endurance summary to {summary_path}")
    return {
        "summary_df": summary_df,
        "summary_path": summary_path,
    }


# Start FTJ endurance with the local target, overrides and repeat count; return the summary.
def main():
    return run_endurance()


if __name__ == "__main__":
    main()
