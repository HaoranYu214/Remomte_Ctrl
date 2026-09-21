# -*- coding: utf-8 -*-

# 阅读入口：FTJ 全套；在本文件改 FTJ_TESTS、RUN_ORDER、INST、通道和 BASE_SAVE_DIR。
# FTJ_TESTS 各阶段 params/current_ranges 为本套测试的配置；无需同步修改单次入口默认参数。
# 流程：main → 按 PREVIEW_ONLY 预览或实测 → 按 RUN_ORDER 执行并分别保存。
# run_package 直接实测；辅助函数 load_test_modules 只加载模块。

"""One-file workflow for the standard FTJ characterization package.

Sequence: RV2 -> PWM -> Identical V1 -> MRD. The maintained measurement
modules own waveform construction and data saving; this file exposes the full
configuration, applies it, and controls execution order and preview behavior.
"""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import time
import traceback


REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))



# =============================================================================
# USER CONFIGURATION
# =============================================================================

PREVIEW_ONLY = False
STOP_ON_ERROR = True
STAGE_SETTLE_TIME_S = 0.0

BASE_SAVE_DIR = Path(
    r"C:\Users\P317151\Documents\data\06-07-2026\03C6\L40um6\FTJ_package1"
)

INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2

COMMON_SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": False,
    "LOAD_RESISTANCE": 1e6,
    # LLEC is unavailable in Segment Arb mode.
    "ENABLE_LLEC": False,
}

# Disable or reorder stages by editing this list.
RUN_ORDER = ["rv2", "pwm", "identical", "mrd"]

# Every ``params`` dictionary is complete. This prevents a workflow stage from
# silently inheriting voltage or timing values left by an earlier invocation.
FTJ_TESTS = {
    "rv2": {
        "display_name": "RV2",
        "module": "measurements.pmu.ftj.ftj_RV2",
        "save_dir": BASE_SAVE_DIR / "RV2",
        "current_ranges": {CH1: 1e-5, CH2: 1e-5},
        "params": {
            "base_v": 0.0,
            "offset_v": -2,
            "vp": 4,
            "write_level_step": 0.2,
            "read_v": -1,
            "scan_cycles": 1,
            "prepost_dwell": 5e-5,
            "write_dwell": 5e-5,
            "read_dwell": 5e-5,
            "prepost_rise": 1e-5,
            "prepost_fall": 1e-5,
            "prepost_idle": 0.5,
            "write_rise": 1e-5,
            "write_fall": 1e-5,
            "write_idle": 0.5,
            "read_rise": 1e-5,
            "read_fall": 1e-5,
            "read_idle": 1e-3,
        },
    },
    "pwm": {
        "display_name": "PWM",
        "module": "measurements.pmu.ftj.ftj_PWM",
        "save_dir": BASE_SAVE_DIR / "PWM",
        "current_ranges": {CH1: 1e-4, CH2: 1e-4},
        "params": {
            "base_v": 0.0,
            "write_positive_v": 6,
            "write_negative_v": -6,
            "read_v": -2,
            "write_base_dwell": 1e-6,
            "width_multipliers": [
                1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000
            ],
            "repeat_count": 1,
            "read_dwell": 5e-5,
            "write_positive_trf": 1e-6,
            "write_negative_trf": 1e-6,
            "read_trf": 1e-5,
            "write_positive_idle": 0.5,
            "write_negative_idle": 0.5,
            "read_idle": 1e-3,
        },
    },
    "identical": {
        "display_name": "Identical V1",
        "module": "measurements.pmu.ftj.ftj_Identical_V1",
        "save_dir": BASE_SAVE_DIR / "Identical",
        "current_ranges": {CH1: 1e-5, CH2: 1e-5},
        "params": {
            "base_v": 0.0,
            "write_positive_v": 0.7,
            "write_negative_v": -5,
            "read_v": -1.2,
            "write_positive_dwell": 5e-5,
            "write_negative_dwell": 5e-5,
            "read_dwell": 5e-5,
            "write_positive_trf": 1e-6,
            "write_negative_trf": 1e-6,
            "read_trf": 1e-6,
            "write_positive_idle": 0.5,
            "write_negative_idle": 0.5,
            "read_idle": 0.5,
            "positive_repeat_count": 50,
            "negative_repeat_count": 50,
            "sequence_cycle_count": 2,
        },
    },
    "mrd": {
        "display_name": "MRD",
        "module": "measurements.pmu.ftj.ftj_MRD",
        "save_dir": BASE_SAVE_DIR / "MRD",
        "current_ranges": {CH1: 1e-3, CH2: 1e-3},
        "params": {
            "base_v": 0.0,
            "reference_v": -6.5,
            "write_voltages": [
                0.1, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 6, 7
            ],
            "read_v": -2,
            "cycles_per_level": 1,
            "reference_rise": 1e-6,
            "reference_dwell": 5e-3,
            "reference_fall": 1e-6,
            "reference_idle": 0.5,
            "write_rise": 1e-6,
            "write_dwell": 5e-5,
            "write_fall": 1e-6,
            "write_idle": 0.1,
            "read_rise": 1e-6,
            "read_dwell": 5e-5,
            "read_fall": 1e-6,
            "read_idle": 0.1,
        },
    },
}


# =============================================================================
# ORCHESTRATION (normally no edits are needed below this line)
# =============================================================================

# 加载工作流依赖的实验模块并返回名称到模块的字典；不连接仪器。
def load_test_modules():
    """Import the maintained FTJ measurements without opening VISA."""
    return {
        test_name: importlib.import_module(config["module"])
        for test_name, config in FTJ_TESTS.items()
    }


# 检查 RUN_ORDER 的阶段名存在且不重复；不连接仪器。
def validate_package_config():
    unknown = [test_name for test_name in RUN_ORDER if test_name not in FTJ_TESTS]
    if unknown:
        raise ValueError(f"RUN_ORDER contains unknown FTJ stages: {unknown}")
    if len(set(RUN_ORDER)) != len(RUN_ORDER):
        raise ValueError("RUN_ORDER must not contain duplicate FTJ stages.")


# 按 RUN_ORDER 实测 FTJ_TESTS 中的各阶段并保存，返回按阶段名组织的结果字典。
# 本函数强制子入口实测；预览由 main 的 PREVIEW_ONLY 分支调用 preview_package。
def run_package(*, modules=None):
    """Run all enabled FTJ stages in order."""
    validate_package_config()
    modules = load_test_modules() if modules is None else modules
    results = {}

    for stage_number, test_name in enumerate(RUN_ORDER, start=1):
        module = modules[test_name]
        config = FTJ_TESTS[test_name]
        display_name = config["display_name"]
        print(f"\n=== FTJ stage {stage_number}/{len(RUN_ORDER)}: {display_name} ===")
        try:
            results[test_name] = module.run_test(
                params_override=config["params"], inst=INST, channels=(CH1, CH2),
                current_ranges=config["current_ranges"], segarb_options=COMMON_SEGARB_OPTIONS,
                save_dir=config["save_dir"], save_results=True, preview_only=False,
            )
        except KeyboardInterrupt:
            raise
        except Exception:
            print(traceback.format_exc())
            if STOP_ON_ERROR:
                raise
            results[test_name] = None

        if STAGE_SETTLE_TIME_S > 0 and stage_number < len(RUN_ORDER):
            time.sleep(float(STAGE_SETTLE_TIME_S))

    print("FTJ package1 complete.")
    return results


# 按工作流配置生成各阶段的预览并统一显示，返回预览结果；不连接仪器。
def preview_package(*, modules=None, show=True):
    """Build labeled previews for every stage and display them together."""
    import matplotlib.pyplot as plt

    validate_package_config()
    modules = load_test_modules() if modules is None else modules
    figures = []
    for test_name in RUN_ORDER:
        module = modules[test_name]
        config = FTJ_TESTS[test_name]
        figures.append(
            module.preview_waveform(
                parameters={**module.params, **config["params"]}, channels=(CH1, CH2),
                show=False,
                title_prefix=f"FTJ package1 | {config['display_name']}",
            )
        )
    if figures and show:
        plt.show()
    return figures


# 根据 PREVIEW_ONLY 选择整套 FTJ 的离线预览或实测，返回对应结果。
def main():
    if PREVIEW_ONLY:
        return preview_package()
    return run_package()


if __name__ == "__main__":
    main()
