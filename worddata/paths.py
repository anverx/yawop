"""Base directory for bundled assets, PyInstaller-aware.

Unfrozen (running from source): the repo root, i.e. the parent of the worddata/
package. Frozen (a PyInstaller one-folder/one-file build): the bundle's extraction
root (sys._MEIPASS), where the .spec places the assets/ and game/assets/ trees.

Keeping this in one place means asset lookups work identically from source, from a
Windows/Linux PyInstaller binary, and (harmlessly) on Android.
"""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    base = getattr(sys, "_MEIPASS", None)  # set by PyInstaller at runtime
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent
