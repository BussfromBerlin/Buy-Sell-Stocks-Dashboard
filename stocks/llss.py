"""LLSS turns from the 9 Nov 2026 note. There is no monthly series here.

A turn counts only after the second following month-end, the last day of
the month two months after the turn. Unconfirmed means the turn missed the
threshold: a top that is not above +1.5, or a bottom that is not below −1.0.
This module does not change Champion buy or sell rules.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime

TOP_CONFIRM = 1.5
BOTTOM_CONFIRM = -1.0

# The note names these turns and no others. It does not give an LLSS value.
KNOWN_TURNS = (
    {
        "date": "2023-10-31",
        "kind": "bottom",
        "confirmed": False,
        "ndx": 14409.78,
        "threshold": "not below −1.0",
    },
    {
        "date": "2024-06-28",
        "kind": "top",
        "confirmed": False,
        "ndx": 19682.87,
        "threshold": "not above +1.5",
    },
    {
        "date": "2026-07-31",
        "kind": "bottom",
        "confirmed": True,
        "ndx": 28274,
        "threshold": "below −1.0",
    },
)

SERIES_MISSING = (
    "The monthly LLSS series is missing. No LLSS line is drawn. "
    "The marks are the known turns on the Nasdaq-100 price."
)

ALERT_RULE = (
    "Unconfirmed means the turn missed the threshold: a top that is not above +1.5, "
    "or a bottom that is not below −1.0. That is not a one-standard-deviation band. "
    "A turn counts only after the second following month-end. "
    "The alert does not change Champion buy or sell rules."
)


def second_following_month_end(turn: date) -> date:
    month = turn.month + 2
    year = turn.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, calendar.monthrange(year, month)[1])


def turn_counts(turn: date, as_of: date) -> bool:
    return as_of > second_following_month_end(turn)


def price_text(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def date_text(iso: str) -> str:
    parsed = datetime.strptime(iso, "%Y-%m-%d").date()
    return f"{parsed.day} {parsed.strftime('%b')} {parsed.year}"


def turn_label(turn: dict) -> str:
    state = "Confirmed" if turn["confirmed"] else "Unconfirmed"
    return (
        f"{state} {turn['kind']} · {date_text(turn['date'])} · "
        f"NDX {price_text(turn['ndx'])} · {turn['threshold']}"
    )


def completed_turns(as_of: date) -> list[dict]:
    done = []
    for turn in KNOWN_TURNS:
        if turn_counts(datetime.strptime(turn["date"], "%Y-%m-%d").date(), as_of):
            done.append(turn)
    return done


def latest_alert(as_of: date) -> str | None:
    """Set only when the latest completed turn is unconfirmed."""
    done = completed_turns(as_of)
    if not done:
        return None
    latest = max(done, key=lambda turn: turn["date"])
    if latest["confirmed"]:
        return None
    return turn_label(latest)


def chart_payload(as_of: date, ndx_bars: list[dict]) -> dict:
    turns = []
    for turn in KNOWN_TURNS:
        counted = turn_counts(datetime.strptime(turn["date"], "%Y-%m-%d").date(), as_of)
        turns.append(
            {
                "date": turn["date"],
                "kind": turn["kind"],
                "confirmed": turn["confirmed"],
                "ndx": turn["ndx"],
                "threshold": turn["threshold"],
                "label": turn_label(turn),
                "counts": counted,
            }
        )
    alert = latest_alert(as_of)
    latest = max(KNOWN_TURNS, key=lambda turn: turn["date"])
    return {
        "seriesMissing": True,
        "message": SERIES_MISSING,
        "rule": ALERT_RULE,
        "topConfirm": TOP_CONFIRM,
        "bottomConfirm": BOTTOM_CONFIRM,
        "turns": turns,
        "ndx": ndx_bars,
        "alert": alert,
        "latestLabel": turn_label(latest),
        "asOf": as_of.isoformat(),
    }
