# -*- coding: utf-8 -*-
"""Map PV2 and triangular-PUND responses over voltage, frequency, and delay."""

from __future__ import annotations

from datetime import datetime
from itertools import product
from pathlib import Path
import sys
import time
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

from keithley4200.parameter_defaults import remember_current_ranges
from keithley4200.output import reserve_summary_stem, save_summary_workbook
from measurements.pmu.fe_cap import PUND_tri, PV2

# =============================================================================
# USER CONFIGURATION
# =============================================================================

INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2

RUN_PV2 = True
RUN_PUND_TRI = True
STOP_ON_ERROR = False
SETTLE_TIME_S = 0.5

SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": True,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}

SAVE_ROOT = Path(r"C:\Users\P317151\Documents\data\10-09-2026\04A1_2700_1200_300\L20_2\Delay_map")
SAVE_DIRS = {
    "PV2": SAVE_ROOT / "PV2",
    "PUND_tri": SAVE_ROOT / "PUND_tri",
}
# One physical device is used for every point and both test types.
DEVICE_AREA_CM2 = (20e-4) ** 2
# DEVICE_AREA_CM2 = (10*1e-4)**2*3.14

# Complete non-map parameters. Every map point starts from a fresh copy of
# these dictionaries; only Vp, rise_time, and delay_time are then overridden.
PV2_BASE_PARAMS = {
    "rise_time": 2.5e-5,
    "delay_time": 1e-3,
    "Vp": 4.5,
    "offset": 0,
    "area_cm2": DEVICE_AREA_CM2,
    "Irange1": 1e-4,
    "Irange2": 1e-4,
}
PUND_BASE_PARAMS = {
    "rise_time": 2.5e-5,
    "delay_time": 1e-3,
    "offset_ramp_time": 1e-4,
    "Vp": 4.5,
    "offset": 0,
    "area_cm2": DEVICE_AREA_CM2,
    "Irange1": 1e-5,
    "Irange2": 1e-6,
}

# Cartesian map axes.
VP_VALUES = [4.0]
# VP_VALUES = [2, 2.5, 3, 3.5, 4.0]
FREQUENCY_VALUES_HZ = [10000]
# FREQUENCY_VALUES_HZ = [500, 1000, 5000, 10000]
# Use a short nonzero segment for the practical "no delay" case.
DELAY_TIME_VALUES_S = [0.9, 1e-1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6]




def frequency_to_rise_time(frequency_hz):
    """Convert full 0,+V,-V,0 triangle frequency to one ramp duration."""
    if frequency_hz <= 0:
        raise ValueError("Frequency must be positive.")
    return 1.0 / (4.0 * frequency_hz)


def make_parameters(base_params, vp, frequency_hz, delay_time_s):
    """Build the complete parameter dictionary for one map point."""
    effective_params = dict(base_params)
    effective_params.update(Vp=float(vp),
                            rise_time=frequency_to_rise_time(frequency_hz),
                            delay_time=float(delay_time_s))
    return effective_params


def run_one_test(
    module,
    test_name,
    base_params,
    save_dir,
    vp,
    frequency_hz,
    delay_time_s,
    run_index,
    total_runs,
):
    """Configure and run one test, returning one summary row."""
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    effective_params = make_parameters(base_params, vp, frequency_hz, delay_time_s)
    options = {**module.SEGARB_OPTIONS, **SEGARB_OPTIONS}
    accepted_ranges = {}

    start_time = datetime.now()
    print(
        f"[{run_index}/{total_runs}] {test_name}: "
        f"Vp={vp:g} V, f={frequency_hz:g} Hz, "
        f"delay={delay_time_s:g} s, "
        f"rise={effective_params['rise_time']:.3e} s"
    )

    status = "ok"
    error_text = ""
    try:
        result = module.run_test(
            params_override=effective_params, inst=INST, channels=(CH1, CH2),
            segarb_options=options, save_dir=save_dir, preview_only=False,
        )
        effective_params = result["params"]
        accepted_ranges = result["accepted_current_ranges"]
    except KeyboardInterrupt:
        raise
    except Exception:
        status = "failed"
        error_text = traceback.format_exc()
        print(error_text)

    remember_current_ranges(
        base_params, accepted_ranges, __file__,
        "PV2_BASE_PARAMS" if test_name == "PV2" else "PUND_BASE_PARAMS",
    )
    end_time = datetime.now()
    return {
        "accepted_current_ranges": dict(accepted_ranges),
        "run_index": run_index,
        "test": test_name,
        "status": status,
        "Vp_V": vp,
        "frequency_Hz": frequency_hz,
        "rise_time_s": effective_params["rise_time"],
        "delay_time_s": delay_time_s,
        "offset_V": effective_params["offset"],
        "offset_ramp_time_s": effective_params.get("offset_ramp_time"),
        "area_cm2": effective_params["area_cm2"],
        "Irange1_A": effective_params["Irange1"],
        "Irange2_A": effective_params["Irange2"],
        "load_config_enabled": options["ENABLE_LOAD_CONFIG"],
        "load_resistance_ohm": options["LOAD_RESISTANCE"],
        "connection_comp_enabled": options["ENABLE_CONNECTION_COMP"],
        "llec_enabled": options["ENABLE_LLEC"],
        "start_time": start_time,
        "end_time": end_time,
        "duration_s": (end_time - start_time).total_seconds(),
        "error": error_text,
    }


def run_map():
    """Run the configured Cartesian map and update one summary workbook."""
    SAVE_ROOT.mkdir(parents=True, exist_ok=True)
    tests = []
    if RUN_PV2:
        tests.append(("PV2", PV2, PV2_BASE_PARAMS, SAVE_DIRS["PV2"]))
    if RUN_PUND_TRI:
        tests.append(
            ("PUND_tri", PUND_tri, PUND_BASE_PARAMS, SAVE_DIRS["PUND_tri"])
        )
    if not tests:
        raise ValueError("At least one of RUN_PV2 or RUN_PUND_TRI must be True.")

    sweep_points = list(
        product(VP_VALUES, FREQUENCY_VALUES_HZ, DELAY_TIME_VALUES_S)
    )
    total_runs = len(sweep_points) * len(tests)
    summary_stem, run_time = reserve_summary_stem(SAVE_ROOT, "map_summary")
    summary_path = Path(f"{summary_stem}.xlsx")
    rows = []
    interrupted = False
    run_index = 0

    try:
        for vp, frequency_hz, delay_time_s in sweep_points:
            for test_name, module, base_params, save_dir in tests:
                run_index += 1
                row = run_one_test(
                    module,
                    test_name,
                    base_params,
                    save_dir,
                    vp,
                    frequency_hz,
                    delay_time_s,
                    run_index,
                    total_runs,
                )
                row["time"] = run_time
                rows.append(row)
                save_summary_workbook(rows, summary_path)
                if row["status"] != "ok" and STOP_ON_ERROR:
                    raise RuntimeError(
                        f"{test_name} failed at Vp={vp:g} V, "
                        f"f={frequency_hz:g} Hz, delay={delay_time_s:g} s."
                    )
                if SETTLE_TIME_S > 0:
                    time.sleep(SETTLE_TIME_S)
    except KeyboardInterrupt:
        interrupted = True
        print(f"Sweep interrupted after {run_index}/{total_runs} runs.")
    finally:
        if rows:
            save_summary_workbook(rows, summary_path)
            print(f"Saved map summary to {summary_path}")

    success_count = sum(row["status"] == "ok" for row in rows)
    status = "interrupted" if interrupted else "complete"
    print(f"Map {status}: {success_count}/{len(rows)} runs successful.")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    run_map()
