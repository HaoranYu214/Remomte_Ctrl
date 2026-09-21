"""Timing helpers for Segment Arb baseline holds."""

import math


def nls_padding_time(params):
    """Return the baseline hold from disturb to half-PUND, in seconds.

    TotalDelay runs from the end of the preset falling edge to the start
    of the first half-PUND rising edge. Existing delays and both disturb
    edges count toward it: padding = TotalDelay - 2*Delaytime - 2*Rt_s - Dwell.
    Dwell is the flat-top duration, not the full disturb pulse duration.
    The hold uses the entry's baseline offset (0 V when offset is zero).

    KXCI manual 7-52: a segment in the default 10 V range lasts 20 ns to
    1 s, with 10 ns resolution. Exact zero padding is omitted. Actual
    hardware timing is limited by that resolution; no software sleep is used.
    """
    total, delay, edge, dwell = (
        float(params[name]) for name in ("TotalDelay", "Delaytime", "Rt_s", "Dwell")
    )
    if not all(math.isfinite(v) and v > 0 for v in (total, delay, edge, dwell)):
        raise ValueError("NLS TotalDelay, Delaytime, Rt_s and Dwell must be finite and positive.")
    occupied = 2 * delay + 2 * edge + dwell
    padding = total - occupied
    if math.isclose(total, occupied, rel_tol=0.0, abs_tol=1e-15):
        return 0.0
    if padding < 0:
        raise ValueError(
            f"NLS TotalDelay={total:g} s is too short; requires at least {occupied:g} s "
            "(2*Delaytime + 2*Rt_s + Dwell)."
        )
    if padding < 20e-9 or padding > 1.0:
        raise ValueError("NLS padding segment must be zero or between 20 ns and 1 s (10 V range).")
    return padding
