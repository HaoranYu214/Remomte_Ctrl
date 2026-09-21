"""Shared PyVISA transport for 4200A-SCS PMU and SMU control.

The vendor ``instrcomms.py`` example is kept unchanged under ``reference``.
This maintained transport deliberately propagates VISA errors so experiments
fail promptly instead of continuing with an empty response.
"""

from __future__ import annotations

import pyvisa as visa


class Communications:
    """Open, read, write, query, and close one VISA instrument resource."""

    def __init__(self, instrument_resource_string=None):
        self._instrument_resource_string = instrument_resource_string
        self._resource_manager = visa.ResourceManager()
        self._instrument_object = None
        self._timeout = 20000
        self._echo_cmds = False

    def connect(self, instrument_resource_string=None, timeout=None):
        if instrument_resource_string is not None:
            self._instrument_resource_string = instrument_resource_string
        if not self._instrument_resource_string:
            raise ValueError("An instrument VISA resource string is required.")
        if self._resource_manager is None:
            self._resource_manager = visa.ResourceManager()
        self._instrument_object = self._resource_manager.open_resource(
            self._instrument_resource_string
        )
        self._instrument_object.timeout = self._timeout if timeout is None else timeout
        if timeout is not None:
            self._timeout = timeout
        if "SOCKET" in self._instrument_resource_string.upper():
            self._instrument_object.send_end = True
        return self

    def disconnect(self):
        if self._instrument_object is not None:
            self._instrument_object.close()
            self._instrument_object = None

    def close(self):
        """Close the instrument and VISA resource manager."""
        self.disconnect()
        if self._resource_manager is not None:
            self._resource_manager.close()
            self._resource_manager = None

    def _echo(self, command):
        if self._echo_cmds:
            print(command)

    def write(self, command: str):
        """Send one command without reading a response."""
        if self._instrument_object is None:
            raise RuntimeError("No instrument connection is open.")
        self._echo(command)
        return self._instrument_object.write(command)

    def read(self):
        """Read one response from the open instrument."""
        if self._instrument_object is None:
            raise RuntimeError("No instrument connection is open.")
        return self._instrument_object.read()

    def query(self, command: str):
        """Send one command and return its stripped response."""
        if self._instrument_object is None:
            raise RuntimeError("No instrument connection is open.")
        self._echo(command)
        return self._instrument_object.query(command).rstrip()
