# Copyright (c) 2026 ssme / Haoran Yu.
# -*- coding: utf-8 -*-
"""Helpers for previewing generated segARB sequence configs."""

from pathlib import Path


MEASURE_MODE_LABELS = {
    0: "off",
    1: "spot discrete",
    2: "waveform discrete",
    3: "spot average",
    4: "waveform average",
}


def _ssr_preview_config(config):
    """Mask isolated output voltage; a floating DUT voltage is unspecified."""
    if len(config) < 8 or config[7] is None:
        return config
    from keithley4200.pmu.pmu_tests import normalize_ssr, _normalize_seg_arb_measurements
    states = normalize_ssr(config[3], config[7])
    result = list(config)
    result[1] = [v if state else float("nan") for v, state in zip(config[1], states)]
    result[2] = [v if state else float("nan") for v, state in zip(config[2], states)]
    modes, starts, stops = _normalize_seg_arb_measurements(config[3], *config[4:7])
    result[4] = [mode if state else 0 for mode, state in zip(modes, states)]
    result[5], result[6] = starts, stops
    return tuple(result)


def _voltage_at(start_v, stop_v, segment_time, offset_time):
    """Linearly interpolate voltage inside one Segment Arb segment."""
    if segment_time <= 0:
        return stop_v
    fraction = max(0.0, min(1.0, offset_time / segment_time))
    return start_v + (stop_v - start_v) * fraction


def sequence_configs_to_dataframe(
    configs,
    *,
    channel_labels=None,
    compress_constant_segments_above=None,
    compressed_segment_width=2e-4,
):
    """Return the exact x/y plotting columns used for waveform previews."""
    import pandas as pd

    columns = {}
    for index, config in enumerate(configs):
        config = _ssr_preview_config(config)
        _seq_id, start_v, stop_v, times = config[:4]
        meas_types = config[4] if len(config) > 4 else [2] * len(times)
        segments = list(zip(start_v, stop_v, times, meas_types))
        x, y, actual_t, relay_states = [], [], [], []
        display_time = 0.0
        real_time = 0.0
        segment_index = 0
        while segment_index < len(segments):
            sv, ev, dt, mt = segments[segment_index]
            actual_duration = float(dt)
            compressible = (
                compress_constant_segments_above is not None
                and dt >= compress_constant_segments_above
                and mt == 0
                and abs(sv - ev) < 1e-12
            )
            next_index = segment_index + 1
            if compressible:
                while next_index < len(segments):
                    nsv, nev, ndt, nmt = segments[next_index]
                    if not (
                        ndt >= compress_constant_segments_above
                        and nmt == 0
                        and abs(nsv - nev) < 1e-12
                        and abs(nsv - sv) < 1e-12
                    ):
                        break
                    actual_duration += float(ndt)
                    next_index += 1
                display_duration = compressed_segment_width
            else:
                display_duration = actual_duration

            if len(config) > 7 and config[7] is not None:
                relay_states.extend([config[7][segment_index]] * 2)
            x.extend([display_time, display_time + display_duration])
            y.extend([sv, ev])
            actual_t.extend([real_time, real_time + actual_duration])
            display_time += display_duration
            real_time += actual_duration
            segment_index = next_index

        label = (
            channel_labels[index]
            if channel_labels is not None and index < len(channel_labels)
            else f"CH{index + 1}"
        ).replace(" ", "_")
        columns[f"T_{label}"] = pd.Series(x, dtype=float)
        columns[f"V_{label}"] = pd.Series(y, dtype=float)
        if relay_states:
            columns[f"SSR_{label}"] = pd.Series(relay_states, dtype=int)
        if compress_constant_segments_above is not None:
            columns[f"ActualT_{label}"] = pd.Series(actual_t, dtype=float)
    return pd.DataFrame(columns)


def _measurement_times(config, compress_above=None, compressed_width=2e-4):
    """Return display and actual midpoint times for measured segments."""
    config = _ssr_preview_config(config)
    start_v, stop_v, times = config[1], config[2], config[3]
    meas_types = config[4] if len(config) > 4 else [2] * len(times)
    meas_start = config[5] if len(config) > 5 else [0.0] * len(times)
    meas_stop = config[6] if len(config) > 6 else list(times)
    segments = list(zip(start_v, stop_v, times, meas_types, meas_start, meas_stop))
    display_time = actual_time = 0.0
    display_points, actual_points = [], []
    segment_index = 0
    while segment_index < len(segments):
        sv, ev, dt, mt, ms, me = segments[segment_index]
        actual_duration = float(dt)
        compressible = (
            compress_above is not None
            and dt >= compress_above
            and mt == 0
            and abs(sv - ev) < 1e-12
        )
        next_index = segment_index + 1
        if compressible:
            while next_index < len(segments):
                nsv, nev, ndt, nmt, _nms, _nme = segments[next_index]
                if not (
                    ndt >= compress_above
                    and nmt == 0
                    and abs(nsv - nev) < 1e-12
                    and abs(nsv - sv) < 1e-12
                ):
                    break
                actual_duration += float(ndt)
                next_index += 1
            display_duration = compressed_width
        else:
            display_duration = actual_duration
        if mt != 0:
            midpoint = (max(0.0, ms) + min(dt, me)) / 2
            display_points.append(display_time + display_duration * midpoint / dt)
            actual_points.append(actual_time + midpoint)
        display_time += display_duration
        actual_time += actual_duration
        segment_index = next_index
    return display_points, actual_points


def preview_sequence_configs(
    configs,
    output_path=None,
    *,
    title_prefix="",
    channel_labels=None,
    compress_constant_segments_above=None,
    compressed_segment_width=2e-4,
    dpi=180,
    show=True,
):
    """Preview one or more segARB sequence configs.

    Supported config tuple shapes:
    (seq_id, start_v, stop_v, time_values)
    (seq_id, start_v, stop_v, time_values, meas_types)
    (seq_id, start_v, stop_v, time_values, meas_types, meas_start, meas_stop)

    If output_path is None, show the figure unless ``show=False``. Otherwise
    save it. ``show=False`` lets a workflow build several figures and display
    them together with one final ``plt.show()``.
    """
    import matplotlib.pyplot as plt

    if not configs:
        raise ValueError("No sequence configs were provided for preview.")

    fig, axes = plt.subplots(len(configs), 1, figsize=(12, max(3.5, 3.5 * len(configs))), sharex=False)
    if title_prefix:
        fig.canvas.manager.set_window_title(str(title_prefix))
    if len(configs) == 1:
        axes = [axes]

    colors = ["tab:blue", "tab:red", "tab:green", "tab:purple", "tab:orange"]
    meas_styles = {
        1: ("black", "spot discrete"),
        2: ("tab:orange", "waveform discrete"),
        3: ("tab:purple", "spot average"),
        4: ("tab:green", "waveform average"),
    }
    for index, (ax, config) in enumerate(zip(axes, configs)):
        config = _ssr_preview_config(config)
        seq_id, start_v, stop_v, times = config[:4]
        meas_types = config[4] if len(config) > 4 else [2] * len(times)
        meas_start = config[5] if len(config) > 5 else [0.0] * len(times)
        meas_stop = config[6] if len(config) > 6 else list(times)
        x = []
        y = []
        meas_lines = {mode: ([], []) for mode in meas_styles}
        spot_x = []
        spot_y = []
        t = 0.0

        segments = list(zip(start_v, stop_v, times, meas_types, meas_start, meas_stop))
        display_segments = []
        segment_index = 0
        while segment_index < len(segments):
            sv, ev, dt, mt, ms, me = segments[segment_index]
            compressible = (
                compress_constant_segments_above is not None
                and dt >= compress_constant_segments_above
                and mt == 0
                and abs(sv - ev) < 1e-12
            )
            if compressible:
                actual_duration = float(dt)
                next_index = segment_index + 1
                while next_index < len(segments):
                    nsv, nev, ndt, nmt, _nms, _nme = segments[next_index]
                    if not (
                        ndt >= compress_constant_segments_above
                        and nmt == 0
                        and abs(nsv - nev) < 1e-12
                        and abs(nsv - sv) < 1e-12
                    ):
                        break
                    actual_duration += float(ndt)
                    next_index += 1
                display_segments.append(
                    (sv, ev, actual_duration, 0, 0.0, 0.0, compressed_segment_width)
                )
                segment_index = next_index
            else:
                display_segments.append((sv, ev, dt, mt, ms, me, dt))
                segment_index += 1

        delay_annotations = []
        floating_labeled = False
        for sv, ev, dt, mt, ms, me, display_dt in display_segments:
            if sv != sv:
                ax.axvspan(t, t+display_dt, color="gray", alpha=0.2,
                           label="SSR open: floating output" if not floating_labeled else None)
                floating_labeled = True
            x.extend([t, t + display_dt])
            y.extend([sv, ev])
            if display_dt != dt:
                delay_annotations.append((t + display_dt / 2, sv, dt))
            if mt != 0:
                ms = max(0.0, min(dt, ms))
                me = max(0.0, min(dt, me))
                start_y = _voltage_at(sv, ev, dt, ms)
                stop_y = _voltage_at(sv, ev, dt, me)
                if mt in (1, 3):
                    spot_t = t + display_dt * (ms + me) / (2 * dt)
                    spot_x.append(spot_t)
                    spot_y.append(_voltage_at(sv, ev, dt, (ms + me) / 2))
                if mt in meas_lines:
                    meas_x, meas_y = meas_lines[mt]
                    meas_x.extend([
                        t + display_dt * ms / dt,
                        t + display_dt * me / dt,
                        None,
                    ])
                    meas_y.extend([start_y, stop_y, None])
            t += display_dt

        color = colors[index % len(colors)]
        ax.plot(x, y, color=color, linewidth=1.2)
        for mode, (mode_label_color, mode_label) in meas_styles.items():
            meas_x, meas_y = meas_lines[mode]
            if meas_x:
                ax.plot(meas_x, meas_y, color=mode_label_color, linewidth=3, alpha=0.55, label=mode_label)
        if spot_x:
            ax.scatter(spot_x, spot_y, color="black", s=18, zorder=3, label="spot sample")
        labeled_delay_durations = set()
        for delay_x, delay_y, actual_duration in delay_annotations:
            ax.plot(
                [delay_x - compressed_segment_width * 0.18, delay_x, delay_x + compressed_segment_width * 0.18],
                [delay_y, delay_y + 0.04, delay_y],
                color="tab:gray",
                linewidth=1.5,
                zorder=4,
            )
            duration_key = round(float(actual_duration), 12)
            if duration_key not in labeled_delay_durations:
                ax.annotate(
                    f"Delay = {actual_duration:g} s (each marker)",
                    (delay_x, delay_y),
                    xytext=(5, 9),
                    textcoords="offset points",
                    ha="left",
                    fontsize=8,
                    color="tab:gray",
                )
                labeled_delay_durations.add(duration_key)
        prefix = f"{title_prefix} " if title_prefix else ""
        channel_name = (
            channel_labels[index]
            if channel_labels is not None and index < len(channel_labels)
            else f"seq {seq_id}"
        )
        ax.set_title(f"{prefix}{channel_name}, {len(times)} expanded segments")
        ax.set_ylabel("Voltage (V)")
        ax.grid(alpha=0.3)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, loc="upper right")

    axes[-1].set_xlabel(
        "Displayed time (long delays compressed and annotated)"
        if compress_constant_segments_above is not None
        else "Time (s)"
    )
    fig.tight_layout()
    if output_path is None:
        if show:
            plt.show()
            return None
        return fig

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    print(f"Saved waveform preview to {output_path}")
    return output_path

#     .----------------------------.
#     | SSS  SSS  M   M  EEEE     |
#     | S    S    MM MM  E        |
#     | SSS  SSS  M M M  EEE      |
#     |   S    S  M   M  E        |
#     | SSS  SSS  M   M  EEEE     |
#     |       haoran yu          |
#     '----------------------------'
