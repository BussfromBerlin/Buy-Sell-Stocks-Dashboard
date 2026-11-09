import unittest
from datetime import date

from stocks.book import champion_note, champion_prices, rank_rows
from stocks.indicators import (
    champion_size,
    lightweight_call,
    log_ohlc,
    nash_score,
    roc_series,
    scored_signal,
    soft_score,
    ticker_risk,
    trix_series,
    watchlist_day,
)
from stocks.llss import KNOWN_TURNS, latest_alert, turn_label


class FormulaTests(unittest.TestCase):
    def test_roc_and_watchlist_day(self):
        closes = [100.0] * 10 + [110.0]
        self.assertAlmostEqual(roc_series(closes, 10)[-1], 10.0)
        day = watchlist_day([2.0, -1.0])
        self.assertAlmostEqual(day["roc"], 0.5)
        self.assertAlmostEqual(day["negativePct"], 50.0)

    def test_lightweight_and_champion_score(self):
        self.assertEqual(lightweight_call(-1, -1, -1), "WAIT")
        self.assertEqual(lightweight_call(2, 1, 0.5), "BUY")
        self.assertEqual(lightweight_call(-1, 2, 0.5), "SELL")
        self.assertEqual(scored_signal(1, 0, 30, "BUY", tx_ok=False), "BUY")
        self.assertEqual(scored_signal(1, 0, 20, "BUY", tx_ok=False), "WAIT")
        self.assertEqual(scored_signal(-0.1, 0, 40, "BUY", tx_ok=False), "SELL")
        self.assertAlmostEqual(champion_size(None), (0.5 - 0.25) / 0.35)

    def test_soft_score_nash_and_risk(self):
        self.assertAlmostEqual(soft_score(33.7, 2.5), 19.8)
        score = nash_score(60, 40, 0)
        self.assertAlmostEqual(score["nash"], 48.5)
        self.assertEqual(score["zone"], "NORMAL")
        risk = ticker_risk("BUY", "BUY", "BUY", 5, -3, 3, 20)
        self.assertEqual(risk, 0)
        self.assertAlmostEqual(log_ohlc(10, 11, 12)[0], __import__("math").log(12))

    def test_entry_and_exit_keep_champion_prices(self):
        opened = champion_prices([
            {"trix2": 1.0, "signal": "BUY", "date": "2026-10-05", "price": 179.37},
            {"trix2": 0.4, "signal": "WAIT", "date": "2026-10-12", "price": 181.0},
        ])
        self.assertEqual(opened["entry"], "2026-10-05 · $179.37")
        self.assertEqual(opened["exitSignal"], "Still open — exit on weekly TRIX2 ≤ 0")

        closed = champion_prices([
            {"trix2": 1.0, "signal": "BUY", "date": "2026-10-05", "price": 179.37},
            {"trix2": -0.2, "signal": "SELL", "date": "2026-11-02", "price": 170.25},
            {"trix2": -0.4, "signal": "SELL", "date": "2026-11-09", "price": 168.0},
        ])
        self.assertEqual(closed["entry"], "2026-10-05 · $179.37")
        self.assertEqual(closed["exitSignal"], "Exit 2026-11-02 · $170.25 — weekly TRIX2 ≤ 0")

        flagged = champion_prices([
            {"trix2": -0.2, "signal": "SELL", "date": "2026-11-02", "price": 84.39},
            {"trix2": -0.5, "signal": "SELL", "date": "2026-11-09", "price": 80.10},
        ])
        self.assertEqual(flagged["entry"], "—")
        self.assertIn("$80.10", flagged["exitSignal"])
        self.assertNotEqual(flagged["exitSignal"], "Exit — weekly TRIX2 ≤ 0")

    def test_rank_follows_champion_not_pulse(self):
        ranked = rank_rows([
            {"ticker": "AAA", "pulse": "BUY", "champion": "SELL", "soft": 40},
            {"ticker": "BBB", "pulse": "SELL", "champion": "BUY", "soft": 1},
        ])
        self.assertEqual([row["ticker"] for row in ranked], ["BBB", "AAA"])
        self.assertNotIn("soft", ranked[0])

    def test_champion_note_does_not_use_pulse_soft_score(self):
        note = champion_note("WAIT", 1.0, 2.0, 20.0, "WAIT")
        self.assertTrue(note.startswith("Champion WAIT"))
        self.assertNotIn("softScore", note)
        self.assertIn("Tx off", note)
        sell = champion_note("SELL", -0.2, 1.0, 40.0, "BUY")
        self.assertIn("Not promoted", sell)

    def test_trix_turns_positive_on_a_rise(self):
        closes = [float(i) for i in range(1, 80)]
        series = [value for value in trix_series(closes, 3) if value is not None]
        self.assertGreater(series[-1], 0)


class LlssTests(unittest.TestCase):
    def test_only_the_known_turns_and_no_series_values(self):
        self.assertEqual([turn["date"] for turn in KNOWN_TURNS], ["2023-10-31", "2024-06-28", "2026-07-31"])
        for turn in KNOWN_TURNS:
            self.assertNotIn("llss", turn)

    def test_labels_keep_the_threshold_meaning(self):
        labels = [turn_label(turn) for turn in KNOWN_TURNS]
        self.assertEqual(
            labels[0],
            "Unconfirmed bottom · 31 Oct 2023 · NDX 14,409.78 · not below −1.0",
        )
        self.assertEqual(
            labels[1],
            "Unconfirmed top · 28 Jun 2024 · NDX 19,682.87 · not above +1.5",
        )
        self.assertEqual(
            labels[2],
            "Confirmed bottom · 31 Jul 2026 · NDX 28,274 · below −1.0",
        )

    def test_alert_follows_the_latest_completed_turn(self):
        self.assertIsNone(latest_alert(date(2026, 11, 9)))
        self.assertIn("Unconfirmed bottom", latest_alert(date(2024, 1, 15)))
        self.assertIn("Unconfirmed top", latest_alert(date(2024, 9, 1)))
        self.assertIsNone(latest_alert(date(2023, 11, 15)))


if __name__ == "__main__":
    unittest.main()
