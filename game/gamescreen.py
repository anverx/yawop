"""WordGameScreen: hosts the word-grid panel full-height (yawop's game screen).

The panel lays itself out as four sections (matrix / Enter / keyboard / Back), so
this screen just drops the default top spacer and lets the panel fill the space.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout

from kivyshell.shell.screens.base import BackgroundedScreen

from .wordgame import WordGame
from .wordgrid import WordGridPanel


class WordGameScreen(BackgroundedScreen):
    def get_padding(self) -> int:
        return 6

    def get_spacing(self) -> int:
        return 4

    def build_content(self) -> None:
        self.content_layout.clear_widgets()  # drop the base top-spacer; game fills the screen
        self._host = BoxLayout()
        self.content_layout.add_widget(self._host)
        self._panel: WordGridPanel | None = None
        self._on_finish: Callable[[bool, int, int], None] | None = None

    def set_game(self, game: WordGame, allowed: set[str], subtitle: str,
                 on_finish: Callable[[bool, int, int], None],
                 on_info: Callable[[str], None]) -> None:
        self._on_finish = on_finish
        self._host.clear_widgets()
        self._panel = WordGridPanel(game, allowed, subtitle=subtitle, on_finish=self._finished,
                                    on_info=on_info, on_back=self._go_menu)
        self._host.add_widget(self._panel)

    def _finished(self, won: bool, duration_ms: int, attempts: int) -> None:
        if self._on_finish:
            self._on_finish(won, duration_ms, attempts)

    def _go_menu(self) -> None:
        self.app.sm.current = "menu"

    def show_reveal(self, text: str) -> None:
        if self._panel:
            self._panel.show_reveal(text)

    # --- hardware keyboard (desktop) ---
    def on_enter(self, *a: Any) -> None:
        Window.bind(on_key_down=self._on_key_down)

    def on_leave(self, *a: Any) -> None:
        Window.unbind(on_key_down=self._on_key_down)

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
