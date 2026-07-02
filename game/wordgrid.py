"""The word-grid game panel, laid out as four vertical sections that split the
screen height: matrix / Enter bar / keyboard / Back.

yawop's game-specific panel. A movable cursor lets letters be entered out of
order (tap a box to move the cursor there).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from kivyshell.uikit import BackButton, RoundedButton, get_theme

from . import theme as T
from .wordgame import MAX_GUESSES, WORD_LEN, Mark, WordGame

_ENTER_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "enter-icon.png")
_MARK_COLOR = {Mark.CORRECT: T.TILE_CORRECT, Mark.PRESENT: T.TILE_PRESENT, Mark.ABSENT: T.TILE_ABSENT}
_KEY_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
_CURSOR = (0.2, 0.5, 0.85, 1)
_ENTER_OK = T.TILE_CORRECT
_ENTER_BAD = (0.86, 0.30, 0.30, 1)
_DARK, _WHITE = (0.1, 0.1, 0.1, 1), (1, 1, 1, 1)


class Tile(ButtonBehavior, Label):
    """A letter cell. Tappable (moves the cursor) and colorable."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("font_name", get_theme().font_name)
        kwargs.setdefault("font_size", "26sp")
        kwargs.setdefault("bold", True)
        super().__init__(**kwargs)
        self.bg = T.TILE_EMPTY
        self.border = True
        self.cursor = False
        self.bind(pos=self._redraw, size=self._redraw)

    def set(self, ch: str, mark: Mark | None, cursor: bool = False) -> None:
        self.text = ch.upper()
        self.cursor = cursor
        if mark is None:
            self.bg, self.border, self.color = T.TILE_EMPTY, True, (0.2, 0.2, 0.2, 1)
        else:
            self.bg, self.border, self.color = _MARK_COLOR[mark], False, _WHITE
        self._redraw()

    def _redraw(self, *a: Any) -> None:
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(4)])
            if self.cursor:
                Color(*_CURSOR)
                Line(rounded_rectangle=[*self.pos, *self.size, dp(4)], width=2)
            elif self.border:
                Color(0.7, 0.7, 0.72, 1)
                Line(rounded_rectangle=[*self.pos, *self.size, dp(4)], width=1)


class EnterButton(ButtonBehavior, AnchorLayout):
    """A wide rounded Enter button with an icon + label; color signals validity."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(anchor_x="center", anchor_y="center", **kwargs)
        self.bg_color = T.KEY_DEFAULT
        self.bind(pos=self._redraw, size=self._redraw)
        inner = BoxLayout(orientation="horizontal", size_hint=(None, None), spacing=dp(10))
        inner.bind(minimum_width=inner.setter("width"), minimum_height=inner.setter("height"))
        self._icon = Image(source=_ENTER_ICON, size_hint=(None, None), size=(dp(26), dp(26)),
                           fit_mode="contain", color=_DARK)
        self._label = Label(text="Enter", font_name=get_theme().font_name, font_size="20sp",
                            bold=True, size_hint=(None, None), color=_DARK)
        self._label.bind(texture_size=self._label.setter("size"))
        inner.add_widget(self._icon)
        inner.add_widget(self._label)
        self.add_widget(inner)

    def set_state(self, bg: tuple, fg: tuple, text: str = "Enter", show_icon: bool = True) -> None:
        self.bg_color = bg
        self._label.text = text
        self._label.color = fg
        self._icon.color = fg
        self._icon.opacity = 1 if show_icon else 0
        self._icon.size = (dp(26), dp(26)) if show_icon else (0, 0)
        self._redraw()

    def _redraw(self, *a: Any) -> None:
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])


class WordGridPanel(BoxLayout):
    """Four sections (matrix / Enter / keyboard / Back) filling the screen height.

    on_finish(won, duration_ms, attempts); on_info(word); on_back().
    """

    def __init__(self, game: WordGame, allowed: set[str], subtitle: str = "",
                 on_finish: Callable[[bool, int], None] | None = None,
                 on_info: Callable[[str], None] | None = None,
                 on_back: Callable[[], None] | None = None,
                 on_guess: Callable[[list[str]], None] | None = None, **kwargs: Any) -> None:
        super().__init__(orientation="vertical", spacing=dp(4), **kwargs)
        self.game = game
        self.allowed = allowed
        self.on_finish = on_finish
        self.on_info = on_info
        self.on_guess = on_guess   # persist in-progress guesses (screen owns elapsed time)
        self._flash = ""
        theme = get_theme()

        # --- Section 1: matrix (subtitle + tile grid + status + reveal) ---
        matrix = BoxLayout(orientation="vertical", size_hint_y=0.52, spacing=dp(2))
        matrix.add_widget(Label(text=subtitle, font_name=theme.font_name, font_size="14sp",
                                color=theme.text_light, size_hint_y=None, height=dp(22)))
        matrix.add_widget(self._build_grid())
        self.status = Label(text="", font_name=theme.font_name, font_size="14sp",
                            color=(0.25, 0.25, 0.25, 1), size_hint_y=None, height=dp(22))
        matrix.add_widget(self.status)
        self.reveal = Label(text="", font_name=theme.font_name, font_size="12sp",
                            color=theme.text_medium, size_hint_y=None, height=0, halign="center", valign="top")
        self.reveal.bind(width=lambda i, w: setattr(i, "text_size", (w, None)),
                         texture_size=lambda i, s: setattr(i, "height", s[1] if i.text else 0))
        matrix.add_widget(self.reveal)
        self.add_widget(matrix)

        # --- Section 2: Enter bar (2/3 width, fatter) ---
        enter_sec = AnchorLayout(size_hint_y=0.14, anchor_x="center")
        self._enter_btn = EnterButton(size_hint=(0.66, 0.74))
        self._enter_btn.bind(on_press=lambda *_: self._enter())
        enter_sec.add_widget(self._enter_btn)
        self.add_widget(enter_sec)

        # --- Section 3: keyboard ---
        self.add_widget(self._build_keyboard())

        # --- Section 4: Back ---
        back_sec = AnchorLayout(size_hint_y=0.10, anchor_x="center")
        back = BackButton(size_hint=(0.5, 0.7))
        back.bind(on_press=lambda *_: on_back() if on_back else None)
        back_sec.add_widget(back)
        self.add_widget(back_sec)

        self.render()

    def _build_grid(self) -> AnchorLayout:
        tile, btn = dp(50), dp(38)
        grid_col = BoxLayout(orientation="vertical", spacing=dp(6), size_hint=(None, None))
        grid_col.bind(minimum_width=grid_col.setter("width"), minimum_height=grid_col.setter("height"))
        self._tiles: list[list[Tile]] = []
        self._info_btns: list[RoundedButton] = []
        for r in range(MAX_GUESSES):
            row = BoxLayout(orientation="horizontal", spacing=dp(6), size_hint=(None, None), height=tile)
            row.bind(minimum_width=row.setter("width"))
            row.add_widget(Widget(size_hint=(None, None), size=(btn, tile)))
            tiles = []
            for c in range(WORD_LEN):
                t = Tile(size_hint=(None, None), size=(tile, tile))
                t.bind(on_release=lambda _t, rr=r, cc=c: self._tap(rr, cc))
                row.add_widget(t)
                tiles.append(t)
            self._tiles.append(tiles)
            info = RoundedButton(text="?", font_size="16sp", bg_color=T.KEY_DEFAULT, color=_DARK,
                                 size_hint=(None, None), size=(btn, tile))
            info.opacity = 0
            info.disabled = True
            info.bind(on_press=lambda _x, rr=r: self._info(rr))
            row.add_widget(info)
            self._info_btns.append(info)
            grid_col.add_widget(row)
        anchor = AnchorLayout(anchor_x="center")
        anchor.add_widget(grid_col)
        return anchor

    def _build_keyboard(self) -> BoxLayout:
        self._keys: dict[str, RoundedButton] = {}
        kb = BoxLayout(orientation="vertical", spacing=dp(5), size_hint_y=0.24, padding=[dp(2), 0])
        for r, letters in enumerate(_KEY_ROWS):
            row = BoxLayout(spacing=dp(4), size_hint_y=1)
            for ch in letters:
                b = self._make_key(ch.upper(), lambda _x, c=ch: self._key(c))
                self._keys[ch] = b
                row.add_widget(b)
            if r == 2:
                row.add_widget(self._make_key("Back", lambda *_: self._backspace(), wide=True))
            kb.add_widget(row)
        return kb

    def _make_key(self, text: str, cb: Callable, wide: bool = False) -> RoundedButton:
        btn = RoundedButton(text=text, font_size="15sp", bg_color=T.KEY_DEFAULT, color=_DARK,
                            size_hint=(1.6 if wide else 1, 1))
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

    def _tap(self, r: int, c: int) -> None:
        if not self.game.finished and r == len(self.game.guesses):
            self.game.set_cursor(c)
            self._flash = ""
            self.render()

    def _enter(self) -> None:
        g = self.game
        if g.finished or not g.is_complete():
            return
        guess = g.current
        if guess != g.answer and guess not in self.allowed:
            return  # the red 'Not a word' button already signals this
        g.submit()
        self.render()
        if g.finished:
            if self.on_finish:
                self.on_finish(g.won, g.attempts)
        elif self.on_guess:
            self.on_guess(list(g.guesses))

    def _info(self, r: int) -> None:
        if self.on_info and r < len(self.game.guesses):
            self.on_info(self.game.guesses[r])

    def on_key_text(self, text: str) -> None:
        if text and text.isalpha():
            self._key(text)

    def on_key_action(self, action: str) -> None:
        (self._enter if action == "enter" else self._backspace)()

    def show_reveal(self, text: str) -> None:
        self.reveal.text = text

    # --- render ---
    def render(self) -> None:
        g = self.game
        active = len(g.guesses)
        for r in range(MAX_GUESSES):
            if r < active:
                for c in range(WORD_LEN):
                    self._tiles[r][c].set(g.guesses[r][c], g.marks[r][c])
            elif r == active and not g.finished:
                for c in range(WORD_LEN):
                    self._tiles[r][c].set(g.slots[c], None, cursor=(c == g.cursor))
            else:
                for c in range(WORD_LEN):
                    self._tiles[r][c].set("", None)
            shown = r < active
            self._info_btns[r].opacity = 1 if shown else 0
            self._info_btns[r].disabled = not shown

        if g.finished or not g.is_complete():
            self._enter_btn.set_state(T.KEY_DEFAULT, _DARK, "Enter", show_icon=True)
        elif g.current == g.answer or g.current in self.allowed:
            self._enter_btn.set_state(_ENTER_OK, _WHITE, "Enter", show_icon=True)
        else:
            self._enter_btn.set_state(_ENTER_BAD, _WHITE, "Not a word", show_icon=False)

        states = g.letter_states()
        for ch, btn in self._keys.items():
            btn.bg_color = _MARK_COLOR[states[ch]] if ch in states else T.KEY_DEFAULT
            btn.color = _WHITE if ch in states else _DARK
            btn._update_bg()

        if g.finished:
            self.status.text = "Solved!" if g.won else f"The word was {g.answer.upper()}"
        else:
            self.status.text = self._flash
