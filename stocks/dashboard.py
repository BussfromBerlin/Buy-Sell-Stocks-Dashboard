"""Assemble the Stocks payload from Yahoo, FRED, and Nasdaq."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

from stocks.book import analyze, rank_rows
from stocks.feed import fetch_fred, fetch_nasdaq100, fetch_yahoo, yahoo_symbol
from stocks.indicators import (
    ROC_HISTORY_START,
    ROC_PERIOD,
    WATCHLIST,
    WATCHLIST_INDEX_START,
    nash_score,
    roc_series,
    roc_zone,
    sample_mean_std,
    watchlist_day,
)
from stocks.llss import chart_payload
from stocks.mri import chart_mri, compute_mri, liquidity_levels

LLSS_CHART_START = "2023-07-01"
FRED_IDS = ("WALCL", "WTREGEN", "RRPONTSYD")


def build(progress=None) -> dict:
    def report(phase: str, done: int, total: int, detail: str = "") -> None:
        if progress:
            progress(phase, done, total, detail)

    symbols, nasdaq_asof, nasdaq_error = fetch_nasdaq100()
    report("list", 1, 1, nasdaq_asof or nasdaq_error or "")
    errors = [nasdaq_error] if nasdaq_error else []
    book_names = list(dict.fromkeys([*WATCHLIST, *symbols]))
    jobs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(symbol: str, interval: str) -> None:
        key = (symbol, interval)
        if key not in seen:
            seen.add(key)
            jobs.append(key)

    for ticker in book_names:
        yahoo = yahoo_symbol(ticker)
        add(yahoo, "1d")
        add(yahoo, "1wk")
    for extra in ("QQQ", "^VIX", "HYG", "IEF"):
        add(extra, "1d")

    frames: dict[tuple[str, str], list] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_yahoo, symbol, interval): (symbol, interval) for symbol, interval in jobs}
        for future in as_completed(futures):
            symbol, interval = futures[future]
            bars, error = future.result()
            frames[(symbol, interval)] = bars
            if error:
                errors.append(error)
            done += 1
            report("prices", done, len(jobs), symbol)

    fred: dict[str, dict[str, float]] = {}
    fred_failed = False
    for index, series_id in enumerate(FRED_IDS, start=1):
        report("liquidity", index, len(FRED_IDS), series_id)
        observations, error = fetch_fred(series_id)
        if error or not observations:
            fred_failed = True
            if error:
                errors.append(error)
        else:
            fred[series_id] = observations

    report("compute", 0, 1, "scores")
    analyses = {}
    for ticker in book_names:
        yahoo = yahoo_symbol(ticker)
        analyses[ticker] = analyze(
            ticker,
            frames.get((yahoo, "1d"), []),
            frames.get((yahoo, "1wk"), []),
        )

    watch_rows = [analyses[ticker] for ticker in WATCHLIST if ticker in analyses]
    ndx_rows = [analyses[ticker] for ticker in symbols if ticker in analyses]
    mri_rows, liquidity = compute_mri_rows(frames, None if fred_failed else fred)
    llss = _llss(frames.get(("^NDX", "1d"), []))
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "errors": errors,
        "watchlistIndex": _watchlist_index(watch_rows),
        "ndxRoc": _ndx_roc(frames.get(("^NDX", "1d"), []), (mri_rows, liquidity)),
        "nashMri": _nash(watch_rows, mri_rows, liquidity),
        "llss": llss,
        "champion": {
            **_champion_card(),
            "alert": llss["alert"],
            "alertRule": llss["rule"],
            "latestTurn": llss["latestLabel"],
            "seriesMissing": True,
        },
        "tabs": {
            "watchlist": rank_rows(watch_rows),
            "ndx100": rank_rows(ndx_rows),
        },
        "nasdaqAsOf": nasdaq_asof,
        "watchlistCount": len(WATCHLIST),
        "ndxCount": len(symbols),
    }
    report("compute", 1, 1, "ready")
    return payload


def compute_mri_rows(frames, fred) -> tuple[list[dict], str]:
    qqq = frames.get(("QQQ", "1d"), [])
    if not qqq:
        return [], "QQQ prices unavailable"
    levels, source = liquidity_levels(
        [bar.date for bar in qqq],
        fred,
        frames.get(("HYG", "1d"), []),
        frames.get(("IEF", "1d"), []),
    )
    rows = compute_mri(qqq, frames.get(("^VIX", "1d"), []), frames.get(("^NDX", "1d"), []), levels)
    return rows, source


def _watchlist_index(rows: list[dict]) -> dict:
    universe = [row for row in rows if row["ticker"] != "NDX" and not row["missing"]]
    risks = [row["risk"] for row in universe if row["risk"] is not None]
    rocs = [row["latestRoc"] for row in universe if row["latestRoc"] is not None]
    by_date: dict[str, list[float]] = defaultdict(list)
    for row in universe:
        for point in row["rocPoints"]:
            if point["date"] >= ROC_HISTORY_START:
                by_date[point["date"]].append(point["roc"])
    history = []
    for day in sorted(by_date):
        stats = watchlist_day(by_date[day])
        stats["date"] = day
        history.append(stats)
    chart = [_round_day(day) for day in history if day["date"] >= WATCHLIST_INDEX_START]
    return {
        "title": "Dash1 Watchlist Risk / ROC Indices",
        "universe": len(universe),
        "listed": sum(1 for row in rows if row["ticker"] != "NDX"),
        "riskIndex": _mean(risks),
        "rocIndex": _mean(rocs),
        "positiveRoc": None if not rocs else 100.0 * sum(1 for value in rocs if value > 0) / len(rocs),
        "series": chart,
        "missing": [row["ticker"] for row in rows if row["ticker"] != "NDX" and row["missing"]],
    }


def _ndx_roc(bars, mri_pack: tuple[list[dict], str]) -> dict:
    mri_rows, _source = mri_pack
    mri_by_date = {row["date"]: row["mri"] for row in mri_rows}
    closes = [bar.close for bar in bars]
    rocs = roc_series(closes, ROC_PERIOD)
    sample = [rocs[i] for i, bar in enumerate(bars) if bar.date >= ROC_HISTORY_START and rocs[i] is not None]
    if not sample:
        return {"title": "NDX Rate of Change", "error": "No NDX daily prices", "series": []}
    mean, std = sample_mean_std(sample)
    series = []
    for i, bar in enumerate(bars):
        if bar.date < WATCHLIST_INDEX_START or rocs[i] is None:
            continue
        series.append(
            {
                "date": bar.date,
                "close": round(bar.close, 2),
                "roc": round(rocs[i], 4),
                "mri": None if mri_by_date.get(bar.date) is None else round(mri_by_date[bar.date], 3),
            }
        )
    last = series[-1]
    z_score, zone = roc_zone(last["roc"], mean, std)
    return {
        "title": "NDX Rate of Change",
        "chartTitle": "NDX · QQQ MRI overlay + ROC(10) since 2025-08-14",
        "asOf": last["date"],
        "close": last["close"],
        "roc": last["roc"],
        "z": None if z_score is None else round(z_score, 3),
        "zone": zone,
        "mean": round(mean, 4),
        "std": round(std, 4),
        "band1": [round(mean - std, 4), round(mean + std, 4)],
        "band2": [round(mean - 2 * std, 4), round(mean + 2 * std, 4)],
        "series": series,
        "error": None,
    }


def _nash(rows: list[dict], mri_rows: list[dict], source: str) -> dict:
    by_date: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["ticker"] == "NDX" or row["missing"]:
            continue
        for point in row["rocPoints"]:
            if point["date"] >= ROC_HISTORY_START:
                by_date[point["date"]].append(point["roc"])
    mri_by_date = {row["date"]: row for row in mri_rows}
    latest = None
    for day in sorted(by_date):
        mri = mri_by_date.get(day)
        if not mri:
            continue
        stats = watchlist_day(by_date[day])
        score = nash_score(mri["mri"], stats["risk"], stats["roc"])
        latest = {
            "date": day,
            "nash": round(float(score["nash"]), 2),
            "zone": score["zone"],
            "state": score["state"],
            "mri": round(mri["mri"], 2),
            "mriZone": mri["zone"],
            "correction": float(score["nash"]) >= 65 and mri["mri"] >= 60,
        }
    if not mri_rows:
        return {"title": "Nash & MRI", "error": "MRI prices unavailable", "series": [], "liquidity": source}
    return {
        "title": "Nash & MRI",
        "error": None if latest else "Nash needs both MRI and the watchlist risk history",
        "liquidity": source,
        "latest": latest,
        "series": chart_mri(mri_rows),
    }


def _llss(bars) -> dict:
    as_of = date.fromisoformat(bars[-1].date) if bars else datetime.now(timezone.utc).date()
    ndx = [
        {"date": bar.date, "close": round(bar.close, 2)}
        for bar in bars
        if bar.date >= LLSS_CHART_START
    ]
    payload = chart_payload(as_of, ndx)
    if not ndx:
        payload["priceError"] = "Nasdaq-100 prices are unavailable. The known turns are still marked."
    return payload


def _champion_card() -> dict:
    return {
        "title": "Champion",
        "rules": (
            "Entry is a scored BUY: weekly TRIX2 > TRIX5, ADX(14) > 25 on log prices, "
            "and daily lite BUY, score at least 3.0. Weekly TRIX2 ≤ 0 is SELL. "
            "Tx P(BUY) is not in the source, so that bit is off and a buy is sized at 0.714×."
        ),
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _round_day(day: dict) -> dict:
    return {
        "date": day["date"],
        "roc": round(day["roc"], 4),
        "risk": round(day["risk"], 3),
        "negativePct": round(day["negativePct"], 3),
        "n": int(day["n"]),
    }
