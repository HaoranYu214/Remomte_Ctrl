"""Repository-level plot helpers for saved SMU sweep data."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


def format_log_tick(value, _position=None):
    """Format a positive power of ten as its physical value."""
    if not math.isfinite(value) or value <= 0:
        return ""
    exponent = round(math.log10(value))
    if not math.isclose(value, 10.0**exponent, rel_tol=1e-9):
        return ""
    return f"1e{exponent}"


def save_current_density_plots(
    data,
    output_base,
    *,
    voltage_column,
    current_density_column,
):
    """Save J-V and log(abs(J))-V plots next to a measurement file."""
    output_base = Path(output_base)
    voltage = pd.to_numeric(data[voltage_column], errors="coerce")
    current_density = pd.to_numeric(
        data[current_density_column], errors="coerce"
    )
    plot_data = pd.DataFrame(
        {"voltage": voltage, "current_density": current_density}
    ).dropna()
    density_label = current_density_column.replace("_A_per_cm2", "")

    if plot_data.empty:
        raise ValueError(
            f"No finite {voltage_column}/{current_density_column} data available "
            "to plot."
        )

    import matplotlib.pyplot as plt

    jv_path = output_base.with_name(f"{output_base.stem}_jv.png")
    log_path = output_base.with_name(f"{output_base.stem}_log_abs_j.png")

    fig, ax = plt.subplots()
    ax.plot(
        plot_data["voltage"],
        plot_data["current_density"],
        marker="o",
        linewidth=1,
    )
    ax.set_xlabel(f"{voltage_column} (V)")
    ax.set_ylabel(f"{density_label} (A/cm²)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(jv_path, dpi=300)
    plt.close(fig)

    log_data = plot_data[plot_data["current_density"] != 0].copy()
    if log_data.empty:
        raise ValueError(
            f"All {current_density_column} values are zero; cannot plot "
            "log(abs(J))."
        )
    log_data["abs_current_density"] = log_data["current_density"].abs()

    fig, ax = plt.subplots()
    ax.plot(
        log_data["voltage"],
        log_data["abs_current_density"],
        marker="o",
        linewidth=1,
    )
    from matplotlib.ticker import FuncFormatter, LogLocator

    ax.set_yscale("log")
    ax.yaxis.set_major_locator(LogLocator(base=10.0))
    ax.yaxis.set_major_formatter(FuncFormatter(format_log_tick))
    ax.set_xlabel(f"{voltage_column} (V)")
    ax.set_ylabel(f"abs({density_label}) (A/cm²)")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(log_path, dpi=300)
    plt.close(fig)

    return jv_path, log_path
