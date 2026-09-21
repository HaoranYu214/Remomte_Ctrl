# -*- coding: utf-8 -*-

# 阅读入口：分段 I–V；先改 TURNING_POINTS、SEGMENT_STEP、PARAMS、通道、INST 和 SAVE_DIR。
# 流程：main → run_test 合并参数/生成电压列表 → SMU 扫描/读回 → 保存 Excel 和 J–V 图。
# run_test 的 params_override 覆盖同名 PARAMS；通道、接线和转折点用独立关键字参数传入。
# 直接运行会实测；离线看电压列表请调用 preview_waveform，本文件没有 PREVIEW_ONLY 开关。

"""Segmented SMU voltage sweep: 0 -> V1 -> 0 -> V2 -> 0."""

from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "pyproject.toml").is_file()
)
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keithley4200.output import measurement_name, reserve_output_stem
from keithley4200.smu.data_processing import build_plot_data, retrieve_variables, save_workbook
from keithley4200.smu.plotting import save_current_density_plots
from keithley4200.smu.session import SMUSession
from keithley4200.smu.system_mode import build_segmented_voltage_path, run_list_voltage_sweep


INST = "TCPIP0::129.125.87.80::1225::SOCKET"
SWEEP_CHANNEL = 1
BIAS_CHANNEL = 2
# List every installed/mapped SMU so initialization explicitly disables all
# unused channels before defining the active sweep and bias pair.
AVAILABLE_CHANNELS = (1, 2, 3, 4)

# Physical SMU-to-probe wiring for this 4200A. SMU1 and SMU2 pass through
# the RPMs attached to PMU1 channels 1 and 2; SMU3/SMU4 (when used by future
# experiments) are direct probe connections.
SMU_CONNECTIONS = {
    1: "rpm:PMU1-1",
    2: "rpm:PMU1-2",
    3: "direct",
    4: "direct",
}


SAVE_DIR = Path(r"C:\Users\P317151\Documents\data\14-09-2026\04A1_2700_1200_300\L20_2\IV5_endurance")

DEVICE_AREA_CM2 = (20e-4) ** 2
# DEVICE_AREA_CM2 = (15*1e-4)**2*3.14

# Generic device-check loop. Package/orchestration files may override these
# globals before calling ``main()`` without duplicating the SMU implementation.
POSITIVE_PEAK_V = 5
NEGATIVE_PEAK_V = -5
TURNING_POINTS = [0.0, POSITIVE_PEAK_V, 0.0, NEGATIVE_PEAK_V, 0.0]
# TURNING_POINTS = [0.0, NEGATIVE_PEAK_V, 0.0, POSITIVE_PEAK_V, 0.0]
SEGMENT_STEP = 0.1

PARAMS = {
    "sweep_current_compliance": 1e-4,
    "bias_voltage": 0.0,
    "bias_current_compliance": 1e-4,
    "sweep_current_range": "auto",
    "bias_current_range": "auto",
    "hold_time": 0.0,
    "sweep_delay": 0.02,
    # IT1=Fast, IT2=Normal, IT3=Quiet.
    "integration": "IT3",
    # None: no overall test deadline; keep polling SP until KXCI completes.
    # Long endurance runs may legitimately take hours or days. Use a positive
    # number only when an explicit wall-clock limit is wanted; "auto" remains
    # available as an opt-in estimate based on points/delay/integration.
    "timeout_s": None,
}

NAMES = {
    "sweep_voltage": "V1",
    "sweep_current": "I1",
    "sweep_current_density": "J1_A_per_cm2",
    "bias_voltage": "V2",
    "bias_current": "I2",
    "bias_current_density": "J2_A_per_cm2",
}


# 离线绘制转折点和步长生成的电压列表；show 控制显示，可指定图片保存路径。
def preview_waveform(output_path=None, *, show=True, title=None, turning_points=None, segment_step=None):
    """Show the exact segmented voltage list, or save it when requested."""
    import matplotlib.pyplot as plt

    turning_points = TURNING_POINTS if turning_points is None else turning_points
    segment_step = SEGMENT_STEP if segment_step is None else segment_step
    sweep_values = build_segmented_voltage_path(turning_points, segment_step)
    figure, axis = plt.subplots(figsize=(9, 4.5))
    axis.plot(range(len(sweep_values)), sweep_values, linewidth=1.4)
    figure_title = title or (
        f"Segmented DC I-V preview ({len(sweep_values)} points)"
    )
    axis.set(
        title=figure_title,
        xlabel="Point index",
        ylabel="Commanded voltage (V)",
    )
    figure.canvas.manager.set_window_title(figure_title)
    axis.grid(alpha=0.3)
    figure.tight_layout()
    if output_path is None:
        if show:
            plt.show()
        return figure

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=200)
    plt.close(figure)
    return output_path


# 合并 PARAMS 与 params_override，按转折点生成电压列表，连接 SMU 扫描并保存 Excel/图。
# 返回输出路径和点数；本函数直接实测，离线检查电压路径请调用 preview_waveform。
def run_test(params_override=None, *, turning_points=None, segment_step=None,
             save_dir=None, file_stem="IV", inst=None, device_area_cm2=None,
             sweep_channel=None, bias_channel=None, available_channels=None,
             smu_connections=None, names=None):
    """Run one complete list sweep using explicit overrides without changing defaults."""
    parameters = dict(PARAMS)
    if params_override is not None:
        unknown = set(params_override) - set(parameters)
        if unknown:
            raise ValueError(f"Unknown segmented IV parameters: {sorted(unknown)}")
        parameters.update(params_override)
    inst = INST if inst is None else inst
    save_dir = SAVE_DIR if save_dir is None else Path(save_dir)
    device_area_cm2 = DEVICE_AREA_CM2 if device_area_cm2 is None else device_area_cm2
    sweep_channel = SWEEP_CHANNEL if sweep_channel is None else sweep_channel
    bias_channel = BIAS_CHANNEL if bias_channel is None else bias_channel
    available_channels = AVAILABLE_CHANNELS if available_channels is None else available_channels
    smu_connections = dict(SMU_CONNECTIONS if smu_connections is None else smu_connections)
    names = dict(NAMES if names is None else names)
    turning_points = list(TURNING_POINTS if turning_points is None else turning_points)
    segment_step = SEGMENT_STEP if segment_step is None else segment_step
    sweep_values = build_segmented_voltage_path(turning_points, segment_step)
    if len(sweep_values) > 4096:
        raise ValueError(
            f"Segmented sweep contains {len(sweep_values)} points; "
            "KXCI VL list sweeps are limited to 4096."
        )
    print(
        f"Segmented sweep: {turning_points}, "
        f"{len(sweep_values)} commanded points."
    )

    with SMUSession(inst) as session:
        variables = run_list_voltage_sweep(
            session.query,
            values=sweep_values,
            sweep_channel=sweep_channel,
            bias_channel=bias_channel,
            sweep_voltage_name=names["sweep_voltage"],
            sweep_current_name=names["sweep_current"],
            bias_voltage_name=names["bias_voltage"],
            bias_current_name=names["bias_current"],
            available_channels=available_channels,
            smu_connections=smu_connections,
            **parameters,
        )
        data = retrieve_variables(
            session.query,
            variables,
            expected_point_count=len(sweep_values),
        )

    # Keep the programmed path next to the measured voltage/current. Series
    # padding makes a point-count mismatch visible instead of hiding it.
    commanded = pd.DataFrame(
        {
            "PointIndex": pd.Series(range(len(sweep_values)), dtype=int),
            "CommandedVoltage": pd.Series(sweep_values, dtype=float),
        }
    )
    data = pd.concat([commanded, data.reset_index(drop=True)], axis=1)
    plot_data = build_plot_data(
        data, area_cm2=device_area_cm2,
        channel1_voltage=names["sweep_voltage"], channel1_current=names["sweep_current"],
        channel2_voltage=names["bias_voltage"], channel2_current=names["bias_current"],
    )

    output_stem = reserve_output_stem(save_dir, measurement_name(file_stem, max(abs(value) for value in turning_points)))
    output_path = Path(f"{output_stem}.xlsx")
    saved_parameters = {
        "INST": inst,
        "DEVICE_AREA_CM2": device_area_cm2,
        "SWEEP_CHANNEL": sweep_channel,
        "BIAS_CHANNEL": bias_channel,
        "AVAILABLE_CHANNELS": available_channels,
        "SMU_CONNECTIONS": smu_connections,
        "TURNING_POINTS": turning_points,
        "SEGMENT_STEP": segment_step,
        "POINT_COUNT": len(sweep_values),
        **names,
        **parameters,
    }
    save_workbook(
        output_path,
        data,
        saved_parameters,
        plot_data=plot_data,
    )
    try:
        jv_path, log_path = save_current_density_plots(
            plot_data,
            output_path,
            voltage_column="V1",
            current_density_column="J1_A_per_cm2",
        )
        print(f"Saved J-V plot: {jv_path.resolve()}")
        print(f"Saved log(abs(J)) plot: {log_path.resolve()}")
    except Exception as exc:
        print(f"Warning: failed to save current-density plots: {exc}")
    print(f"Saved segmented SMU sweep: {output_path.resolve()}")
    return {
        "output_path": output_path,
        "jv_plot_path": jv_path if "jv_path" in locals() else None,
        "log_plot_path": log_path if "log_path" in locals() else None,
        "point_count": len(sweep_values),
    }


# 使用本文件默认配置调用 run_test，返回本次分段 I–V 的输出信息。
def main():
    """Keep the standalone and existing workflow entry point."""
    return run_test()


if __name__ == "__main__":
    main()
