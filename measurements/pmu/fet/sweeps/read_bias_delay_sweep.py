# -*- coding: utf-8 -*-
"""Sweep Vg_read, Vd_read, and write-to-read delay using the dual FeFET test."""

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

from keithley4200.output import prepare_output_dir, reserve_summary_stem, voltage_tag
from measurements.pmu.fet import bipolar_program_read as dual


# Three independent sweep dimensions.
VG_READ_VALUES = (-0.5, -0.2, -0.1, 0.0, 0.1, 0.2, 0.5)
VD_READ_VALUES = (-2, -1, -0.5, 0.5, 1.0, 2.0)
DELAY_TIMES = (1e-5, 1e-3, 1e-2, 1e-1, 1.0, 10.0)

# Extra FeFET-style repeated-state test, run once for every Vg_read/Vd_read
# pair after its normal retention sweep using the base test repeat counts is complete.
FEFET_REPEAT_N = 30
FEFET_REPEAT_T = 1e-3

SWEEP_NAME = "dual_3d_Vg_Vd_delay_sweep"


def validate_sweep():
    if not VG_READ_VALUES or not VD_READ_VALUES or not DELAY_TIMES:
        raise ValueError("VG_READ_VALUES, VD_READ_VALUES, and DELAY_TIMES cannot be empty.")
    if any(float(delay) <= 0 for delay in DELAY_TIMES):
        raise ValueError("Every delay must be greater than zero.")
    if int(FEFET_REPEAT_N) < 1:
        raise ValueError("FEFET_REPEAT_N must be a positive integer.")
    if float(FEFET_REPEAT_T) <= 0:
        raise ValueError("FEFET_REPEAT_T must be greater than zero.")
    if dual.PREVIEW_ONLY:
        raise ValueError("Set PREVIEW_ONLY = False in bipolar_program_read.py.")


def calculate_metrics(raw_data):
    """Pair positive/negative reads and calculate state-separation metrics."""
    index_columns = ["Vg_read_V", "Vd_read_V", "RequestedDelay_s"]
    current_table = raw_data.pivot_table(
        index=index_columns,
        columns="WritePolarity",
        values="Id",
        aggfunc="mean",
    ).reset_index()
    for polarity in ("Positive", "Negative"):
        if polarity not in current_table:
            raise ValueError(f"Missing {polarity} Id data in 3D sweep results.")

    current_table = current_table.rename(
        columns={"Positive": "Ids_Positive_A", "Negative": "Ids_Negative_A"}
    )
    positive = current_table["Ids_Positive_A"].abs()
    negative = current_table["Ids_Negative_A"].abs()
    current_table["MemoryWindow_A"] = (positive - negative).abs()
    current_table["CurrentRatio"] = np.maximum(positive, negative) / np.maximum(
        np.minimum(positive, negative), np.finfo(float).tiny
    )
    current_table["NormalizedContrast"] = current_table["MemoryWindow_A"] / np.maximum(
        positive + negative, np.finfo(float).tiny
    )
    return current_table.sort_values(index_columns).reset_index(drop=True)


def rank_read_biases(metrics):
    """Rank Vg/Vd pairs by the smallest absolute window across all delays."""
    ranking = metrics.groupby(["Vg_read_V", "Vd_read_V"], as_index=False).agg(
        WorstContrast=("NormalizedContrast", "min"),
        MeanContrast=("NormalizedContrast", "mean"),
        WorstCurrentRatio=("CurrentRatio", "min"),
        MinimumWindow_A=("MemoryWindow_A", "min"),
        MeanWindow_A=("MemoryWindow_A", "mean"),
    )
    # Absolute current window is harder for near-zero/noise-floor currents to
    # game than a ratio or normalized contrast.
    ranking["RobustScore_A"] = ranking["MinimumWindow_A"]
    return ranking.sort_values(
        ["RobustScore_A", "WorstContrast"], ascending=False
    ).reset_index(drop=True)


def save_retention_plot(metrics, output_path):
    fig, axis = plt.subplots(figsize=(10, 6))
    for (vg, vd), group in metrics.groupby(["Vg_read_V", "Vd_read_V"]):
        ordered = group.sort_values("RequestedDelay_s")
        axis.plot(
            ordered["RequestedDelay_s"],
            ordered["NormalizedContrast"],
            marker="o",
            label=f"Vg={vg:g} V, Vd={vd:g} V",
        )
    axis.set_xscale("log")
    axis.set_xlabel("Write-to-read delay (s)")
    axis.set_ylabel("Normalized contrast |I+ - I-| / (|I+| + |I-|)")
    axis.set_title("FeFET read-bias comparison over retention delay")
    axis.grid(True, which="both", alpha=0.3)
    axis.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_3d_plot(metrics, output_path):
    fig = plt.figure(figsize=(10, 7))
    axis = fig.add_subplot(111, projection="3d")
    points = axis.scatter(
        np.log10(metrics["RequestedDelay_s"]),
        metrics["Vg_read_V"],
        metrics["Vd_read_V"],
        c=metrics["NormalizedContrast"],
        cmap="viridis",
        s=55,
    )
    axis.set_xlabel("log10(delay / s)")
    axis.set_ylabel("Vg_read (V)")
    axis.set_zlabel("Vd_read (V)")
    axis.set_title("FeFET 3D read-condition sweep")
    colorbar = fig.colorbar(points, ax=axis, pad=0.12)
    colorbar.set_label("Normalized positive/negative contrast")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_repeated_fefet_plot(frame, output_path, vg, vd):
    """Plot the extra N repeated Positive/Negative reads for one bias pair."""
    fig, axis = plt.subplots(figsize=(8, 5))
    for polarity, group in frame.groupby("WritePolarity", sort=False):
        ordered = group.sort_values("PolarityRepeat")
        axis.plot(
            ordered["PolarityRepeat"],
            ordered["Id"],
            marker="o",
            label=str(polarity),
        )
    axis.set_xlabel("Positive/negative state repeat index")
    axis.set_ylabel("Ids, PMU CH2 (A)")
    axis.set_title(
        "Repeated FeFET program/read\n"
        f"Vg_read={vg:g} V, Vd_read={vd:g} V, "
        f"N={int(FEFET_REPEAT_N)}, t={float(FEFET_REPEAT_T):g} s"
    )
    axis.grid(alpha=0.3)
    axis.legend(title="Write polarity")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def _annotated_heatmap(table, title, colorbar_label, output_path, value_scale=1.0):
    """Save a compact Vg-row/Vd-column heatmap with numeric cell labels."""
    fig, axis = plt.subplots(figsize=(10, 6))
    values = table.to_numpy(dtype=float) * value_scale
    image = axis.imshow(values, aspect="auto", cmap="viridis")
    axis.set_xticks(range(len(table.columns)), [f"{v:g}" for v in table.columns])
    axis.set_yticks(range(len(table.index)), [f"{v:g}" for v in table.index])
    axis.set_xlabel("Vd_read (V)")
    axis.set_ylabel("Vg_read (V)")
    axis.set_title(title)
    threshold = np.nanmedian(values)
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            value = values[row, column]
            axis.text(
                column,
                row,
                f"{value:.2f}",
                ha="center",
                va="center",
                color="white" if value < threshold else "black",
                fontsize=8,
            )
    colorbar = fig.colorbar(image, ax=axis)
    colorbar.set_label(colorbar_label)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def save_clear_summary_plots(metrics, ranking, repeated_data, output_stem):
    """Save human-readable heatmaps and rankings in addition to the 3D plot."""
    longest_delay = metrics["RequestedDelay_s"].max()
    long_data = metrics[metrics["RequestedDelay_s"] == longest_delay]
    long_window = long_data.pivot(
        index="Vg_read_V", columns="Vd_read_V", values="MemoryWindow_A"
    ).sort_index().sort_index(axis=1)
    _annotated_heatmap(
        long_window,
        f"Positive/negative Ids window at delay = {longest_delay:g} s",
        "Absolute memory window (nA)",
        Path(f"{output_stem}_01_long_delay_window_heatmap.png"),
        value_scale=1e9,
    )

    top = ranking.head(10).sort_values("MinimumWindow_A")
    labels = [
        f"Vg={vg:g}, Vd={vd:g} V"
        for vg, vd in zip(top["Vg_read_V"], top["Vd_read_V"])
    ]
    fig, axis = plt.subplots(figsize=(9, 6))
    bars = axis.barh(labels, top["MinimumWindow_A"] * 1e9, color="tab:blue")
    axis.bar_label(bars, fmt="%.2f nA", padding=3)
    axis.set_xlabel("Smallest |Ids+ - Ids−| over every tested delay (nA)")
    axis.set_title("Top read-bias conditions by worst-case absolute window")
    axis.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(Path(f"{output_stem}_02_top10_read_bias_ranking.png"), dpi=180)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(9, 6))
    for item in ranking.head(6).itertuples(index=False):
        group = metrics[
            (metrics["Vg_read_V"] == item.Vg_read_V)
            & (metrics["Vd_read_V"] == item.Vd_read_V)
        ].sort_values("RequestedDelay_s")
        axis.plot(
            group["RequestedDelay_s"],
            group["MemoryWindow_A"] * 1e9,
            marker="o",
            label=f"Vg={item.Vg_read_V:g}, Vd={item.Vd_read_V:g} V",
        )
    axis.set_xscale("log")
    axis.set_xlabel("Write-to-read delay (s)")
    axis.set_ylabel("Absolute positive/negative Ids window (nA)")
    axis.set_title("Retention of the six most practical read-bias conditions")
    axis.grid(True, which="both", alpha=0.3)
    axis.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(Path(f"{output_stem}_03_top6_window_retention.png"), dpi=180)
    plt.close(fig)

    if repeated_data is not None and not repeated_data.empty:
        stats = repeated_data.groupby(
            ["Vg_read_V", "Vd_read_V", "WritePolarity"]
        )["Id"].agg(["mean", "std"]).reset_index()
        means = stats.pivot(
            index=["Vg_read_V", "Vd_read_V"], columns="WritePolarity", values="mean"
        )
        stds = stats.pivot(
            index=["Vg_read_V", "Vd_read_V"], columns="WritePolarity", values="std"
        )
        repeat_snr = (
            (means["Positive"].abs() - means["Negative"].abs()).abs()
            / np.sqrt(stds["Positive"] ** 2 + stds["Negative"] ** 2)
        ).rename("RepeatSeparationSNR").reset_index()
        snr_table = repeat_snr.pivot(
            index="Vg_read_V", columns="Vd_read_V", values="RepeatSeparationSNR"
        ).sort_index().sort_index(axis=1)
        _annotated_heatmap(
            snr_table,
            "Repeated-state separation relative to repeat scatter",
            "Separation / combined standard deviation",
            Path(f"{output_stem}_04_repeated_state_stability_heatmap.png"),
        )


def main():
    validate_sweep()
    output_dir = prepare_output_dir(Path(dual.SAVE_DIR) / SWEEP_NAME)
    total_runs = len(VG_READ_VALUES) * len(VD_READ_VALUES) * len(DELAY_TIMES)
    minimum_wait = (
        len(VG_READ_VALUES)
        * len(VD_READ_VALUES)
        * 2
        * sum(float(delay) for delay in DELAY_TIMES)
    )
    repeat_wait = (
        len(VG_READ_VALUES)
        * len(VD_READ_VALUES)
        * 2
        * int(FEFET_REPEAT_N)
        * float(FEFET_REPEAT_T)
    )
    print(f"3D sweep: {total_runs} independent dual tests")
    print(
        "Programmed delay alone requires at least "
        f"{(minimum_wait + repeat_wait) / 60:.1f} min, including the extra repeated tests."
    )
    print(
        "The first positive point uses the device state present before the script starts; "
        "subsequent positive points follow a preceding negative write."
    )

    rows = []
    repeated_rows = []
    run_index = 0
    for vg in VG_READ_VALUES:
        for vd in VD_READ_VALUES:
            bias_dir = output_dir / f"Vg{voltage_tag(vg)}_Vd{voltage_tag(vd)}"
            for delay in DELAY_TIMES:
                run_index += 1
                delay = float(delay)
                print(
                    f"\n=== Run {run_index}/{total_runs}: Vg={vg:g} V, "
                    f"Vd={vd:g} V, delay={delay:g} s ==="
                )
                result_path = dual.run_test(
                    params_override={"read_gate_voltage": float(vg),
                                     "read_drain_voltage": float(vd),
                                     "read_delay": delay},
                    save_dir=bias_dir, output_tag=None, preview_only=False,
                )["output_path"]
                if result_path is None:
                    raise RuntimeError("The dual test did not return a result workbook.")
                frame = pd.read_excel(result_path, sheet_name="FET_Data")
                frame.insert(0, "Vg_read_V", float(vg))
                frame.insert(1, "Vd_read_V", float(vd))
                frame.insert(2, "RequestedDelay_s", delay)
                frame.insert(3, "SweepRunIndex", run_index)
                rows.append(frame)

            # Additional repeated FeFET-like data set for this Vg/Vd pair.
            repeat_tag = f"repeated_N{int(FEFET_REPEAT_N)}_t{float(FEFET_REPEAT_T):g}s"
            repeat_dir = bias_dir / (
                f"repeated_FeFET_N{int(FEFET_REPEAT_N)}_t{float(FEFET_REPEAT_T):g}s"
            )
            print(
                f"\n=== Extra repeated FeFET: Vg={vg:g} V, Vd={vd:g} V, "
                f"N={int(FEFET_REPEAT_N)}, t={float(FEFET_REPEAT_T):g} s ==="
            )
            repeated_path = dual.run_test(
                params_override={"read_gate_voltage": float(vg),
                                 "read_drain_voltage": float(vd),
                                 "read_delay": float(FEFET_REPEAT_T),
                                 "positive_program_read_repeats": int(FEFET_REPEAT_N),
                                 "negative_program_read_repeats": int(FEFET_REPEAT_N)},
                output_tag=repeat_tag, save_dir=repeat_dir, preview_only=False,
            )["output_path"]
            if repeated_path is None:
                raise RuntimeError("The repeated FeFET test did not return a workbook.")
            repeated = pd.read_excel(repeated_path, sheet_name="FET_Data")
            repeated.insert(0, "Vg_read_V", float(vg))
            repeated.insert(1, "Vd_read_V", float(vd))
            repeated.insert(2, "RepeatDelay_t_s", float(FEFET_REPEAT_T))
            repeated_rows.append(repeated)
            repeat_plot = Path(repeated_path).parent / "Ids_vs_repeat.png"
            try:
                save_repeated_fefet_plot(repeated, repeat_plot, float(vg), float(vd))
            except Exception as exc:
                print(
                    "Warning: repeated FeFET plot could not be saved; "
                    f"measurement workbook is safe: {exc}"
                )


    raw_data = pd.concat(rows, ignore_index=True)
    metrics = calculate_metrics(raw_data)
    ranking = rank_read_biases(metrics)
    repeated_data = pd.concat(repeated_rows, ignore_index=True)
    summary_stem, run_time = reserve_summary_stem(output_dir, "FET3D_summary")
    raw_data = raw_data.assign(time=run_time)
    metrics = metrics.assign(time=run_time)
    ranking = ranking.assign(time=run_time)
    repeated_data = repeated_data.assign(time=run_time)
    workbook_path = Path(f"{summary_stem}.xlsx")
    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        raw_data.to_excel(writer, sheet_name="All_Raw_Data", index=False)
        metrics.to_excel(writer, sheet_name="Delay_Metrics", index=False)
        ranking.to_excel(writer, sheet_name="Read_Bias_Ranking", index=False)
        repeated_data.to_excel(writer, sheet_name="Repeated_FeFET_Data", index=False)

    retention_plot = Path(f"{summary_stem}_retention.png")
    scatter_plot = Path(f"{summary_stem}_scatter.png")
    save_retention_plot(metrics, retention_plot)
    save_3d_plot(metrics, scatter_plot)
    save_clear_summary_plots(metrics, ranking, repeated_data, summary_stem)
    best = ranking.iloc[0]
    print(f"Saved 3D summary: {workbook_path.resolve()}")
    print(
        f"Best robust read bias in this sweep: Vg={best.Vg_read_V:g} V, "
        f"Vd={best.Vd_read_V:g} V, minimum window={best.MinimumWindow_A * 1e9:.3g} nA"
    )
    return workbook_path, retention_plot, scatter_plot


if __name__ == "__main__":
    main()
