# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: NLS parameter sweep; edit BASE_PARAMS, Dwell_list, Vsquare_list, INST, channels and SAVE_DIR.
# Copy BASE_PARAMS and override Dwell/Vsquare per point; do not inherit the single-run PARAMS as sweep defaults.
# Flow: run_sweep iterates combinations -> run_nls_switch_test acquires/saves -> summary workbook.
# PREVIEW_ONLY=True at the file entry point previews only the first combination; run_sweep directly acquires data.

"""Batch parameter sweep for the NLS switch test."""

from pathlib import Path
import sys
import time

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

from measurements.pmu.programmed.NLS_1C_switch import (
    preview_nls_waveform,
    run_nls_switch_test,
)
from keithley4200.output import prepare_output_dir, reserve_summary_stem
from keithley4200.output import set_workbook_author
from keithley4200.pmu.session import PMUSession
from keithley4200.pmu.timing import nls_padding_time

INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": True,
    "LOAD_RESISTANCE": 1e3,
    "ENABLE_LLEC": False,
}
PREVIEW_ONLY = False

BASE_PARAMS = dict(
    offset=0,
    Vp=5,
    Rt_p=2.5e-4,
    Delaytime=5e-4,
    Rt_s=1e-7,
    TotalDelay=0.11,
    Dwell=1e-6,
    Irange1=1e-5,
    Irange2=1e-5,
    MeasureSquare=False,
    area_cm2=(20*1e-4)**2*3.14,
)

SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\19-08-2026\Johanna\NLS_Sweep")
Dwell_list = np.logspace(-7, -1, 31)
Vsquare_list = np.arange(0, 2.0, 0.1)


# Preview only the first NLS parameter combination without hardware access; it does not represent all sweep points.
def preview_sweep_waveform(output_path=None):
    """Preview the first configured sweep point without connecting to the PMU."""
    preview_params = BASE_PARAMS.copy()
    preview_params["Dwell"] = float(Dwell_list[0])
    preview_params["Vsquare"] = float(Vsquare_list[0])
    return preview_nls_waveform(
        preview_params,
        output_path,
        ch1=CH1,
        ch2=CH2,
    )


# Iterate Dwell_list x Vsquare_list, acquire each PMU point and save results and summaries.
# Return a list of point results; the file entry point handles the PREVIEW_ONLY branch.
def run_sweep():
    """Run a Dwell x Vsquare sweep and save a summary workbook."""
    for dwell in Dwell_list:
        nls_padding_time({**BASE_PARAMS, "Dwell": float(dwell)})
    output_dir = prepare_output_dir(SAVE_DIR)
    summary_stem, run_time = reserve_summary_stem(output_dir, "NLS_summary")
    results = []
    summary_data = []
    total_tests = len(Dwell_list) * len(Vsquare_list)
    test_idx = 0
    interrupted = False

    with PMUSession(INST, channels=(CH1, CH2)) as session:
        query = session.query
        try:
            for dwell in Dwell_list:
                for vsquare in Vsquare_list:
                    test_idx += 1
                    print(f"[{test_idx}/{total_tests}] Dwell={dwell:.1e}s, Vsquare={vsquare:.2f}V")
                    params = BASE_PARAMS.copy()
                    params["Vsquare"] = vsquare
                    params["Dwell"] = dwell

                    try:
                        result = run_nls_switch_test(
                            query,
                            CH1,
                            CH2,
                            params,
                            output_dir,
                            segarb_options=SEGARB_OPTIONS,
                        )
                        result["params"] = params.copy()
                        results.append(result)
                        if "df_vp_ch1" in result and result["df_vp_ch1"] is not None:
                            pol = result["df_vp_ch1"]["Polarization"].values
                            pr_value = -pol[0] + pol[-1] if len(pol) > 0 else None
                        else:
                            pr_value = None
                        summary_data.append(
                            {
                                "Vsquare": vsquare,
                                "Dwell": dwell,
                                "TotalDelay": params["TotalDelay"],
                                "PaddingDelay": nls_padding_time(params),
                                "Pr": pr_value,
                                "ENABLE_LOAD_CONFIG": SEGARB_OPTIONS["ENABLE_LOAD_CONFIG"],
                                "LOAD_RESISTANCE": SEGARB_OPTIONS["LOAD_RESISTANCE"],
                            }
                        )
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        print(f"  Test failed: {exc}")
                        results.append({"params": params.copy(), "success": False, "error": str(exc)})
                        summary_data.append(
                            {
                                "Vsquare": vsquare,
                                "Dwell": dwell,
                                "TotalDelay": params["TotalDelay"],
                                "PaddingDelay": nls_padding_time(params),
                                "Pr": None,
                                "ENABLE_LOAD_CONFIG": SEGARB_OPTIONS["ENABLE_LOAD_CONFIG"],
                                "LOAD_RESISTANCE": SEGARB_OPTIONS["LOAD_RESISTANCE"],
                            }
                        )
                    time.sleep(0.5)
        except KeyboardInterrupt:
            interrupted = True
            print(f"User interrupted after {test_idx}/{total_tests} test points.")

    if summary_data:
        df_summary = pd.DataFrame(summary_data).assign(time=run_time)
        with pd.ExcelWriter(f"{summary_stem}.xlsx", engine="openpyxl") as writer:
            set_workbook_author(writer.book)
            df_summary.to_excel(writer, index=False)

    status = "interrupted" if interrupted else "complete"
    success_count = sum(1 for result in results if result.get("success", False))
    print(f"Sweep {status}: {success_count}/{len(results)} successful.")
    return results


if __name__ == "__main__":
    if PREVIEW_ONLY:
        preview_sweep_waveform()
    else:
        run_sweep()
