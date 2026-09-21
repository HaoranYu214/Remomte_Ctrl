# -*- coding: utf-8 -*-
# Copyright (c) 2026 ssme / Haoran Yu.
# PMU data-processing helpers.
"""
PMU buffer reading, saving, channel merging, and analysis.
"""

import numpy as np
import pandas as pd
import locale
import csv

from keithley4200.output import saved_at


def _channel_data_columns(ch, field_count, pulse_iv=None):
    """Return columns for waveform/segARB or pulse-I-V records."""
    standard = [f"Voltage {ch}", f"Current {ch}", f"Timestamp {ch}", f"Status {ch}"]
    if field_count == 8:
        return [
            f"Voltage High {ch}", f"Current High {ch}",
            f"Timestamp High {ch}", f"Status High {ch}",
            f"Voltage Low {ch}", f"Current Low {ch}",
            f"Timestamp Low {ch}", f"Status Low {ch}",
        ]
    if field_count != 4:
        raise ValueError(
            f"CH{ch} returned {field_count} values per point; expected 4 or 8."
        )
    if pulse_iv == (False, True):
        return [
            f"Voltage Low {ch}", f"Current Low {ch}",
            f"Timestamp Low {ch}", f"Status Low {ch}",
        ]
    return standard


def read_channel_data(Q, ch, block=2048, debug=False, pulse_iv=None):
    """Read channel buffers in blocks; return voltage/current/time/status or None.
    
    debug=True prints raw response samples for investigating parsing precision.
    """
    # DATA:GET allows 2048 points per block (7-7): V/I/time/status, or eight fields for High+Low.
    # Keep raw Status codes; they are neither Boolean flags nor TEST_MODE values.
    count = int(Q(f":PMU:DATA:COUNT? {ch}").strip())
    if count == 0:
        return None
    if debug:
        print(f"🔍 [DEBUG] CH{ch} 数据点数: {count}")
    
    if pulse_iv is not None:
        if len(pulse_iv) != 2:
            raise ValueError("pulse_iv must be (acquire_high, acquire_low).")
        pulse_iv = tuple(bool(value) for value in pulse_iv)
        if pulse_iv == (False, False):
            raise ValueError("Pulse I-V must acquire at least High or Low data.")

    cols = None
    chunks = []
    for start in range(0, count, block):
        resp = Q(f":PMU:DATA:GET {ch}, {start}, {block}")
        if not resp:
            continue
        
        # Show the first raw response block when debugging.
        if debug and start == 0:
            print(f"🔍 [DEBUG] CH{ch} 原始响应长度: {len(resp)}")
            print(f"🔍 [DEBUG] CH{ch} 前500字符:\n{resp[:500]}")
            # Inspect the first record before numeric conversion.
            first_row = resp.split(";")[0] if ";" in resp else resp
            print(f"🔍 [DEBUG] CH{ch} 第一个数据点原始: '{first_row}'")
        
        rows = [seg.split(",") for seg in resp.split(";") if seg.strip()]
        if not rows:
            continue
        field_counts = {len(row) for row in rows}
        if len(field_counts) != 1:
            raise ValueError(
                f"CH{ch} returned inconsistent record widths: {sorted(field_counts)}."
            )
        chunk_cols = _channel_data_columns(ch, field_counts.pop(), pulse_iv=pulse_iv)
        if cols is None:
            cols = chunk_cols
        elif cols != chunk_cols:
            raise ValueError(f"CH{ch} data layout changed while reading blocks.")
        chunks.append(pd.DataFrame(rows, columns=cols))
    
    if not chunks:
        return None
    
    result = pd.concat(chunks, ignore_index=True)
    numeric_columns = [
        column for column in result.columns
        if column.startswith(("Voltage ", "Current ", "Timestamp "))
    ]
    result[numeric_columns] = result[numeric_columns].astype(float)
    result = result.reset_index(drop=True)
    if pulse_iv is not None:
        result.attrs["pulse_iv_acquire_high"] = pulse_iv[0]
        result.attrs["pulse_iv_acquire_low"] = pulse_iv[1]
    
    if debug:
        print(f"🔍 [DEBUG] CH{ch} 解析后前3行:\n{result.head(3).to_string()}")
    
    return result


def read_both_channels(Q, ch1, ch2, debug=False, pulse_iv=None):
    """Read both channels; a channel with no data returns None."""
    df1 = read_channel_data(Q, ch1, debug=debug, pulse_iv=pulse_iv)
    df2 = read_channel_data(Q, ch2, debug=debug, pulse_iv=pulse_iv)
    return df1, df2


def select_pulse_iv_level(df, ch, level="High"):
    """Return one pulse-I-V level using the standard four-column schema."""
    if df is None or df.empty:
        return df
    level = level.title()
    if level not in ("High", "Low"):
        raise ValueError("level must be 'High' or 'Low'.")

    source_columns = [
        f"Voltage {level} {ch}",
        f"Current {level} {ch}",
        f"Timestamp {level} {ch}",
        f"Status {level} {ch}",
    ]
    if all(column in df.columns for column in source_columns):
        result = df[source_columns].copy()
        result.columns = [
            f"Voltage {ch}",
            f"Current {ch}",
            f"Timestamp {ch}",
            f"Status {ch}",
        ]
        result.attrs.update(df.attrs)
        result.attrs["pulse_iv_selected_level"] = level
        return result

    standard_columns = [
        f"Voltage {ch}",
        f"Current {ch}",
        f"Timestamp {ch}",
        f"Status {ch}",
    ]
    if all(column in df.columns for column in standard_columns):
        return df.copy()
    raise ValueError(f"CH{ch} does not contain {level} pulse-I-V data.")


def merge_channels(dfs: dict):
    """Join channels 1/2 by row index; pad unequal lengths with NaN."""
    d1, d2 = dfs.get(1), dfs.get(2)
    if d1 is None and d2 is None:
        return pd.DataFrame()
    if d1 is None:
        return d2.copy()
    if d2 is None:
        return d1.copy()
    return pd.concat([d1.reset_index(drop=True), d2.reset_index(drop=True)], axis=1)


def add_resistance_columns(df, eps=1e-12, res_min=1.0, res_max=1e15):
    """Add Resistance 1/2 in place where matching voltage/current columns exist."""
    if df is None or df.empty:
        return df
    for ch in (1, 2):
        vcol, icol, rcol = f"Voltage {ch}", f"Current {ch}", f"Resistance {ch}"
        if vcol in df.columns and icol in df.columns:
            i = df[icol].astype(float)
            valid_i = np.abs(i) >= eps
            r = pd.Series(np.where(valid_i, df[vcol] / i, np.nan), index=df.index)
            keep = (np.abs(r) >= res_min) & (np.abs(r) <= res_max)
            df[rcol] = r.where(keep, np.nan)
    return df


def calculate_polarization(current_data, time_data, area_cm2):
    """Integrate current and center polarization; area is in cm^2, output in uC/cm^2."""
    charge = np.zeros_like(current_data, dtype=float)
    for i in range(1, len(current_data)):
        dt = time_data[i] - time_data[i-1]
        charge[i] = charge[i-1] + dt * current_data[i]
    midpoint = len(charge) // 2
    center_offset = (charge[0] + charge[midpoint]) / 2.0 if len(charge) > 1 else 0.0
    polarization = (charge - center_offset) / area_cm2 * 1e6
    return polarization


def analyze_pund_diff(df_ch1, df_ch2, params):
    """
    Analyze the legacy endurance PUND layout: 22 equally sampled segments.

    Returns df_total, pund_diff, and meta. Do not use this index-based helper
    for arbitrary segment lengths or selectively unmeasured segments. The
    standalone PUND entries own their separate waveform-specific analysis.
    """
    if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
        raise ValueError("PUND原始数据为空")

    def _detect_ch(df, kind='Voltage'):
        for c in df.columns:
            if c.startswith(f'{kind} '):
                try:
                    return int(c.split(' ')[1])
                except:
                    continue
        raise ValueError(f"无法在列中识别通道号: {list(df.columns)}")

    ch1 = _detect_ch(df_ch1, 'Voltage')
    ch2 = _detect_ch(df_ch2, 'Voltage')

    v_total = df_ch1[f'Voltage {ch1}'].values - df_ch2[f'Voltage {ch2}'].values
    i_total = -df_ch2[f'Current {ch2}'].values
    t_total = df_ch1[f'Timestamp {ch1}'].values
    df_total = pd.DataFrame({'Time': t_total, 'Voltage': v_total, 'Current': i_total})
    
    total_points = len(i_total)
    seg_points = total_points // 22
    if seg_points == 0:
        raise ValueError("PUND数据点数不足，无法按22段进行差分")

    pund_pairs = [(6, 10, 'P'), (8, 12, 'U'), (14, 18, 'N'), (16, 20, 'D')]
    v_collect, i_collect, labels = [], [], []
    
    for seg_a, seg_b, label in pund_pairs:
        a0, a1 = seg_a * seg_points, (seg_a + 1) * seg_points
        b0, b1 = seg_b * seg_points, (seg_b + 1) * seg_points
        v_seg = v_total[a0:a1]
        i_diff = i_total[a0:a1] - i_total[b0:b1]
        if len(v_seg) == 0 or len(i_diff) == 0:
            continue
        v_collect.append(v_seg)
        i_collect.append(i_diff)
        labels.extend([label] * len(v_seg))
    
    if not v_collect:
        raise ValueError("PUND差分阶段提取失败")
    
    v_all = np.concatenate(v_collect)
    i_all = np.concatenate(i_collect)
    dt_est = (t_total[-1] - t_total[0]) / max(len(i_all)-1, 1)
    time_local = np.arange(len(i_all)) * dt_est
    P = calculate_polarization(i_all, time_local, params.get('area_cm2', 1.0))
    
    diff_df = pd.DataFrame({
        'Time': time_local, 'Voltage': v_all, 'DiffCurrent': i_all,
        'Polarization': P, 'Segment': labels
    })
    return {'df_total': df_total, 'pund_diff': diff_df, 
            'meta': {'points_per_segment': seg_points, 'pairs': pund_pairs}}


def analyze_nis_switch(df_ch1, df_ch2, params):
    """
    Return NLS channel frames and MeasureSquare metadata without processing.

    The measurement entry owns waveform-specific analysis. The legacy
    function name is retained for existing callers.
    """
    if df_ch1 is None or df_ch2 is None or df_ch1.empty or df_ch2.empty:
        raise ValueError("NIS Switch 原始数据为空")

    measure_square = params.get('MeasureSquare', True)
    
    return {
        'df_ch1': df_ch1,
        'df_ch2': df_ch2,
        'meta': {
            'measure_square': measure_square,
            'points_ch1': len(df_ch1),
            'points_ch2': len(df_ch2)
        }
    }


# === Saving ===

def save_channels_separate_excel(dfs: dict, path, *, parameters=None):
    """Save channels to separate Excel sheets with the supplied parameter snapshot.

    Returns a success flag; callers must check it if saving is required."""
    if not dfs or all(df is None or df.empty for df in dfs.values()):
        print(f"⚠️ 无数据，跳过保存：{path}")
        return False
    
    try:
        if not path.lower().endswith(".xlsx"):
            path = path + ".xlsx"
        
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            saved_sheets = 0
            for ch, df in dfs.items():
                if df is not None and not df.empty:
                    sheet_name = f"Channel_{ch}"
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    print(f"✅ 已保存 CH{ch} 到 {sheet_name}: {df.shape}")
                    saved_sheets += 1
            
            # Save the caller's parameter snapshot; numeric codes must be interpreted by parameter name.
            metadata = {**(parameters or {}), "saved_at": saved_at()}
            pd.DataFrame(
                [{"name": key, "value": repr(value)} for key, value in metadata.items()]
            ).to_excel(writer, sheet_name="Parameters", index=False)
            if saved_sheets > 0:
                print(f"✅ Excel文件已保存：{path} (共{saved_sheets}个sheet)")
                return True
            else:
                print(f"⚠️ 没有有效数据保存到：{path}")
                return False
    except Exception as e:
        print(f"❌ 保存Excel失败: {e}")
        return False


def save_csv(df, path, sep=None, for_excel=True):
    """Save a DataFrame as CSV; use ';' in decimal-comma locales for Excel.

    Returns False on empty input or a save error; does not raise save errors."""
    if df is None or df.empty:
        print(f"⚠️ 无数据，跳过保存：{path}")
        return False

    if sep is None:
        try:
            decimal_point = locale.localeconv().get('decimal_point', '.')
        except Exception:
            decimal_point = '.'
        sep = ';' if decimal_point == ',' else ','

    encoding = 'utf-8-sig' if for_excel else 'utf-8'
    print(f"📊 保存数据: 形状 {df.shape}, 列数 {len(df.columns)}, 分隔符='{sep}'")

    try:
        df.to_csv(path, index=False, sep=sep, encoding=encoding,
                  float_format='%.6e', na_rep='NaN', quoting=csv.QUOTE_MINIMAL)
        print(f"✅ 已保存：{path}")
        
        test_df = pd.read_csv(path, nrows=1, sep=sep)
        if len(test_df.columns) == len(df.columns):
            print(f"✅ 验证成功: {len(df.columns)} 列正确保存")
        else:
            print(f"⚠️ 列数不匹配: 原始 {len(df.columns)}, 读取 {len(test_df.columns)}")
        return True
    except Exception as e:
        print(f"❌ 保存失败: {e}")
        return False


def save_excel(df, path):
    """Save one DataFrame to Excel; return False on empty input or a save error."""
    if df is None or df.empty:
        print(f"⚠️ 无数据，跳过保存：{path}")
        return False
    try:
        if not path.lower().endswith(".xlsx"):
            path = path + ".xlsx"
        df.to_excel(path, index=False)
        print(f"✅ 已保存 Excel：{path}")
        return True
    except Exception as e:
        print(f"❌ 保存失败: {e}")
        return False


def print_data_summary(df):
    """Print a summary of available channel data."""
    if df is not None and not df.empty:
        print("\n📊 数据摘要：")
        print("  形状   :", df.shape)
        print("  列名   :", list(df.columns))
        for ch in (1, 2):
            for col in (f"Voltage {ch}", f"Current {ch}", f"Resistance {ch}"):
                if col in df.columns:
                    s = df[col].dropna()
                    if not s.empty:
                        print(f"  {col}: min={s.min():.3e}, max={s.max():.3e}")
    else:
        print("⚠️ 无有效数据")


# === Synthetic data ===

def remanent_polarization(voltage, polarization, *, zero_endpoint=False):
    """Return signed (Pr_positive, Pr_negative) at zero applied voltage.

    Follow the return branch after each positive/negative voltage extremum,
    interpolating between adjacent finite samples that bracket 0 V. Values
    retain the polarization input units (normally uC/cm^2). Do not substitute
    peak polarization or a value at the bias offset. Missing crossings return
    NaN; non-finite gaps are never bridged. If the programmed final voltage is
    exactly zero, zero_endpoint=True permits linear extrapolation from the
    last two finite adjacent samples by at most one voltage sample interval.
    This accounts for acquisition windows that omit the exact endpoint.
    Input is one loop or return branch, not multiple concatenated cycles.
    """
    voltage = np.asarray(voltage, dtype=float)
    polarization = np.asarray(polarization, dtype=float)
    if voltage.ndim != 1 or polarization.ndim != 1 or voltage.shape != polarization.shape:
        raise ValueError("Voltage and polarization must be equal-length one-dimensional arrays.")
    if len(voltage) < 2 or not np.isfinite(voltage).any():
        return float("nan"), float("nan")
    finite_voltage = np.isfinite(voltage)
    positive_peak = int(np.argmax(np.where(finite_voltage, voltage, -np.inf)))
    negative_peak = int(np.argmin(np.where(finite_voltage, voltage, np.inf)))

    def crossing(start, stop, sign):
        if sign * voltage[start] <= 0:
            return float("nan")
        for index in range(start, stop):
            v0, v1 = voltage[index:index + 2]
            p0, p1 = polarization[index:index + 2]
            if not np.isfinite([v0, v1, p0, p1]).all():
                continue
            if sign * v0 > 0 and sign * v1 <= 0:
                return float(p0 + (p1 - p0) * (-v0) / (v1 - v0))
        if zero_endpoint and stop == len(voltage) - 1:
            v0, v1 = voltage[-2:]
            p0, p1 = polarization[-2:]
            if (np.isfinite([v0, v1, p0, p1]).all()
                    and sign * v0 > sign * v1 > 0
                    and abs(v1) <= abs(v1 - v0) * (1 + 1e-12)):
                return float(p0 + (p1 - p0) * (-v0) / (v1 - v0))
        return float("nan")

    positive_stop = negative_peak if negative_peak > positive_peak else len(voltage) - 1
    negative_stop = positive_peak if positive_peak > negative_peak else len(voltage) - 1
    return (crossing(positive_peak, positive_stop, 1),
            crossing(negative_peak, negative_stop, -1))
