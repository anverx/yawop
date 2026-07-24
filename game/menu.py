"""yawop main menu: supplies a MenuConfig to kivyshell's shared MenuScreen."""

from __future__ import annotations

from typing import Any

from kivy.uix.label import Label

from kivyshell.shell.adapter import Variant
from kivyshell.shell.screens.menu import MenuConfig, MenuScreen


class WordMenuScreen(MenuScreen):
    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self._embolden()

    def on_enter(self) -> None:
        super().on_enter()          # refresh streak / completion badges
        self._embolden()            # keep menu text bold after any rebuild

    def _embolden(self) -> None:
        """Bold every text label in the menu (titles, buttons, streak)."""
        for w in self.walk(restrict=True):
            if isinstance(w, Label):
                w.bold = True

    def menu_config(self) -> MenuConfig:
        return MenuConfig(
            daily_title="Today's Word",
            daily_variants=[Variant("easy", "Easy"), Variant("medium", "Medium"), Variant("hard", "Hard")],
            on_daily=lambda v: self.app.start_daily(v.id),
            calendar_label="Calendar",
            on_calendar=self.app.show_calendar,
            streak_text=self.app.streak_text,
            actions=[
                ("Random Game", self.app.start_random),
                ("How to play", self.app.show_help),
                ("Logbook", self.app.show_logbook),
                ("About", self.app.show_about),
            ],
            exit_label="Exit",
            on_exit=self.app.exit_app,
            daily_completion=self.app.daily_completion,
        )
