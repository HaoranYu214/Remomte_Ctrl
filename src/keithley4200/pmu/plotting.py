# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.
# PMU plotting helpers.
"""
Plot management and visualization helpers for Keithley 4200A data.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from keithley4200.output import prepare_output_dir, reserve_output_stem
from pathlib import Path


class PlotManager:
    """
    Manage figure display and saving within a context.
    mode:
      - 'batched': show all figures on context exit; block controls blocking.
      - 'headless': close figures without displaying them.
      - 'save': save directly to the configured directory with reserved run numbers.
    """
    def __init__(self, mode='batched', block=True, close_after_show=False,
                 save_dir="outputs", save_ext="png", save_dpi=150,
                 run_tag=None, filename_prefix="fig"):
        self.mode = mode
        self.block = block
        self.close_after_show = close_after_show
        self._figs = []
        self._interactive_prev = plt.isinteractive()

        # Output settings
        self.save_dir = Path(save_dir)
        self.save_ext = save_ext
        self.save_dpi = save_dpi
        self.run_tag = run_tag
        self._output_dir = None
        self.filename_prefix = filename_prefix
        self._save_counter = 0

    def __enter__(self):
        if self.mode == 'batched':
            plt.ion()     # Build all figures without blocking between plots.
        else:  # 'save' / 'headless'
            plt.ioff()    # Disable interactive display.
        return self

    def add(self, fig, name=None):
        if fig is None:
            return
        if self.mode == 'save':
            self._save_counter += 1
            stem = name or f"{self.filename_prefix}_{self._save_counter}"
            if self._output_dir is None:
                self._output_dir = (
                    self.save_dir / self.run_tag if self.run_tag else prepare_output_dir(self.save_dir)
                )
            output_stem = reserve_output_stem(self._output_dir, stem)
            path = Path(f"{output_stem}.{self.save_ext}")
            fig.savefig(path, dpi=self.save_dpi, bbox_inches="tight", pad_inches=0.05)
            print(f"💾 已保存图像：{path}")
            plt.close(fig)
        else:
            self._figs.append(fig)

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.mode == 'batched':
                if self.block:
                    plt.ioff()                 # Blocking display.
                    plt.show(block=True)
                else:
                    plt.ion()                  # Nonblocking display.
                    plt.show(block=False)
                if self.close_after_show:
                    for f in self._figs:
                        try: plt.close(f)
                        except: pass
            elif self.mode == 'headless':
                for f in self._figs:
                    try: plt.close(f)
                    except: pass
            # Save mode already saved and closed figures in add().
        finally:
            if self._interactive_prev:
                plt.ion()
            else:
                plt.ioff()


def apply_symlog_with_ticks(ax, data, linthresh=1e-12, max_decades=8, unit=""):
    """
    Apply symlog with symmetric ticks, including zero and the linear threshold.
    unit: tick-label suffix, such as "A" or "ohm".
    """
    data = np.asarray(data)
    data = data[np.isfinite(data)]
    if data.size == 0:
        ax.set_yscale("linear")
        return

    dmax = np.nanmax(np.abs(data))
    if not np.isfinite(dmax) or dmax == 0:
        ax.set_yscale("linear")
        return

    ax.set_yscale("symlog", linthresh=linthresh, linscale=1.0)

    hi_exp = int(np.ceil(np.log10(dmax)))
    lo_exp = int(np.floor(np.log10(linthresh)))
    if hi_exp - lo_exp > max_decades:
        lo_exp = hi_exp - max_decades

    decades = 10.0 ** np.arange(lo_exp, hi_exp + 1)
    neg_ticks = (-decades[decades > linthresh])[::-1].tolist()
    core_ticks = [-linthresh, 0.0, linthresh]
    pos_ticks = decades[decades > linthresh].tolist()
    ticks = neg_ticks + core_ticks + pos_ticks

    ax.set_yticks(ticks)
    ax.yaxis.set_major_formatter(
        mtick.FuncFormatter(lambda v, p: "0" if v == 0 else f"{v:.0e}{unit}")
    )
    ax.set_ylim(-1.2 * dmax, 1.2 * dmax)


def plot_time_series(df, channels=(1, 2), width_us=None, amp_v=None, 
                    resistance_scale='log', show=False, return_fig=True):
    """
    Plot available voltage, current, and resistance versus time.
    
    Args:
        df: measured data as a DataFrame
        channels: channel numbers, default (1, 2)
        width_us: pulse width in microseconds, used only in the title
        amp_v: amplitude in volts, used only in the title
        resistance_scale: 'log' uses symmetric log, 'linear' uses linear axes
        show: display immediately when True
        return_fig: return the Figure when True
    """
    if df is None or df.empty:
        print("⚠️ 无数据，跳过绘图")
        return None

    # Detect available measurements.
    data_types = []
    if any(f"Voltage {ch}" in df.columns for ch in channels):
        data_types.append('voltage')
    if any(f"Current {ch}" in df.columns for ch in channels):
        data_types.append('current')
    if any(f"Resistance {ch}" in df.columns for ch in channels):
        data_types.append('resistance')
    
    if not data_types:
        print("⚠️ 未找到可绘制的数据列")
        return None

    # Allocate one subplot per measurement type.
    n_plots = len(data_types)
    fig, axes = plt.subplots(n_plots, 1, figsize=(12, 4 * n_plots))
    if n_plots == 1:
        axes = [axes]

    # Figure title
    suffix = []
    if width_us is not None: suffix.append(f"{width_us} µs")
    if amp_v is not None:    suffix.append(f"{amp_v} V")
    title = "Dual-channel Measurements" + (" - " + ", ".join(suffix) if suffix else "")
    fig.suptitle(title, fontsize=14, fontweight='bold')

    # Channel colors and measurement markers
    colors = {1: 'darkred', 2: 'darkblue'}
    markers = {'voltage': 'o', 'current': '^', 'resistance': 'd'}
    units = {'voltage': 'V', 'current': 'A', 'resistance': 'Ω'}

    for i, data_type in enumerate(data_types):
        ax = axes[i]
        
        for ch in channels:
            col_data = f"{data_type.title()} {ch}"
            col_time = f"Timestamp {ch}"
            
            if col_data in df.columns and col_time in df.columns:
                data = df[col_data]
                time = df[col_time]
                
                # Keep finite resistance values.
                if data_type == 'resistance':
                    valid = np.isfinite(data)
                    if valid.any():
                        data = data[valid]
                        time = time[valid]
                    else:
                        continue
                
                # Plot the selected channel.
                ax.plot(time, data, 
                       color=colors[ch], linewidth=1.5, 
                       marker=markers[data_type], markersize=3,
                       markerfacecolor=colors[ch], markeredgecolor=colors[ch],
                       label=f'Channel {ch} {data_type.title()}', alpha=0.8)
        
        # Label axes with physical units.
        unit = units[data_type]
        ax.set_ylabel(f"{data_type.title()} ({unit})")
        ax.set_title(f"{data_type.title()} vs Time")
        
        # Apply the requested resistance scale.
        if data_type == 'resistance' and resistance_scale == 'log':
            all_res_data = []
            for ch in channels:
                col = f"Resistance {ch}"
                if col in df.columns:
                    valid_data = df[col].dropna()
                    if not valid_data.empty:
                        all_res_data.extend(valid_data.tolist())
            
            if all_res_data:
                apply_symlog_with_ticks(ax, all_res_data, linthresh=1.0, unit="Ω")
        
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # Label time on the final subplot.
        if i == len(data_types) - 1:
            ax.set_xlabel("Time (s)")

    plt.tight_layout()
    if show: plt.show()
    return fig if return_fig else None


def plot_iv_characteristics(df, channels=(1, 2), width_us=None, amp_v=None,
                           current_linthresh=1e-12, show=False, return_fig=True):
    """
    Plot current versus voltage with a symmetric-log current axis.
    """
    if df is None or df.empty:
        print("⚠️ 无数据，跳过I-V图")
        return None

    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    
    # Figure title
    suffix = []
    if width_us is not None: suffix.append(f"{width_us} µs")
    if amp_v is not None:    suffix.append(f"{amp_v} V")
    title = "I-V Characteristics" + (" - " + ", ".join(suffix) if suffix else "")
    fig.suptitle(title, fontsize=14, fontweight='bold')

    colors = {1: 'red', 2: 'blue'}
    
    for ch in channels:
        v_col = f"Voltage {ch}"
        i_col = f"Current {ch}"
        
        if v_col in df.columns and i_col in df.columns:
            voltage = df[v_col].dropna()
            current = df[i_col].dropna()
            
            if not voltage.empty and not current.empty:
                ax.plot(voltage, current, 
                       color=colors[ch], linewidth=2, marker='o', markersize=4,
                       label=f'Channel {ch}', alpha=0.7)

    ax.set_xlabel("Voltage (V)")
    ax.set_ylabel("Current (A)")
    
    # Use a symmetric-log current axis to retain sign and zero.
    all_currents = []
    for ch in channels:
        i_col = f"Current {ch}"
        if i_col in df.columns:
            all_currents.extend(df[i_col].dropna().tolist())
    
    if all_currents:
        apply_symlog_with_ticks(ax, all_currents, linthresh=current_linthresh, unit="A")
    
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    plt.tight_layout()
    if show: plt.show()
    return fig if return_fig else None


# Legacy names retained for existing callers; all render available data types.
def plot_currents(df, width_us=None, amp_v=None, show=False, return_fig=True):
    """Legacy entry for the combined time-series plot."""
    return plot_time_series(df, channels=(1, 2), width_us=width_us, amp_v=amp_v, 
                           show=show, return_fig=return_fig)

def plot_voltages(df, width_us=None, amp_v=None, show=False, return_fig=True):
    """Legacy entry for the combined time-series plot."""
    return plot_time_series(df, channels=(1, 2), width_us=width_us, amp_v=amp_v, 
                           show=show, return_fig=return_fig)

def plot_resistances(df, width_us=None, amp_v=None, res_min=1.0, 
                    resistance_scale='log', show=False, return_fig=True):
    """Legacy time-series entry; res_min is unused, filter resistance before plotting."""
    return plot_time_series(df, channels=(1, 2), width_us=width_us, amp_v=amp_v, 
                           resistance_scale=resistance_scale, show=show, return_fig=return_fig)


def save_ids_dual_axis_plot(
    configs,
    ids,
    output_path,
    *,
    read_gate_voltage,
    read_drain_voltage,
    read_delay,
    compress_above=0.1,
    compressed_width=2e-4,
    dpi=180,
):
    """Save Gate/Drain voltage and measured CH2 Ids on a dual-y plot."""
    from .preview import sequence_configs_to_dataframe, _measurement_times
    import matplotlib.pyplot as plt
    import pandas as pd

    waveform = sequence_configs_to_dataframe(
        configs,
        channel_labels=("CH1", "CH2"),
        compress_constant_segments_above=compress_above,
        compressed_segment_width=compressed_width,
    )
    display_times, actual_times = _measurement_times(
        configs[1], compress_above, compressed_width
    )
    ids = pd.to_numeric(pd.Series(ids), errors="coerce").reset_index(drop=True)
    if len(ids) != len(display_times):
        raise ValueError(
            f"Ids plot expected {len(display_times)} CH2 read points, received {len(ids)}."
        )

    fig, voltage_axis = plt.subplots(figsize=(12, 6))
    voltage_axis.plot(waveform["T_CH1"], waveform["V_CH1"], label="Gate pulse (CH1)")
    voltage_axis.plot(waveform["T_CH2"], waveform["V_CH2"], label="Drain pulse (CH2)")
    voltage_axis.set_xlabel("Displayed time (long delays compressed)")
    voltage_axis.set_ylabel("Programmed voltage (V)")
    voltage_axis.grid(alpha=0.3)

    current_axis = voltage_axis.twinx()
    current_axis.plot(
        display_times,
        ids,
        color="black",
        marker="o",
        linewidth=1.2,
        markersize=4,
        label="Ids (PMU CH2)",
    )
    current_axis.set_ylabel("Ids (A)")
    voltage_axis.set_title("FeFET program/read waveform and CH2 Ids")
    voltage_axis.text(
        0.01,
        0.02,
        f"Ids source: PMU CH2 Current\nVg_read = {read_gate_voltage:g} V\n"
        f"Vd_read = {read_drain_voltage:g} V\nRead delay = {read_delay:g} s",
        transform=voltage_axis.transAxes,
        va="bottom",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8},
    )
    handles1, labels1 = voltage_axis.get_legend_handles_labels()
    handles2, labels2 = current_axis.get_legend_handles_labels()
    voltage_axis.legend(handles1 + handles2, labels1 + labels2, loc="upper right")
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    print(f"Saved Ids dual-axis plot to {output_path}")
    return pd.DataFrame(
        {
            "DisplayTime_s": display_times,
            "ActualProgramTime_s": actual_times,
            "Ids_CH2_A": ids,
            "Vg_read_V": read_gate_voltage,
            "Vd_read_V": read_drain_voltage,
        }
    )

#   I |    .  *  .
#     | .           .   ssme
#     +-------------- V
#          h.y.
