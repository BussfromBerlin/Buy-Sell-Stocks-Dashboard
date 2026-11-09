# Stocks

A stock dashboard. Buy and sell are the Champion model. The ticker tabs still show the Pulse columns.

## Run

```bash
python3 -m stocks
```

Open http://127.0.0.1:8765/stocks. The same page is also at `/`. The server listens on `0.0.0.0:8765`.

**Refresh** refetches Yahoo, Nasdaq, and FRED, then recomputes every card. It is not a browser reload of the last payload.

The first load fetches Yahoo prices (10-year daily and weekly), the Nasdaq-100 list, and FRED liquidity. No API key. Results are cached under `data/cache/` for the rest of that UTC day. Refresh ignores that cache, fetches again, and recomputes the cards. If FRED fails, MRI liquidity uses the HYG/IEF close ratio. Names with no prices stay in the book with a note.

## Pulse columns

Rank, Ticker, Price, Pulse, Entry, Max buy, Exit signal, Weekly 2/4/6, Daily 2/5/12, Note.

These are the Pulse table headers from Dash1 `scripts/render_trix_html.py` (weekly 2/4/6, daily 2/5/12). The Pulse column is that research call. It does not decide the trade, and neither does softScore.

Buy and sell are Champion. Weekly TRIX (2, 5, 7) is on price. Daily TRIX (3, 6, 16) and ADX(14) are on ln(H/L/C). Weekly TRIX2 ≤ 0 is SELL and is never promoted. Otherwise the score is weekly TRIX2 > TRIX5 (1.50) + ADX > 25 (1.25) + daily lite BUY (0.75) + Tx (0.50). BUY at 3.0 or more. Tx is missing, so that bit is off and is not a veto: a buy needs the other three and is sized at 0.714× from p = 0.5. LLSS is not a gate.

Entry keeps the Champion entry date and price. Exit signal shows the Champion exit date and price (`Exit 2026-11-02 · $170.25 — weekly TRIX2 ≤ 0`). A position that is still open says so.

- Dash1 watchlist: the 45 names in Dash1 `watchlist.json` as of 2026-11-08 13:10 UTC, in that order. It is not labeled as a universe of 42.
- NDX 100: https://api.nasdaq.com/api/quote/list-type/nasdaq100

## Charts

1. **Dash1 Watchlist Risk / ROC Indices.** Daily ROC(10) for every watchlist name except NDX. ROC index is the equal-weight mean. Risk is `clamp(50 − roc×3 + (negative% − 50)×0.45)`. The chart starts 2025-08-14. The headline risk index is the cross-section of model, weekly, and daily calls, ROC, the 52-week drawdown, and ATR.
2. **NDX Rate of Change.** Yahoo `^NDX` daily ROC(10), bands from the sample since 2021-01-01, drawn since 2025-08-14, with QQQ MRI on the same dates.
3. **Nash & MRI.** MRI is the equal-weight mix of VIX, MFI(14), consolidation, liquidity, accumulation, ADX, and moving averages on QQQ. Nash is `clamp(0.42·MRI + 0.33·watch risk + 0.17·ROC pressure + 0.08·|MRI − watch risk|)`. The chart is the MRI history. Nash is the readout.
4. **LLSS turns on NDX.** The monthly LLSS series is not in the source, so there is no LLSS line. The Nasdaq-100 close is plotted from 2023-07-01, with only these turns marked: unconfirmed bottom 31 Oct 2023 at 14,409.78 (not below −1.0), unconfirmed top 28 Jun 2024 at 19,682.87 (not above +1.5), confirmed bottom 31 Jul 2026 at 28,274 (below −1.0). A turn counts after the second following month-end. The latest completed turn is confirmed, so the Champion card does not raise an unconfirmed-turn alert.

Prices: `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={1d|1wk}&range=10y`. `NDX` is `^NDX`. Liquidity: `https://fred.stlouisfed.org/graph/fredgraph.csv?id={WALCL|WTREGEN|RRPONTSYD}`.
