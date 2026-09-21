# -*- coding: utf-8 -*-

# 阅读入口：先 PV2 后三角 PUND；先改本文件 PV2_PARAMS、PUND_PARAMS、INST 和 BASE_SAVE_DIR。
# 本文件参数覆盖单次测量默认值；VP_BOTH/RISE_TIME/OFFSET_BOTH 等用于构造这两组配置。
# 流程：main → 按 PREVIEW_ONLY 预览或实测 → 顺序调用两次 run_test 并分别保存。
# 直接调用 run_pv_and_pund 会实测；preview_pv_and_pund 用于离线预览。

"""One-click baseline workflow: run one PV2, then one triangular PUND."""

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

from keithley4200.parameter_defaults import remember_current_ranges



# =============================================================================
# USER CONFIGURATION
# =============================================================================

PREVIEW_ONLY = False
STOP_ON_ERROR = True
SETTLE_TIME_S = 0.5

# Change this one path to relocate all PV2 and PUND outputs.
BASE_SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\14-09-2026\04A1_2700_1200_300\L20_2\PV4_afterIVendurance")
SAVE_DIRS = {
    "PV2": BASE_SAVE_DIR,
    "PUND_tri": BASE_SAVE_DIR,
}

INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2
DEVICE_AREA_CM2 = (20e-4) ** 2
# DEVICE_AREA_CM2 = (10*1e-4)**2*3.14
VP_BOTH = -4
RISE_TIME = 2.5e-4
OFFSET_BOTH = 0


# These dictionaries override the measurement files' default params.  Therefore Vp/rise_time/delay_time/offset also control the PV2
# conditioning triangle and every PUND preset/P/U/N/D pulse; no waveform part
# falls back to a hidden value from the original entry files.
PV2_PARAMS = {
    "rise_time": RISE_TIME,
    "delay_time": 1e-3,
    "Vp": VP_BOTH,
    "offset": OFFSET_BOTH,
    "area_cm2": DEVICE_AREA_CM2,
    "Irange1": 1e-05,
    "Irange2": 1e-06,
}

PUND_PARAMS = {
    "rise_time": RISE_TIME,
    "delay_time": 1e-3,
    "offset_ramp_time": 1e-4,
    "Vp": VP_BOTH,
    "offset": OFFSET_BOTH,
    "area_cm2": DEVICE_AREA_CM2,
    "Irange1": 1e-05,
    "Irange2": 1e-06,
}

SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": True,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}

# =============================================================================
# WORKFLOW
# =============================================================================

# 加载 PV2 和三角 PUND 模块并返回字典；导入本身不打开仪器连接。
def load_measurements():
    """Load the maintained PV2 and PUND measurement modules without VISA I/O."""
    return {
        "PV2": importlib.import_module("measurements.pmu.fe_cap.PV2"),
        "PUND_tri": importlib.import_module("measurements.pmu.fe_cap.PUND_tri"),
    }


# 按传入参数或本文件配置先测 PV2、再测三角 PUND，分别保存结果并返回结果字典。
# 此函数执行实测；离线预览应调用 preview_pv_and_pund，或由 main 按 PREVIEW_ONLY 分流。
def run_pv_and_pund(
    *,
    inst=INST,
    channels=(CH1, CH2),
    pv2_params=None,
    pund_params=None,
    segarb_options=None,
    save_dirs=None,
    settle_time_s=SETTLE_TIME_S,
    stop_on_error=STOP_ON_ERROR,
    modules=None,
):
    """Run PV2 followed by PUND_tri."""
    modules = load_measurements() if modules is None else modules
    pv2_params = dict(PV2_PARAMS if pv2_params is None else pv2_params)
    pund_params = dict(PUND_PARAMS if pund_params is None else pund_params)
    segarb_options = dict(
        SEGARB_OPTIONS if segarb_options is None else segarb_options
    )
    save_dirs = dict(SAVE_DIRS if save_dirs is None else save_dirs)

    results = {}
    steps = (
        ("PV2", modules["PV2"], pv2_params),
        ("PUND_tri", modules["PUND_tri"], pund_params),
    )
    for step_number, (name, module, params) in enumerate(steps, start=1):
        save_dir = Path(save_dirs[name])
        save_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== PV and PUND {step_number}/2: {name} ===")
        try:
            results[name] = module.run_test(
                params_override=params, inst=inst, channels=channels,
                segarb_options=segarb_options, save_dir=save_dir, preview_only=False,
            )
        except KeyboardInterrupt:
            raise
        except Exception:
            if stop_on_error:
                raise
            print(traceback.format_exc())
        finally:
            # Reuse accepted ranges for subsequent calls in this Python process.
            accepted = results.get(name, {}).get("accepted_current_ranges", {})
            params.update(accepted)
            defaults = PV2_PARAMS if name == "PV2" else PUND_PARAMS
            remember_current_ranges(
                defaults, accepted, __file__, "PV2_PARAMS" if name == "PV2" else "PUND_PARAMS",
            )
        if step_number == 1 and settle_time_s > 0:
            time.sleep(float(settle_time_s))

    print("PV and PUND complete.")
    return results


# 按工作流参数离线生成 PV2 和三角 PUND 预览，返回预览结果；不保存图片。
def preview_pv_and_pund(
    *,
    inst=INST,
    channels=(CH1, CH2),
    pv2_params=None,
    pund_params=None,
    segarb_options=None,
    modules=None,
    show=True,
    title_prefix=None,
):
    """Show the existing PV2 and PUND previews without saving image files."""
    import matplotlib.pyplot as plt

    modules = load_measurements() if modules is None else modules
    pv2_params = dict(PV2_PARAMS if pv2_params is None else pv2_params)
    pund_params = dict(PUND_PARAMS if pund_params is None else pund_params)
    segarb_options = dict(
        SEGARB_OPTIONS if segarb_options is None else segarb_options
    )
    results = []
    for name, module, params in (
        ("PV2", modules["PV2"], pv2_params),
        ("PUND_tri", modules["PUND_tri"], pund_params),
    ):
        preview_title = (
            None if title_prefix is None else f"{title_prefix} | {name}"
        )
        results.append(
            module.preview_waveform(
                parameters={**module.params, **params}, channels=channels,
                show=False,
                title_prefix=preview_title,
            )
        )
    if show:
        plt.show()
    return results


# 根据 PREVIEW_ONLY 选择 PV2/PUND 的离线预览或顺序实测，返回对应结果。
def main():
    if PREVIEW_ONLY:
        return preview_pv_and_pund()
    return run_pv_and_pund()


if __name__ == "__main__":
    main()
