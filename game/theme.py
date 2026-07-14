"""yawop's kivyshell Theme: word-game palette, splash background, W badge."""

from __future__ import annotations

import os

from kivyshell.uikit import Theme

from worddata.paths import app_root

_ROOT = str(app_root())            # repo root, or the PyInstaller bundle root
_HERE = os.path.join(_ROOT, "game")  # game/ package assets live under here

# Black, upside-down W badge shown on the calendar for a failed daily.
FAILED_BADGE = os.path.join(_HERE, "assets", "failed-badge.png")

# Wordle-ish tile colors, exposed for the game panel.
TILE_CORRECT = (0.42, 0.67, 0.39, 1)   # green
TILE_PRESENT = (0.79, 0.71, 0.34, 1)   # gold/yellow
TILE_ABSENT = (0.47, 0.48, 0.50, 1)    # gray
TILE_EMPTY = (0.95, 0.95, 0.96, 1)     # near-white
KEY_DEFAULT = (0.82, 0.84, 0.86, 1)


def build_theme() -> Theme:
    return Theme(
        # A cool blue palette to distinguish yawop from yaque's green.
        button=(0.36, 0.56, 0.86, 1),
        button_down=(0.28, 0.46, 0.74, 1),
        button_gray=(0.75, 0.75, 0.78, 1),
        button_gray_down=(0.6, 0.6, 0.63, 1),
        button_unselected=(0.7, 0.7, 0.73, 1),
        link=(0.2, 0.45, 0.8, 1),
        background_image=os.path.join(_ROOT, "assets", "images", "splash.jpeg"),
        # Completion badge: a stylized gold 'W' (Word/Wordle), used like yaque's crown.
        badge_icon=os.path.join(_HERE, "assets", "w-badge.png"),
        badge_on_time=(0.95, 0.77, 0.06, 1),   # gold W (solved same day)
        badge_late=(0.72, 0.76, 0.85, 1),      # silver-ish (solved later)
    )
