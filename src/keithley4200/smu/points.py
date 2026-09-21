# Copyright (c) 2026 ssme / Haoran Yu.
"""Pure point generation for SMU voltage lists; no instrument communication.

All paths contain at most 4096 finite points. Linear/segment paths include
both endpoints; the final interval may be shorter than the requested step.
"""
from collections.abc import Sequence
import math
import numpy as np


def validate_list_points(values):
    """Copy a custom list without sorting or removing deliberate repeats."""
    result = []
    for value in values:
        if len(result) >= 4096:
            raise ValueError("A list sweep is limited to 4096 points.")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("List points must be finite.")
        result.append(value)
    if not result:
        raise ValueError("Provide at least one list point.")
    return result


def build_segmented_voltage_path(turning_points, step):
    """Build a list sweep through several turning points.

    Example:
        ``turning_points=[0, 2, 0, -3, 0]`` produces
        ``0 -> 2 -> 0 -> -3 -> 0``.

    ``step`` may be one positive number shared by all segments, or one
    positive number per segment. Segment endpoints are always included and
    shared endpoints are not duplicated.
    """
    def clean(value):
        return float(f"{float(value):.12g}")

    turning_points = [clean(value) for value in turning_points]
    if len(turning_points) < 2:
        raise ValueError("turning_points must contain at least two voltages.")

    segment_count = len(turning_points) - 1
    if isinstance(step, Sequence) and not isinstance(step, (str, bytes)):
        steps = [float(value) for value in step]
        if len(steps) != segment_count:
            raise ValueError(
                f"Expected {segment_count} segment steps, received {len(steps)}."
            )
    else:
        steps = [float(step)] * segment_count

    if not all(math.isfinite(v) for v in turning_points + steps):
        raise ValueError("Voltages and steps must be finite.")
    if any(v <= 0 for v in steps):
        raise ValueError("All segment steps must be positive.")
    intervals = [abs(b-a)/s for a,b,s in zip(turning_points, turning_points[1:], steps)]
    if any(not math.isfinite(n) or n > 4096 for n in intervals) or 1 + sum(math.ceil(n) for n in intervals) > 4096:
        raise ValueError("A list sweep is limited to 4096 points.")
    values = [turning_points[0]]
    for start, stop, segment_step in zip(
        turning_points[:-1],
        turning_points[1:],
        steps,
    ):
        if segment_step <= 0:
            raise ValueError("All segment steps must be positive.")
        if start == stop:
            continue

        direction = 1.0 if stop > start else -1.0
        index = 1
        next_value = start + direction * segment_step
        tolerance = max(abs(start), abs(stop), segment_step, 1.0) * 1e-12
        while (
            next_value < stop - tolerance
            if direction > 0
            else next_value > stop + tolerance
        ):
            values.append(clean(next_value))
            index += 1
            next_value = start + direction * index * segment_step
        values.append(clean(stop))

    return values



def build_linear_voltage_path(start, stop, step):
    """Generate an endpoint-inclusive list; step sign must match direction."""
    start, stop, step = float(start), float(stop), float(step)
    if not all(math.isfinite(v) for v in (start, stop, step)) or step == 0:
        raise ValueError("Linear endpoints and step must be finite; step must be nonzero.")
    if start != stop and (stop > start) != (step > 0):
        raise ValueError("Linear step sign must match the sweep direction.")
    return build_segmented_voltage_path([start, stop], abs(step))


def build_log_voltage_path(start, stop, count):
    """Generate geometric spacing, including same-sign nonzero endpoints."""
    start, stop = float(start), float(stop)
    if not all(math.isfinite(v) for v in (start, stop)) or start == 0 or stop == 0 or (start > 0) != (stop > 0):
        raise ValueError("Log endpoints must be finite, nonzero and have the same sign.")
    if isinstance(count, bool) or not isinstance(count, (int, np.integer)) or not 2 <= count <= 4096:
        raise ValueError("Log count must be an integer in 2..4096.")
    return validate_list_points(np.geomspace(start, stop, count))

#     .----------------------------.
#     | SSS  SSS  M   M  EEEE     |
#     | S    S    MM MM  E        |
#     | SSS  SSS  M M M  EEE      |
#     |   S    S  M   M  E        |
#     | SSS  SSS  M   M  EEEE     |
#     |       haoran yu          |
#     '----------------------------'
