"""yawop main menu: supplies a MenuConfig to kivyshell's shared MenuScreen."""

from __future__ import annotations

from kivyshell.shell.adapter import Variant
from kivyshell.shell.screens.menu import MenuConfig, MenuScreen


class WordMenuScreen(MenuScreen):
    def menu_config(self) -> MenuConfig:
        return MenuConfig(
            daily_title="Today's Word",
            daily_variants=[Variant("easy", "Easy"), Variant("medium", "Medium"), Variant("hard", "Hard")],
            on_daily=lambda v: self.app.start_daily(v.id),
            actions=[
                ("Random Game", self.app.start_random),
                ("About", self.app.show_about),
            ],
            exit_label="Exit",
            on_exit=self.app.exit_app,
        )
