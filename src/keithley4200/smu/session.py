# Copyright (c) 2026 ssme / Haoran Yu.
"""Safe connection lifecycle for repository 4200A-SCS SMU scripts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..transport import Communications


@dataclass
class SMUSession:
    """Connect to KXCI and expose the query callable used by SMU helpers.

    Output shutdown is performed by the System/User Mode helper that knows the
    active channels. The session always closes VISA resources, including when
    the experiment raises an exception.
    """

    instrument_resource: str
    timeout: Optional[int] = None
    write_termination: str = "\0"
    read_termination: str = "\0"
    echo_commands: bool = False

    def __post_init__(self):
        self.client = None

    def connect(self):
        try:
            self.client = Communications(self.instrument_resource)
            self.client.connect(timeout=self.timeout)
            instrument = self.client._instrument_object
            if instrument is None:
                raise RuntimeError("Failed to connect to the 4200A-SCS.")
            instrument.write_termination = self.write_termination
            instrument.read_termination = self.read_termination
            self.client._echo_cmds = self.echo_commands
        except BaseException:
            if self.client is not None:
                self.client.close()
            self.client = None
            raise
        return self

    @property
    def query(self):
        if self.client is None:
            raise RuntimeError("SMUSession is not connected.")
        return self.client.query

    def disconnect(self):
        if self.client is not None:
            self.client.close()
            self.client = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.disconnect()
        return False
