"""yawop logbook: Games / Stats / Activity tabs on kivyshell's LogbookScreen."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView

from kivyshell.shell.screens.logbook import LogbookConfig, LogbookTab
from kivyshell.shell.screens.logbook import LogbookScreen as _LogbookScreen
from kivyshell.uikit import (
    BarChart,
    CaptionLabel,
    DateSeparator,
    StatRow,
    SubtitleLabel,
    TableCellLabel,
    TableHeaderLabel,
    styled,
)

from . import theme as T
from .store import DIFFICULTIES, answer_of

SEG_COLORS = {"easy": T.TILE_CORRECT, "medium": T.TILE_PRESENT, "hard": (0.86, 0.42, 0.42, 0.9)}


def _fmt_ms(ms: int | None) -> str:
    if not ms:
        return "-"
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


class WordLogbookScreen(_LogbookScreen):
    def logbook_config(self) -> LogbookConfig:
        self._games = ScrollView(size_hint=(1, 1))
        self._games_list = styled(BoxLayout, "list_layout")
        self._games_list.bind(minimum_height=self._games_list.setter("height"))
        self._games.add_widget(self._games_list)

        self._stats = ScrollView(size_hint=(1, 1))
        self._stats_box = styled(BoxLayout, "list_layout", spacing=dp(4))
        self._stats_box.bind(minimum_height=self._stats_box.setter("height"))
        self._stats.add_widget(self._stats_box)

        self._activity = BoxLayout(orientation="vertical")

        return LogbookConfig(title="Logbook", tabs=[
            LogbookTab("games", "Games", build=lambda: self._games, refresh=self._refresh_games),
            LogbookTab("stats", "Stats", build=lambda: self._stats, refresh=self._refresh_stats),
            LogbookTab("activity", "Activity", build=lambda: self._activity, refresh=self._refresh_activity),
        ])

    def _refresh_games(self) -> None:
        self._games_list.clear_widgets()
        plays = self.app.store.all_plays(limit=200)
        if not plays:
            self._games_list.add_widget(SubtitleLabel("No games played yet", size_hint_y=None, height=dp(36)))
            return
        header = styled(BoxLayout, "table_header_row")
        for col in ("Word", "Level", "Time", "Result", "When"):
            header.add_widget(TableHeaderLabel(col))
        self._games_list.add_widget(header)
        cur_date = None
        for p in plays:
            d = (p.started_at or "")[:10]
            if d != cur_date:
                cur_date = d
                self._games_list.add_widget(DateSeparator(self._nice_date(d)))
            self._games_list.add_widget(self._row(p))

    def _row(self, p: Any) -> BoxLayout:
        row = styled(BoxLayout, "logbook_row")
        try:
            when = datetime.fromisoformat(p.started_at).strftime("%H:%M")
        except (ValueError, TypeError):
            when = "?"
        row.add_widget(TableCellLabel(answer_of(p.code).upper()))
        row.add_widget(TableCellLabel(p.variant_id.title()))
        row.add_widget(TableCellLabel(_fmt_ms(p.duration_ms)))
        row.add_widget(TableCellLabel("Won" if p.completed else "-"))
        row.add_widget(TableCellLabel(when))
        return row

    def _refresh_stats(self) -> None:
        self._stats_box.clear_widgets()
        agg = self.app.store.stats_by_difficulty()
        self._stats_box.add_widget(SubtitleLabel("By difficulty", color=(1, 1, 1, 1)))
        header = StatRow()
        for col in ("Level", "Played", "Won", "Best"):
            header.add_widget(TableHeaderLabel(col))
        self._stats_box.add_widget(header)
        for diff in DIFFICULTIES:
            a = agg[diff]
            r = StatRow()
            r.add_widget(TableCellLabel(diff.title()))
            r.add_widget(TableCellLabel(str(a["count"])))
            r.add_widget(TableCellLabel(str(a["completed"])))
            r.add_widget(TableCellLabel(_fmt_ms(a["best"])))
            self._stats_box.add_widget(r)

    def _refresh_activity(self) -> None:
        self._activity.clear_widgets()
        self._activity.add_widget(SubtitleLabel("Games per day (30 days)", color=(1, 1, 1, 1)))
        data = self.app.store.games_per_day(30)
        total = sum(sum(v.values()) for _, v in data)
        self._activity.add_widget(BarChart(data, segment_colors=SEG_COLORS))
        self._activity.add_widget(CaptionLabel(f"{total} games in the last 30 days", color=(1, 1, 1, 1)))

    @staticmethod
    def _nice_date(d: str) -> str:
        try:
            dt = datetime.fromisoformat(d).date()
            today = datetime.now().date()
            if dt == today:
                return "Today"
            return dt.strftime("%A, %b %d")
        except (ValueError, TypeError):
            return d or "?"
