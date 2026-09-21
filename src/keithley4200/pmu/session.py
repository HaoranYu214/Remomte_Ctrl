"""Helpers for PMU test sessions.

This module centralizes the repetitive instrument lifecycle used by the
top-level test scripts:
1. connect to the 4200A,
2. apply the PMU string terminators,
3. expose the `query` callable used by the existing test helpers,
4. always switch outputs off before disconnecting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Tuple

from ..transport import Communications
from .pmu_tests import power_off_outputs


@dataclass
class PMUSession:
    """Context manager for a single PMU test run."""

    instrument_resource: str
    channels: Iterable[int] = field(default_factory=tuple)
    timeout: Optional[int] = None
    write_termination: str = "\0"
    read_termination: str = "\0"

    def __post_init__(self) -> None:
        self.channels = tuple(self.channels)
        self.client: Optional[Communications] = None

    def connect(self) -> "PMUSession":
        """Open the VISA session and configure terminators for PMU queries."""
        try:
            self.client = Communications(self.instrument_resource)
            self.client.connect(timeout=self.timeout)
            instrument = self.client._instrument_object
            if instrument is None:
                raise RuntimeError("Failed to connect to the instrument.")
            instrument.write_termination = self.write_termination
            instrument.read_termination = self.read_termination
        except BaseException:
            if self.client is not None:
                self.client.close()
            self.client = None
            raise
        return self

    @property
    def query(self):
        """Expose the underlying query callable expected by the test helpers."""
        if self.client is None:
            raise RuntimeError("PMUSession is not connected.")
        return self.client.query

    def power_off(self) -> None:
        """Turn off the configured channels if a connection is active."""
        if self.client is None or not self.channels:
            return
        power_off_outputs(self.client.query, self.channels)

    def disconnect(self) -> None:
        """Close the VISA connection if it is still open."""
        if self.client is None:
            return
        self.client.close()
        self.client = None

    def __enter__(self) -> "PMUSession":
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            self.power_off()
        finally:
            self.disconnect()
        return False
