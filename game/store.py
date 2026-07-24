"""yawop persistence: wraps kivyshell's generic SqliteStore.

Variant = difficulty (easy/medium/hard). Daily challenges are keyed by date;
random games have date=None (they show in the logbook but not the calendar/streak).
The answer word is encoded into the challenge `code` so the logbook can show it.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from datetime import date, timedelta

from kivyshell.shell import Completion, SqliteStore

DIFFICULTIES = ["easy", "medium", "hard"]
FAILED = "failed"  # calendar marker for a daily that was played but not solved


def _code(d: str | None, difficulty: str, answer: str) -> str:
    return f"{'d' if d else 'r'}:{d or ''}:{difficulty}:{answer}"


def answer_of(code: str) -> str:
    return code.split(":")[-1]


@dataclass
class Resume:
    """What start() hands back: the play to record against, plus any saved state
    (elapsed time + guesses) to resume a daily puzzle mid-solve."""
    play_id: int
    elapsed_ms: int = 0
    guesses: list = field(default_factory=list)


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
        days = ms.days
        # kivyshell month_status only reports solved days; merge in FAILED ones
        # (a dated play that finished without a win) so the calendar can mark them.
        like = f"{self.year:04d}-{self.month:02d}-%"
        rows = self._db._db.execute(
            "SELECT c.date, c.variant_id FROM plays p JOIN challenges c ON c.id=p.challenge_id "
            "WHERE c.date LIKE ? AND p.completed=0 AND p.completed_at IS NOT NULL", (like,)).fetchall()
        for d, diff in rows:
            cell = days.setdefault(d, {})
            if cell.get(diff, Completion.NONE) is Completion.NONE:  # a win wins over a failure
                cell[diff] = FAILED
        return CalData(ms.month_name, ms.streak_text, days, ms.month_badge, ms.protected_dates)


class WordStore:
    def __init__(self) -> None:
        self._db = SqliteStore()

    def open(self, data_dir: str) -> None:
        self._db.open(data_dir)
        # Board state per play: resumes an unfinished daily, and (once finished)
        # keeps the played-out board so it can always be reviewed. Each snapshot is
        # ~80 bytes (guesses as JSON + elapsed), so we keep every game indefinitely.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS progress ("
            "play_id INTEGER PRIMARY KEY, elapsed_ms INTEGER DEFAULT 0, state TEXT)")
        self._conn.commit()

    def close(self) -> None:
        self._db.close()

    @property
    def _conn(self):
        return self._db._db  # the underlying sqlite3 connection

    # --- play lifecycle ---
    def start(self, difficulty: str, day: str | None, answer: str) -> Resume:
        """Begin (or resume) a play. Dated/daily puzzles resume an unfinished play
        with its saved elapsed time + guesses; random games always start fresh."""
        cid = self._db.record_challenge(difficulty, day, _code(day, difficulty, answer))
        if day is not None:
            row = self._conn.execute(
                "SELECT p.id, pr.elapsed_ms, pr.state FROM plays p "
                "LEFT JOIN progress pr ON pr.play_id = p.id "
                "WHERE p.challenge_id=? AND p.completed_at IS NULL "
                "ORDER BY p.id DESC LIMIT 1", (cid,)).fetchone()
            if row:
                return Resume(row[0], row[1] or 0, json.loads(row[2]) if row[2] else [])
        return Resume(self._db.start_play(cid))

    def save_progress(self, play_id: int, elapsed_ms: int, guesses: list[str]) -> None:
        self._conn.execute(
            "INSERT INTO progress(play_id, elapsed_ms, state) VALUES(?,?,?) "
            "ON CONFLICT(play_id) DO UPDATE SET elapsed_ms=excluded.elapsed_ms, state=excluded.state",
            (play_id, elapsed_ms, json.dumps(guesses)))
        self._conn.commit()

    def finish(self, play_id: int, won: bool, duration_ms: int, attempts: int,
               guesses: list[str], elapsed_ms: int) -> None:
        self._db.finish_play(play_id, won, duration_ms, attempts)
        # Keep the final board (the finishing guess never reaches save_progress) so
        # the game stays reviewable forever.
        self.save_progress(play_id, elapsed_ms, guesses)

    def review_daily(self, day: str, difficulty: str):
        """The played-out board of a finished dated puzzle:
        (answer, guesses, elapsed_ms, won). None if never played, or played
        before boards were saved."""
        row = self._conn.execute(
            "SELECT pr.state, pr.elapsed_ms, p.completed, c.code FROM plays p "
            "JOIN challenges c ON c.id=p.challenge_id "
            "JOIN progress pr ON pr.play_id=p.id "
            "WHERE c.date=? AND c.variant_id=? AND p.completed_at IS NOT NULL "
            "ORDER BY p.id DESC LIMIT 1", (day, difficulty)).fetchone()
        if not row or not row[0]:
            return None
        return (answer_of(row[3]), json.loads(row[0]), row[1] or 0, bool(row[2]))

    def review_play(self, code: str, started_at: str):
        """The played-out board of a specific finished play (logbook row):
        (answer, guesses, elapsed_ms, won). None if that play has no saved board
        (e.g. it finished before boards were saved)."""
        row = self._conn.execute(
            "SELECT pr.state, pr.elapsed_ms, p.completed FROM plays p "
            "JOIN challenges c ON c.id=p.challenge_id "
            "JOIN progress pr ON pr.play_id=p.id "
            "WHERE c.code=? AND p.started_at=? AND p.completed_at IS NOT NULL "
            "LIMIT 1", (code, started_at)).fetchone()
        if not row or not row[0]:
            return None
        return (answer_of(code), json.loads(row[0]), row[1] or 0, bool(row[2]))

    def daily_finished(self, day: str, difficulty: str) -> bool:
        """True if this dated puzzle was already played to a finish (won OR failed);
        such dailies can't be retried."""
        row = self._conn.execute(
            "SELECT 1 FROM plays p JOIN challenges c ON c.id=p.challenge_id "
            "WHERE c.date=? AND c.variant_id=? AND p.completed_at IS NOT NULL LIMIT 1",
            (day, difficulty)).fetchone()
        return row is not None

    # --- menu / calendar ---
    def today_completion(self) -> dict[str, bool]:
        c = self._db.completion_today(date.today().isoformat(), DIFFICULTIES)
        return {k: (v is not Completion.NONE) for k, v in c.items()}

    def today_failed(self) -> dict[str, bool]:
        """Per-difficulty: today's daily was played to a finish but NOT solved (a loss).
        Mutually exclusive with today_completion (one play per daily)."""
        today = date.today().isoformat()
        out = {d: False for d in DIFFICULTIES}
        rows = self._conn.execute(
            "SELECT c.variant_id FROM plays p JOIN challenges c ON c.id=p.challenge_id "
            "WHERE c.date=? AND p.completed_at IS NOT NULL AND p.completed=0", (today,)).fetchall()
        for (d,) in rows:
            if d in out:
                out[d] = True
        return out

    def streak(self) -> int:
        return self._db.streak()

    def calendar_state(self) -> _CalState:
        return _CalState(self._db)

    # --- logbook ---
    def all_plays(self, limit: int = 200, offset: int = 0):
        return self._db.all_plays(limit=limit, offset=offset)

    def stats_by_difficulty(self) -> dict:
        agg = {d: {"played": 0, "won": 0, "best": None, "tries_sum": 0} for d in DIFFICULTIES}
        for p in self._db.all_plays(limit=100000):
            a = agg.get(p.variant_id)
            if a is None or p.completed_at is None:  # only finished games
                continue
            a["played"] += 1
            if p.completed:
                a["won"] += 1
                if p.attempts:
                    a["tries_sum"] += p.attempts
                if p.duration_ms:
                    a["best"] = p.duration_ms if a["best"] is None else min(a["best"], p.duration_ms)
        for a in agg.values():
            a["avg_tries"] = round(a["tries_sum"] / a["won"], 1) if a["won"] else None
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
