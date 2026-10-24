"""Tests for the Wordle scoring + game logic (pure, no kivy)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from game.wordgame import Mark, WordGame, score_guess  # noqa: E402

C, P, A = Mark.CORRECT, Mark.PRESENT, Mark.ABSENT


class TestScoring(unittest.TestCase):
    def test_all_correct(self):
        self.assertEqual(score_guess("abide", "abide"), [C, C, C, C, C])

    def test_present_and_absent(self):
        # answer CRANE, guess REACT: R present, E present, A correct, C present, T absent
        self.assertEqual(score_guess("react", "crane"), [P, P, C, P, A])

    def test_duplicate_letters_limited_by_answer(self):
        # answer ABIDE (one 'a'); guess AAHED -> first A correct, second A absent
        marks = score_guess("aahed", "abide")
        self.assertEqual(marks[0], C)
        self.assertEqual(marks[1], A)  # no second 'a' left in answer

    def test_duplicate_present_not_over_credited(self):
        # answer LEVEL, guess EAGER: first E present, second E present? LEVEL has two E's
        self.assertEqual(score_guess("eerie", "level")[0], P)


class TestWordGame(unittest.TestCase):
    def test_win_flow(self):
        g = WordGame("abide")
        for ch in "wrong":
            g.add_letter(ch)
        self.assertTrue(g.submit())
        self.assertFalse(g.won)
        for ch in "abide":
            g.add_letter(ch)
        g.submit()
        self.assertTrue(g.won)
        self.assertTrue(g.finished)

    def test_lose_after_max_guesses(self):
        g = WordGame("abide", max_guesses=2)
        for _ in range(2):
            for ch in "wrong":
                g.add_letter(ch)
            g.submit()
        self.assertTrue(g.finished)
        self.assertFalse(g.won)

    def test_backspace_and_length_cap(self):
        g = WordGame("abide")
        for ch in "abcdefg":  # more than 5
            g.add_letter(ch)
        self.assertEqual(len(g.current), 5)
        g.backspace()
        self.assertEqual(len(g.current), 4)

    def test_letter_states_prefers_correct(self):
        g = WordGame("abide")
        for ch in "aahed":
            g.add_letter(ch)
        g.submit()
        self.assertEqual(g.letter_states()["a"], C)  # correct beats absent


class TestRestore(unittest.TestCase):
    """restore() replays saved guesses; the review feature rebuilds finished boards this way."""

    def test_restore_partial_resume(self):
        g = WordGame("crane")
        g.restore(["slate", "brace"])
        self.assertEqual(len(g.guesses), 2)
        self.assertFalse(g.finished)  # still mid-game

    def test_restore_won_board(self):
        g = WordGame("crane")
        g.restore(["slate", "brace", "crane"])
        self.assertTrue(g.won)
        self.assertTrue(g.finished)
        self.assertEqual(len(g.guesses), 3)

    def test_restore_lost_board(self):
        g = WordGame("vexil", max_guesses=6)
        g.restore(["adieu", "story", "point", "lucky", "frame", "blush"])
        self.assertTrue(g.finished)
        self.assertFalse(g.won)
        self.assertEqual(len(g.guesses), 6)

    def test_restore_preserves_marks_per_row(self):
        g = WordGame("crane")
        g.restore(["crane"])
        self.assertEqual(g.marks[0], [C, C, C, C, C])


class TestExtend(unittest.TestCase):
    """extend() powers 'another try': reopen a finished board and keep playing."""

    def test_extend_reopens_after_loss(self):
        g = WordGame("abide", max_guesses=1)
        for ch in "wrong":
            g.add_letter(ch)
        g.submit()
        self.assertTrue(g.finished)
        g.extend(1)
        self.assertFalse(g.finished)
        self.assertEqual(g.max_guesses, 2)

    def test_can_guess_after_extend(self):
        g = WordGame("abide", max_guesses=1)
        for ch in "wrong":
            g.add_letter(ch)
        g.submit()
        g.extend(1)
        for ch in "abide":
            g.add_letter(ch)
        self.assertTrue(g.submit())
        self.assertTrue(g.won)

    def test_bonus_win_stays_lost(self):
        # lose at max, then solve in a bonus row: won, but 'lost' sticks (still a loss)
        g = WordGame("abide", max_guesses=1)
        for ch in "wrong":
            g.add_letter(ch)
        g.submit()
        self.assertTrue(g.lost)
        g.extend(1)
        self.assertTrue(g.lost)  # extend does not clear the loss
        for ch in "abide":
            g.add_letter(ch)
        g.submit()
        self.assertTrue(g.won)
        self.assertTrue(g.lost)  # solved, but the game was already lost

    def test_clean_win_not_lost(self):
        g = WordGame("abide", max_guesses=6)
        for ch in "abide":
            g.add_letter(ch)
        g.submit()
        self.assertTrue(g.won)
        self.assertFalse(g.lost)


if __name__ == "__main__":
    unittest.main()
