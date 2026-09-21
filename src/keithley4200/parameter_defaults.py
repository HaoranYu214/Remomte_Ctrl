"""Persist accepted PMU ranges without rewriting unrelated source code."""
import ast
import math
import os
from pathlib import Path
import tempfile
import warnings


RANGE_KEYS = ('Irange1', 'Irange2')


def write_current_range_defaults(source_path, ranges, parameter_name='params'):
    """Replace only range value expressions in a top-level params dictionary.

    Support both {...} and dict(...) configuration styles. Preserve comments,
    encoding, and line endings. The complete edited source is parsed before an
    atomic replacement. A concurrent edit detected before replacement aborts it.
    """
    accepted = {key: float(ranges[key]) for key in RANGE_KEYS if key in ranges}
    if not accepted:
        return
    if any(not math.isfinite(value) or value <= 0 for value in accepted.values()):
        raise ValueError('Accepted current ranges must be finite and positive.')
    path = Path(source_path)
    original = path.read_bytes()
    bom = original.startswith(b'\xef\xbb\xbf')
    source = original.decode('utf-8-sig')
    tree = ast.parse(source, filename=str(path))
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == parameter_name
                           for target in node.targets)]
    if len(assignments) != 1:
        raise ValueError(f'Expected one top-level {parameter_name} assignment in {path.name}.')
    value = assignments[0].value
    if isinstance(value, ast.Dict):
        fields = {key.value: item for key, item in zip(value.keys, value.values)
                  if isinstance(key, ast.Constant) and isinstance(key.value, str)}
    elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'dict':
        fields = {item.arg: item.value for item in value.keywords}
    else:
        raise ValueError(f'{parameter_name} must be a dictionary literal or dict(...).')
    if not accepted.keys() <= fields.keys():
        raise ValueError(f'Missing current-range fields in {parameter_name}.')
    # AST column offsets are UTF-8 byte offsets, even when a line has Chinese text.
    raw = source.encode('utf-8')
    offsets = [0]
    for line in raw.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    edits = []
    for key, new_range in accepted.items():
        node = fields[key]
        try:
            if float(ast.literal_eval(node)) == new_range:
                continue
        except (ValueError, TypeError):
            pass
        edits.append((offsets[node.lineno-1] + node.col_offset,
                      offsets[node.end_lineno-1] + node.end_col_offset,
                      repr(new_range).encode('ascii')))
    if not edits:
        return
    for start, end, replacement in sorted(edits, reverse=True):
        raw = raw[:start] + replacement + raw[end:]
    ast.parse(raw.decode('utf-8'), filename=str(path))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.',
                                         suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write((b'\xef\xbb\xbf' if bom else b'') + raw)
        if path.read_bytes() != original:
            raise OSError(f'{path.name} changed while updating current ranges; keeping the newer file.')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def remember_current_ranges(defaults, ranges, source_path, parameter_name='params'):
    """Update memory and source defaults; a write failure must not discard data."""
    accepted = {key: ranges[key] for key in RANGE_KEYS if key in ranges}
    defaults.update(accepted)
    if not accepted:
        return
    try:
        write_current_range_defaults(source_path, accepted, parameter_name)
    except (OSError, ValueError, SyntaxError) as exc:
        warnings.warn(f'Accepted ranges are in memory but could not be saved to {source_path}: {exc}',
                      RuntimeWarning, stacklevel=2)
