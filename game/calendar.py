"""yawop calendar: supplies a CalendarConfig to kivyshell's CalendarScreen."""

from __future__ import annotations

from datetime import date

from kivyshell.shell import Completion
from kivyshell.shell.screens.calendar import CalendarConfig
from kivyshell.shell.screens.calendar import CalendarScreen as _CalendarScreen
from kivyshell.uikit import get_styles, get_theme

from .daycell import WordDayCell


class WordCalendarScreen(_CalendarScreen):
    def calendar_config(self) -> CalendarConfig:
        return CalendarConfig(
            new_state=self.app.store.calendar_state,
            make_cell=lambda day, status: WordDayCell(day, status, **get_styles()["cell"]),
            on_day=lambda d: self.app.play_date(d),
            month_badge_color=self._badge_color,
        )

    @staticmethod
    def _badge_color(crown: object) -> tuple | None:
        t = get_theme()
        if crown == Completion.ON_TIME:
            return t.badge_on_time
        if crown == Completion.LATE:
            return t.badge_late
        return None
