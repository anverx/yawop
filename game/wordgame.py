"""Wordle-style game logic (pure Python, no kivy)."""

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
    """Holds the answer, submitted guesses, and the in-progress guess."""

    def __init__(self, answer: str, max_guesses: int = MAX_GUESSES) -> None:
        self.answer = answer.lower()
        self.max_guesses = max_guesses
        self.guesses: list[str] = []
        self.marks: list[list[Mark]] = []
        self.current = ""
        self.won = False
        self.finished = False

    def add_letter(self, ch: str) -> None:
        if not self.finished and len(self.current) < WORD_LEN and ch.isalpha():
            self.current += ch.lower()

    def backspace(self) -> None:
        self.current = self.current[:-1]

    def submit(self) -> bool:
        """Score and record the current guess (assumed valid). True if accepted."""
        if self.finished or len(self.current) != WORD_LEN:
            return False
        self.marks.append(score_guess(self.current, self.answer))
        self.guesses.append(self.current)
        if self.current == self.answer:
            self.won = self.finished = True
        elif len(self.guesses) >= self.max_guesses:
            self.finished = True
        self.current = ""
        return True

    def letter_states(self) -> dict[str, Mark]:
        """Best-known state per letter, for keyboard coloring."""
        rank = {Mark.ABSENT: 0, Mark.PRESENT: 1, Mark.CORRECT: 2}
        best: dict[str, Mark] = {}
        for guess, marks in zip(self.guesses, self.marks):
            for ch, mk in zip(guess, marks):
                if ch not in best or rank[mk] > rank[best[ch]]:
                    best[ch] = mk
        return best
