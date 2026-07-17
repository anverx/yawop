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
