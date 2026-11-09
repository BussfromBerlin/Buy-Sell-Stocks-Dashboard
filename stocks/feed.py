"""Yahoo, FRED, and Nasdaq feeds. No API keys. Dash1 uses the same unsigned URLs."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
USER_AGENT = "Mozilla/5.0"
YAHOO = {"NDX": "^NDX", "VIX": "^VIX"}


@dataclass(frozen=True)
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def yahoo_symbol(ticker: str) -> str:
    return YAHOO.get(ticker, ticker)


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _fetch(url: str, attempts: int = 4, timeout: int = 30) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(1.2 * (attempt + 1))
        except Exception as exc:  # network reset, timeout
            last = exc
            time.sleep(0.6 * (attempt + 1))
    assert last is not None
    raise last


def _cache_path(name: str) -> Path:
    safe = name.replace("^", "").replace("/", "_")
    return CACHE / f"{safe}.json"


def _read_fresh(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("fetchedOn") == today_utc():
        return payload
    return None


def _write_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def fetch_yahoo(symbol: str, interval: str, refresh: bool = False) -> tuple[list[Bar], str | None]:
    """Return bars and an error string. Cached for the UTC day unless refresh is set."""
    key = f"yahoo_{symbol}_{interval}"
    path = _cache_path(key)
    if not refresh:
        cached = _read_fresh(path)
        if cached is not None:
            return _bars(cached.get("bars") or []), None
    quoted = urllib.parse.quote(symbol, safe=".")
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quoted}?interval={interval}&range=10y"
    )
    try:
        payload = json.loads(_fetch(url))
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0]
    except Exception as exc:
        return [], f"{symbol} {interval}: {exc}"
    bars: list[Bar] = []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    for i, ts in enumerate(timestamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        high = highs[i] if i < len(highs) and highs[i] is not None else close
        low = lows[i] if i < len(lows) and lows[i] is not None else close
        open_ = opens[i] if i < len(opens) and opens[i] is not None else close
        volume = volumes[i] if i < len(volumes) and volumes[i] is not None else 0
        date = datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
        bars.append(Bar(date, float(open_), float(high), float(low), float(close), float(volume)))
    bars.sort(key=lambda bar: bar.date)
    if not bars:
        return [], f"{symbol} {interval}: empty chart"
    _write_cache(
        path,
        {
            "fetchedOn": today_utc(),
            "bars": [bar.__dict__ for bar in bars],
        },
    )
    return bars, None


def _bars(rows: list[dict]) -> list[Bar]:
    return [
        Bar(row["date"], row["open"], row["high"], row["low"], row["close"], row["volume"])
        for row in rows
    ]


def fetch_fred(series_id: str, refresh: bool = False) -> tuple[dict[str, float], str | None]:
    path = _cache_path(f"fred_{series_id}")
    if not refresh:
        cached = _read_fresh(path)
        if cached is not None:
            return {row["date"]: row["value"] for row in cached["rows"]}, None
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        text = _fetch(url, attempts=2, timeout=12).decode("utf-8", errors="replace")
    except Exception as exc:
        return {}, f"{series_id}: {exc}"
    rows: list[dict] = []
    for line in text.splitlines()[1:]:
        if "," not in line:
            continue
        date, raw = line.split(",", 1)
        raw = raw.strip()
        if not raw or raw == ".":
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        rows.append({"date": date.strip(), "value": value})
    if not rows:
        return {}, f"{series_id}: no observations"
    _write_cache(path, {"fetchedOn": today_utc(), "rows": rows})
    return {row["date"]: row["value"] for row in rows}, None


def fetch_nasdaq100(refresh: bool = False) -> tuple[list[str], str | None, str | None]:
    path = _cache_path("nasdaq100")
    if not refresh:
        cached = _read_fresh(path)
        if cached is not None:
            return cached["symbols"], cached.get("asOf"), None
    url = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
    try:
        payload = json.loads(_fetch(url))
        table = payload["data"]["data"]
        rows = table["rows"]
    except Exception as exc:
        return [], None, f"Nasdaq 100 list: {exc}"
    symbols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    if not symbols:
        return [], None, "Nasdaq 100 list: no symbols"
    as_of = table.get("asOf")
    _write_cache(path, {"fetchedOn": today_utc(), "symbols": symbols, "asOf": as_of})
    return symbols, as_of, None


def forward_fill(observations: dict[str, float], dates: list[str]) -> list[float | None]:
    keys = sorted(observations)
    out: list[float | None] = []
    index = 0
    last: float | None = None
    for date in dates:
        while index < len(keys) and keys[index] <= date:
            last = observations[keys[index]]
            index += 1
        out.append(last)
    return out
