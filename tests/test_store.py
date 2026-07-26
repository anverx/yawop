"""Tests for game.store: play lifecycle, board save/restore, daily completion,
and statistics. Modelled on yaque's tests/test_database.py (temp-dir per test,
one class per concern, a message on every assertion).

game/__init__ puts the vendored kivyshell submodule on sys.path, and none of
this pulls in Kivy, so it runs headless like the other suites.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from game.store import WordStore  # noqa: E402
from kivyshell.shell import Completion  # noqa: E402


class _StoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = WordStore()
        self.store.open(self._tmp.name)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()


class TestPlayReview(_StoreTest):
    """Finishing a game snapshots its board so it can be reviewed later."""

    def test_won_daily_reviews_full_board(self):
        """A solved daily returns (answer, guesses, elapsed, won=True)."""
        r = self.store.start("medium", "2026-07-17", "crane")
        self.store.save_progress(r.play_id, 12000, ["slate", "brace"])  # mid-game autosave
        # the finishing guess never reaches save_progress, so finish() must snapshot it
        self.store.finish(r.play_id, True, 45000, 3, ["slate", "brace", "crane"], 45000)
        self.assertEqual(self.store.review_daily("2026-07-17", "medium"),
                         ("crane", ["slate", "brace", "crane"], 45000, True),
                         "won daily should review with the full board")

    def test_lost_daily_reviews_as_loss(self):
        """A daily lost at the 6th guess reviews with won=False."""
        guesses = ["adieu", "story", "point", "lucky", "frame", "blush"]
        r = self.store.start("hard", "2026-07-16", "vexil")
        self.store.finish(r.play_id, False, 60000, 6, guesses, 60000)
        answer, gs, elapsed, won = self.store.review_daily("2026-07-16", "hard")
        self.assertEqual((answer, gs, elapsed), ("vexil", guesses, 60000),
                         "lost daily should review with its guesses and time")
        self.assertFalse(won, "review should report the loss")

    def test_review_none_when_never_played(self):
        """A day that was never played has no board to review."""
        self.assertIsNone(self.store.review_daily("2026-01-01", "easy"),
                          "unplayed day should have no snapshot")

    def test_finish_keeps_snapshot(self):
        """finish() must retain the board (it used to delete it)."""
        r = self.store.start("medium", "2026-07-15", "grape")
        self.store.finish(r.play_id, True, 10000, 1, ["grape"], 10000)
        self.assertIsNotNone(self.store.review_daily("2026-07-15", "medium"),
                             "finishing should not discard the board")

    def test_random_game_reviews_by_play_reference(self):
        """A finished random game is reopened from a logbook row via (code, started_at)."""
        r = self.store.start("easy", None, "mango")
        self.store.finish(r.play_id, True, 30000, 2, ["lemon", "mango"], 30000)
        p = self.store.all_plays()[0]  # the only (random) play; date is None
        self.assertIsNone(p.date, "random game has no date")
        self.assertEqual(self.store.review_play(p.code, p.started_at),
                         ("mango", ["lemon", "mango"], 30000, True),
                         "logbook review should return that play's board")


class TestResume(_StoreTest):
    """An unfinished daily is resumable but not reviewable."""

    def test_unfinished_daily_resumes(self):
        """start() on an in-progress daily returns its play id, guesses and elapsed."""
        r = self.store.start("easy", "2026-07-14", "toast")
        self.store.save_progress(r.play_id, 5000, ["slate"])
        resumed = self.store.start("easy", "2026-07-14", "toast")
        self.assertEqual((resumed.play_id, resumed.guesses, resumed.elapsed_ms),
                         (r.play_id, ["slate"], 5000),
                         "resuming should recover the same play and its state")

    def test_unfinished_daily_not_reviewable(self):
        """An in-progress daily is not offered for review and is not 'finished'."""
        r = self.store.start("easy", "2026-07-14", "toast")
        self.store.save_progress(r.play_id, 5000, ["slate"])
        self.assertIsNone(self.store.review_daily("2026-07-14", "easy"),
                          "in-progress daily should not be reviewable")
        self.assertFalse(self.store.daily_finished("2026-07-14", "easy"),
                         "in-progress daily should not count as finished")

    def test_random_never_resumes(self):
        """Random games always start fresh (day is None), never resume."""
        r1 = self.store.start("easy", None, "mango")
        self.store.save_progress(r1.play_id, 3000, ["lemon"])
        r2 = self.store.start("easy", None, "mango")
        self.assertNotEqual(r2.play_id, r1.play_id, "random should be a new play")
        self.assertEqual(r2.guesses, [], "random should not carry prior guesses")


class TestDailyCompletion(_StoreTest):
    """daily_finished() is strict: a loss finishes the daily just like a win."""

    def test_finished_after_win(self):
        r = self.store.start("medium", "2026-06-15", "crane")
        self.store.finish(r.play_id, True, 30000, 3, ["arose", "crane"], 30000)
        self.assertTrue(self.store.daily_finished("2026-06-15", "medium"),
                        "a won daily is finished")

    def test_finished_after_loss(self):
        """Losing still finishes the daily: no retry allowed."""
        guesses = ["adieu", "story", "point", "lucky", "frame", "blush"]
        r = self.store.start("medium", "2026-06-15", "vexil")
        self.store.finish(r.play_id, False, 60000, 6, guesses, 60000)
        self.assertTrue(self.store.daily_finished("2026-06-15", "medium"),
                        "a lost daily is still finished")

    def test_not_finished_when_unplayed(self):
        self.assertFalse(self.store.daily_finished("2026-06-15", "medium"),
                         "an unplayed daily is not finished")

    def test_difficulties_are_independent(self):
        """Finishing one difficulty does not finish the others for that day."""
        r = self.store.start("easy", "2026-06-15", "cloud")
        self.store.finish(r.play_id, True, 20000, 2, ["c379z"[:5], "cloud"], 20000)
        self.assertTrue(self.store.daily_finished("2026-06-15", "easy"), "easy finished")
        self.assertFalse(self.store.daily_finished("2026-06-15", "hard"), "hard untouched")

    def test_other_dates_do_not_count(self):
        r = self.store.start("medium", "2026-06-14", "crane")
        self.store.finish(r.play_id, True, 30000, 3, ["crane"], 30000)
        self.assertFalse(self.store.daily_finished("2026-06-15", "medium"),
                         "another day's completion should not count")

    def test_today_won_vs_failed_status(self):
        """today_completion marks wins, today_failed marks losses; mutually exclusive."""
        import datetime
        today = datetime.date.today().isoformat()
        w = self.store.start("easy", today, "crane")
        self.store.finish(w.play_id, True, 30000, 3, ["arose", "crane"], 30000)
        f = self.store.start("hard", today, "vexil")
        self.store.finish(f.play_id, False, 60000, 6,
                          ["adieu", "story", "point", "lucky", "frame", "blush"], 60000)
        won, failed = self.store.today_completion(), self.store.today_failed()
        self.assertTrue(won["easy"] and not failed["easy"], "won daily -> won, not failed")
        self.assertTrue(failed["hard"] and not won["hard"], "lost daily -> failed, not won")
        self.assertFalse(won["medium"] or failed["medium"], "unplayed -> neither")


class TestMonthCrown(_StoreTest):
    """The monthly crown requires a COMPLETED month with EVERY day won."""

    def _win_day(self, iso: str, on_time: bool = True) -> None:
        r = self.store.start("easy", iso, "crane")
        self.store.finish(r.play_id, True, 1000, 1, ["crane"], 1000)
        if on_time:  # finish() stamps 'now'; force the challenge date so it counts on-time
            self.store._conn.execute("UPDATE plays SET completed_at=? WHERE id=?", (iso + "T10:00:00", r.play_id))
            self.store._conn.commit()

    def _crown(self, y: int, m: int):
        cal = self.store.calendar_state()
        cal.year, cal.month = y, m
        return cal.fetch_data().month_crown

    def test_no_crown_while_a_day_is_unplayed(self):
        import calendar
        y, m = 2021, 2                       # a completed, 28-day month
        n = calendar.monthrange(y, m)[1]
        for dd in range(1, n):               # win days 1..27, leave the last
            self._win_day(f"{y}-{m:02d}-{dd:02d}")
        self.assertEqual(self._crown(y, m), Completion.NONE, "one day unplayed -> no crown")
        self._win_day(f"{y}-{m:02d}-{n:02d}")  # now finish the month
        self.assertEqual(self._crown(y, m), Completion.ON_TIME, "every day won on-time -> gold crown")

    def test_no_crown_for_current_month(self):
        import datetime
        today = datetime.date.today()
        self._win_day(today.isoformat())
        self.assertEqual(self._crown(today.year, today.month), Completion.NONE,
                         "current month isn't over -> no crown even if today is won")

    def test_late_wins_give_silver_not_gold(self):
        import calendar
        y, m = 2021, 4
        n = calendar.monthrange(y, m)[1]
        for dd in range(1, n + 1):           # all won, but back-played (completed_at = today, i.e. late)
            self._win_day(f"{y}-{m:02d}-{dd:02d}", on_time=False)
        self.assertEqual(self._crown(y, m), Completion.LATE, "all won but late -> silver crown")


class TestStatistics(_StoreTest):
    """stats_by_difficulty aggregates only finished games; wins drive avg/best."""

    def test_stats_count_wins_losses_and_best(self):
        won = self.store.start("medium", "2026-06-10", "crane")
        self.store.finish(won.play_id, True, 40000, 3, ["arose", "slate", "crane"], 40000)
        won2 = self.store.start("medium", "2026-06-11", "grape")
        self.store.finish(won2.play_id, True, 25000, 5, ["a", "b", "c", "d", "grape"], 25000)
        lost = self.store.start("medium", "2026-06-12", "vexil")
        self.store.finish(lost.play_id, False, 90000, 6,
                          ["adieu", "story", "point", "lucky", "frame", "blush"], 90000)

        m = self.store.stats_by_difficulty()["medium"]
        self.assertEqual(m["played"], 3, "all three finished games counted")
        self.assertEqual(m["won"], 2, "two wins")
        self.assertEqual(m["best"], 25000, "best time is the fastest win")
        self.assertEqual(m["avg_tries"], 4.0, "avg tries over wins = (3+5)/2")

    def test_stats_empty_when_no_games(self):
        m = self.store.stats_by_difficulty()["easy"]
        self.assertEqual((m["played"], m["won"], m["best"], m["avg_tries"]),
                         (0, 0, None, None), "no games -> zeros and no best/avg")


if __name__ == "__main__":
    unittest.main()
