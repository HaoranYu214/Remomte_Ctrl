# -*- coding: utf-8 -*-
"""One-click FTJ characterization package.

Sequence: initial PV-and-PUND -> PV2/PUND map -> post-map PV-and-PUND ->
pre-IV PV-and-PUND -> multi-voltage segmented DC I-V -> post-IV PV-and-PUND.
Existing measurements and workflows perform each experiment; this file only
exposes parameters, applies them, orders stages, and audits outputs.
"""

from __future__ import annotations

from datetime import datetime
import importlib
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

# =============================================================================
# USER CONFIGURATION
# =============================================================================

# Safety default: preview waveforms only. Set False only for a real run.
# Preview mode never creates PMUSession or SMUSession.
# Stop the remaining package after a failed/interrupted hardware stage.

PREVIEW_ONLY = False
STOP_ON_ERROR = True
STAGE_SETTLE_TIME_S = 1.0

INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2

# Change this one path to relocate the complete package output.
BASE_SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\25-08-2026\03B4_hZO_2700_800_100\R10_1")

# Physical properties and the common baseline waveform.

# DEVICE_AREA_CM2 = (20e-4) ** 2
DEVICE_AREA_CM2 = (10*1e-4)**2*3.14
PV_PUND_VP = 4.5
PV_PUND_RISE_TIME_S = 2.5e-5
PV_PUND_DELAY_TIME_S = 2.5e-5
PV_PUND_OFFSET_V = 0.0

# Stages can be disabled or reordered by editing this list.
RUN_ORDER = [
    "initial_pv_and_pund",
    "pv2_pund_map",
    "pv_and_pund_after_map",
    "pv_and_pund_before_iv",
    "segmented_iv",
    "pv_and_pund_after_iv",
]

# Output folders are derived from BASE_SAVE_DIR; normally no edits are needed.
SAVE_DIRS = {
    "initial_pv_and_pund": BASE_SAVE_DIR / "01_initial_PV_and_PUND",
    "pv2_pund_map": BASE_SAVE_DIR / "02_PV2_PUND_map",
    "pv_and_pund_after_map": BASE_SAVE_DIR / "03_PV_and_PUND_after_Map",
    "pv_and_pund_before_iv": BASE_SAVE_DIR / "04_PV_and_PUND_before_IV",
    "segmented_iv": BASE_SAVE_DIR / "05_segmented_DC_IV",
    "pv_and_pund_after_iv": BASE_SAVE_DIR / "06_PV_and_PUND_after_IV",
}

COMMON_SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": True,
    "LOAD_RESISTANCE": 1e3,
    "ENABLE_LLEC": False,
}

# One baseline unit: PV2 followed by PUND. All four package checkpoints use it.
PV_AND_PUND_REPEAT_COUNT = 1
PV_AND_PUND_SETTLE_TIME_S = 0.5

PV2_PARAMS = {
    "rise_time": PV_PUND_RISE_TIME_S,
    "delay_time": PV_PUND_DELAY_TIME_S,
    "Vp": PV_PUND_VP,
    "offset": PV_PUND_OFFSET_V,
    "area_cm2": DEVICE_AREA_CM2,
    "Irange1": 1e-5,
    "Irange2": 1e-5,
}

PUND_PARAMS = {
    "rise_time": PV_PUND_RISE_TIME_S,
    "delay_time": PV_PUND_DELAY_TIME_S,
    "offset_ramp_time": 1e-4,
    "Vp": PV_PUND_VP,
    "offset": PV_PUND_OFFSET_V,
    "area_cm2": DEVICE_AREA_CM2,
    "Irange1": 1e-5,
    "Irange2": 1e-6,
}

# Cartesian PV2/PUND map. It starts from PV2_PARAMS/PUND_PARAMS and overrides
# Vp, rise_time (from frequency), and delay_time at every map point.
PV2_PUND_MAP = {
    "run_pv2": True,
    "run_pund_tri": True,
    "vp_values": [4, 4.5, 5],
    "frequency_values_hz": [
        # 125,
        250,
        500,
        1000,
        2000,
        5000,
        10000,
        20000,
        50000,
        # 100000,
    ],
    "delay_time_values_s": [1e-3],
    "settle_time_s": 0.5,
}

# I-V conditions. Each condition uses a symmetric path:
# 0 -> +Vmax -> 0 -> -Vmax -> 0.
# Each repeat is a separate System Mode execution/workbook and each condition
# is saved in a subfolder named by its ``name`` field.
IV_TESTS = [
    {"name": "IV1", "vmax_v": 4, "repeat_count": 1},
    {"name": "IV2", "vmax_v": 4.5, "repeat_count": 1},
    {"name": "IV3", "vmax_v": 5, "repeat_count": 3},
]

# Parameters shared by every I-V condition above.
# timeout_s=None means no total-duration deadline; SP is polled until complete.
SEGMENTED_IV = {
    "settle_time_s": 1.0,
    "segment_step": 0.1,
    "sweep_channel": 1,
    "bias_channel": 2,
    "available_channels": (1, 2, 3, 4),
    # Current wiring: SMU1/2 through RPM PMU1-1/1-2; SMU3/4 direct.
    "smu_connections": {
        1: "rpm:PMU1-1",
        2: "rpm:PMU1-2",
        3: "direct",
        4: "direct",
    },
    "params": {
        "sweep_current_compliance": 1e-4,
        "bias_voltage": 0.0,
        "bias_current_compliance": 1e-4,
        "sweep_current_range": "auto",
        "bias_current_range": "auto",
        "hold_time": 0.0,
        "sweep_delay": 0.02,
        "integration": "IT2",
        "timeout_s": None,
    },
    "names": {
        "sweep_voltage": "V1",
        "sweep_current": "I1",
        "sweep_current_density": "J1_A_per_cm2",
        "bias_voltage": "V2",
        "bias_current": "I2",
        "bias_current_density": "J2_A_per_cm2",
    },
}


# =============================================================================
# ORCHESTRATION (normally no edits are needed below this line)
# =============================================================================

def load_test_modules():
    """Import existing tests lazily; importing this package never opens VISA."""
    return {
        "pair": importlib.import_module("workflows.pv_and_pund"),
        "map": importlib.import_module("workflows.pv2_pund_map"),
        "iv": importlib.import_module("measurements.smu.iv.segmented_voltage_sweep"),
    }


def _replace_dict(target, values):
    target.clear()
    target.update(values)


PAIR_STAGE_NAMES = {
    "initial_pv_and_pund",
    "pv_and_pund_after_map",
    "pv_and_pund_before_iv",
    "pv_and_pund_after_iv",
}


def configure_map(module):
    module.INST = INST
    module.CH1, module.CH2 = CH1, CH2
    module.DEVICE_AREA_CM2 = DEVICE_AREA_CM2
    module.VP_VALUES = list(PV2_PUND_MAP["vp_values"])
    module.FREQUENCY_VALUES_HZ = list(PV2_PUND_MAP["frequency_values_hz"])
    module.DELAY_TIME_VALUES_S = list(PV2_PUND_MAP["delay_time_values_s"])
    module.RUN_PV2 = bool(PV2_PUND_MAP["run_pv2"])
    module.RUN_PUND_TRI = bool(PV2_PUND_MAP["run_pund_tri"])
    module.STOP_ON_ERROR = bool(STOP_ON_ERROR)
    module.SETTLE_TIME_S = float(PV2_PUND_MAP["settle_time_s"])
    module.SAVE_ROOT = SAVE_DIRS["pv2_pund_map"]
    module.SAVE_DIRS = {
        "PV2": module.SAVE_ROOT / "PV2",
        "PUND_tri": module.SAVE_ROOT / "PUND_tri",
    }
    _replace_dict(module.SEGARB_OPTIONS, COMMON_SEGARB_OPTIONS)

    module.PV2_BASE_PARAMS = dict(PV2_PARAMS)
    module.PUND_BASE_PARAMS = dict(PUND_PARAMS)



def iv_turning_points(vmax_v):
    """Build the package's symmetric segmented I-V path."""
    vmax_v = float(vmax_v)
    return [0.0, vmax_v, 0.0, -vmax_v, 0.0]


def configure_iv(module, iv_test):
    module.INST = INST
    module.DEVICE_AREA_CM2 = DEVICE_AREA_CM2
    module.SWEEP_CHANNEL = int(SEGMENTED_IV["sweep_channel"])
    module.BIAS_CHANNEL = int(SEGMENTED_IV["bias_channel"])
    module.AVAILABLE_CHANNELS = tuple(SEGMENTED_IV["available_channels"])
    module.SMU_CONNECTIONS = dict(SEGMENTED_IV["smu_connections"])
    module.TURNING_POINTS = iv_turning_points(iv_test["vmax_v"])
    module.SEGMENT_STEP = SEGMENTED_IV["segment_step"]
    module.PARAMS = dict(SEGMENTED_IV["params"])
    module.NAMES = dict(SEGMENTED_IV["names"])
    module.SAVE_DIR = SAVE_DIRS["segmented_iv"] / str(iv_test["name"])


def validate_package_config(modules):
    unknown = [name for name in RUN_ORDER if name not in SAVE_DIRS]
    if unknown:
        raise ValueError(f"RUN_ORDER contains unknown stages: {unknown}")
    if len(set(RUN_ORDER)) != len(RUN_ORDER):
        raise ValueError("RUN_ORDER must not contain duplicate stages.")

    if int(PV_AND_PUND_REPEAT_COUNT) <= 0:
        raise ValueError("PV_AND_PUND_REPEAT_COUNT must be positive.")
    if not IV_TESTS:
        raise ValueError("IV_TESTS must contain at least one I-V condition.")

    iv_names = [str(iv_test["name"]).strip() for iv_test in IV_TESTS]
    if any(not name for name in iv_names):
        raise ValueError("Every IV_TESTS entry must have a non-empty name.")
    if len(set(iv_names)) != len(iv_names):
        raise ValueError("IV_TESTS names must be unique.")

    iv_point_counts = {}
    for iv_test, name in zip(IV_TESTS, iv_names):
        vmax_v = float(iv_test["vmax_v"])
        if vmax_v <= 0:
            raise ValueError(f"{name}.vmax_v must be positive.")
        if int(iv_test["repeat_count"]) <= 0:
            raise ValueError(f"{name}.repeat_count must be positive.")
        sweep_values = modules["iv"].build_segmented_voltage_path(
            iv_turning_points(vmax_v), SEGMENTED_IV["segment_step"]
        )
        if len(sweep_values) > 4096:
            raise ValueError(
                f"{name} creates {len(sweep_values)} points; KXCI allows 4096."
            )
        iv_point_counts[name] = len(sweep_values)

    map_config = PV2_PUND_MAP
    if not map_config["vp_values"] or not map_config["frequency_values_hz"]:
        raise ValueError("PV/PUND voltage and frequency lists must not be empty.")
    if not map_config["delay_time_values_s"]:
        raise ValueError("PV/PUND delay list must not be empty.")
    if not map_config["run_pv2"] and not map_config["run_pund_tri"]:
        raise ValueError("PV/PUND map must enable PV2 and/or PUND_tri.")
    map_parameter_points = (
        len(map_config["vp_values"])
        * len(map_config["frequency_values_hz"])
        * len(map_config["delay_time_values_s"])
    )
    return {
        "iv_point_counts": iv_point_counts,
        "map_parameter_points": map_parameter_points,
    }


def run_pv_and_pund_stage(module, stage_name):
    save_root = SAVE_DIRS[stage_name]
    for run_index in range(1, int(PV_AND_PUND_REPEAT_COUNT) + 1):
        print(f"PV and PUND repeat {run_index}/{PV_AND_PUND_REPEAT_COUNT}")
        results = module.run_pv_and_pund(
            inst=INST,
            channels=(CH1, CH2),
            pv2_params=dict(PV2_PARAMS),
            pund_params=dict(PUND_PARAMS),
            segarb_options=dict(COMMON_SEGARB_OPTIONS),
            save_dirs={
                "PV2": save_root,
                "PUND_tri": save_root,
            },
            settle_time_s=float(PV_AND_PUND_SETTLE_TIME_S),
            stop_on_error=STOP_ON_ERROR,
        )
        for name, defaults in (("PV2", PV2_PARAMS), ("PUND_tri", PUND_PARAMS)):
            result = (results or {}).get(name)
            if result is not None:
                remember_current_ranges(
                    defaults, result.get("accepted_current_ranges", {}), __file__,
                    "PV2_PARAMS" if name == "PV2" else "PUND_PARAMS",
                )


def run_map_stage(module):
    configure_map(module)
    result = module.run_map()
    if "accepted_current_ranges" in result.columns:
        for _, row in result.iterrows():
            name = "PV2_PARAMS" if row["test"] == "PV2" else "PUND_PARAMS"
            defaults = PV2_PARAMS if row["test"] == "PV2" else PUND_PARAMS
            remember_current_ranges(defaults, row["accepted_current_ranges"], __file__, name)
    expected_runs = (
        len(PV2_PUND_MAP["vp_values"])
        * len(PV2_PUND_MAP["frequency_values_hz"])
        * len(PV2_PUND_MAP["delay_time_values_s"])
        * (
            int(PV2_PUND_MAP["run_pv2"])
            + int(PV2_PUND_MAP["run_pund_tri"])
        )
    )
    if len(result) != expected_runs:
        raise RuntimeError(
            f"PV2/PUND map is incomplete: {len(result)}/{expected_runs} runs recorded."
        )
    failed = result[result["status"] != "ok"] if not result.empty else result
    if not failed.empty:
        raise RuntimeError(f"PV2/PUND map contains {len(failed)} failed runs.")


def run_iv_stage(module):
    total_runs = sum(int(iv_test["repeat_count"]) for iv_test in IV_TESTS)
    completed_runs = 0
    for iv_test in IV_TESTS:
        configure_iv(module, iv_test)
        repeat_count = int(iv_test["repeat_count"])
        for run_index in range(1, repeat_count + 1):
            print(
                f"{iv_test['name']}: symmetric +/-{float(iv_test['vmax_v']):g} V, "
                f"repeat {run_index}/{repeat_count}"
            )
            module.main()
            completed_runs += 1
            if completed_runs < total_runs:
                time.sleep(float(SEGMENTED_IV["settle_time_s"]))


def run_package():
    """Run enabled stages and preserve a live package-level audit trail."""
    modules = load_test_modules()
    counts = validate_package_config(modules)
    enabled_map_tests = int(PV2_PUND_MAP["run_pv2"]) + int(
        PV2_PUND_MAP["run_pund_tri"]
    )
    iv_description = ", ".join(
        f"{name}={point_count} points"
        for name, point_count in counts["iv_point_counts"].items()
    )
    print(
        f"Package preflight: segmented I-V ({iv_description}); "
        f"PV/PUND map={counts['map_parameter_points'] * enabled_map_tests} runs."
    )

    summary_stem, run_time = reserve_summary_stem(BASE_SAVE_DIR, "package_summary")
    summary_path = Path(f"{summary_stem}.xlsx")
    rows = []
    for stage_number, stage_name in enumerate(RUN_ORDER, start=1):
        started = datetime.now()
        status = "ok"
        error_text = ""
        print(f"\n=== Stage {stage_number}/{len(RUN_ORDER)}: {stage_name} ===")
        try:
            if stage_name in PAIR_STAGE_NAMES:
                run_pv_and_pund_stage(modules["pair"], stage_name)
            elif stage_name == "pv2_pund_map":
                run_map_stage(modules["map"])
            elif stage_name == "segmented_iv":
                run_iv_stage(modules["iv"])
        except KeyboardInterrupt:
            status = "interrupted"
            error_text = "KeyboardInterrupt"
        except Exception:
            status = "failed"
            error_text = traceback.format_exc()
            print(error_text)
        ended = datetime.now()
        rows.append(
            {
                "time": run_time,
                "stage_number": stage_number,
                "stage": stage_name,
                "status": status,
                "start_time": started,
                "end_time": ended,
                "duration_s": (ended - started).total_seconds(),
                "error": error_text,
            }
        )
        save_summary_workbook(rows, summary_path)

        if status != "ok" and (STOP_ON_ERROR or status == "interrupted"):
            raise RuntimeError(
                f"Package stopped after {stage_name}: {status}. "
                f"See {summary_path}"
            )
        if (
            status == "ok"
            and STAGE_SETTLE_TIME_S > 0
            and stage_number < len(RUN_ORDER)
        ):
            time.sleep(float(STAGE_SETTLE_TIME_S))

    save_summary_workbook(rows, summary_path)
    print(f"FTJ package complete. Summary: {summary_path.resolve()}")
    return pd.DataFrame(rows)


def preview_package():
    """Build every package preview, then display all figures together."""
    import matplotlib.pyplot as plt

    modules = load_test_modules()
    counts = validate_package_config(modules)
    results = []

    if any(stage_name in PAIR_STAGE_NAMES for stage_name in RUN_ORDER):
        results.extend(
            modules["pair"].preview_pv_and_pund(
                inst=INST,
                channels=(CH1, CH2),
                pv2_params=dict(PV2_PARAMS),
                pund_params=dict(PUND_PARAMS),
                segarb_options=dict(COMMON_SEGARB_OPTIONS),
                show=False,
                title_prefix="Package baseline (stages 01, 03, 04, 06)",
            )
        )

    if "pv2_pund_map" in RUN_ORDER:
        configure_map(modules["map"])
        combinations = list(
            product(
                PV2_PUND_MAP["vp_values"],
                PV2_PUND_MAP["frequency_values_hz"],
                PV2_PUND_MAP["delay_time_values_s"],
            )
        )
        representatives = [combinations[0]]
        if combinations[-1] != combinations[0]:
            representatives.append(combinations[-1])
        for representative_index, (vp, frequency, delay) in enumerate(
            representatives
        ):
            map_position = (
                "first point" if representative_index == 0 else "last point"
            )
            for test_name, child, base_params, enabled in (
                (
                    "PV2",
                    modules["map"].PV2,
                    modules["map"].PV2_BASE_PARAMS,
                    PV2_PUND_MAP["run_pv2"],
                ),
                (
                    "PUND_tri",
                    modules["map"].PUND_tri,
                    modules["map"].PUND_BASE_PARAMS,
                    PV2_PUND_MAP["run_pund_tri"],
                ),
            ):
                if not enabled:
                    continue
                point_params = modules["map"].make_parameters(
                    base_params, vp, frequency, delay,
                )
                display_name = "PV2" if test_name == "PV2" else "Triangular PUND"
                results.append(
                    child.preview_waveform(
                        parameters=point_params, channels=(CH1, CH2),
                        show=False,
                        title_prefix=(
                            f"PV2/PUND Map | {map_position} | {display_name} | "
                            f"Vp={float(vp):g} V, f={float(frequency):g} Hz, "
                            f"delay={float(delay):g} s"
                        ),
                    )
                )

    if "segmented_iv" in RUN_ORDER:
        iv_figures = []
        for iv_test in IV_TESTS:
            configure_iv(modules["iv"], iv_test)
            iv_figures.append(
                modules["iv"].preview_waveform(
                    show=False,
                    title=(
                        f"{iv_test['name']} | Segmented DC I-V | "
                        f"+/-{float(iv_test['vmax_v']):g} V | "
                        f"repeat count={int(iv_test['repeat_count'])}"
                    ),
                )
            )
        results.extend(iv_figures)

    if results:
        plt.show()

    iv_description = ", ".join(
        f"{name}={point_count} points"
        for name, point_count in counts["iv_point_counts"].items()
    )
    print(
        f"Preview complete: {len(results)} labeled figures shown together, "
        f"no images saved; "
        f"segmented I-V ({iv_description})."
    )
    return results


def main():
    if PREVIEW_ONLY:
        return preview_package()
    return run_package()


if __name__ == "__main__":
    main()
