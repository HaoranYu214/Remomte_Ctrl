"""4200A-SCS SMU User Mode spot-source and measurement helpers."""

from __future__ import annotations

import operator

from .common import clear_kxci_error, raise_for_kxci_error, validate_channel
from .data_processing import parse_kxci_reading
from .routing import connect_smus_to_probes, restore_rpms_to_pulse


def initialize_user_mode(query, *, active_channels=(), smu_connections=None):
    """Reset User Mode and optionally connect RPM-backed SMUs to probes.

    Returns the RPM targets that the caller must restore after turning off all
    active SMU sources.
    """
    query("EM 1,0")
    clear_kxci_error(query)
    query("BC")
    query("*RST")
    rpm_targets = ()
    if active_channels:
        rpm_targets = connect_smus_to_probes(
            query,
            active_channels,
            smu_connections,
        )
    query("US")
    return rpm_targets


def restore_user_mode_rpms(query, rpm_targets, *, best_effort=False):
    """Restore RPMs after User Mode sources have been turned off."""
    restore_rpms_to_pulse(query, rpm_targets, best_effort=best_effort)


# DV range_code (5-33): 0 auto, 1=20 V, 2/3=200 V; 4=200 mV and 5=2 V require a preamplifier.
# current_compliance is in A, separate from source/measurement ranges; choose a DUT-specific safe limit.
def source_voltage(query, channel, voltage, current_compliance, *, range_code=0):
    """Configure an SMU channel with DV in User Mode."""
    channel = validate_channel(channel)
    try:
        range_code = operator.index(range_code)
    except TypeError as exc:
        raise ValueError("Voltage range_code must be an integer from 0 through 5.") from exc
    if range_code not in (0, 1, 2, 3, 4, 5):
        raise ValueError("Voltage range_code must be 0 through 5.")
    query(f"DV{channel}, {range_code}, {voltage}, {current_compliance}")
    raise_for_kxci_error(query, context=f"DV setup for CH{channel}")


def source_current(query, channel, current, voltage_compliance, *, range_code=0):
    """Configure an SMU channel with DI in User Mode."""
    channel = validate_channel(channel)
    try:
        range_code = operator.index(range_code)
    except TypeError as exc:
        raise ValueError("Current range_code must be an integer from 0 through 13.") from exc
    if range_code not in range(14):
        raise ValueError("Current range_code must be 0 through 13.")
    query(f"DI{channel}, {range_code}, {current}, {voltage_compliance}")
    raise_for_kxci_error(query, context=f"DI setup for CH{channel}")


def measure_current(query, channel):
    channel = validate_channel(channel)
    value, _status = parse_kxci_reading(query(f"TI{channel}"))
    return value


def measure_voltage(query, channel):
    channel = validate_channel(channel)
    value, _status = parse_kxci_reading(query(f"TV{channel}"))
    return value


def power_off_voltage_source(query, channel):
    channel = validate_channel(channel)
    query(f"DV{channel}")


def power_off_current_source(query, channel):
    channel = validate_channel(channel)
    query(f"DI{channel}")


def power_off_user_channels(query, voltage_channels=(), current_channels=()):
    """Best-effort User Mode shutdown for channels configured by DV or DI."""
    for channel in voltage_channels:
        try:
            power_off_voltage_source(query, channel)
        except Exception:
            pass
    for channel in current_channels:
        try:
            power_off_current_source(query, channel)
        except Exception:
            pass
