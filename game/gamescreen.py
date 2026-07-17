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
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from kivyshell.shell.screens.base import BackgroundedScreen
from kivyshell.uikit import ClockLabel, styled

from .wordgame import WordGame
from .wordgrid import WordGridPanel


class WordGameScreen(BackgroundedScreen):
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
                 elapsed_ms: int = 0, return_to: str = "menu") -> None:
        self._on_finish = on_finish
        self._on_progress = on_progress
        self._return_to = return_to
        self._elapsed = elapsed_ms // 1000
        self._update_clock()
        if self._panel is not None:
            self._host.remove_widget(self._panel)
        self._panel = WordGridPanel(game, allowed, subtitle=subtitle, on_finish=self._finished,
                                    on_info=on_info, on_back=self._go_menu, on_guess=self._progress)
        self._host.add_widget(self._panel)
        self._start_timer()

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
        if self._on_finish:
            self._on_finish(won, self._elapsed * 1000, attempts)

    def _progress(self, guesses: list) -> None:
        self._save_progress(guesses)

    def _save_progress(self, guesses: list | None = None) -> None:
        if self._on_progress and self._panel and not self._panel.game.finished:
            gs = guesses if guesses is not None else list(self._panel.game.guesses)
            self._on_progress(gs, self._elapsed * 1000)

    def _go_menu(self) -> None:
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
