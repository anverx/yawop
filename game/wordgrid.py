"""The word-grid game panel: 6x5 tile grid + on-screen keyboard + guess logic.

This is yawop's game-specific panel (the equivalent of yaque's board). It reuses
kivyshell primitives (RoundedButton, styled labels) but owns the play mechanics.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from kivyshell.uikit import RoundedButton, get_theme

from . import theme as T
from .wordgame import MAX_GUESSES, WORD_LEN, Mark, WordGame

_MARK_COLOR = {Mark.CORRECT: T.TILE_CORRECT, Mark.PRESENT: T.TILE_PRESENT, Mark.ABSENT: T.TILE_ABSENT}
_KEY_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]


class Tile(Label):
    """A single letter cell with a rounded, colorable background."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("font_name", get_theme().font_name)
        kwargs.setdefault("font_size", "28sp")
        kwargs.setdefault("bold", True)
        super().__init__(**kwargs)
        self.bg = T.TILE_EMPTY
        self.border = True
        self.bind(pos=self._redraw, size=self._redraw)

    def set(self, ch: str, mark: Mark | None) -> None:
        self.text = ch.upper()
        if mark is None:
            self.bg, self.border, self.color = T.TILE_EMPTY, True, (0.2, 0.2, 0.2, 1)
        else:
            self.bg, self.border, self.color = _MARK_COLOR[mark], False, (1, 1, 1, 1)
        self._redraw()

    def _redraw(self, *a: Any) -> None:
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(4)])
            if self.border:
                Color(0.7, 0.7, 0.72, 1)
                Line(rounded_rectangle=[*self.pos, *self.size, dp(4)], width=1)


class WordGridPanel(BoxLayout):
    """Renders a WordGame and drives play. on_finish(won: bool, duration_ms: int)."""

    def __init__(self, game: WordGame, allowed: set[str],
                 on_finish: Callable[[bool, int, int], None] | None = None,
                 on_info: Callable[[str], None] | None = None, **kwargs: Any) -> None:
        super().__init__(orientation="vertical", spacing=dp(8), **kwargs)
        self.game = game
        self.allowed = allowed
        self.on_finish = on_finish
        self.on_info = on_info
        self._started = time.monotonic()
        self._flash = ""

        # Grid: one horizontal row per guess = leading spacer + 5 tiles + a '?' button.
        # The spacer mirrors the button width so the tiles stay centered.
        tile, btn = dp(52), dp(40)
        grid_col = BoxLayout(orientation="vertical", spacing=dp(6), size_hint=(None, None))
        grid_col.bind(minimum_width=grid_col.setter("width"), minimum_height=grid_col.setter("height"))
        self._tiles: list[list[Tile]] = []
        self._info_btns: list[RoundedButton] = []
        for r in range(MAX_GUESSES):
            row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint=(None, None), height=tile)
            row.bind(minimum_width=row.setter("width"))
            row.add_widget(Widget(size_hint=(None, None), size=(btn, tile)))  # leading spacer
            tiles = []
            for _ in range(WORD_LEN):
                t = Tile(size_hint=(None, None), size=(tile, tile))
                row.add_widget(t)
                tiles.append(t)
            self._tiles.append(tiles)
            info = RoundedButton(text="?", font_size="18sp", bg_color=T.KEY_DEFAULT,
                                 color=(0.1, 0.1, 0.1, 1), size_hint=(None, None), size=(btn, tile))
            info.opacity = 0
            info.disabled = True
            info.bind(on_press=lambda _x, rr=r: self._info(rr))
            row.add_widget(info)
            self._info_btns.append(info)
            grid_col.add_widget(row)
        anchor = AnchorLayout(anchor_x="center")
        anchor.add_widget(grid_col)
        self.add_widget(anchor)

        # Status / message line
        self.status = Label(text="", font_name=get_theme().font_name, font_size="15sp",
                            color=(0.25, 0.25, 0.25, 1), size_hint_y=None, height=dp(24))
        self.add_widget(self.status)

        # Keyboard
        self._keys: dict[str, RoundedButton] = {}
        kb = BoxLayout(orientation="vertical", spacing=dp(5), size_hint_y=None)
        kb.bind(minimum_height=kb.setter("height"))
        for r, letters in enumerate(_KEY_ROWS):
            row = BoxLayout(spacing=dp(4), size_hint_y=None, height=dp(48),
                           padding=[dp(2), 0])
            if r == 2:
                row.add_widget(self._make_key("Enter", lambda *_: self._enter(), wide=True))
            for ch in letters:
                btn = self._make_key(ch.upper(), lambda _, c=ch: self._key(c))
                self._keys[ch] = btn
                row.add_widget(btn)
            if r == 2:
                row.add_widget(self._make_key("Back", lambda *_: self._backspace(), wide=True))
            kb.add_widget(row)
        self.add_widget(kb)

        self.render()

    def _make_key(self, text: str, cb: Callable, wide: bool = False) -> RoundedButton:
        btn = RoundedButton(text=text, font_size="15sp", bg_color=T.KEY_DEFAULT,
                            color=(0.1, 0.1, 0.1, 1), size_hint_x=(1.6 if wide else 1))
        btn.bind(on_press=cb)
        return btn

    # --- input ---
    def _key(self, ch: str) -> None:
        self.game.add_letter(ch)
        self._flash = ""
        self.render()

    def _backspace(self) -> None:
        self.game.backspace()
        self._flash = ""
        self.render()

    def _enter(self) -> None:
        g = self.game
        if g.finished or len(g.current) != WORD_LEN:
            return
        if g.current != g.answer and g.current not in self.allowed:
            self._flash = "Not in word list"
            self.render()
            return
        g.submit()
        self.render()
        if g.finished and self.on_finish:
            self.on_finish(g.won, int((time.monotonic() - self._started) * 1000), g.attempts)

    def _info(self, r: int) -> None:
        if self.on_info and r < len(self.game.guesses):
            self.on_info(self.game.guesses[r])

    def on_key_text(self, text: str) -> None:
        """Forwarded hardware-keyboard input (a letter)."""
        if text and text.isalpha():
            self._key(text)

    def on_key_action(self, action: str) -> None:
        """Forwarded 'enter' or 'backspace' from hardware keyboard."""
        (self._enter if action == "enter" else self._backspace)()

    # --- render ---
    def render(self) -> None:
        g = self.game
        for r in range(MAX_GUESSES):
            if r < len(g.guesses):
                for c in range(WORD_LEN):
                    self._tiles[r][c].set(g.guesses[r][c], g.marks[r][c])
            elif r == len(g.guesses) and not g.finished:
                for c in range(WORD_LEN):
                    self._tiles[r][c].set(g.current[c] if c < len(g.current) else "", None)
            else:
                for c in range(WORD_LEN):
                    self._tiles[r][c].set("", None)
            shown = r < len(g.guesses)          # '?' appears once a guess is accepted
            self._info_btns[r].opacity = 1 if shown else 0
            self._info_btns[r].disabled = not shown

        states = g.letter_states()
        for ch, btn in self._keys.items():
            btn.bg_color = _MARK_COLOR[states[ch]] if ch in states else T.KEY_DEFAULT
            btn.color = (1, 1, 1, 1) if ch in states else (0.1, 0.1, 0.1, 1)
            btn._update_bg()

        if g.finished:
            self.status.text = "Solved!" if g.won else f"The word was {g.answer.upper()}"
        else:
            self.status.text = self._flash
