# -*- coding: utf-8 -*-
"""FTJ Identical V2: separate executions with real Python inter-pulse waits."""

from pathlib import Path
import sys
import time

import pandas as pd

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.output import measurement_name, reserve_output_stem, time_tag, saved_at, voltage_tag
from keithley4200.pmu.data_processing import read_both_channels
from keithley4200.pmu.pmu_tests import (
    execute_segARB_test,
    power_off_outputs,
    validate_segment_arb_configs,
)
from keithley4200.pmu.session import PMUSession
# These KXCI error commands apply to all cards, including PMU (manual 4-2/4-3).
from keithley4200.smu.common import clear_kxci_error, raise_for_kxci_error
from keithley4200.measurement_parameters import merge_parameters, remap_channel_options
from keithley4200.tools.waveform_preview import preview_sequence_configs


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
CH1, CH2 = 1, 2
SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\14-09-2026\04A1_2700_1200_300\L30_2\FTJ\Identical_V2")
FILE_STEM = "Identical2"

CURRENT_RANGES = {CH1: 1e-5, CH2: 1e-5}
SEGARB_OPTIONS = {
    "ENABLE_CONNECTION_COMP": False,
    "ENABLE_LOAD_CONFIG": True,
    "LOAD_RESISTANCE": 1e6,
    "ENABLE_LLEC": False,
}

params = {
    # Voltage held before/after every write and read pulse.
    "base_v": 0.0,
    "write_positive_v": 6,
    "write_negative_v": -6,
    "read_v": -2,
    "write_positive_dwell": 5e-5,
    "write_negative_dwell": 5e-5,
    "read_dwell": 5e-5,
    "write_positive_trf": 1e-6,
    "write_negative_trf": 1e-6,
    "read_trf": 1e-6,
    "write_positive_idle": 0.1,
    "write_negative_idle": 0.1,
    "read_idle": 1e-3,
    "wait_after_positive_write_s": 1.0,
    "wait_after_read_s": 1.0,
    "wait_after_negative_write_s": 1.0,
    "positive_repeat_count": 100,
    "negative_repeat_count": 100,
    "plan_repeat_count": 3,
}

PREVIEW_ONLY = False
WRITE_POSITIVE_SEQ_ID = 1
READ_SEQ_ID = 2
WRITE_NEGATIVE_SEQ_ID = 3


def build_waveform(*, parameters=None, channels=None):
    """Build pulse arrays and execution metadata from this run's parameters."""
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels

    base_v = float(parameters["base_v"])
    write_positive_v = float(parameters["write_positive_v"])
    write_negative_v = float(parameters["write_negative_v"])
    read_v = float(parameters["read_v"])
    write_positive_dwell = float(parameters["write_positive_dwell"])
    write_negative_dwell = float(parameters["write_negative_dwell"])
    read_dwell = float(parameters["read_dwell"])
    write_positive_trf = float(parameters["write_positive_trf"])
    write_negative_trf = float(parameters["write_negative_trf"])
    read_trf = float(parameters["read_trf"])
    write_positive_idle = float(parameters["write_positive_idle"])
    write_negative_idle = float(parameters["write_negative_idle"])
    read_idle = float(parameters["read_idle"])
    wait_after_write_positive_s = float(parameters["wait_after_positive_write_s"])
    wait_after_read_s = float(parameters["wait_after_read_s"])
    wait_after_write_negative_s = float(parameters["wait_after_negative_write_s"])
    positive_repeat_count = int(parameters["positive_repeat_count"])
    negative_repeat_count = int(parameters["negative_repeat_count"])
    plan_repeat_count = int(parameters["plan_repeat_count"])
    if min(positive_repeat_count, negative_repeat_count, plan_repeat_count) < 0:
        raise ValueError("Identical V2 repeat counts cannot be negative.")
    time_values_write_positive = [
        write_positive_trf, write_positive_dwell,
        write_positive_trf, write_positive_idle,
    ]
    time_values_write_negative = [
        write_negative_trf, write_negative_dwell,
        write_negative_trf, write_negative_idle,
    ]
    time_values_read = [read_trf, read_dwell, read_trf, read_idle]
    no_measure = [0, 0, 0, 0]
    zero_windows = [0.0] * 4
    read_types = [0, 1, 0, 0]
    read_start = [0.0, read_dwell * 0.5, 0.0, 0.0]
    read_stop = [0.0, read_dwell * 0.9, 0.0, 0.0]
    ch1_write_positive_config, ch2_write_positive_config = _pulse_config(
        WRITE_POSITIVE_SEQ_ID, write_positive_v, time_values_write_positive,
        no_measure, zero_windows, zero_windows,
        base_v=base_v,
    )
    ch1_read_config, ch2_read_config = _pulse_config(
        READ_SEQ_ID, read_v, time_values_read, read_types, read_start, read_stop,
        base_v=base_v,
    )
    ch1_write_negative_config, ch2_write_negative_config = _pulse_config(
        WRITE_NEGATIVE_SEQ_ID, write_negative_v, time_values_write_negative,
        no_measure, zero_windows, zero_windows,
        base_v=base_v,
    )
    write_positive_entry = {
        "name": "write_positive",
        "seq_configs": {
            ch1: [ch1_write_positive_config], ch2: [ch2_write_positive_config]
        },
        "wait_after_s": wait_after_write_positive_s,
    }
    read_entry = {
        "name": "read",
        "seq_configs": {ch1: [ch1_read_config], ch2: [ch2_read_config]},
        "wait_after_s": wait_after_read_s,
    }
    write_negative_entry = {
        "name": "write_negative",
        "seq_configs": {
            ch1: [ch1_write_negative_config], ch2: [ch2_write_negative_config]
        },
        "wait_after_s": wait_after_write_negative_s,
    }
    one_plan = (
        [write_positive_entry, read_entry] * positive_repeat_count
        + [write_negative_entry, read_entry] * negative_repeat_count
    )
    test_plan = one_plan * plan_repeat_count
    seq_configs = {
        ch1: [ch1_write_positive_config, ch1_read_config, ch1_write_negative_config],
        ch2: [ch2_write_positive_config, ch2_read_config, ch2_write_negative_config],
    }
    validate_segment_arb_configs(seq_configs)
    return {
        'test_plan': test_plan,
        'ch1_read_config': ch1_read_config,
        'ch1_write_negative_config': ch1_write_negative_config,
        'ch1_write_positive_config': ch1_write_positive_config,
        'seq_configs': seq_configs,
    }


def _pulse_config(seq_id, voltage, time_values, meas_types, meas_start, meas_stop, *, base_v):
    ch1_start = [base_v, voltage, voltage, base_v]
    ch1_stop = [voltage, voltage, base_v, base_v]
    zeros = [0.0] * 4
    ch1_config = (
        seq_id, ch1_start, ch1_stop, time_values,
        meas_types, meas_start, meas_stop,
    )
    ch2_config = (
        seq_id, zeros.copy(), zeros.copy(), time_values,
        meas_types, meas_start, meas_stop,
    )
    return ch1_config, ch2_config


def preview_waveform(
    output_path=None,
    *,
    show=True,
    title_prefix='FTJ Identical V2 CH1',
    channels=None,
    parameters=None,
    waveform=None,
):
    parameters = params if parameters is None else parameters
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    waveform = build_waveform(parameters=parameters, channels=channels) if waveform is None else waveform

    return preview_sequence_configs(
        [waveform['ch1_write_positive_config'], waveform['ch1_read_config'], waveform['ch1_write_negative_config']],
        output_path,
        title_prefix=title_prefix,
        show=show,
    )


def run_single_test(query, test, *, channels=None, current_ranges=None, segarb_options=None):
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    current_ranges = dict(current_ranges) if current_ranges is not None else dict(zip(channels, (CURRENT_RANGES[CH1], CURRENT_RANGES[CH2])))
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)

    clear_kxci_error(query)

    def checked_query(command):
        # Idle status is also returned when EXECUTE never started (7-32).
        # Check configuration before starting, then catch final verification errors.
        if command == ":PMU:EXECUTE":
            raise_for_kxci_error(query, context=f"{test['name']} configuration")
        response = query(command)
        if command == ":PMU:EXECUTE":
            raise_for_kxci_error(query, context=f"{test['name']} EXECUTE")
        return response

    try:
        execute_segARB_test(
            checked_query,
            channels=[ch1, ch2],
            seq_configs=test["seq_configs"],
            seq_list={channel: [(config[0], 1) for config in configs]
                      for channel, configs in test["seq_configs"].items()},
            current_ranges=current_ranges,
            options=segarb_options,
        )
        raise_for_kxci_error(query, context=f"{test['name']} completion")
        df_ch1, df_ch2 = read_both_channels(query, ch1, ch2)
        raise_for_kxci_error(query, context=f"{test['name']} data readout")
        return df_ch1, df_ch2
    finally:
        power_off_outputs(query, (ch1, ch2))



def save_checkpoint(path, rows, frames, params_df):
    """Replace one workbook only after its updated checkpoint is fully written."""
    import os
    import tempfile

    handle, temporary = tempfile.mkstemp(prefix=f".{path.stem}_", suffix=".xlsx", dir=path.parent)
    os.close(handle)
    try:
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            pd.DataFrame(rows).to_excel(writer, sheet_name="Summary", index=False)
            combined.to_excel(writer, sheet_name="RawCombined", index=False)
            params_df.to_excel(writer, sheet_name="Parameters", index=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_test(
    params_override=None,
    *,
    save_results=True,
    save_dir=None,
    file_stem=None,
    channels=None,
    current_ranges=None,
    inst=None,
    preview_only=None,
    segarb_options=None,
):
    parameters = merge_parameters(params, params_override)
    channels = tuple(channels) if channels is not None else (CH1, CH2)
    ch1, ch2 = channels
    current_ranges = dict(current_ranges) if current_ranges is not None else dict(zip(channels, (CURRENT_RANGES[CH1], CURRENT_RANGES[CH2])))
    file_stem = FILE_STEM if file_stem is None else str(file_stem)
    inst = INST if inst is None else inst
    preview_only = PREVIEW_ONLY if preview_only is None else preview_only
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)
    segarb_options = remap_channel_options(SEGARB_OPTIONS, (CH1, CH2), channels, segarb_options)
    waveform = build_waveform(parameters=parameters, channels=channels)

    if preview_only:
        return {"preview": preview_waveform(channels=channels, parameters=parameters, waveform=waveform), "output_path": None, "params": dict(parameters), "accepted_current_ranges": {}}

    summary_rows = []
    combined_frames = []

    output_path = None
    if save_results:
        save_dir.mkdir(parents=True, exist_ok=True)
        output_stem = reserve_output_stem(
            save_dir, measurement_name(file_stem, None,
                "Vp" + voltage_tag(parameters["write_positive_v"]),
                "Vn" + voltage_tag(parameters["write_negative_v"]),
                "tw" + time_tag(parameters["write_positive_dwell"])),
        )
        output_path = Path(f"{output_stem}.xlsx")
        saved_params = {
            "saved_at": saved_at(),
            **parameters,
            "inst": inst,
            "channels": (ch1, ch2),
            "current_ranges": current_ranges,
            "segarb_options": segarb_options,
        }
        params_df = pd.DataFrame(
            {"name": saved_params.keys(), "value": map(repr, saved_params.values())}
        )

    index = 0
    test = {"name": "session"}
    try:
        with PMUSession(inst, channels=(ch1, ch2)) as session:
            query = session.query
            for index, test in enumerate(waveform['test_plan'], start=1):
                print(f"Running {test['name']} ({index}/{len(waveform['test_plan'])}) ...")
                df_ch1, df_ch2 = run_single_test(query, test, channels=channels, current_ranges=current_ranges, segarb_options=segarb_options)
                merged_df = pd.concat(
                    [frame.reset_index(drop=True) for frame in (df_ch1, df_ch2)
                     if frame is not None], axis=1) if any(
                         frame is not None for frame in (df_ch1, df_ch2)) else pd.DataFrame()
                if merged_df is not None and not merged_df.empty:
                    merged_df.insert(0, "test_name", test["name"])
                    merged_df.insert(1, "test_index", index)
                    merged_df.insert(2, "wait_after_s", test["wait_after_s"])
                    combined_frames.append(merged_df)
                summary_rows.append(
                    {
                        "test_index": index,
                        "test_name": test["name"],
                        f"points_ch{ch1}": 0 if df_ch1 is None else len(df_ch1),
                        f"points_ch{ch2}": 0 if df_ch2 is None else len(df_ch2),
                        "wait_after_s": test["wait_after_s"],
                        "status": "ok",
                        "error": "",
                    }
                )
                if test["name"] == "read" and any(
                        frame is None or frame.empty for frame in (df_ch1, df_ch2)):
                    raise RuntimeError(
                        f"Read step {index} returned no data on one or both channels. "
                        "Stopping before further write pulses; inspect the instrument errors and command log.")
                if save_results:
                    save_checkpoint(output_path, summary_rows, combined_frames, params_df)
                if test["wait_after_s"] > 0:
                    time.sleep(test["wait_after_s"])

    except BaseException as exc:
        if summary_rows and summary_rows[-1]["test_index"] == index:
            summary_rows[-1].update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed", error=str(exc))
        else:
            summary_rows.append(dict(test_index=index,
                                     test_name=test["name"],
                                     status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                                     error=str(exc)))
        raise
    finally:
        if save_results:
            save_checkpoint(output_path, summary_rows, combined_frames, params_df)
            print(f"Saved Identical V2 checkpoint: {output_path}")

    summary_df = pd.DataFrame(summary_rows)
    combined_df = (
        pd.concat(combined_frames, ignore_index=True)
        if combined_frames else pd.DataFrame()
    )
    result = {
        "summary_df": summary_df,
        "combined_df": combined_df,
        "output_path": output_path,
    }
    result.update(params=dict(parameters), accepted_current_ranges={})
    result["settings"] = {"inst": inst, "channels": channels, "segarb_options": segarb_options}
    return result


if __name__ == "__main__":
    run_test()
