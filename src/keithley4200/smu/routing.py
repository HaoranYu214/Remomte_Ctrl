"""Explicit SMU-to-probe routing for systems fitted with 4225-RPMs.

Runnable experiments describe each physical connection with a mapping such as::

    {
        1: "rpm:PMU1-1",
        2: "rpm:PMU1-2",
        3: "direct",
        4: "direct",
    }

Only active channels are switched.  Direct connections do not send an RPM
command; RPM connections use the System Mode ``RP`` command documented by
Keithley.  Mode 2 connects the SMU (blue LED), and mode 0 restores the pulse
path (green LED).

Manual reference: 4200A-KXCI-907-01 Rev. D (May 2024), printed pages 7-67 to
7-68 (``RP`` usage, LED state, and safe shutdown).  The equivalent current
command ``:PMU:RPM:CONFIGURE`` is documented on printed pages 7-22 to 7-23.
"""

from __future__ import annotations

import re

from .common import normalize_channels, raise_for_kxci_error, validate_channel


RPM_MODE_PULSE = 0
RPM_MODE_SMU = 2

DIRECT_CONNECTION = "direct"
_RPM_CONNECTION = re.compile(r"^rpm\s*:\s*(PMU[1-9]-[12])$", re.IGNORECASE)


def _normalize_connection(connection, *, channel):
    if not isinstance(connection, str):
        raise ValueError(
            f"SMU{channel} connection must be 'direct' or 'rpm:PMUN-C'."
        )
    connection = connection.strip()
    if connection.lower() == DIRECT_CONNECTION:
        return DIRECT_CONNECTION
    match = _RPM_CONNECTION.fullmatch(connection)
    if match is None:
        raise ValueError(
            f"Invalid SMU{channel} connection {connection!r}; expected "
            "'direct' or an RPM such as 'rpm:PMU1-1'."
        )
    return f"rpm:{match.group(1).upper()}"


def normalize_smu_connections(connections, *, active_channels):
    """Validate a complete connection entry for every active SMU channel."""
    active_channels = normalize_channels(active_channels, name="active_channels")
    if connections is None:
        # Backward-compatible library behavior. Runnable experiments should
        # pass an explicit map so hardware topology is never inferred.
        return {channel: DIRECT_CONNECTION for channel in active_channels}
    if not hasattr(connections, "items"):
        raise ValueError("smu_connections must be a channel-to-connection mapping.")

    normalized = {}
    for raw_channel, connection in connections.items():
        channel = validate_channel(raw_channel, name="smu_connections channel")
        if channel in normalized:
            raise ValueError(f"smu_connections contains duplicate channel {channel}.")
        normalized[channel] = _normalize_connection(connection, channel=channel)

    missing = set(active_channels).difference(normalized)
    if missing:
        raise ValueError(
            "smu_connections is missing active channel(s): "
            + ", ".join(f"SMU{channel}" for channel in sorted(missing))
        )

    rpm_targets = [
        connection.split(":", 1)[1]
        for channel, connection in normalized.items()
        if channel in active_channels and connection.startswith("rpm:")
    ]
    if len(rpm_targets) != len(set(rpm_targets)):
        raise ValueError("Active SMU channels must not share the same RPM target.")
    return {channel: normalized[channel] for channel in active_channels}


# RP modes (7-67): 0 PMU, 1 CV two-wire, 2 SMU, 3 CV four-wire; this helper selects SMU routing.
def connect_smus_to_probes(query, active_channels, smu_connections):
    """Switch RPM-backed active SMUs to the probe outputs.

    Returns the RPM hardware IDs that were switched.  The caller must restore
    these IDs only after all SMU outputs have entered standby or been disabled.
    """
    connections = normalize_smu_connections(
        smu_connections,
        active_channels=active_channels,
    )
    rpm_targets = tuple(
        connection.split(":", 1)[1]
        for connection in connections.values()
        if connection.startswith("rpm:")
    )
    if not rpm_targets:
        return ()

    switched = []
    try:
        query("SS")
        for rpm_target in rpm_targets:
            query(f"RP {rpm_target}, {RPM_MODE_SMU}")
            switched.append(rpm_target)
        raise_for_kxci_error(query, context="RPM switch to SMU path")
        return tuple(switched)
    except BaseException:
        restore_rpms_to_pulse(query, switched, best_effort=True)
        raise


def restore_rpms_to_pulse(query, rpm_targets, *, best_effort=False):
    """Return selected RPMs to their default PMU/pulse path."""
    rpm_targets = tuple(str(target).strip().upper() for target in rpm_targets)
    if not rpm_targets:
        return

    try:
        query("SS")
        for rpm_target in rpm_targets:
            if not re.fullmatch(r"PMU[1-9]-[12]", rpm_target):
                raise ValueError(f"Invalid RPM target {rpm_target!r}.")
            query(f"RP {rpm_target}, {RPM_MODE_PULSE}")
        raise_for_kxci_error(query, context="RPM restore to pulse path")
    except BaseException:
        if not best_effort:
            raise
