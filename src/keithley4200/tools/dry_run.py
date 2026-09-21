# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.
r"""Generic dry-run runner for PMU test scripts.

Usage:
    python src\keithley4200\tools\dry_run.py
    python src\keithley4200\tools\dry_run.py measurements\pmu\ftj\ftj_RV2.py
    python src\keithley4200\tools\dry_run.py --no-save measurements\pmu\ftj\ftj_RV2.py

The target script is executed, but instrument communication is intercepted and
printed instead of sent to the real PMU.
"""

from __future__ import annotations

import argparse
import runpy
import sys
import time
from pathlib import Path


# Locate the source checkout without assuming a fixed directory depth.
# Installed packages can still dry-run an explicitly supplied script.
REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents
     if (parent / "pyproject.toml").is_file() and (parent / "measurements").is_dir()),
    None,
)
SRC_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCRIPT = (
    REPO_ROOT / "measurements" / "pmu" / "ftj" / "ftj_RV2.py"
    if REPO_ROOT is not None else None
)

# Edit this path when you want to click "Run" on dry_run.py from the IDE.
TARGET_SCRIPT = DEFAULT_SCRIPT
NO_SAVE = True


class DryRunState:
    """Command-driven synthetic data, for control-flow checks, not device physics.

    Waveform segments use 32 samples; spot segments use one sample. Unmeasured
    segments advance time without producing records. Unsupported/oversized
    acquisitions fail explicitly instead of returning misleading dummy points.
    """

    MAX_POINTS = 65_536
    SAMPLES_PER_SEGMENT = 32

    def __init__(self) -> None:
        self.command_index = 0
        self._reset()

    def _reset(self):
        self.sequences = {}
        self.execution = {}
        self.settings = {}
        self.records = {}
        self.segment_arb = False

    def print_command(self, command: str) -> None:
        self.command_index += 1
        print(f"{self.command_index:03d}: {command}")

    def query_response(self, command: str) -> str:
        name, _, payload = command.strip().partition(" ")
        name = name.upper()
        args = [part.strip() for part in payload.split(",") if part.strip()]
        if name == ":PMU:INIT":
            self._reset()
            self.segment_arb = bool(int(args[0]))
        elif name.startswith(":PMU:SARB:SEQ:"):
            key = name.removeprefix(":PMU:SARB:SEQ:")
            append = key.endswith(":ADD")
            key = key.removesuffix(":ADD")
            if key in {"STARTV", "STOPV", "TIME", "MEAS:TYPE", "MEAS:START", "MEAS:STOP", "SSR"}:
                sequence = self.sequences.setdefault((int(args[0]), int(args[1])), {})
                values = [float(value) for value in args[2:]]
                if append:
                    sequence[key].extend(values)
                else:
                    sequence[key] = values
        elif name == ":PMU:SARB:WFM:SEQ:LIST":
            self.execution[int(args[0])] = [
                (int(args[i]), int(args[i + 1])) for i in range(1, len(args), 2)
            ]
        elif name == ":PMU:EXECUTE":
            self.records = self._generate_segments() if self.segment_arb else self._generate_pulses()
        elif name == ":PMU:DATA:COUNT?":
            return str(len(self.records.get(int(args[0]), [])))
        elif name == ":PMU:DATA:GET":
            channel, start, count = map(int, args)
            return ";".join(
                ",".join(format(value, ".12g") for value in row)
                for row in self.records.get(channel, [])[start:start + count]
            )
        elif name in {":PMU:PULSE:TRAIN", ":PMU:PULSE:TIMES", ":PMU:MEASURE:PIV",
                      ":PMU:SWEEP:PULSE:AMPLITUDE", ":PMU:TIMES:WAVEFORM", ":PMU:TIMES:PIV"}:
            self.settings[name, int(args[0])] = [float(value) for value in args[1:]]
        elif name in {":PMU:MEASURE:MODE", ":PMU:PULSE:BURST:COUNT"}:
            self.settings[name] = int(args[0])
        return "0"

    def _append(self, rows, voltage, timestamp):
        if len(rows) >= self.MAX_POINTS:
            raise ValueError("Dry-run acquisition exceeds 65536 synthetic points; reduce loops for this offline check.")
        rows.append([voltage, voltage * 1e-6, timestamp, 0])

    def _generate_segments(self):
        result = {}
        for channel, execution in self.execution.items():
            rows = result[channel] = []
            elapsed = 0.0
            for sequence_id, loops in execution:
                sequence = self.sequences[channel, sequence_id]
                durations = sequence["TIME"]
                modes = sequence["MEAS:TYPE"]
                if not any(modes):
                    elapsed += sum(durations) * loops
                    continue
                for _ in range(loops):
                    for i, duration in enumerate(durations):
                        mode = int(modes[i])
                        if not sequence.get("SSR", [1]*len(durations))[i] and mode:
                            raise NotImplementedError("Dry-run cannot simulate measurements on an SSR-open channel.")
                        if mode in (3, 4):
                            raise NotImplementedError("Dry-run does not model averaged Segment Arb modes 3/4.")
                        count = self.SAMPLES_PER_SEGMENT if mode == 2 else int(mode == 1)
                        start, stop = sequence["MEAS:START"][i], sequence["MEAS:STOP"][i]
                        for j in range(count):
                            offset = start + (j + 0.5) / count * (stop - start)
                            voltage = sequence["STARTV"][i] + (
                                sequence["STOPV"][i] - sequence["STARTV"][i]
                            ) * offset / duration
                            self._append(rows, voltage, elapsed + offset)
                        elapsed += duration
        # A simple two-terminal resistor placeholder when both channels sample
        # the same instants. No ferroelectric/memristor response is simulated.
        if len(result) == 2:
            first, second = result.values()
            if len(first) == len(second):
                for a, b in zip(first, second):
                    if abs(a[2] - b[2]) < 1e-12:
                        a[1] = (a[0] - b[0]) * 1e-6
                        b[1] = -a[1]
        return result

    def _generate_pulses(self):
        result = {}
        mode = self.settings.get(":PMU:MEASURE:MODE", 1)
        if mode not in (0, 1, 2):
            raise NotImplementedError("Dry-run does not model averaged pulse modes 3/4.")
        channels = [key[1] for key in self.settings if isinstance(key, tuple) and key[0] == ":PMU:PULSE:TIMES"]
        sweeps = {}
        for channel in channels:
            sweep = self.settings.get((":PMU:SWEEP:PULSE:AMPLITUDE", channel))
            if sweep:
                start, stop, step, base, dual = sweep
                if step == 0:
                    raise ValueError("Dry-run sweep step must be nonzero.")
                count = round(abs((stop - start) / step)) + 1
                if count > self.MAX_POINTS:
                    raise ValueError("Dry-run pulse sweep is too large.")
                values = [start + (stop - start) * i / max(count - 1, 1) for i in range(count)]
                sweeps[channel] = (base, values + values[-2::-1] if dual else values)
        sweep_count = max((len(values) for _, values in sweeps.values()), default=1)
        for channel in channels:
            rows = result[channel] = []
            if mode == 0:
                continue
            period, width, rise, fall, delay = self.settings[":PMU:PULSE:TIMES", channel]
            base, levels = sweeps.get(channel, (0, []))
            if not levels:
                base, level = self.settings[":PMU:PULSE:TRAIN", channel]
                levels = [level] * sweep_count
            burst = self.settings.get(":PMU:PULSE:BURST:COUNT", 1)
            if len(levels) * burst > self.MAX_POINTS:
                raise ValueError("Dry-run pulse count exceeds 65536.")
            for index in range(len(levels) * burst):
                level = levels[index // burst]
                origin = index * period
                if mode == 1:
                    high, low = self.settings.get((":PMU:MEASURE:PIV", channel), (1, 0))
                    record = []
                    for enabled, voltage, offset in ((high, level, delay + width / 2), (low, base, period - fall / 2)):
                        if enabled:
                            record.extend([voltage, voltage * 1e-6, origin + offset, 0])
                    rows.append(record)
                else:
                    for j in range(128):
                        offset = period * (j + 0.5) / 128
                        phase = offset - delay
                        if 0 <= phase < rise:
                            voltage = base + (level - base) * phase / rise
                        elif rise <= phase < width:
                            voltage = level
                        elif width <= phase < width + fall:
                            voltage = level + (base - level) * (phase - width) / fall
                        else:
                            voltage = base
                        self._append(rows, voltage, origin + offset)
        return result


class DummyInstrument:
    """Minimal stand-in for the VISA instrument object."""

    def __init__(self) -> None:
        self.timeout = 20000
        self.write_termination = "\0"
        self.read_termination = "\0"
        self.send_end = True

    def close(self) -> None:
        return


class DryRunCommunications:
    """Drop-in replacement for Communications that only prints commands."""

    def __init__(self, instrument_resource_string=None, state: DryRunState | None = None):
        self._instrument_resource_string = instrument_resource_string
        self._instrument_object = DummyInstrument()
        self._state = state or DryRunState()

    def connect(self, instrument_resource_string=None, timeout=None):
        if instrument_resource_string is not None:
            self._instrument_resource_string = instrument_resource_string
        self._state.print_command(
            f"# CONNECT {self._instrument_resource_string} timeout={timeout if timeout is not None else 20000}"
        )

    def disconnect(self):
        self._state.print_command("# DISCONNECT")

    def close(self):
        self.disconnect()

    def write(self, command: str):
        self._state.print_command(command)
        self._state.query_response(command)

    def read(self):
        return ""

    def query(self, command: str):
        self._state.print_command(command)
        return self._state.query_response(command)


class DryRunSession:
    """Drop-in replacement for PMUSession."""

    def __init__(self, instrument_resource, channels=(), timeout=None, write_termination="\0", read_termination="\0"):
        self.instrument_resource = instrument_resource
        self.channels = tuple(channels)
        self.timeout = timeout
        self.write_termination = write_termination
        self.read_termination = read_termination
        self._state = DryRunState()
        self.client = DryRunCommunications(instrument_resource, state=self._state)

    def __enter__(self):
        self.client.connect(timeout=self.timeout)
        self.client._instrument_object.write_termination = self.write_termination
        self.client._instrument_object.read_termination = self.read_termination
        self._state.print_command(
            f"# SET_TERMINATION write={self.write_termination!r} read={self.read_termination!r}"
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        for channel in self.channels:
            self.client.query(f":PMU:OUTPUT:STATE {channel}, 0")
        self.client.disconnect()
        return False

    @property
    def query(self):
        return self.client.query


def install_dry_run_hooks(no_save=False):
    """Patch imported modules so test scripts print instead of connecting."""
    for path in (SRC_ROOT, REPO_ROOT):
        if path is not None and str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import keithley4200.output as output
    import keithley4200.parameter_defaults as parameter_defaults
    import keithley4200.pmu.data_processing as data_processing
    import keithley4200.transport as transport
    import keithley4200.pmu.session as session
    import matplotlib.figure as mpl_figure
    import pandas as pd

    # Synthetic data must never change the real experiment starting ranges.
    parameter_defaults.write_current_range_defaults = (
        lambda source_path, ranges, parameter_name="params":
        print(f"# SKIP_DEFAULTS {source_path} {parameter_name}: {ranges}")
    )
    state = DryRunState()

    class SharedDryRunCommunications(DryRunCommunications):
        def __init__(self, instrument_resource_string=None):
            super().__init__(instrument_resource_string=instrument_resource_string, state=state)

    class SharedDryRunSession(DryRunSession):
        def __init__(self, instrument_resource, channels=(), timeout=None, write_termination="\0", read_termination="\0"):
            self.instrument_resource = instrument_resource
            self.channels = tuple(channels)
            self.timeout = timeout
            self.write_termination = write_termination
            self.read_termination = read_termination
            self._state = state
            self.client = SharedDryRunCommunications(instrument_resource)

    transport.Communications = SharedDryRunCommunications
    session.Communications = SharedDryRunCommunications
    session.PMUSession = SharedDryRunSession

    if no_save:
        class DummyExcelWriter:
            def __init__(self, path, *args, **kwargs):
                self.path = path

            def __enter__(self):
                print(f"# SKIP_SAVE ExcelWriter -> {self.path}")
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_save_channels_separate_excel(dfs, path, **kwargs):
            print(f"# SKIP_SAVE save_channels_separate_excel -> {path}")
            return True

        def fake_save_csv(df, path, sep=None, for_excel=True):
            print(f"# SKIP_SAVE save_csv -> {path}")
            return True

        def fake_save_excel(df, path):
            print(f"# SKIP_SAVE save_excel -> {path}")
            return True

        def fake_fig_save(self, fname, *args, **kwargs):
            print(f"# SKIP_SAVE figure.savefig -> {fname}")

        def fake_df_to_excel(self, excel_writer, *args, **kwargs):
            print(f"# SKIP_SAVE DataFrame.to_excel -> {excel_writer}")

        def fake_df_to_csv(self, path_or_buf=None, *args, **kwargs):
            print(f"# SKIP_SAVE DataFrame.to_csv -> {path_or_buf}")

        # Name previews must not consume real acquisition numbers in no-save mode.
        output.reserve_output_stem = lambda directory, name: Path(directory) / f"{name}_r001"
        output.prepare_output_dir = lambda directory: Path(directory)
        output.save_summary_workbook = lambda rows, path, **kwargs: print(f"# SKIP_SAVE summary -> {path}")
        data_processing.save_channels_separate_excel = fake_save_channels_separate_excel
        data_processing.save_csv = fake_save_csv
        data_processing.save_excel = fake_save_excel
        mpl_figure.Figure.savefig = fake_fig_save

        pd.ExcelWriter = DummyExcelWriter
        pd.DataFrame.to_excel = fake_df_to_excel
        pd.DataFrame.to_csv = fake_df_to_csv

    time.sleep = lambda *_args, **_kwargs: None


def parse_args():
    """Parse the optional target script path."""
    parser = argparse.ArgumentParser(description="Dry-run any PMU test script.")
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write any Excel/CSV/image outputs during the dry run.",
    )
    parser.add_argument(
        "script",
        nargs="?",
        default=None,
        help="Path to the test script to execute in dry-run mode.",
    )
    return parser.parse_args()


def dry_run_script(script, no_save=True):
    """Execute any PMU test script under dry-run hooks."""
    script_path = Path(script).resolve()
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    install_dry_run_hooks(no_save=no_save)
    print(f"DRY RUN: {script_path}")
    if no_save:
        print("DRY RUN MODE: saves disabled")
    runpy.run_path(str(script_path), run_name="__main__")


def main():
    """CLI entrypoint. If no CLI script is passed, use the editable default target."""
    args = parse_args()
    script = Path(args.script) if args.script else TARGET_SCRIPT
    if script is None:
        raise ValueError("No source checkout found; pass the measurement script path explicitly.")
    no_save = args.no_save if args.script else NO_SAVE
    dry_run_script(script, no_save=no_save)


if __name__ == "__main__":
    main()
