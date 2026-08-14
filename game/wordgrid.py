"""The word-grid game panel, laid out as four vertical sections that split the
screen height: matrix / Enter bar / keyboard / Back.

yawop's game-specific panel. A movable cursor lets letters be entered out of
order (tap a box to move the cursor there).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from kivy.clock import Clock
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from kivyshell.uikit import BackButton, RoundedButton, get_theme

from worddata.paths import app_root

from . import theme as T
from .wordgame import WORD_LEN, Mark, WordGame

_ENTER_ICON = os.path.join(str(app_root()), "game", "assets", "enter-icon.png")
# Backspace glyph (U+232B) rendered to a tintable PNG, since Kivy's bundled Roboto
# has no glyph for it (would show a tofu box).
_BACKSPACE_ICON = os.path.join(str(app_root()), "game", "assets", "backspace-icon.png")
_MARK_COLOR = {Mark.CORRECT: T.TILE_CORRECT, Mark.PRESENT: T.TILE_PRESENT, Mark.ABSENT: T.TILE_ABSENT}
_KEY_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
# Global letter frequency across every valid guess word (assets/allowed_guesses_all.txt),
# normalized so the commonest letter = 99 (integer, top capped at 99 so it stays 2 digits).
# A ballpark "which letters are more likely" hint, shown small under each key like an
# atomic mass on the periodic table. Regenerate with the script in the commit message.
LETTER_MASS = {
    "a": 89, "b": 24, "c": 30, "d": 36, "e": 98, "f": 16, "g": 24, "h": 26,
    "i": 56, "j": 4, "k": 22, "l": 50, "m": 29, "n": 44, "o": 65, "p": 30,
    "q": 2, "r": 61, "s": 99, "t": 49, "u": 37, "v": 10, "w": 15, "x": 4,
    "y": 30, "z": 6,
}
_CURSOR = (0.10, 0.62, 1.0, 1)       # neon-blue "type here" cell
_CURSOR_GLOW = (0.25, 0.72, 1.0)     # soft halo around it (alpha added per layer)
_ENTER_OK = T.TILE_CORRECT
_ENTER_BAD = (0.86, 0.30, 0.30, 1)
_DARK, _WHITE = (0.1, 0.1, 0.1, 1), (1, 1, 1, 1)
_WARN_BG = (0.98, 0.87, 0.90, 1)     # subdued pink: this letter/position contradicts a prior clue


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

    def set(self, ch: str, mark: Mark | None, cursor: bool = False, warn: bool = False) -> None:
        self.text = ch.upper()
        self.cursor = cursor
        if mark is None:
            # warn = a light pink hint that this letter contradicts an earlier clue
            self.bg = _WARN_BG if warn else T.TILE_EMPTY
            self.border, self.color = True, (0.2, 0.2, 0.2, 1)
        else:
            self.bg, self.border, self.color = _MARK_COLOR[mark], False, _WHITE
        self._redraw()

    def _redraw(self, *a: Any) -> None:
        self.canvas.before.clear()
        x, y = self.pos
        w, h = self.size
        with self.canvas.before:
            if self.cursor:
                # neon-blue "type here" cell with a soft glowing edge (layered halos)
                for pad, alpha in ((dp(7), 0.16), (dp(4), 0.28), (dp(2), 0.5)):
                    Color(*_CURSOR_GLOW, alpha)
                    RoundedRectangle(pos=(x - pad, y - pad), size=(w + 2 * pad, h + 2 * pad), radius=[dp(7)])
                Color(*_CURSOR)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(5)])
            else:
                Color(*self.bg)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(4)])
                if self.border:
                    Color(0.7, 0.7, 0.72, 1)
                    Line(rounded_rectangle=[*self.pos, *self.size, dp(4)], width=1)


_ROW_HIGHLIGHT = (0.89, 0.93, 0.99, 0.95)  # soft band behind the active row


class GuessRow(BoxLayout):
    """A grid row that shows a soft background band while it's the active row."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._hl = False
        self.bind(pos=self._redraw, size=self._redraw)

    def set_highlight(self, on: bool) -> None:
        if on != self._hl:
            self._hl = on
            self._redraw()

    def _redraw(self, *a: Any) -> None:
        self.canvas.before.clear()
        if self._hl:
            with self.canvas.before:
                Color(*_ROW_HIGHLIGHT)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])


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
                            bold=True, markup=True, halign="center", size_hint=(None, None), color=_DARK)
        self._label.bind(texture_size=self._label.setter("size"))
        inner.add_widget(self._icon)
        inner.add_widget(self._label)
        self.add_widget(inner)

    def set_state(self, bg: tuple, fg: tuple, text: str = "Enter", show_icon: bool = True,
                  sub: str = "") -> None:
        self.bg_color = bg
        from kivy.metrics import sp
        self._label.text = f"{text}\n[size={round(sp(12))}]{sub}[/size]" if sub else text
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
        self._win_caption = ""     # "M:SS · N tries", shown under "Victory!" (screen sets it)
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

    def _build_grid(self) -> ScrollView:
        # Scrollable so 'another try' can append rows past the initial six.
        self._tile_px, self._btn_px = dp(42), dp(34)
        self._grid_col = BoxLayout(orientation="vertical", spacing=dp(8), size_hint=(None, None))
        self._grid_col.bind(minimum_width=self._grid_col.setter("width"),
                            minimum_height=self._grid_col.setter("height"))
        self._tiles: list[list[Tile]] = []
        self._info_btns: list[RoundedButton] = []
        self._rows: list[GuessRow] = []
        for r in range(self.game.max_guesses):
            self._grid_col.add_widget(self._make_row(r))
        holder = AnchorLayout(anchor_x="center", size_hint=(1, None))
        holder.add_widget(self._grid_col)
        self._grid_col.bind(height=lambda _i, h: setattr(holder, "height", h))
        holder.height = self._grid_col.height
        self._scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(2))
        self._scroll.add_widget(holder)
        return self._scroll

    def _make_row(self, r: int) -> BoxLayout:
        tile, btn = self._tile_px, self._btn_px
        row = GuessRow(orientation="horizontal", spacing=dp(8), size_hint=(None, None), height=tile)
        row.bind(minimum_width=row.setter("width"))
        self._rows.append(row)
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
        return row

    def add_attempt(self) -> None:
        """'Another try': grow the game by one guess and append a row to the grid."""
        self.game.extend(1)
        self._grid_col.add_widget(self._make_row(len(self._tiles)))
        self.render()
        Clock.schedule_once(lambda _dt: setattr(self._scroll, "scroll_y", 0), 0)  # show newest row

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
                bk = self._make_key("", lambda *_: self._backspace(), wide=True)
                self._draw_backspace_icon(bk)
                row.add_widget(bk)
            kb.add_widget(row)
        return kb

    def _make_key(self, text: str, cb: Callable, wide: bool = False) -> RoundedButton:
        btn = RoundedButton(text=text, font_size="18sp", bg_color=T.KEY_DEFAULT, color=_DARK,
                            size_hint=(1.6 if wide else 1, 1))
        mass = LETTER_MASS.get(text.lower()) if len(text) == 1 and text.isalpha() else None
        if mass is not None:
            # letter (symbol) over its frequency (atomic-mass style). The number has no
            # color tag, so it inherits the key's foreground and stays legible when the
            # key turns green/gold/gray during play.
            from kivy.metrics import sp
            btn.text = f"[b]{text}[/b]\n[size={round(sp(9))}]{mass}[/size]"
            btn.bind(size=lambda b, *_: setattr(b, "text_size", b.size))
        btn.bind(on_press=cb)
        return btn

    def _draw_backspace_icon(self, btn: RoundedButton) -> None:
        """Draw the ⌫ glyph (a tinted PNG) centred on the backspace key. Roboto lacks
        the real character, so we paint the icon on the key's canvas instead of text."""
        from kivy.core.image import Image as CoreImage
        from kivy.graphics import Color, Rectangle
        tex = CoreImage(_BACKSPACE_ICON).texture
        ar = tex.width / tex.height

        def redraw(*_a: Any) -> None:
            btn.canvas.after.clear()
            ih = min(btn.height * 0.42, btn.width * 0.55 / ar)
            iw = ih * ar
            with btn.canvas.after:
                Color(*_DARK)
                Rectangle(texture=tex, size=(iw, ih),
                          pos=(btn.center_x - iw / 2, btn.center_y - ih / 2))

        btn.bind(pos=redraw, size=redraw)
        redraw()

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
        if not self.on_info:
            return
        guesses = self.game.guesses
        if r < len(guesses):
            self.on_info(guesses[r], True)  # committed guess: safe to show provenance
        elif r == len(guesses) and self.game.is_complete():
            self.on_info(self.game.current, False)  # peek before committing: hide provenance (it's a hint)

    def on_key_text(self, text: str) -> None:
        if text and text.isalpha():
            self._key(text)

    def on_key_action(self, action: str) -> None:
        (self._enter if action == "enter" else self._backspace)()

    def set_win_caption(self, text: str) -> None:
        """Persist time/tries under the 'Victory!' bar (survives closing the popup)."""
        self._win_caption = text
        self.render()

    def show_reveal(self, text: str) -> None:
        self.reveal.text = text

    def _clue_constraints(self):
        """From committed rows: known letter per position (green), letters barred from
        a position (yellow there), and fully-absent letters (gray). Used to pink-warn
        contradictions on the active row."""
        g = self.game
        greens: dict[int, str] = {}
        barred: dict[int, set] = {i: set() for i in range(WORD_LEN)}
        for guess, marks in zip(g.guesses, g.marks):
            for i, (ch, mk) in enumerate(zip(guess, marks)):
                if mk == Mark.CORRECT:
                    greens[i] = ch
                elif mk == Mark.PRESENT:
                    barred[i].add(ch)
        absent = {c for c, st in g.letter_states().items() if st == Mark.ABSENT}
        return greens, barred, absent

    # --- render ---
    def render(self) -> None:
        g = self.game
        active = len(g.guesses)
        greens, barred, absent = self._clue_constraints()
        for r in range(len(self._tiles)):
            if r < active:
                for c in range(WORD_LEN):
                    self._tiles[r][c].set(g.guesses[r][c], g.marks[r][c])
            elif r == active and not g.finished:
                for c in range(WORD_LEN):
                    ch = g.slots[c]
                    warn = bool(ch) and (
                        (c in greens and ch != greens[c])   # this spot is already known to be another letter
                        or ch in barred[c]                  # this letter is known NOT to sit here (was yellow here)
                        or ch in absent)                    # this letter isn't in the word at all
                    self._tiles[r][c].set(ch, None, cursor=(c == g.cursor), warn=warn)
            else:
                for c in range(WORD_LEN):
                    self._tiles[r][c].set("", None)
            # '?' shows for submitted rows, and on the active row as soon as a valid
            # word is typed (Enter green) so you can look it up before committing.
            shown = r < active or (
                r == active and not g.finished and g.is_complete()
                and (g.current == g.answer or g.current in self.allowed))
            self._info_btns[r].opacity = 1 if shown else 0
            self._info_btns[r].disabled = not shown
            self._rows[r].set_highlight(r == active and not g.finished)

        if g.finished:  # Enter is irrelevant now: announce the outcome instead
            if g.won and not g.lost:
                self._enter_btn.set_state(_ENTER_OK, _WHITE, "Victory!", show_icon=False,
                                          sub=self._win_caption)
            else:  # lost, or solved only in an 'another try' bonus row after losing
                self._enter_btn.set_state(_ENTER_BAD, _WHITE, "Game over", show_icon=False)
        elif not g.is_complete():
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
            self.status.text = ""  # the Success / Game Failed popups handle the end state
        else:
            self.status.text = self._flash
