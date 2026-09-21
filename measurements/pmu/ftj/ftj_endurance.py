# -*- coding: utf-8 -*-

# 阅读入口：重复运行一个 FTJ 实验；先选 TARGET_MODULE_NAME，再设 LOOP_COUNT 和 SAVE_DIR。
# TARGET_PARAM_OVERRIDES 只覆盖指定参数，未列出的值继承目标模块 params。
# TARGET_INST/CHANNELS/CURRENT_RANGES/SEGARB_OPTIONS 为 None 时沿用目标入口对应设置。
# 流程：main → run_endurance → 逐轮调用目标 run_test → 每轮保存状态汇总。
# 这里强制实测，不受目标文件 PREVIEW_ONLY 控制；SAVE_EVERY_RUN 控制单轮数据保存。

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
    r"C:\Users\P317151\Documents\data\14-09-2026\04A1_2700_1200_300\L30_2\FTJ\endurance6V"
)
# Number of complete target runs, not individual write-pulse pairs.
LOOP_COUNT = 1000
SAVE_EVERY_RUN = True
STOP_ON_ERROR = True
FILE_STEM_PREFIX = "ftj_endurance"


# 按模块名加载 FTJ 实验入口，返回模块对象；导入本身不连接仪器。
def load_ftj_module(module_name=None):
    """Import one maintained FTJ measurement module without opening VISA."""
    module_name = TARGET_MODULE_NAME if module_name is None else module_name
    module = importlib.import_module(module_name)
    if not callable(getattr(module, "run_test", None)):
        raise TypeError(f"{module_name} does not provide run_test(...).")
    return module


# 把一轮的编号、状态、起止时间和错误信息整理成汇总记录。
def make_summary_row(run_index, status, start_time, end_time, error_text):
    return {
        "run_index": run_index,
        "status": status,
        "start_time": start_time,
        "end_time": end_time,
        "duration_s": (end_time - start_time).total_seconds(),
        "error": error_text,
    }


# 合并目标脚本默认参数与 TARGET_PARAM_OVERRIDES（或 param_overrides），循环调用实测入口。
# 每轮更新状态汇总，返回 summary_df 和 summary_path；save_every_run 控制单轮数据保存。
# 调用时明确传入 preview_only=False，因此目标脚本的预览开关不控制此处。
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


# 按本文件目标模块、参数覆盖和循环次数启动 FTJ endurance，返回汇总结果。
def main():
    return run_endurance()


if __name__ == "__main__":
    main()
