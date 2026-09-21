# Copyright (c) 2026 ssme / Haoran Yu.
"""Reusable PMU fixed-current-range assessment and automatic retry helpers."""

from __future__ import annotations

import numpy as np


# Experiment range subset for a 10 V RPM; other PMU/RPM configurations differ (KXCI 7-15).
# Minimum: 100 nA here, versus 100 uA for a 40 V RPM. Measurement range is not current compliance.
DEFAULT_CURRENT_RANGES = (1e-7, 1e-6, 1e-5, 1e-4, 1e-3)


def normalize_current_range(value, current_ranges=DEFAULT_CURRENT_RANGES):
    """Return the supported current range nearest to value on a log scale."""
    if value <= 0:
        raise ValueError("Current range must be positive.")
    return min(
        current_ranges,
        key=lambda candidate: abs(np.log10(value / candidate)),
    )


def _longest_high_current_plateau(current, current_range):
    """Return the longest nearly constant run near the top of a current range."""
    current = np.asarray(current, dtype=float)
    if len(current) == 0:
        return 0

    high_current = np.abs(current) >= 0.9 * current_range
    tolerance = max(current_range * 1e-5, 1e-15)
    longest = 1 if high_current[0] else 0
    run_length = longest
    for index in range(1, len(current)):
        same_level = abs(current[index] - current[index - 1]) <= tolerance
        if high_current[index] and high_current[index - 1] and same_level:
            run_length += 1
        else:
            run_length = 1 if high_current[index] else 0
        longest = max(longest, run_length)
    return longest


def assess_current_range(
    current,
    current_range,
    *,
    current_ranges=DEFAULT_CURRENT_RANGES,
    overrange_ratio=1.1,
    underrange_ratio=0.1,
    plateau_min_points=20,
    plateau_min_fraction=0.01,
):
    """Recommend increasing, decreasing, or keeping a fixed current range."""
    current = np.asarray(current, dtype=float)
    finite_current = current[np.isfinite(current)]
    if len(finite_current) == 0:
        raise ValueError("Cannot assess current range from empty/non-finite data.")

    current_range = normalize_current_range(current_range, current_ranges)
    range_index = current_ranges.index(current_range)
    peak_current = float(np.max(np.abs(finite_current)))
    plateau_points = _longest_high_current_plateau(
        finite_current,
        current_range,
    )
    plateau_threshold = max(
        plateau_min_points,
        int(np.ceil(len(finite_current) * plateau_min_fraction)),
    )
    # Clipping ratios, utilization thresholds and plateau lengths are software heuristics, not safety limits.
    clipped = (
        peak_current >= overrange_ratio * current_range
        or plateau_points >= plateau_threshold
    )

    if clipped:
        if range_index == len(current_ranges) - 1:
            return {
                "action": "keep_max",
                "range": current_range,
                "peak": peak_current,
                "plateau_points": plateau_points,
                "reason": "clipping detected, but maximum range is already selected",
            }
        return {
            "action": "increase",
            "range": current_ranges[range_index + 1],
            "peak": peak_current,
            "plateau_points": plateau_points,
            "reason": "current clipping/plateau detected",
        }

    if peak_current < underrange_ratio * current_range:
        if range_index == 0:
            return {
                "action": "keep_min",
                "range": current_range,
                "peak": peak_current,
                "plateau_points": plateau_points,
                "reason": "signal is small, but minimum range is already selected",
            }
        return {
            "action": "decrease",
            "range": current_ranges[range_index - 1],
            "peak": peak_current,
            "plateau_points": plateau_points,
            "reason": "peak current is below one tenth of the range",
        }

    return {
        "action": "keep",
        "range": current_range,
        "peak": peak_current,
        "plateau_points": plateau_points,
        "reason": "range utilization is suitable",
    }


def acquire_with_auto_current_range(
    acquire_once,
    initial_ranges,
    current_extractors,
    *,
    labels=None,
    current_ranges=DEFAULT_CURRENT_RANGES,
    max_attempts=8,
    test_name="Measurement",
):
    """Acquire repeatedly until all fixed current ranges are suitable.

    acquire_once receives the current ``{key: range}`` mapping and returns any
    test-specific result. Each current extractor receives that result and
    returns the corresponding measured current array.
    """
    ranges = {
        key: normalize_current_range(value, current_ranges)
        for key, value in initial_ranges.items()
    }
    if set(ranges) != set(current_extractors):
        raise ValueError("Range keys and current extractor keys must match.")
    labels = labels or {}

    for attempt in range(1, max_attempts + 1):
        range_text = ", ".join(
            f"{labels.get(key, key)}={value:.0e} A"
            for key, value in ranges.items()
        )
        print(f"{test_name} range check {attempt}/{max_attempts}: {range_text}")
        # A range retry reapplies the full waveform, including any programming or conditioning pulses.
        result = acquire_once(dict(ranges))

        assessments = {
            key: assess_current_range(
                current_extractors[key](result),
                ranges[key],
                current_ranges=current_ranges,
            )
            for key in ranges
        }

        rerun = False
        for key, assessment in assessments.items():
            label = labels.get(key, key)
            old_range = ranges[key]
            action = assessment["action"]
            print(
                f"  {label}: peak={assessment['peak']:.3e} A, "
                f"plateau={assessment['plateau_points']} points, "
                f"{assessment['reason']}."
            )
            if action in ("increase", "decrease"):
                new_range = assessment["range"]
                ranges[key] = new_range
                rerun = True
                print(
                    f"  {label} range changed from "
                    f"{old_range:.0e} A to {new_range:.0e} A; rerunning."
                )
            elif action == "keep_min":
                print(f"  {label}: keeping minimum range {old_range:.0e} A.")
            elif action == "keep_max":
                print(
                    f"  WARNING: {label} may be clipped at maximum range "
                    f"{old_range:.0e} A; accepting and saving this acquisition."
                )

        if not rerun:
            print(f"{test_name} current ranges accepted; saving this acquisition.")
            return result, ranges, assessments

    raise RuntimeError(
        f"{test_name} current ranges did not stabilize after {max_attempts} attempts."
    )
