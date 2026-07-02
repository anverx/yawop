"""Wordle-style game logic (pure Python, no kivy).

The current guess is a list of 5 slots with a movable cursor, so letters can be
entered out of order (tap a box to move the cursor there).
"""

from __future__ import annotations

from enum import Enum

WORD_LEN = 5
MAX_GUESSES = 6


class Mark(Enum):
    CORRECT = "correct"   # right letter, right position
    PRESENT = "present"   # in the word, wrong position
    ABSENT = "absent"     # not in the word


def score_guess(guess: str, answer: str) -> list[Mark]:
    """Standard Wordle scoring, with correct duplicate-letter handling."""
    guess, answer = guess.lower(), answer.lower()
    marks = [Mark.ABSENT] * len(guess)
    pool: dict[str, int] = {}
    for i, (g, a) in enumerate(zip(guess, answer)):
        if g == a:
            marks[i] = Mark.CORRECT
        else:
            pool[a] = pool.get(a, 0) + 1
    for i, g in enumerate(guess):
        if marks[i] is Mark.CORRECT:
            continue
        if pool.get(g, 0) > 0:
            marks[i] = Mark.PRESENT
            pool[g] -= 1
    return marks


class WordGame:
    """Answer + submitted guesses + the in-progress guess (slots + cursor)."""

    def __init__(self, answer: str, max_guesses: int = MAX_GUESSES) -> None:
        self.answer = answer.lower()
        self.max_guesses = max_guesses
        self.guesses: list[str] = []
        self.marks: list[list[Mark]] = []
        self.slots: list[str] = [""] * WORD_LEN
        self.cursor = 0
        self.won = False
        self.finished = False

    @property
    def current(self) -> str:
        return "".join(self.slots)

    def is_complete(self) -> bool:
        return all(self.slots)

    def _next_empty(self, start: int) -> int | None:
        for i in list(range(start + 1, WORD_LEN)) + list(range(0, start + 1)):
            if not self.slots[i]:
                return i
        return None

    def set_cursor(self, i: int) -> None:
        if not self.finished and 0 <= i < WORD_LEN:
            self.cursor = i

    def add_letter(self, ch: str) -> None:
        if self.finished or not ch.isalpha():
            return
        self.slots[self.cursor] = ch.lower()
        nxt = self._next_empty(self.cursor)   # jump to the next empty slot (wraps)
        if nxt is not None:
            self.cursor = nxt

    def backspace(self) -> None:
        if self.finished:
            return
        if self.slots[self.cursor]:
            self.slots[self.cursor] = ""
        elif self.cursor > 0:
            self.cursor -= 1
            self.slots[self.cursor] = ""

    def submit(self) -> bool:
        """Score and record the current guess (assumed complete + valid)."""
        if self.finished or not self.is_complete():
            return False
        guess = self.current
        self.marks.append(score_guess(guess, self.answer))
        self.guesses.append(guess)
        if guess == self.answer:
            self.won = self.finished = True
        elif len(self.guesses) >= self.max_guesses:
            self.finished = True
        self.slots = [""] * WORD_LEN
        self.cursor = 0
        return True

    def restore(self, guesses: list[str]) -> None:
        """Replay previously-saved guesses to rebuild state (for resuming a game)."""
        for g in guesses:
            if self.finished or len(g) != WORD_LEN:
                break
            self.slots = list(g.lower())
            self.cursor = 0
            self.submit()

    @property
    def attempts(self) -> int:
        return len(self.guesses)

    def letter_states(self) -> dict[str, Mark]:
        """Best-known state per letter, for keyboard coloring."""
        rank = {Mark.ABSENT: 0, Mark.PRESENT: 1, Mark.CORRECT: 2}
        best: dict[str, Mark] = {}
        for guess, marks in zip(self.guesses, self.marks):
            for ch, mk in zip(guess, marks):
                if ch not in best or rank[mk] > rank[best[ch]]:
                    best[ch] = mk
        return best
