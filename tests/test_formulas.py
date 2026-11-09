import unittest
from datetime import date

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
