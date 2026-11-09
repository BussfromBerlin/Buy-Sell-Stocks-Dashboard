"""Indicator math copied from the Dash1 extract.

ADX, ATR, MFI, CMF, and Bollinger bandwidth are the standard definitions
named by that extract. The extract gives the surrounding weights and
thresholds; it does not restate those textbook recursions.
"""

from __future__ import annotations

import math

PRODUCTION_WEEKLY = (2, 5, 7)
PRODUCTION_DAILY = (3, 6, 16)
PULSE_WEEKLY = (2, 4, 6)
PULSE_DAILY = (2, 5, 12)
ADX_PERIOD = 14
ADX_ENTRY_MIN = 25.0
ROC_PERIOD = 10

WEIGHT_WEEKLY = 1.50
WEIGHT_ADX = 1.25
WEIGHT_DAILY = 0.75
WEIGHT_TX = 0.50
SCORED_MIN = 3.0

WATCHLIST_INDEX_START = "2025-08-14"
ROC_HISTORY_START = "2021-01-01"
MRI_WINDOW_START = "2016-08-01"
MRI_CHART_DAYS = 252 * 4

# Dash1 watchlist.json order, updatedAt 2026-11-08 13:10 UTC. NDX stays in
# the book and is dropped only by the Risk/ROC index.
WATCHLIST = (
    "AMD", "GLW", "AVGO", "NVDA", "MU", "NEE", "AAPL", "ESTC", "MRVL", "INTC",
    "HOOD", "WOLF", "PAAS", "GOOGL", "AMAT", "COHR", "DELL", "ENTG", "MKSI",
    "LITE", "WDC", "NDX", "NBIS", "AAOI", "PLTR", "MP", "LLY", "CAT", "LULU",
    "SMCI", "ALAB", "SNDK", "FTNT", "GS", "CRDO", "FIGR", "META", "FN", "ZZZZ",
    "RAK.V", "SECZ", "PBR", "WM", "TEM", "SPCX",
)


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def ema(values: list[float | None], period: int) -> list[float | None]:
    """EMA. The seed is the SMA of the first `period` finite values."""
    k = 2 / (period + 1)
    out: list[float | None] = [None] * len(values)
    buf: list[float] = []
    prev: float | None = None
    for i, value in enumerate(values):
        if value is None:
            continue
        if prev is None:
            buf.append(value)
            if len(buf) == period:
                prev = sum(buf) / period
                out[i] = prev
            continue
        prev = value * k + prev * (1 - k)
        out[i] = prev
    return out


def trix_series(closes: list[float | None], period: int) -> list[float | None]:
    """1-bar percent change of a triple EMA."""
    triple = ema(ema(ema(closes, period), period), period)
    out: list[float | None] = [None] * len(closes)
    prev: float | None = None
    for i, value in enumerate(triple):
        if value is None:
            continue
        if prev not in (None, 0):
            out[i] = 100.0 * (value - prev) / prev
        prev = value
    return out


def roc_series(closes: list[float | None], period: int = ROC_PERIOD) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    for i in range(period, len(closes)):
        prev = closes[i - period]
        cur = closes[i]
        if prev not in (None, 0) and cur is not None:
            out[i] = 100.0 * (cur / prev - 1.0)
    return out


def sma(values: list[float | None], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    window: list[float] = []
    total = 0.0
    for i, value in enumerate(values):
        if value is None:
            window.clear()
            total = 0.0
            continue
        window.append(value)
        total += value
        if len(window) > period:
            total -= window.pop(0)
        if len(window) == period:
            out[i] = total / period
    return out


def lightweight_call(
    fast: float | None, med: float | None, slow: float | None
) -> str | None:
    """Daily lite, also used for a weekly stack call.

    WAIT if all three are negative. SELL if fast is under both others and
    (max >= 1 or slow > 0). BUY if fast is over both, all three are positive,
    and max < 6. Otherwise WAIT. None if any input is missing.
    """
    if fast is None or med is None or slow is None:
        return None
    highest = max(fast, med, slow)
    if fast < 0 and med < 0 and slow < 0:
        return "WAIT"
    if fast < med and fast < slow and (highest >= 1 or slow > 0):
        return "SELL"
    if fast > med and fast > slow and fast > 0 and med > 0 and slow > 0 and highest < 6:
        return "BUY"
    return "WAIT"


def log_ohlc(high: float, low: float, close: float) -> tuple[float, float, float] | None:
    """ln of positive prices. Swap an inverted high/low. Raise high to ln(close)."""
    if high <= 0 or low <= 0 or close <= 0:
        return None
    ln_high = math.log(high)
    ln_low = math.log(low)
    ln_close = math.log(close)
    if ln_high < ln_low:
        ln_high, ln_low = ln_low, ln_high
    if ln_high < ln_close:
        ln_high = ln_close
    return ln_high, ln_low, ln_close


def wilder_adx(
    highs: list[float | None],
    lows: list[float | None],
    closes: list[float | None],
    period: int = ADX_PERIOD,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Wilder ADX, +DI, and -DI. Returns (adx, plus_di, minus_di)."""
    n = len(closes)
    tr: list[float | None] = [None] * n
    plus_dm: list[float | None] = [None] * n
    minus_dm: list[float | None] = [None] * n
    for i in range(1, n):
        high, low, close = highs[i], lows[i], closes[i]
        prev_h, prev_l, prev_c = highs[i - 1], lows[i - 1], closes[i - 1]
        if None in (high, low, close, prev_h, prev_l, prev_c):
            continue
        tr[i] = max(high - low, abs(high - prev_c), abs(low - prev_c))
        up = high - prev_h
        down = prev_l - low
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0

    def wilder(src: list[float | None]) -> list[float | None]:
        out: list[float | None] = [None] * n
        total = 0.0
        count = 0
        prev: float | None = None
        for i in range(1, n):
            if src[i] is None:
                continue
            if prev is None:
                total += src[i]
                count += 1
                if count == period:
                    prev = total
                    out[i] = prev
            else:
                prev = prev - (prev / period) + src[i]
                out[i] = prev
        return out

    smooth_tr = wilder(tr)
    smooth_plus = wilder(plus_dm)
    smooth_minus = wilder(minus_dm)
    plus_di: list[float | None] = [None] * n
    minus_di: list[float | None] = [None] * n
    dx: list[float | None] = [None] * n
    for i in range(n):
        if not smooth_tr[i]:
            continue
        plus_di[i] = 100.0 * smooth_plus[i] / smooth_tr[i]
        minus_di[i] = 100.0 * smooth_minus[i] / smooth_tr[i]
        denom = plus_di[i] + minus_di[i]
        if denom:
            dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / denom

    adx: list[float | None] = [None] * n
    buf: list[float] = []
    prev_adx: float | None = None
    for i, value in enumerate(dx):
        if value is None:
            continue
        if prev_adx is None:
            buf.append(value)
            if len(buf) == period:
                prev_adx = sum(buf) / period
                adx[i] = prev_adx
        else:
            prev_adx = (prev_adx * (period - 1) + value) / period
            adx[i] = prev_adx
    return adx, plus_di, minus_di


def atr_series(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> list[float | None]:
    n = len(closes)
    tr: list[float | None] = [None] * n
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    out: list[float | None] = [None] * n
    total = 0.0
    count = 0
    prev: float | None = None
    for i in range(1, n):
        if tr[i] is None:
            continue
        if prev is None:
            total += tr[i]
            count += 1
            if count == period:
                prev = total / period
                out[i] = prev
        else:
            prev = (prev * (period - 1) + tr[i]) / period
            out[i] = prev
    return out


def cmf_series(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    period: int,
) -> list[float | None]:
    n = len(closes)
    mfv: list[float] = []
    for i in range(n):
        span = highs[i] - lows[i]
        multiplier = 0.0 if span == 0 else ((closes[i] - lows[i]) - (highs[i] - closes[i])) / span
        mfv.append(multiplier * volumes[i])
    out: list[float | None] = [None] * n
    for i in range(period - 1, n):
        vol = sum(volumes[i - period + 1 : i + 1])
        if vol:
            out[i] = sum(mfv[i - period + 1 : i + 1]) / vol
    return out


def mfi_series(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    period: int = 14,
) -> list[float | None]:
    typical = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    out: list[float | None] = [None] * len(closes)
    for i in range(period, len(closes)):
        positive = 0.0
        negative = 0.0
        for j in range(i - period + 1, i + 1):
            flow = typical[j] * volumes[j]
            if typical[j] > typical[j - 1]:
                positive += flow
            elif typical[j] < typical[j - 1]:
                negative += flow
        if positive == 0 and negative == 0:
            continue
        if negative == 0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + positive / negative)
    return out


def bollinger_bandwidth(closes: list[float], period: int = 20, nstd: float = 2.0) -> list[float | None]:
    """(upper − lower) / middle, population standard deviation."""
    out: list[float | None] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        if mean == 0:
            continue
        var = sum((value - mean) ** 2 for value in window) / period
        std = math.sqrt(var)
        out[i] = (2 * nstd * std) / mean
    return out


def expanding_percentile(values: list[float | None], min_obs: int = 1) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    history: list[float] = []
    for i, value in enumerate(values):
        if value is None:
            continue
        history.append(value)
        if len(history) < min_obs:
            continue
        at_or_below = sum(1 for item in history if item <= value)
        out[i] = 100.0 * at_or_below / len(history)
    return out


def is_window_high(values: list[float | None], index: int, window: int) -> bool:
    if values[index] is None or index + 1 < window:
        return False
    chunk = values[index - window + 1 : index + 1]
    if any(value is None for value in chunk):
        return False
    return values[index] >= max(chunk)


def soft_score(adx: float | None, spread: float | None) -> float | None:
    """19.8 − 0.35·(ADX−33.7) + 1.15·(spread−2.5) − 0.10·(ADX−33.7)·(spread−2.5)."""
    if adx is None or spread is None:
        return None
    adx_gap = adx - 33.7
    spread_gap = spread - 2.5
    return 19.8 - 0.35 * adx_gap + 1.15 * spread_gap - 0.10 * adx_gap * spread_gap


def scored_signal(
    trix2: float | None,
    trix5: float | None,
    adx: float | None,
    daily_lite: str | None,
    tx_ok: bool = False,
) -> str | None:
    """Champion production score. A weekly TRIX2 ≤ 0 is SELL and is not promoted."""
    if trix2 is None:
        return None
    if trix2 <= 0:
        return "SELL"
    score = 0.0
    if trix5 is not None and trix2 > trix5:
        score += WEIGHT_WEEKLY
    if adx is not None and adx > ADX_ENTRY_MIN:
        score += WEIGHT_ADX
    if daily_lite == "BUY":
        score += WEIGHT_DAILY
    if tx_ok:
        score += WEIGHT_TX
    return "BUY" if score >= SCORED_MIN else "WAIT"


def champion_size(p_buy: float | None) -> float:
    """max(0.4, min(1.6, (p − 0.25) / 0.35)). Missing Tx uses p = 0.5."""
    p_value = 0.5 if p_buy is None else float(p_buy)
    return max(0.4, min(1.6, (p_value - 0.25) / 0.35))


def ticker_risk(
    model: str,
    weekly_call: str,
    daily_call: str,
    roc: float,
    pct_from_52w_high: float,
    atr_pct: float,
    adx: float,
) -> float:
    score = {"BUY": 25, "WAIT": 55, "SELL": 82}[model]
    score += {"BUY": -8, "WAIT": 4, "SELL": 14}[weekly_call]
    score += {"BUY": -8, "WAIT": 4, "SELL": 16}[daily_call]
    score += clamp(-roc * 2, -14, 18)
    if pct_from_52w_high <= -30:
        score += 18
    elif pct_from_52w_high <= -15:
        score += 10
    elif pct_from_52w_high >= -5:
        score += -6
    score += clamp((atr_pct - 4) * 2, -4, 12)
    if adx >= 25 and model == "SELL":
        score += 8
    return clamp(score)


def watchlist_day(rocs: list[float]) -> dict[str, float]:
    avg_roc = sum(rocs) / len(rocs)
    pct_negative = 100.0 * sum(1 for value in rocs if value < 0) / len(rocs)
    risk = clamp(50.0 - avg_roc * 3.0 + (pct_negative - 50.0) * 0.45)
    return {
        "roc": avg_roc,
        "negativePct": pct_negative,
        "risk": risk,
        "n": float(len(rocs)),
    }


def nash_score(mri: float, watch_risk: float, roc: float) -> dict[str, float | str]:
    roc_pressure = clamp(50.0 - roc * 3.5)
    disagreement = abs(mri - watch_risk)
    score = clamp(0.42 * mri + 0.33 * watch_risk + 0.17 * roc_pressure + 0.08 * disagreement)
    if score >= 75:
        zone = "CRISIS"
    elif score >= 65:
        zone = "HIGH"
    elif score >= 55:
        zone = "ELEVATED"
    elif score >= 45:
        zone = "NORMAL"
    else:
        zone = "CALM"
    return {
        "nash": score,
        "zone": zone,
        "state": "RISK_OFF" if score >= 65 else "RISK_ON",
        "rocPressure": roc_pressure,
        "disagreement": disagreement,
    }


def sample_mean_std(values: list[float]) -> tuple[float, float]:
    """Sample mean and sample standard deviation (n − 1)."""
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((value - mean) ** 2 for value in values) / (n - 1)
    return mean, math.sqrt(var)


def roc_zone(roc: float, mean: float, std: float) -> tuple[float | None, str]:
    if std == 0:
        return None, "AVERAGE"
    z_score = (roc - mean) / std
    if z_score > 1:
        return z_score, "HIGH"
    if z_score < -1:
        return z_score, "LOW"
    return z_score, "AVERAGE"
