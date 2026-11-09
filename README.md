# Stocks

A stock dashboard on the Champion model, with the Pulse book and the Dash1 charts.

## Run

```bash
python3 -m stocks
```

Open http://127.0.0.1:8765

The first load fetches Yahoo prices (10-year daily and weekly), the Nasdaq-100 list, and FRED liquidity. No API key. Results are cached under `data/cache/` for the rest of that UTC day. If FRED fails, MRI liquidity uses the HYG/IEF close ratio. Names with no prices stay in the book with a note.

## Pulse columns

Rank, Ticker, Price, Pulse, Entry, Max buy, Exit signal, Weekly 2/4/6, Daily 2/5/12, Note.

These are the Pulse table headers from Dash1 `scripts/render_trix_html.py` (weekly 2/4/6, daily 2/5/12). Pulse is a BUY only when both stacks are BUY, CMF(20) ≥ 0, and softScore ≥ 18. Weekly TRIX2 ≤ 0 is the exit.

Entry, Max buy, and Exit signal are Champion, not a Pulse size. Champion buys when weekly TRIX2 > TRIX5, ADX(14) > 25 on log prices, and the daily 3/6/16 lite call is BUY (score 3.5 of 4.0). Weekly TRIX2 ≤ 0 is SELL and is never promoted. Tx P(BUY) is not in the source, so that bit is off and a buy is sized at 0.714× from p = 0.5. LLSS does not change those rules.

- Dash1 watchlist: the 45 names in Dash1 `watchlist.json` as of 2026-11-08 13:10 UTC, in that order. It is not labeled as a universe of 42.
- NDX 100: https://api.nasdaq.com/api/quote/list-type/nasdaq100

## Charts

1. **Dash1 Watchlist Risk / ROC Indices.** Daily ROC(10) for every watchlist name except NDX. ROC index is the equal-weight mean. Risk is `clamp(50 − roc×3 + (negative% − 50)×0.45)`. The chart starts 2025-08-14. The headline risk index is the cross-section of model, weekly, and daily calls, ROC, the 52-week drawdown, and ATR.
2. **NDX Rate of Change.** Yahoo `^NDX` daily ROC(10), bands from the sample since 2021-01-01, drawn since 2025-08-14, with QQQ MRI on the same dates.
3. **Nash & MRI.** MRI is the equal-weight mix of VIX, MFI(14), consolidation, liquidity, accumulation, ADX, and moving averages on QQQ. Nash is `clamp(0.42·MRI + 0.33·watch risk + 0.17·ROC pressure + 0.08·|MRI − watch risk|)`. The chart is the MRI history. Nash is the readout.
4. **LLSS turns on NDX.** The monthly LLSS series is not in the source, so there is no LLSS line. The Nasdaq-100 close is plotted from 2023-07-01, with only these turns marked: unconfirmed bottom 31 Oct 2023 at 14,409.78 (not below −1.0), unconfirmed top 28 Jun 2024 at 19,682.87 (not above +1.5), confirmed bottom 31 Jul 2026 at 28,274 (below −1.0). A turn counts after the second following month-end. The latest completed turn is confirmed, so the Champion card does not raise an unconfirmed-turn alert.

Prices: `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={1d|1wk}&range=10y`. `NDX` is `^NDX`. Liquidity: `https://fred.stlouisfed.org/graph/fredgraph.csv?id={WALCL|WTREGEN|RRPONTSYD}`.
