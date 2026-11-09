"""QQQ MRI. Seven equal weights. Liquidity is FRED excess reserves, else HYG/IEF."""

from __future__ import annotations

from stocks.feed import Bar, forward_fill
from stocks.indicators import (
    MRI_CHART_DAYS,
    MRI_WINDOW_START,
    atr_series,
    bollinger_bandwidth,
    clamp,
    cmf_series,
    expanding_percentile,
    is_window_high,
    mfi_series,
    roc_series,
    sma,
    wilder_adx,
)


def liquidity_levels(
    qqq_dates: list[str],
    fred: dict[str, dict[str, float]] | None,
    hyg: list[Bar] | None,
    ief: list[Bar] | None,
) -> tuple[list[float | None], str]:
    if fred and all(fred.get(name) for name in ("WALCL", "WTREGEN", "RRPONTSYD")):
        walcl = forward_fill(fred["WALCL"], qqq_dates)
        wtregen = forward_fill(fred["WTREGEN"], qqq_dates)
        rrp = forward_fill(fred["RRPONTSYD"], qqq_dates)
        levels: list[float | None] = []
        for a, b, c in zip(walcl, wtregen, rrp):
            levels.append(None if None in (a, b, c) else a - b - c)
        if any(level is not None for level in levels):
            return levels, "FRED WALCL − WTREGEN − RRPONTSYD"
    hyg_map = {bar.date: bar.close for bar in hyg or []}
    ief_map = {bar.date: bar.close for bar in ief or []}
    ratio: list[float | None] = []
    for date in qqq_dates:
        left = hyg_map.get(date)
        right = ief_map.get(date)
        ratio.append(None if left is None or not right else left / right)
    if any(value is not None for value in ratio):
        return ratio, "HYG/IEF"
    return [None] * len(qqq_dates), "unavailable"


def compute_mri(
    qqq: list[Bar],
    vix: list[Bar],
    ndx: list[Bar],
    liquidity: list[float | None],
) -> list[dict]:
    bars = [bar for bar in qqq if bar.date >= MRI_WINDOW_START]
    if not bars:
        return []
    # Liquidity was aligned to the unfiltered QQQ calendar. Realign by date.
    liq_map = {}
    if len(liquidity) == len(qqq):
        liq_map = {bar.date: liquidity[i] for i, bar in enumerate(qqq)}
    dates = [bar.date for bar in bars]
    levels = [liq_map.get(date) for date in dates]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    vix_map = {bar.date: bar.close for bar in vix}
    ndx_map = {bar.date: bar.close for bar in ndx}
    vix_closes = [vix_map.get(date) for date in dates]

    vix_pct = expanding_percentile(vix_closes, min_obs=60)
    vix_roc = roc_series(vix_closes, 5)
    mfi = mfi_series(highs, lows, closes, volumes, 14)
    bandwidth = bollinger_bandwidth(closes, 20, 2.0)
    atr = atr_series(highs, lows, closes, 14)
    atr_pct = [
        None if atr[i] is None or closes[i] == 0 else atr[i] / closes[i] * 100.0
        for i in range(len(closes))
    ]
    band_pct = expanding_percentile(bandwidth)
    atr_pctile = expanding_percentile(atr_pct)
    liq_change = roc_series(levels, 65)
    liq_pct = expanding_percentile(liq_change)
    cmf = cmf_series(highs, lows, closes, volumes, 21)
    adx, plus_di, minus_di = wilder_adx(highs, lows, closes, 14)
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)

    mri_values: list[float | None] = []
    components: list[dict] = []
    for i in range(len(bars)):
        parts: dict[str, float] = {}
        if vix_pct[i] is not None and vix_roc[i] is not None:
            parts["vix"] = 0.7 * vix_pct[i] + 0.3 * clamp(50 + vix_roc[i] * 2)
        if mfi[i] is not None:
            value = mfi[i]
            if value >= 80:
                base = 70 + min(25, (value - 80) * 1.25)
            elif value <= 20:
                base = 35
            else:
                base = 40 + (value - 50) * 0.5
            if is_window_high(closes, i, 63) and not is_window_high(mfi, i, 63):
                base += 20
            parts["mfi"] = base
        if band_pct[i] is not None and atr_pctile[i] is not None:
            parts["consolidation"] = ((100 - band_pct[i]) + (100 - atr_pctile[i])) / 2
        if liq_pct[i] is not None:
            parts["liquidity"] = 100 - liq_pct[i]
        if cmf[i] is not None:
            base = clamp(50 - cmf[i] * 180)
            if is_window_high(closes, i, 63) and not is_window_high(cmf, i, 63):
                base += 20
            parts["accumulation"] = base
        if adx[i] is not None and plus_di[i] is not None and minus_di[i] is not None:
            trend = clamp(adx[i] * 2)
            gap = minus_di[i] - plus_di[i]
            if minus_di[i] > plus_di[i]:
                parts["adx"] = clamp(50 + trend * 0.5 + min(25, gap))
            else:
                parts["adx"] = clamp(50 - trend * 0.45 + max(-25, gap))
        ma = _moving_averages(i, closes, sma20, sma50, sma200)
        if ma is not None:
            parts["moving_averages"] = ma
        components.append(parts)
        mri_values.append(sum(parts.values()) / len(parts) if parts else None)

    zones = _zones(mri_values)
    rows = []
    for i, bar in enumerate(bars):
        if mri_values[i] is None:
            continue
        rows.append(
            {
                "date": bar.date,
                "qqq": closes[i],
                "ndx": ndx_map.get(bar.date),
                "vix": vix_closes[i],
                "mri": mri_values[i],
                "zone": zones[i],
            }
        )
    return rows


def chart_mri(rows: list[dict]) -> list[dict]:
    tail = rows[-MRI_CHART_DAYS:]
    return [
        {"date": row["date"], "mri": round(row["mri"], 3), "zone": row["zone"]}
        for row in tail
    ]


def _moving_averages(i, closes, sma20, sma50, sma200) -> float | None:
    if None in (sma20[i], sma50[i], sma200[i]):
        return None
    if i < 5 or sma50[i - 5] is None or sma200[i - 5] is None:
        return None
    score = 50.0
    score += 12 if closes[i] < sma20[i] else -8
    score += 16 if closes[i] < sma50[i] else -10
    score += 18 if closes[i] < sma200[i] else -12
    score += 14 if sma20[i] < sma50[i] < sma200[i] else -10
    score += 10 if sma50[i] < sma50[i - 5] else -6
    score += 8 if sma200[i] < sma200[i - 5] else -5
    return score


def _zones(values: list[float | None]) -> list[str | None]:
    zones: list[str | None] = []
    history: list[float] = []
    for value in values:
        if value is None:
            zones.append(None)
            continue
        history.append(value)
        if len(history) < 252:
            zones.append(None)
            continue
        mean = sum(history) / len(history)
        var = sum((item - mean) ** 2 for item in history) / (len(history) - 1)
        std = var ** 0.5
        z_score = 0.0 if std == 0 else (value - mean) / std
        if z_score < -1:
            zones.append("Calm")
        elif z_score < 1:
            zones.append("Normal")
        elif z_score < 2:
            zones.append("Elevated")
        elif z_score < 3:
            zones.append("High")
        else:
            zones.append("Crisis")
    return zones
