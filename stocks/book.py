"""Per-ticker Pulse columns and Champion entry, size, and exit."""

from __future__ import annotations

import bisect

from stocks.feed import Bar
from stocks.indicators import (
    ADX_PERIOD,
    PULSE_DAILY,
    PULSE_WEEKLY,
    PRODUCTION_DAILY,
    PRODUCTION_WEEKLY,
    ROC_PERIOD,
    atr_series,
    champion_size,
    cmf_series,
    lightweight_call,
    log_ohlc,
    roc_series,
    scored_signal,
    soft_score,
    ticker_risk,
    trix_series,
    wilder_adx,
)


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _nums(values: list[float | None]) -> str:
    return " / ".join(_fmt(value) for value in values)


def analyze(ticker: str, daily: list[Bar], weekly: list[Bar]) -> dict:
    """One book row plus the series the watchlist index needs."""
    if not daily:
        return _empty(ticker, "No Yahoo daily prices")
    price = daily[-1].close
    if not weekly:
        row = _empty(ticker, "No Yahoo weekly prices")
        row["price"] = price
        row["priceText"] = _fmt(price)
        return row

    closes = [bar.close for bar in daily]
    highs = [bar.high for bar in daily]
    lows = [bar.low for bar in daily]
    volumes = [bar.volume for bar in daily]
    log_high: list[float | None] = []
    log_low: list[float | None] = []
    log_close: list[float | None] = []
    for bar in daily:
        logged = log_ohlc(bar.high, bar.low, bar.close)
        if logged is None:
            log_high.append(None)
            log_low.append(None)
            log_close.append(None)
        else:
            log_high.append(logged[0])
            log_low.append(logged[1])
            log_close.append(logged[2])

    daily_champion = {period: trix_series(log_close, period) for period in PRODUCTION_DAILY}
    daily_pulse = {period: trix_series(closes, period) for period in PULSE_DAILY}
    adx, _plus_di, _minus_di = wilder_adx(log_high, log_low, log_close, ADX_PERIOD)
    cmf20 = cmf_series(highs, lows, closes, volumes, 20)
    roc = roc_series(closes, ROC_PERIOD)
    atr = atr_series(highs, lows, closes, 14)

    weekly_closes = [bar.close for bar in weekly]
    weekly_trix = {
        period: trix_series(weekly_closes, period)
        for period in set(PRODUCTION_WEEKLY + PULSE_WEEKLY)
    }
    dates = [bar.date for bar in daily]

    in_position = False
    entry: tuple[str, float] | None = None
    exit_text = "—"
    last_signal: str | None = None
    last_daily: int | None = None
    for i in range(len(weekly)):
        start = weekly[i].date
        end = weekly[i + 1].date if i + 1 < len(weekly) else "9999-12-31"
        left = bisect.bisect_left(dates, start)
        right = bisect.bisect_left(dates, end)
        daily_index = right - 1 if right > left else None
        trix2 = weekly_trix[2][i]
        trix5 = weekly_trix[5][i]
        if daily_index is None:
            adx_value = None
            lite = None
        else:
            adx_value = adx[daily_index]
            lite = lightweight_call(
                daily_champion[3][daily_index],
                daily_champion[6][daily_index],
                daily_champion[16][daily_index],
            )
        signal = scored_signal(trix2, trix5, adx_value, lite, tx_ok=False)
        if trix2 is not None and trix2 <= 0:
            in_position = False
            entry = None
            exit_text = "Exit — weekly TRIX2 ≤ 0"
        elif signal == "BUY":
            if not in_position:
                if daily_index is None:
                    entry = (weekly[i].date, weekly[i].close)
                else:
                    entry = (daily[daily_index].date, daily[daily_index].close)
                in_position = True
            exit_text = "Still open — exit on weekly TRIX2 ≤ 0"
        elif in_position:
            exit_text = "Still open — exit on weekly TRIX2 ≤ 0"
        else:
            exit_text = "—"
        last_signal = signal
        last_daily = daily_index

    week = len(weekly) - 1
    if last_daily is None:
        pulse, note = None, "No daily bar in the latest week"
        weekly_call = None
        daily_call = None
        risk = None
        latest_roc = None
    else:
        pulse_fast = weekly_trix[PULSE_WEEKLY[0]][week]
        pulse_med = weekly_trix[PULSE_WEEKLY[1]][week]
        pulse_slow = weekly_trix[PULSE_WEEKLY[2]][week]
        weekly_call = lightweight_call(pulse_fast, pulse_med, pulse_slow)
        daily_call_pulse = lightweight_call(
            daily_pulse[2][last_daily],
            daily_pulse[5][last_daily],
            daily_pulse[12][last_daily],
        )
        champion_weekly = lightweight_call(
            weekly_trix[2][week], weekly_trix[5][week], weekly_trix[7][week]
        )
        champion_daily = lightweight_call(
            daily_champion[3][last_daily],
            daily_champion[6][last_daily],
            daily_champion[16][last_daily],
        )
        spread = None
        if weekly_trix[2][week] is not None and weekly_trix[5][week] is not None:
            spread = weekly_trix[2][week] - weekly_trix[5][week]
        soft = soft_score(adx[last_daily], spread)
        pulse, note = _pulse(
            weekly_call,
            daily_call_pulse,
            pulse_fast,
            cmf20[last_daily],
            soft,
        )
        latest_roc = roc[last_daily]
        risk = _risk(
            last_signal,
            champion_weekly,
            champion_daily,
            latest_roc,
            closes,
            last_daily,
            atr[last_daily],
            adx[last_daily],
        )
        daily_call = daily_call_pulse
        weekly_nums = _nums([pulse_fast, pulse_med, pulse_slow])
        daily_nums = _nums(
            [daily_pulse[2][last_daily], daily_pulse[5][last_daily], daily_pulse[12][last_daily]]
        )

    if last_daily is None:
        weekly_nums = "—"
        daily_nums = "—"
        daily_call = None
        soft = None

    size = champion_size(None) if last_signal == "BUY" else None
    roc_points = [
        {"date": daily[i].date, "roc": roc[i]}
        for i in range(len(daily))
        if roc[i] is not None
    ]
    return {
        "ticker": ticker,
        "price": price,
        "priceText": _fmt(price),
        "pulse": pulse,
        "entry": "—" if not in_position or entry is None else f"{entry[0]} · ${_fmt(entry[1])}",
        "maxBuy": "—" if size is None else f"{size:.3f}×",
        "exitSignal": exit_text,
        "weeklyCall": weekly_call,
        "weeklyNums": weekly_nums,
        "dailyCall": daily_call,
        "dailyNums": daily_nums,
        "note": note,
        "soft": soft,
        "risk": risk,
        "latestRoc": latest_roc,
        "rocPoints": roc_points,
        "missing": False,
    }


def _pulse(weekly_call, daily_call, weekly_trix2, cmf, soft) -> tuple[str | None, str]:
    if weekly_trix2 is None:
        return None, "Not enough weekly history"
    if weekly_trix2 <= 0:
        return "SELL", "Weekly TRIX2 ≤ 0"
    if weekly_call == "BUY" and daily_call == "BUY":
        failures: list[str] = []
        if cmf is None or cmf < 0:
            failures.append("CMF missing" if cmf is None else f"CMF {cmf:.3f} < 0")
        if soft is None or soft < 18:
            failures.append("softScore missing" if soft is None else f"softScore {soft:.1f} < 18")
        if failures:
            return "WAIT", "Demoted: " + ", ".join(failures)
        return "BUY", f"Daily BUY and weekly BUY, CMF {cmf:.3f}, softScore {soft:.1f}"
    return "WAIT", f"Weekly {weekly_call or '—'}, daily {daily_call or '—'}"


def _risk(model, weekly_call, daily_call, roc, closes, index, atr, adx) -> float | None:
    if None in (model, weekly_call, daily_call, roc, atr, adx):
        return None
    start = max(0, index - 251)
    window = closes[start : index + 1]
    if not window or max(window) == 0:
        return None
    pct = (closes[index] / max(window) - 1.0) * 100.0
    atr_pct = atr / closes[index] * 100.0
    return ticker_risk(model, weekly_call, daily_call, roc, pct, atr_pct, adx)


def _empty(ticker: str, note: str) -> dict:
    return {
        "ticker": ticker,
        "price": None,
        "priceText": "—",
        "pulse": None,
        "entry": "—",
        "maxBuy": "—",
        "exitSignal": "—",
        "weeklyCall": None,
        "weeklyNums": "—",
        "dailyNums": "—",
        "dailyCall": None,
        "note": note,
        "soft": None,
        "risk": None,
        "latestRoc": None,
        "rocPoints": [],
        "missing": True,
    }


def rank_rows(rows: list[dict]) -> list[dict]:
    """Display order is Pulse call, then softScore. Not champion_buy_strength."""
    order = {"BUY": 0, "WAIT": 1, "SELL": 2}

    def key(row: dict):
        soft = row.get("soft")
        return (
            row.get("pulse") not in order,
            order.get(row.get("pulse"), 9),
            -(soft if isinstance(soft, (int, float)) else -1e18),
            row["ticker"],
        )

    ranked = []
    for rank, row in enumerate(sorted(rows, key=key), start=1):
        public = {k: v for k, v in row.items() if k not in ("rocPoints", "soft", "risk", "latestRoc")}
        public["rank"] = rank
        ranked.append(public)
    return ranked
