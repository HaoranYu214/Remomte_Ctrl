# Copyright (c) 2026 ssme / Haoran Yu.
"""Offline previews of commanded SMU channel voltages; no instrument access."""

import math
from pathlib import Path


def preview_channel_voltages(channel_values, output_path=None, *, show=True, title=None):
    """Plot commanded voltages by channel against point index, without hardware.

    channel_values maps channel labels to equally sized voltage lists.
    Include constant channels as repeated values. With output_path, save and
    close the figure and return the path; otherwise return the figure.
    """
    traces = {str(channel): [float(v) for v in values]
              for channel, values in channel_values.items()}
    if not traces or any(not values for values in traces.values()):
        raise ValueError("Provide at least one channel with nonempty voltage points.")
    if len({len(values) for values in traces.values()}) != 1:
        raise ValueError("Channel voltage lists must have the same point count.")
    if any(not math.isfinite(v) for values in traces.values() for v in values):
        raise ValueError("Preview voltages must be finite.")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(9, 4.5))
    for channel, values in traces.items():
        axis.plot(range(len(values)), values, linewidth=1.4, label=channel)
    figure_title = title or "SMU commanded voltage preview"
    axis.set(title=figure_title, xlabel="Point index", ylabel="Commanded voltage (V)")
    figure.canvas.manager.set_window_title(figure_title)
    axis.grid(alpha=0.3)
    axis.legend()
    figure.tight_layout()
    if output_path is None:
        if show:
            plt.show()
        return figure
    output_path = Path(output_path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, dpi=200)
    finally:
        plt.close(figure)
    return output_path


# Preview gate/drain voltage plans by point index, not actual instrument time.
def preview_fet_family(configs, *, show=True):
    """Prepare physical terminal voltages; plotting is shared with other IV tests."""
    channel_values = {}
    for index, config in enumerate(configs, 1):
        gate_sweep = config["sweep_terminal"] == "gate"
        source = config["source_voltage"]
        sweep = [value + source for value in config["values"]]
        fixed = [config["bias_voltage"] + source] * len(sweep)
        for terminal, values in (("gate", sweep if gate_sweep else fixed),
                                 ("drain", fixed if gate_sweep else sweep),
                                 ("source", [source] * len(sweep))):
            channel = config[f"{terminal}_channel"]
            channel_values[f"CH{channel} ({terminal}, curve {index})"] = values
    return preview_channel_voltages(channel_values, show=show,
                                   title="FET commanded channel voltages")

#     /\_/\
#    ( ^.^ )
#     (")(")  ssme / haoran yu
