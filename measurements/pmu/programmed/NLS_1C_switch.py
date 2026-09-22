# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.

# Start here: one NLS test; edit PARAMS, INST, CH1/CH2, SEGARB_OPTIONS and SAVE_DIR.
# Flow: PREVIEW_ONLY at the file entry point -> waveform construction -> PMU session -> run_nls_switch_test acquisition/save.
# run_nls_switch_test accepts an existing query connection and params; NLS_1C_switch_list.py handles batch runs.

"""NLS switch test helpers and standalone entrypoint."""

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

from keithley4200.pmu.preview import preview_sequence_configs
from keithley4200.output import measurement_name, reserve_output_stem, voltage_tag, time_tag, saved_at
from keithley4200.output import set_workbook_author
from keithley4200.pmu.data_processing import calculate_polarization, read_both_channels
from keithley4200.pmu.pmu_tests import execute_segARB_test, power_off_outputs
from keithley4200.pmu.session import PMUSession
from keithley4200.pmu.timing import nls_padding_time


SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": True,
    "LOAD_RESISTANCE": 1e3,
    "ENABLE_LLEC": False,
}
INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2
PARAMS = dict(

    Vsquare=1,



    offset=0,
    Vp=5,
    Rt_p=2.5e-4,
    Delaytime=5e-4,
    Rt_s=1e-7,
    TotalDelay=0.11,
    Dwell=1e-6,
    Irange1=1e-4,
    Irange2=1e-4,
    MeasureSquare=False,
    area_cm2=(20*1e-4)**2*3.14,

    
)
SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\Jingtian\2025-12-14\BTO\Device3")
PREVIEW_ONLY = True


# Build both NLS program/read waveforms and acquisition windows without connecting to hardware.
def make_nls_seq_configs(ch1, ch2, params):
    """Build the NLS sequence with a fixed preset-to-read interval."""
    measure_square = params.get("MeasureSquare", True)
    offset = params["offset"]
    vp = params["Vp"]
    rt_p = params["Rt_p"]
    delay_time = params["Delaytime"]
    vsquare = params["Vsquare"]
    rt_s = params["Rt_s"]
    dwell = params["Dwell"]

    start_voltages = [
        0,
        0,
        offset,
        -vp + offset,
        offset,
        offset,
        vsquare + offset,
        vsquare + offset,
        offset,
        offset,
        vp + offset,
        offset,
        offset,
        vp + offset,
    ]
    stop_voltages = [
        0,
        offset,
        -vp + offset,
        offset,
        offset,
        vsquare + offset,
        vsquare + offset,
        offset,
        offset,
        vp + offset,
        offset,
        offset,
        vp + offset,
        offset,
    ]
    time_values = [
        rt_p,
        rt_p,
        rt_p,
        rt_p,
        delay_time,
        rt_s,
        dwell,
        rt_s,
        delay_time,
        rt_p,
        rt_p,
        delay_time,
        rt_p,
        rt_p,
    ]
    measure_square_type = 2 if measure_square else 0
    meas_types = [
        0,
        0,
        0,
        0,
        0,
        measure_square_type,
        measure_square_type,
        measure_square_type,
        0,
        2,
        2,
        0,
        2,
        2,
    ]

    padding = nls_padding_time(params)
    if padding:
        start_voltages.insert(9, offset)
        stop_voltages.insert(9, offset)
        time_values.insert(9, padding)
        meas_types.insert(9, 0)

    ch1_config = (1, start_voltages, stop_voltages, time_values, meas_types)
    ch2_config = (
        1,
        [0.0] * len(time_values),
        [0.0] * len(time_values),
        time_values,
        meas_types,
    )
    return {ch1: [ch1_config], ch2: [ch2_config]}


# Preview both NLS channels from params offline; save an image if output_path is supplied.
def preview_nls_waveform(params, output_path=None, *, ch1=1, ch2=2):
    """Preview both programmed NLS channels without connecting to the PMU."""
    seq_configs = make_nls_seq_configs(ch1, ch2, params)
    return preview_sequence_configs(
        seq_configs[ch1] + seq_configs[ch2],
        output_path,
        title_prefix="NLS switch",
        channel_labels=(f"CH{ch1}", f"CH{ch2}"),
    )


# Build a parameter table from this run's settings and instrument options without acquiring data.
def build_params_table(params, segarb_options):
    """Return NLS parameters and common PMU options as a two-column table."""
    rows = [{"name": name, "value": repr(value)} for name, value in params.items()]
    rows.extend(
        {"name": name, "value": repr(value)}
        for name, value in segarb_options.items()
    )
    rows.append({"name": "PaddingDelay", "value": repr(nls_padding_time(params))})
    rows.append({"name": "saved_at", "value": saved_at()})
    return pd.DataFrame(rows)


# Execute one NLS test through the caller's query connection; save raw/analysis data and return results.
def run_nls_switch_test(
    Q,
    ch1,
    ch2,
    params,
    save_dir,
    fname_prefix=None,
    *,
    segarb_options=None,
):
    """Run one NLS switch measurement and save raw and processed outputs."""
    seq_configs = make_nls_seq_configs(ch1, ch2, params)
    if segarb_options is None:
        segarb_options = SEGARB_OPTIONS
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    if fname_prefix is None:
        fname_prefix = measurement_name(
            "NLS", params["Vsquare"], "tw" + time_tag(params["Dwell"]),
            "Vr" + voltage_tag(params["Vp"]), "tr" + time_tag(params["Rt_p"]),
        )
    fname_base = reserve_output_stem(save_dir, fname_prefix)

    print(
        "Running NLS switch "
        f"(Vp={params['Vp']}V, Vsquare={params['Vsquare']:.2f}V, Dwell={params['Dwell']:.1e}s)..."
    )
    current_ranges = {ch1: params["Irange1"], ch2: params["Irange2"]}
    execute_segARB_test(
        Q,
        [ch1, ch2],
        seq_configs,
        current_ranges=current_ranges,
        options=segarb_options,
    )
    df_ch1, df_ch2 = read_both_channels(Q, ch1, ch2)
    power_off_outputs(Q, (ch1, ch2))
    if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
        raise ValueError("NLS switch returned empty channel data.")

    result = {"df_ch1": df_ch1, "df_ch2": df_ch2, "success": True}
    excel_path = f"{fname_base}.xlsx"

    if params["MeasureSquare"]:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            set_workbook_author(writer.book)
            df_ch1.to_excel(writer, sheet_name="Raw_CH1", index=False)
            df_ch2.to_excel(writer, sheet_name="Raw_CH2", index=False)
            build_params_table(params, segarb_options).to_excel(
                writer,
                sheet_name="Parameters",
                index=False,
            )

        fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        for axis, df, channel, title in (
            (axes[0], df_ch1, ch1, "CH1 Waveform"),
            (axes[1], df_ch2, ch2, "CH2 Waveform"),
        ):
            time = df[f"Timestamp {channel}"]
            voltage = df[f"Voltage {channel}"]
            current = df[f"Current {channel}"]
            axis_current = axis.twinx()
            axis.plot(time, voltage, "b-", linewidth=0.8)
            axis_current.plot(time, current * 1e6, "r-", linewidth=0.8)
            axis.set_ylabel("Voltage (V)", color="b")
            axis_current.set_ylabel("Current (uA)", color="r")
            axis.set_title(title)
            axis.grid(alpha=0.3)
        axes[1].set_xlabel("Time (s)")
        fig.suptitle("NLS Switch - Waveform Check", fontsize=14)
        fig.tight_layout()
        fig.savefig(f"{fname_base}_waveform.png", dpi=300)
        plt.close(fig)
        return result

    area_cm2 = params.get("area_cm2", 1.0)

    # Subtract and integrate two read-current groups for one channel; return time, voltage, differential current and polarization.
    def process_channel(df, channel):
        voltage = df[f"Voltage {channel}"].values
        current = df[f"Current {channel}"].values
        total_points = len(voltage)
        seg_pts = total_points // 4

        current_first = current[: 2 * seg_pts]
        current_second = current[2 * seg_pts : 4 * seg_pts]
        voltage_first = voltage[: 2 * seg_pts]

        min_len = min(len(current_first), len(current_second))
        diff_current = current_first[:min_len] - current_second[:min_len]
        diff_voltage = voltage_first[:min_len]
        time_step = params["Rt_p"] * 4 / total_points
        diff_time = np.arange(1, min_len + 1) * time_step
        polarization = calculate_polarization(diff_current, diff_time, area_cm2)
        return pd.DataFrame(
            {
                "Time": diff_time,
                "Voltage": diff_voltage,
                "DiffCurrent": diff_current,
                "Polarization": polarization,
            }
        )

    df_vp_ch1 = process_channel(df_ch1, ch1)
    df_vp_ch2 = process_channel(df_ch2, ch2)
    result["df_vp_ch1"] = df_vp_ch1
    result["df_vp_ch2"] = df_vp_ch2

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        set_workbook_author(writer.book)
        df_ch1.to_excel(writer, sheet_name="Raw_CH1", index=False)
        df_ch2.to_excel(writer, sheet_name="Raw_CH2", index=False)
        df_vp_ch1.to_excel(writer, sheet_name="VP_CH1", index=False)
        df_vp_ch2.to_excel(writer, sheet_name="VP_CH2", index=False)
        build_params_table(params, segarb_options).to_excel(
            writer,
            sheet_name="Parameters",
            index=False,
        )

    fig, axis = plt.subplots(figsize=(6, 5))
    axis.plot(df_vp_ch2["Voltage"], df_vp_ch2["Polarization"], "r-", linewidth=1)
    axis.set_xlabel("Voltage (V)")
    axis.set_ylabel("Polarization (uC/cm^2)")
    axis.set_title("CH2 V-P (Tri1 - Tri2)")
    axis.grid(alpha=0.3)

    fig.suptitle("NLS Switch - Differential Polarization", fontsize=14)
    fig.tight_layout()
    fig.savefig(f"{fname_base}_vp.png", dpi=300)
    plt.close(fig)
    return result


if __name__ == "__main__":
    if PREVIEW_ONLY:
        preview_nls_waveform(PARAMS, ch1=CH1, ch2=CH2)
    else:
        make_nls_seq_configs(CH1, CH2, PARAMS)
        with PMUSession(INST, channels=(CH1, CH2)) as session:
            run_nls_switch_test(
                session.query,
                CH1,
                CH2,
                PARAMS,
                SAVE_DIR,
                segarb_options=SEGARB_OPTIONS,
            )
