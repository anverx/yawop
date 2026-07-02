"""yawop — a Wordle-style word puzzle built on kivyshell.

WordApp reuses kivyshell's GameShellApp + shared screens (splash/menu/calendar/
logbook); the only game-specific screens are the menu config and the word-grid
game screen. Answers come from the shipped dictionaries via worddata; plays and
completions are persisted with kivyshell's SqliteStore.
"""

from __future__ import annotations

import datetime
from typing import Any

from kivy.core.window import Window
from kivy.utils import platform

import worddata

from kivyshell.shell.app import GameShellApp
from kivyshell.shell.screens.splash import SplashScreen
from kivyshell.uikit import set_theme

from . import theme as T
from .calendar import WordCalendarScreen
from .gamescreen import WordGameScreen
from .logbook import WordLogbookScreen
from .menu import WordMenuScreen
from .store import WordStore
from .wordgame import WordGame
from worddata.store import allowed_guesses

DEFAULT_PACK = "subtlex-us"
# (pack_id, short label) shown in the Random Game options popup.
PACKS = [("subtlex-us", "US"), ("subtlex-uk", "UK"), ("wordle", "Official"), ("arcane", "Arcane")]
PACK_LABEL = dict(PACKS)
DIFFICULTIES = ["easy", "medium", "hard"]

if platform not in ("android", "ios"):
    Window.size = (400, 720)


class WordApp(GameShellApp):
    def open_storage(self) -> None:
        set_theme(T.build_theme())
        self._allowed = allowed_guesses()
        self.store = WordStore()
        self.store.open(self.user_data_dir)
        self._play_id: int | None = None
        self._last_random = {"pack": DEFAULT_PACK, "difficulty": "medium"}

    def close_storage(self) -> None:
        self.store.close()

    def create_screens(self) -> list:
        self.menu_screen = WordMenuScreen(self, name="menu")
        self.game_screen = WordGameScreen(self, name="game")
        self.calendar_screen = WordCalendarScreen(self, name="calendar")
        self.logbook_screen = WordLogbookScreen(self, name="logbook")
        return [SplashScreen(name="splash"), self.menu_screen, self.game_screen,
                self.calendar_screen, self.logbook_screen]

    # --- menu data ---
    def streak_text(self) -> str:
        s = self.store.streak()
        return f"Streak: {s} day{'s' if s != 1 else ''}" if s > 0 else "Start a streak!"

    def daily_completion(self) -> dict[str, bool]:
        return self.store.today_completion()

    # --- game flow ---
    def start_daily(self, difficulty: str) -> None:
        today = datetime.date.today().isoformat()
        self._start(DEFAULT_PACK, difficulty, today, f"Daily · {difficulty.title()}")

    def start_random(self, instance: Any = None) -> None:
        """Open the Random Game options popup: difficulty + word pack."""
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.widget import Widget

        from kivyshell.uikit import (
            FixedGrayRoundedButton,
            FixedRoundedButton,
            Popup,
            PopupContent,
            SelectableButton,
            SelectableButtonGroup,
            SubtitleLabel,
            TitleLabel,
            get_styles,
            styled,
        )

        sel = dict(self._last_random)
        content = PopupContent()
        content.add_widget(TitleLabel("Random Game"))

        content.add_widget(SubtitleLabel("Difficulty"))
        diff_row = styled(BoxLayout, "selection_row")
        diff_group = SelectableButtonGroup(on_select=lambda v: sel.__setitem__("difficulty", v))
        for d in DIFFICULTIES:
            b = SelectableButton(text=d.title(), selected=(d == sel["difficulty"]), **get_styles()["selection_btn"])
            diff_group.add(d, b)
            diff_row.add_widget(b)
        content.add_widget(diff_row)

        content.add_widget(SubtitleLabel("Word Pack"))
        pack_row = styled(BoxLayout, "selection_row")
        pack_group = SelectableButtonGroup(on_select=lambda v: sel.__setitem__("pack", v))
        for pid, label in PACKS:
            b = SelectableButton(text=label, selected=(pid == sel["pack"]), **get_styles()["selection_btn"])
            pack_group.add(pid, b)
            pack_row.add_widget(b)
        content.add_widget(pack_row)

        content.add_widget(styled(Widget, "spacer_sm"))
        holder: list = []

        def on_play(_x: Any) -> None:
            self._last_random = dict(sel)
            holder[0].dismiss()
            self._start(sel["pack"], sel["difficulty"], None,
                        f"{PACK_LABEL[sel['pack']]} · {sel['difficulty'].title()}")

        play = FixedRoundedButton(text="Play")
        play.bind(on_press=on_play)
        content.add_widget(play)
        cancel = FixedGrayRoundedButton(text="Cancel")
        content.add_widget(cancel)

        popup = Popup(content, height=360, width_hint=0.85)
        holder.append(popup)
        cancel.bind(on_press=popup.dismiss)
        popup.open()

    def play_date(self, d: datetime.date) -> None:
        """Tapping a calendar day: choose a difficulty, then play that day's word."""
        from kivyshell.uikit import FixedGrayRoundedButton, Popup, PopupContent, RoundedButton, SizeButtonRow, TitleLabel
        content = PopupContent()
        title = "Today's Word" if d == datetime.date.today() else d.strftime("%B %d, %Y")
        content.add_widget(TitleLabel(title, height=40))
        row = SizeButtonRow()
        popup_holder: list = []

        def choose(diff: str) -> None:
            popup_holder[0].dismiss()
            self._start(DEFAULT_PACK, diff, d.isoformat(), f"{title} · {diff.title()}")

        for diff in ("easy", "medium", "hard"):
            btn = RoundedButton(text=diff.title())
            btn.bind(on_press=lambda _x, dd=diff: choose(dd))
            row.add_widget(btn)
        content.add_widget(row)
        cancel = FixedGrayRoundedButton(text="Cancel")
        content.add_widget(cancel)
        popup = Popup(content, height=200, width_hint=0.8)
        popup_holder.append(popup)
        cancel.bind(on_press=popup.dismiss)
        popup.open()

    def _start(self, pack: str, difficulty: str, day: str | None, subtitle: str) -> None:
        answer = worddata.pick_word(pack, difficulty, seed=day)
        self._current = (pack, difficulty, answer)
        self._play_id = self.store.start(difficulty, day, answer)
        self.game_screen.set_game(WordGame(answer), self._allowed, subtitle, self._on_finish)
        self.sm.current = "game"

    def _on_finish(self, won: bool, duration_ms: int, attempts: int) -> None:
        _, _, answer = self._current
        if self._play_id is not None:
            self.store.finish(self._play_id, won, duration_ms, attempts)  # record win AND lose
        self._play_id = None
        entry = worddata.lookup_entry(answer)
        definition = entry["senses"][0]["definition"] if entry and entry.get("senses") else ""
        self.game_screen.show_reveal(f"{answer.upper()} — {definition}" if definition else answer.upper())

    def show_about(self, instance: Any = None) -> None:
        from kivyshell.uikit import FixedGrayRoundedButton, Popup, PopupContent, SubtitleLabel, TitleLabel
        content = PopupContent()
        content.add_widget(TitleLabel("yawop"))
        content.add_widget(SubtitleLabel("Yet Another WOrd Puzzle"))
        close = FixedGrayRoundedButton(text="Close")
        content.add_widget(close)
        popup = Popup(content, height=220)
        close.bind(on_press=popup.dismiss)
        popup.open()
