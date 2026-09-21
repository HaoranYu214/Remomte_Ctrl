"""Short, grouped output names and atomic reservations for measurement runs.

Reserve ONCE per acquisition, then append .xlsx / _i2.png / ... to that stem.
Reservations are permanent so an interrupted run's number is never reused.
"""

from datetime import datetime
from pathlib import Path
import json
import math
import re


# saved_at/time records save or summary time; r001 identifies an output group, not a test mode.
# Saved parameter values retain their caller-defined meaning:
# PREVIEW_ONLY: preview instead of acquisition; SAVE_WAVEFORM_PREVIEW: extra plot;
# SAVE_EVERY_RUN: per-run results (endurance summaries are still maintained).
# MeasureSquare disables acquisition of the write segment, not its output.
# Booleans (True/False or 1/0) must not be confused with numeric acquisition modes.
def saved_at():
    """Return an ISO timestamp with local UTC offset and microseconds."""
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def voltage_tag(value):
    """Readable voltage label; two integer digits and two fixed decimals.

    Labels round to 0.01 V; equal rounded labels use separate run numbers. Signed
    labels retain polarity; alphabetical order is not numeric order for negatives.
    The full precision setting remains in the workbook's Parameters sheet.
    """
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Voltage must be finite.")
    digits = f"{abs(value):.2f}"
    integer, _, fraction = digits.partition(".")
    sign = "-" if value < 0 and float(digits) != 0 else ""
    return f"{sign}{integer.zfill(2)}.{fraction}V"


def time_tag(seconds):
    """Use microseconds consistently, without rounding sub-us pulses to zero."""
    value = float(seconds)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Time must be finite and nonnegative.")
    return f"{value * 1e6:.9g}us"


def measurement_name(test, voltage=None, *details):
    """Test, voltage, then optional timing/bias tags, without a run number."""
    parts = [str(test)]
    if voltage is not None:
        parts.append(voltage_tag(voltage))
    parts.extend(str(detail) for detail in details if detail)
    return "_".join(parts)


def _validate_name(name):
    name = str(name)
    if not name or name in (".", "..") or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError("Output name must be a single valid filename component.")
    if name.endswith((" ", ".")):
        raise ValueError("Output name must not end with a space or dot.")
    return name


def _group_exists(directory, stem):
    # Check every companion, not just .xlsx. This also protects old outputs
    # that were created before the reservation ledger was introduced.
    folded = stem.casefold()
    return any(
        entry.name.casefold() == folded
        or entry.name.casefold().startswith((folded + ".", folded + "_"))
        for entry in directory.iterdir()
    )


def reserve_output_stem(directory, name):
    """Atomically claim the first free name_rNNN for an entire output group.

    .reservations is an internal persistent ledger. Exclusive file creation
    coordinates both threads and separate processes using this helper. Keep
    the ledger when moving a run directory; gaps after failures are intentional.
    This cannot coordinate an unrelated program that ignores reservations.
    """
    directory = Path(directory)
    name = _validate_name(name)
    directory.mkdir(parents=True, exist_ok=True)
    ledger = directory / ".reservations"
    ledger.mkdir(exist_ok=True)
    pattern = re.compile(re.escape(name) + r"_r(\d+)(?:$|[_.])", re.IGNORECASE)
    occupied = set()
    for parent in (directory, ledger):
        for entry in parent.iterdir():
            match = pattern.match(entry.name)
            if match:
                occupied.add(int(match.group(1)))
    index = 1
    while True:
        if index in occupied:
            index += 1
            continue
        stem = f"{name}_r{index:03d}"
        if not _group_exists(directory, stem):
            try:
                with (ledger / f"{stem.casefold()}.json").open("x", encoding="utf-8") as handle:
                    json.dump({"stem": stem, "reserved_at": saved_at()}, handle)
            except FileExistsError:
                pass
            else:
                if not _group_exists(directory, stem):
                    return directory / stem
        index += 1


def prepare_output_dir(directory):
    """Use the configured directory directly, without adding a time subfolder."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def reserve_summary_stem(directory, label="summary"):
    """Reserve one summary workbook name and return their shared time parameter.

    The timestamp is captured once per invocation; update the same workbook
    throughout the run. The usual atomic run suffix
    also protects separate processes that start within the same second.
    """
    run_time = saved_at()
    stamp = datetime.fromisoformat(run_time).strftime("%Y%m%d_%H%M%S")
    return reserve_output_stem(directory, f"{label}_{stamp}"), run_time


def save_summary_workbook(rows, path, *, sheet_name="Summary"):
    """Update one Excel summary atomically, retaining its previous good version.

    Use the same reserved path after each stage and at completion; no CSV
    companion is created. Callers supply summary fields without output paths.
    """
    import os
    import tempfile
    import pandas as pd

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.stem}_", suffix=".xlsx", dir=path.parent)
    os.close(handle)
    try:
        frame.to_excel(temporary, sheet_name=sheet_name, index=False, engine="openpyxl")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path
