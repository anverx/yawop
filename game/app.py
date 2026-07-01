"""yawop — a Wordle-style word puzzle built on kivyshell.

WordApp reuses kivyshell's GameShellApp (ScreenManager, splash->menu, navigation)
and MenuScreen; the only game-specific screens are the menu config and the
word-grid game screen. Answers come from the shipped dictionaries via worddata.
"""

from __future__ import annotations

import datetime
import random
from typing import Any

from kivy.core.window import Window
from kivy.utils import platform

import worddata
from worddata.store import allowed_guesses

from kivyshell.shell.app import GameShellApp
from kivyshell.shell.screens.splash import SplashScreen
from kivyshell.uikit import set_theme

from . import theme as T
from .gamescreen import WordGameScreen
from .menu import WordMenuScreen
from .wordgame import WordGame

DEFAULT_PACK = "subtlex-us"
RANDOM_PACKS = ["subtlex-us", "subtlex-uk", "wordle", "arcane"]

if platform not in ("android", "ios"):
    Window.size = (400, 720)


class WordApp(GameShellApp):
    def open_storage(self) -> None:
        set_theme(T.build_theme())
        self._allowed = allowed_guesses()

    def create_screens(self) -> list:
        self.menu_screen = WordMenuScreen(self, name="menu")
        self.game_screen = WordGameScreen(self, name="game")
        return [SplashScreen(name="splash"), self.menu_screen, self.game_screen]

    # --- game flow ---
    def start_daily(self, difficulty: str) -> None:
        seed = datetime.date.today().isoformat()
        self._start(DEFAULT_PACK, difficulty, seed, f"Daily · {difficulty.title()}")

    def start_random(self, instance: Any = None) -> None:
        pack = random.choice(RANDOM_PACKS)
        difficulty = random.choice(["easy", "medium", "hard"])
        self._start(pack, difficulty, None, f"Random · {pack} · {difficulty}")

    def _start(self, pack: str, difficulty: str, seed: str | None, subtitle: str) -> None:
        answer = worddata.pick_word(pack, difficulty, seed=seed)
        self._current = (pack, difficulty, answer)
        self.game_screen.set_game(WordGame(answer), self._allowed, subtitle, self._on_finish)
        self.sm.current = "game"

    def _on_finish(self, won: bool, duration_ms: int) -> None:
        _, _, answer = self._current
        entry = worddata.lookup_entry(answer)
        definition = entry["senses"][0]["definition"] if entry and entry.get("senses") else ""
        self.game_screen.show_reveal(f"{answer.upper()} — {definition}" if definition else answer.upper())
        # TODO: record completion/streak via kivyshell SqliteStore (adds calendar/logbook later).

    def show_about(self, instance: Any = None) -> None:
        from kivyshell.uikit import (
            FixedGrayRoundedButton,
            Popup,
            PopupContent,
            SubtitleLabel,
            TitleLabel,
        )
        content = PopupContent()
        content.add_widget(TitleLabel("yawop"))
        content.add_widget(SubtitleLabel("Yet Another WOrd Puzzle"))
        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=220)
        close.bind(on_press=popup.dismiss)
        popup.open()
