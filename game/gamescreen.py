"""WordGameScreen: a stopwatch top-bar over the word-grid panel.

The screen owns the elapsed-time clock (ticks each second, seeds from a resumed
game's saved time) and drives persistence: it saves in-progress guesses + elapsed
after each guess and on leaving, and reports the final duration on finish.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from kivyshell.shell.screens.base import BackgroundedScreen
from kivyshell.uikit import ClockLabel, styled

from . import theme as T
from .wordgame import WordGame
from .wordgrid import WordGridPanel


class WordGameScreen(BackgroundedScreen):
    def __init__(self, app, **kwargs) -> None:
        super().__init__(app, **kwargs)
        # Game screen only: replace the themed splash image + white tint overlay with a
        # single flat color. The faint splash behind the grid is distracting; every other
        # screen keeps the shared background. Content column stays on top untouched.
        root = self.children[0]  # BackgroundedScreen's FloatLayout
        for w in list(root.children):
            if w is not self.content_layout:      # drop the background Image and the overlay
                root.remove_widget(w)
        with root.canvas.before:
            Color(*T.GAME_BG)
            self._bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._sync_bg, size=self._sync_bg)

    def _sync_bg(self, instance, _value) -> None:
        self._bg_rect.pos = instance.pos
        self._bg_rect.size = instance.size

    def get_padding(self) -> int:
        return 6

    def get_spacing(self) -> int:
        return 4

    def build_content(self) -> None:
        self.content_layout.clear_widgets()  # drop the base top-spacer; game fills the screen
        self._host = BoxLayout(orientation="vertical", spacing=dp(2))
        top = styled(BoxLayout, "header_bar")
        self.clock_label = ClockLabel("0:00")
        top.add_widget(self.clock_label)
        self._host.add_widget(top)
        self.content_layout.add_widget(self._host)
        self._panel: WordGridPanel | None = None
        self._on_finish: Callable[[bool, int, int], None] | None = None
        self._on_progress: Callable[[list, int], None] | None = None
        self._elapsed = 0          # seconds
        self._timer_ev = None
        self._return_to = "menu"   # screen the Back button returns to

    def set_game(self, game: WordGame, allowed: set[str], subtitle: str,
                 on_finish: Callable[[bool, int, int], None],
                 on_info: Callable[[str], None],
                 on_progress: Callable[[list, int], None] | None = None,
                 elapsed_ms: int = 0, return_to: str = "menu",
                 keyboard: list[str] | None = None,
                 letter_mass: dict[str, int] | None = None) -> None:
        self._on_finish = on_finish
        self._on_progress = on_progress
        self._return_to = return_to
        self._elapsed = elapsed_ms // 1000
        self._update_clock()
        if self._panel is not None:
            self._host.remove_widget(self._panel)
        self._panel = WordGridPanel(game, allowed, subtitle=subtitle, on_finish=self._finished,
                                    on_info=on_info, on_back=self._go_menu, on_guess=self._progress,
                                    keyboard=keyboard, letter_mass=letter_mass)
        self._host.add_widget(self._panel)
        self._apply_win_caption()   # a resumed/reviewed clean win shows its time straight away
        self._start_timer()

    def _apply_win_caption(self) -> None:
        """Show 'M:SS · N tries' under the Victory bar for a cleanly-won game."""
        g = self._panel.game if self._panel else None
        if g and g.won and not g.lost:
            m, s = divmod(self._elapsed, 60)
            tries = f"{g.attempts} {'try' if g.attempts == 1 else 'tries'}"
            self._panel.set_win_caption(f"{m}:{s:02d} · {tries}")

    # --- stopwatch ---
    def _start_timer(self) -> None:
        if self._timer_ev is None and self._panel is not None and not self._panel.game.finished:
            self._timer_ev = Clock.schedule_interval(self._tick, 1)

    def _stop_timer(self) -> None:
        if self._timer_ev is not None:
            self._timer_ev.cancel()
            self._timer_ev = None

    def _tick(self, _dt: float) -> None:
        self._elapsed += 1
        self._update_clock()

    def _update_clock(self) -> None:
        m, s = divmod(self._elapsed, 60)
        self.clock_label.text = f"{m}:{s:02d}"

    # --- game events ---
    def _finished(self, won: bool, attempts: int) -> None:
        self._stop_timer()
        self._apply_win_caption()   # freeze time/tries under the Victory bar before the popup
        if self._on_finish:
            self._on_finish(won, self._elapsed * 1000, attempts)

    def _progress(self, guesses: list) -> None:
        self._save_progress(guesses)

    def _save_progress(self, guesses: list | None = None) -> None:
        if self._on_progress and self._panel and not self._panel.game.finished:
            gs = guesses if guesses is not None else list(self._panel.game.guesses)
            self._on_progress(gs, self._elapsed * 1000)

    def _go_menu(self) -> None:
        if hasattr(self.app, "_log"):
            self.app._log(f"back to {self._return_to} (finished={self._panel.game.finished if self._panel else '?'})")
        self.app.sm.current = self._return_to

    def show_reveal(self, text: str) -> None:
        if self._panel:
            self._panel.show_reveal(text)

    def another_try(self) -> None:
        """Append one more guess row and keep playing (unranked) after a fail."""
        if self._panel:
            self._panel.show_reveal("")
            self._panel.add_attempt()
            self._start_timer()

    # --- lifecycle: run the clock only while the screen is shown ---
    def on_enter(self, *a: Any) -> None:
        Window.bind(on_key_down=self._on_key_down)
        self._start_timer()

    def on_leave(self, *a: Any) -> None:
        Window.unbind(on_key_down=self._on_key_down)
        self._stop_timer()
        self._save_progress()  # persist elapsed even if no new guess was made

    def _on_key_down(self, window: Any, key: int, scancode: int, text: str, modifiers: list) -> bool:
        if not self._panel:
            return False
        if key == 13:
            self._panel.on_key_action("enter")
            return True
        if key == 8:
            self._panel.on_key_action("backspace")
            return True
        if text and text.isalpha() and len(text) == 1:
            self._panel.on_key_text(text)
            return True
        return False
