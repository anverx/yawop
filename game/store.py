"""yawop persistence: wraps kivyshell's generic SqliteStore.

Variant = difficulty (easy/medium/hard). Daily challenges are keyed by date;
random games have date=None (they show in the logbook but not the calendar/streak).
The answer word is encoded into the challenge `code` so the logbook can show it.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from datetime import date, timedelta

from kivyshell.shell import Completion, SqliteStore

DIFFICULTIES = ["easy", "medium", "hard"]


def _code(d: str | None, difficulty: str, answer: str) -> str:
    return f"{'d' if d else 'r'}:{d or ''}:{difficulty}:{answer}"


def answer_of(code: str) -> str:
    return code.split(":")[-1]


@dataclass
class CalData:
    """Field names match what kivyshell's CalendarScreen reads."""
    month_name: str
    streak_text: str
    month_status: dict           # date_iso -> {difficulty: Completion}
    month_crown: object          # Completion
    protected_dates: set = field(default_factory=set)


class _CalState:
    """CalendarState-like object over the store (year/month nav + fetch_data)."""

    def __init__(self, db: SqliteStore) -> None:
        self._db = db
        t = date.today()
        self.year, self.month = t.year, t.month

    def _is_current(self) -> bool:
        t = date.today()
        return (self.year, self.month) == (t.year, t.month)

    def prev_month(self) -> None:
        self.month -= 1
        if self.month == 0:
            self.month, self.year = 12, self.year - 1

    def next_month(self) -> bool:
        if self._is_current():
            return False
        self.month += 1
        if self.month == 13:
            self.month, self.year = 1, self.year + 1
        return True

    def fetch_data(self) -> CalData:
        ms = self._db.month_status(self.year, self.month, DIFFICULTIES)
        return CalData(ms.month_name, ms.streak_text, ms.days, ms.month_badge, ms.protected_dates)


class WordStore:
    def __init__(self) -> None:
        self._db = SqliteStore()

    def open(self, data_dir: str) -> None:
        self._db.open(data_dir)

    def close(self) -> None:
        self._db.close()

    # --- play lifecycle ---
    def start(self, difficulty: str, day: str | None, answer: str) -> int:
        cid = self._db.record_challenge(difficulty, day, _code(day, difficulty, answer))
        return self._db.start_play(cid)

    def complete(self, play_id: int, duration_ms: int) -> None:
        self._db.complete_play(play_id, duration_ms)

    # --- menu / calendar ---
    def today_completion(self) -> dict[str, bool]:
        c = self._db.completion_today(date.today().isoformat(), DIFFICULTIES)
        return {k: (v is not Completion.NONE) for k, v in c.items()}

    def streak(self) -> int:
        return self._db.streak()

    def calendar_state(self) -> _CalState:
        return _CalState(self._db)

    # --- logbook ---
    def all_plays(self, limit: int = 200, offset: int = 0):
        return self._db.all_plays(limit=limit, offset=offset)

    def stats_by_difficulty(self) -> dict:
        agg = {d: {"count": 0, "completed": 0, "best": None, "total": 0} for d in DIFFICULTIES}
        for p in self._db.all_plays(limit=100000):
            a = agg.get(p.variant_id)
            if a is None:
                continue
            a["count"] += 1
            if p.completed:
                a["completed"] += 1
                if p.duration_ms:
                    a["total"] += p.duration_ms
                    a["best"] = p.duration_ms if a["best"] is None else min(a["best"], p.duration_ms)
        return agg

    def games_per_day(self, days: int = 30) -> list[tuple[str, dict[str, int]]]:
        window = [(date.today() - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
        counts: dict[str, dict[str, int]] = {}
        for p in self._db.all_plays(limit=100000):
            if not p.completed:
                continue
            d = (p.completed_at or p.started_at or "")[:10]
            if d in window:
                counts.setdefault(d, {})
                counts[d][p.variant_id] = counts[d].get(p.variant_id, 0) + 1
        return [(d, counts.get(d, {})) for d in window]
