"""Common KXCI validation and error-queue helpers for SMU control."""

# Shared by both SMU command families.

from __future__ import annotations

import re


_ERROR_CODE = re.compile(r"\(\s*(-?\d+)\s*\)\s*$")


def normalize_channels(channels, *, name="channels"):
    """Return unique KXCI channel numbers in their configured order."""
    normalized = []
    for raw_channel in channels:
        channel = int(raw_channel)
        if channel != raw_channel or not 1 <= channel <= 9:
            raise ValueError(f"{name} must contain integer channels from 1 to 9.")
        if channel in normalized:
            raise ValueError(f"{name} contains duplicate channel {channel}.")
        normalized.append(channel)
    if not normalized:
        raise ValueError(f"{name} must contain at least one channel.")
    return tuple(normalized)


def validate_channel(channel, *, name="channel"):
    """Validate and return one KXCI channel number."""
    return normalize_channels((channel,), name=name)[0]


def clear_kxci_error(query):
    """Clear errors so later checks refer only to the current configuration."""
    query(":ERROR:LAST:CLEAR")


def get_kxci_error(query):
    """Return the current KXCI error text, or ``None`` when no error is stored."""
    response = str(query(":ERROR:LAST:GET")).strip()
    normalized = response.upper().replace("_", " ")
    if normalized in ("", "0", "ACK") or "NO ERROR" in normalized:
        return None
    code_match = _ERROR_CODE.search(response)
    if code_match is not None and int(code_match.group(1)) == 0:
        return None
    return response


def raise_for_kxci_error(query, *, context="KXCI configuration"):
    """Raise immediately when KXCI retained a command/setup error."""
    error = get_kxci_error(query)
    if error is not None:
        raise RuntimeError(f"{context} failed: {error}")
