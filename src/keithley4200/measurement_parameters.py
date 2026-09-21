# Copyright (c) 2026 ssme / Haoran Yu.
"""Small parameter-copy helpers; pulse design stays in measurement scripts."""
from copy import deepcopy


def merge_parameters(defaults, overrides=None):
    """Copy defaults and apply partial overrides, rejecting misspelled keys."""
    result = deepcopy(defaults)
    if overrides is not None:
        unknown = set(overrides) - set(defaults)
        if unknown:
            raise ValueError(f"Unknown measurement parameters: {sorted(unknown)}")
        result.update(deepcopy(overrides))
    return result


def remap_channel_options(defaults, original_channels, channels, overrides=None):
    """Copy channel-specific options when the channel assignment changes."""
    options = deepcopy(defaults)
    channels = tuple(channels)
    if len(channels) != 2 or channels[0] == channels[1]:
        raise ValueError('channels must contain two distinct channel numbers.')
    remap = dict(zip(original_channels, channels))
    if 'LOAD_RESISTANCES' in options:
        options['LOAD_RESISTANCES'] = {remap.get(ch, ch): value
                                     for ch, value in options['LOAD_RESISTANCES'].items()}
    for key in ('LLEC_CHANNELS', 'CONNECTION_COMP_CHANNELS'):
        if key in options:
            options[key] = tuple(remap.get(ch, ch) for ch in options[key])
    options.update(deepcopy(overrides or {}))
    return options
