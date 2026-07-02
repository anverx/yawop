"""WordGameScreen: hosts the word-grid panel (yawop's game-specific screen).

kivyshell doesn't ship a game screen (that's the per-game piece), so yawop builds
its own on top of the shared BackgroundedScreen.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout

from kivyshell.shell.screens.base import BackgroundedScreen
from kivyshell.uikit import CaptionLabel, TitleSmLabel

from .wordgame import WordGame
from .wordgrid import WordGridPanel


class WordGameScreen(BackgroundedScreen):
    def build_content(self) -> None:
        self.title = TitleSmLabel("")
        self.content_layout.add_widget(self.title)
        self._host = BoxLayout()
        self.content_layout.add_widget(self._host)
        self.reveal = CaptionLabel("", size_hint_y=None, height=0)
        self.reveal.halign = "center"
        self.content_layout.add_widget(self.reveal)
        self.add_back_button()
        self._panel: WordGridPanel | None = None
        self._on_finish: Callable[[bool, int, int], None] | None = None

    def set_game(self, game: WordGame, allowed: set[str], subtitle: str,
                 on_finish: Callable[[bool, int, int], None],
                 on_info: Callable[[str], None]) -> None:
        self.title.text = subtitle
        self.reveal.text = ""
        self.reveal.height = 0
        self._on_finish = on_finish
        self._host.clear_widgets()
        self._panel = WordGridPanel(game, allowed, on_finish=self._finished, on_info=on_info)
        self._host.add_widget(self._panel)

    def _finished(self, won: bool, duration_ms: int, attempts: int) -> None:
        if self._on_finish:
            self._on_finish(won, duration_ms, attempts)

    def show_reveal(self, text: str) -> None:
        from kivy.metrics import dp
        self.reveal.text = text
        self.reveal.height = dp(40)
        self.reveal.text_size = (self.reveal.width, None)

    # --- hardware keyboard (desktop) ---
    def on_enter(self, *a: Any) -> None:
        Window.bind(on_key_down=self._on_key_down)

    def on_leave(self, *a: Any) -> None:
        Window.unbind(on_key_down=self._on_key_down)

    def _on_key_down(self, window: Any, key: int, scancode: int, text: str, modifiers: list) -> bool:
        if not self._panel:
            return False
        if key == 13:      # Enter
            self._panel.on_key_action("enter")
            return True
        if key == 8:       # Backspace
            self._panel.on_key_action("backspace")
            return True
        if text and text.isalpha() and len(text) == 1:
            self._panel.on_key_text(text)
            return True
        return False
