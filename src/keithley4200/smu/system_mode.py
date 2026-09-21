# Copyright (c) 2026 ssme / Haoran Yu.
"""4200A-SCS SMU System Mode configuration and execution helpers.

System Mode is used for Clarius-style sweeps. It is separate from User Mode
DV/DI/TI/TV commands.
"""

from __future__ import annotations

import time
from .points import build_segmented_voltage_path  # Backward-compatible import location.

from .common import (
    clear_kxci_error,
    normalize_channels,
    raise_for_kxci_error,
    validate_channel,
)


SOURCE_VOLTAGE = 1
SOURCE_CURRENT = 2

FUNCTION_VAR1 = 1
FUNCTION_VAR2 = 2
FUNCTION_CONSTANT = 3
FUNCTION_VAR1_RATIO = 4
DEFAULT_AVAILABLE_CHANNELS = (1, 2, 3, 4)


def disable_system_channels(query, channels):
    """Disable explicitly listed System Mode channels on the DE page."""
    channels = normalize_channels(channels, name="available_channels")
    query("DE")
    for channel in channels:
        query(f"CH{channel}")
    return channels


def initialize_system_mode(query, *, available_channels=DEFAULT_AVAILABLE_CHANNELS):
    """Reset System Mode and disable every known SMU before redefining use."""
    query("EM 1,0")
    clear_kxci_error(query)
    query("BC")
    query("*RST")
    return disable_system_channels(query, available_channels)


def configure_auto_standby(query, channels, *, enabled=True):
    """Put active SMUs in standby automatically when a test completes."""
    for channel in normalize_channels(channels, name="active_channels"):
        query(f"ST {channel}, {1 if enabled else 0}")


def shutdown_system_mode(query, channels):
    """Best-effort channel disable after setup or execution has stopped.

    ``execute_and_wait`` owns test abortion because it knows whether ``ME1``
    may have reached the instrument.  In particular, do not send ``MD`` while
    B4 (Busy) is set: KXCI rejects page changes during test execution (-980).
    """
    commands = ["DE"]
    try:
        channels = normalize_channels(channels, name="available_channels")
    except (TypeError, ValueError):
        channels = ()
    commands.extend(f"CH{channel}" for channel in channels)
    for command in commands:
        try:
            query(command)
        except BaseException:
            pass


def define_channel(
    query,
    channel,
    voltage_name,
    current_name,
    *,
    source_mode=SOURCE_VOLTAGE,
    source_function=FUNCTION_CONSTANT,
):
    channel = validate_channel(channel)
    for name, value in (("voltage_name", voltage_name), ("current_name", current_name)):
        if not value or len(str(value)) > 6:
            raise ValueError(f"{name} must contain 1 to 6 characters.")
    if source_mode not in (SOURCE_VOLTAGE, SOURCE_CURRENT, 3):
        raise ValueError("source_mode must be voltage, current, or common.")
    if source_function not in (
        FUNCTION_VAR1,
        FUNCTION_VAR2,
        FUNCTION_CONSTANT,
        FUNCTION_VAR1_RATIO,
    ):
        raise ValueError("source_function must be a valid KXCI CH function.")
    query(
        f"CH{channel}, '{voltage_name}', '{current_name}', "
        f"{source_mode}, {source_function}"
    )


# SMU voltage source bounds (5-16, 5-33): -210..210 V, further constrained by
# the installed module/range. Current compliance maximum magnitude is 0.105 A
# for 4200/4201 or 1.05 A for 4210/4211; this is not a DUT safety recommendation.
# VL minimum compliance is 100 pA with a preamp, 100 nA without (5-16).
def configure_constant_voltage(query, channel, voltage, current_compliance):
    channel = validate_channel(channel)
    query(f"VC{channel}, {voltage}, {current_compliance}")


def configure_constant_current(query, channel, current, voltage_compliance):
    channel = validate_channel(channel)
    query(f"IC{channel}, {current}, {voltage_compliance}")


# RG sets the autorange floor (5-41), not current compliance; source helpers configure compliance separately.
# Range floor: 100 nA without a preamp, down to 1 pA with one; maximum
# measurement range is 100 mA or 1 A depending on the SMU model (5-41).
def configure_current_range(query, channel, current_range):
    """Set the lowest current measurement range for one SMU channel.

    Use ``None`` or ``"auto"`` to leave the instrument in its default autorange
    behavior. Numeric values send the System Mode ``RG`` command.
    """
    if current_range is None:
        return
    channel = validate_channel(channel)
    if isinstance(current_range, str):
        if current_range.strip().lower() in ("auto", "default", ""):
            return
        current_range = float(current_range)
    current_range = float(current_range)
    if current_range <= 0:
        raise ValueError("current_range must be positive, 'auto', or None.")
    query(f"RG {channel}, {current_range:.9g}")


def configure_linear_voltage_sweep(
    query,
    *,
    start,
    stop,
    step,
    current_compliance,
    sweep_variable=1,
):
    validate_linear_sweep(start, stop, step)
    query(f"VR{sweep_variable}, {start}, {stop}, {step}, {current_compliance}")


def configure_linear_current_sweep(
    query,
    *,
    start,
    stop,
    step,
    voltage_compliance,
    sweep_variable=1,
):
    validate_linear_sweep(start, stop, step)
    query(f"IR{sweep_variable}, {start}, {stop}, {step}, {voltage_compliance}")


def linear_sweep_point_count(start, stop, step):
    """Return the KXCI VAR1 point count defined by the programming manual."""
    start = float(start)
    stop = float(stop)
    step = float(step)
    if step == 0:
        raise ValueError("Linear sweep step must be nonzero.")
    return int(abs((stop - start) / step) + 1.5)


def validate_linear_sweep(start, stop, step):
    """Reject linear sweeps that KXCI cannot represent safely."""
    point_count = linear_sweep_point_count(start, stop, step)
    if point_count < 1:
        raise ValueError("Linear sweep must contain at least one point.")
    if point_count > 1024:
        raise ValueError(
            f"KXCI VAR1 sweeps are limited to 1024 points; requested {point_count}."
        )
    return point_count


# VL accepts at most 4096 expanded list points (5-16), not 4096 turning points.
def configure_list_voltage_sweep(
    query,
    values,
    *,
    channel,
    current_compliance,
    mode=1,
):
    """Configure a voltage list on the actual SMU/VS channel number."""
    values = [float(value) for value in values]
    channel = validate_channel(channel)
    if not values:
        raise ValueError("values must contain at least one voltage.")
    if len(values) > 4096:
        raise ValueError("KXCI list sweeps are limited to 4096 points.")
    value_text = ",".join(f"{float(value):.12g}" for value in values)
    if mode not in (0, 1):
        raise ValueError("List sweep mode must be 0 (subordinate) or 1 (master).")
    query(f"VL{channel},{mode},{current_compliance},{value_text}")




# DT: 0-6.553 s; HT: 0-655.3 s; IT1/2/3: 0.1/1/10 PLC (5-10, 5-12, 5-39).
# IT4 custom values: delay/filter factors 0-100 and integration 0.01-10 PLC.
# Host-side timeout/settle parameters are software policy, not these KXCI delays.
def configure_timing(
    query,
    *,
    hold_time=0.0,
    sweep_delay=0.0,
    integration="IT1",
):
    """Configure hold, per-point delay, and SMU integration settings.

    integration accepts IT1/IT2/IT3, or a complete custom command such as
    ``IT4, delay_factor, filter_factor, aperture_plc``.
    """
    hold_time = float(hold_time)
    sweep_delay = float(sweep_delay)
    if hold_time < 0:
        raise ValueError("hold_time must be nonnegative.")
    if not 0 <= sweep_delay <= 6.553:
        raise ValueError("sweep_delay must be between 0 and 6.553 seconds.")
    query(f"HT {hold_time:g}")
    query(f"DT {sweep_delay:g}")
    integration = str(integration).strip()
    if not integration.upper().startswith("IT"):
        raise ValueError("integration must be an IT command.")
    query(integration)


def configure_measurement_list(
    query,
    variables,
    *,
    display_mode=2,
    current_ranges=None,
):
    variables = [str(variable) for variable in variables]
    if not variables or len(variables) > 6:
        raise ValueError("KXCI LI requires between 1 and 6 variables.")
    invalid_variables = [
        variable
        for variable in variables
        if not variable
        or (
            len(variable) > 6
            and not (
                len(variable) == 7
                and variable[-1].upper() in {"T", "S"}
                and len(variable[:-1]) <= 6
            )
        )
    ]
    if invalid_variables:
        raise ValueError(
            "KXCI measurement names must contain at most 6 characters; "
            "a seventh character is allowed only for a T/S suffix."
        )
    variable_text = ", ".join(f"'{variable}'" for variable in variables)
    query(f"SM DM{display_mode}")
    if current_ranges:
        for channel, current_range in current_ranges:
            configure_current_range(query, channel, current_range)
    query(f"LI {variable_text}")


def estimate_smu_timeout_s(
    point_count,
    *,
    hold_time=0.0,
    sweep_delay=0.0,
    integration="IT1",
    line_frequency_hz=50.0,
    safety_factor=3.0,
    fixed_overhead_s=60.0,
    minimum_timeout_s=300.0,
):
    """Return a conservative wall-clock timeout for one System Mode sweep.

    IT1, IT2, and IT3 use 0.1, 1, and 10 power-line cycles respectively.
    For a custom ``IT4,...`` command, the fourth field is used as its aperture
    in PLC.  An unrecognised custom form falls back to 10 PLC so automatic
    timeout remains conservative.  This is only a software watchdog; it does
    not change instrument timing or the programmed waveform.
    """
    point_count = int(point_count)
    if point_count <= 0:
        raise ValueError("point_count must be positive.")
    hold_time = float(hold_time)
    sweep_delay = float(sweep_delay)
    line_frequency_hz = float(line_frequency_hz)
    safety_factor = float(safety_factor)
    fixed_overhead_s = float(fixed_overhead_s)
    minimum_timeout_s = float(minimum_timeout_s)
    if hold_time < 0 or sweep_delay < 0:
        raise ValueError("hold_time and sweep_delay must be nonnegative.")
    if line_frequency_hz <= 0 or safety_factor <= 0:
        raise ValueError("line_frequency_hz and safety_factor must be positive.")
    if fixed_overhead_s < 0 or minimum_timeout_s <= 0:
        raise ValueError("Timeout overhead must be nonnegative and minimum positive.")

    integration_text = str(integration).strip().upper()
    aperture_plc = {"IT1": 0.1, "IT2": 1.0, "IT3": 10.0}.get(integration_text)
    if aperture_plc is None and integration_text.startswith("IT4"):
        fields = [field.strip() for field in integration_text.split(",")]
        try:
            aperture_plc = float(fields[3])
        except (IndexError, ValueError):
            aperture_plc = 10.0
    if aperture_plc is None or aperture_plc <= 0:
        aperture_plc = 10.0

    aperture_s = aperture_plc / line_frequency_hz
    programmed_time_s = hold_time + point_count * (sweep_delay + aperture_s)
    return max(
        minimum_timeout_s,
        programmed_time_s * safety_factor + fixed_overhead_s,
    )


def resolve_smu_timeout_s(
    timeout_s,
    *,
    point_count,
    hold_time=0.0,
    sweep_delay=0.0,
    integration="IT1",
):
    """Resolve the optional sweep watchdog policy.

    ``None``/``"off"`` means no overall test deadline. ``"auto"`` requests a
    point-count estimate, and a positive numeric value is a fixed number of
    seconds. VISA still applies its own timeout to each individual query.
    """
    if timeout_s is None or (
        isinstance(timeout_s, str)
        and timeout_s.strip().lower() in {"", "none", "off", "disabled"}
    ):
        return None
    if isinstance(timeout_s, str) and timeout_s.strip().lower() in {
        "auto",
        "default",
    }:
        return estimate_smu_timeout_s(
            point_count,
            hold_time=hold_time,
            sweep_delay=sweep_delay,
            integration=integration,
        )
    resolved = float(timeout_s)
    if resolved <= 0:
        raise ValueError("timeout_s must be positive, None/'off', or 'auto'.")
    return resolved


def execute_and_wait(
    query,
    *,
    execution_mode=1,
    timeout_s=300.0,
    poll_interval_s=0.2,
):
    """Start a System Mode test and wait for SP to report completion."""
    poll_interval_s = float(poll_interval_s)
    if timeout_s is not None:
        timeout_s = float(timeout_s)
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive or None.")
    if poll_interval_s < 0:
        raise ValueError("poll_interval_s must be nonnegative.")
    query("MD")
    measurement_may_be_running = False
    try:
        # Set this before query(): the command may reach KXCI even if reading
        # its ACK later raises a VISA exception.
        measurement_may_be_running = True
        query(f"ME{execution_mode}")
        deadline = None if timeout_s is None else time.monotonic() + timeout_s
        while True:
            response = query("SP").strip()
            try:
                status = int(response)
            except ValueError:
                status = None
                raise_for_kxci_error(query, context="SMU execution")
            data_ready = status is not None and bool(status & 0b00000001)
            busy = status is not None and bool(status & 0b00010000)
            if data_ready and not busy:
                raise_for_kxci_error(query, context="SMU execution")
                return status
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(
                    f"SMU System Mode test did not finish within {timeout_s:g} s; "
                    f"last SP response={response!r}."
                )
            time.sleep(poll_interval_s)
    except BaseException:
        if measurement_may_be_running:
            try:
                # ME1/ME2/ME3 were issued from the MD page.  ME4 is therefore
                # the valid first command while the test is still Busy; an MD
                # page command here would itself generate KXCI error -980.
                query("ME4")
            except BaseException:
                pass
        raise
