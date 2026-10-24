"""Calendar day cell: day number + three completion marks (easy/medium/hard)."""

from __future__ import annotations

from typing import Any

from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image

from kivyshell.shell import Completion
from kivyshell.uikit import CompletionIcon, DayLabel, get_theme

from .store import DIFFICULTIES, FAILED
from .theme import FAILED_BADGE


class WordDayCell(ButtonBehavior, BoxLayout):
    def __init__(self, day: int, status: dict | None, **kwargs: Any) -> None:
        super().__init__(orientation="vertical", **kwargs)
        self.day = day
        self.background_color = get_theme().button
        self._update_bg()
        self.bind(pos=self._update_bg, size=self._update_bg, state=self._update_bg)

        self.add_widget(DayLabel(str(day), color=(1, 1, 1, 1), size_hint_y=0.5))

        theme = get_theme()
        by_status = {Completion.ON_TIME: theme.badge_on_time, Completion.LATE: theme.badge_late}
        row = BoxLayout(orientation="horizontal", size_hint_y=0.5, spacing=dp(1),
                        padding=[dp(2), 0, dp(2), dp(2)])
        for diff in DIFFICULTIES:
            st = (status or {}).get(diff, Completion.NONE)
            if st == FAILED:  # black upside-down crown
                row.add_widget(Image(source=FAILED_BADGE, fit_mode="contain"))
            else:
                row.add_widget(CompletionIcon(by_status.get(st, (0.5, 0.5, 0.5, 0.3)), fit_mode="contain"))
        self.add_widget(row)

    def _update_bg(self, *a: Any) -> None:
        self.canvas.before.clear()
        with self.canvas.before:
            theme = get_theme()
            Color(*(theme.button_down if self.state == "down" else self.background_color))
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
