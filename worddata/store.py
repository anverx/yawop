"""Read-only access to the shipped dictionaries under assets/dictionaries/.

Stdlib only — the game depends on this, not on the build-time pipeline. The
pipeline publishes the finished per-pack dictionary.jsonl + tiers.json here
(see `make -C pipeline publish`).
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import app_root

# assets/dictionaries/ lives at the app root (repo root, or the PyInstaller bundle).
ASSETS = app_root() / "assets" / "dictionaries"
TIER_ORDER = ("easy", "medium", "hard")


def read_lines(path) -> list[str]:
    return [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def read_jsonl(path) -> list[dict]:
    return [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def packs() -> list[str]:
    """Names of all shipped packs (those with a dictionary.jsonl)."""
    return sorted(p.parent.name for p in ASSETS.glob("*/dictionary.jsonl"))


def allowed_guesses() -> set[str]:
    """The full set of valid 5-letter words a player may guess (union across packs)."""
    f = ASSETS / "allowed_guesses_all.txt"
    return set(read_lines(f)) if f.exists() else set()


def solution_blocklist() -> set[str]:
    """Vulgar/anatomical words kept as valid guesses but excluded from puzzle
    SOLUTIONS by default. Applied at pick time unless the player opts in. (Slurs
    are removed from the shipped data entirely, so they never reach this list.)"""
    f = ASSETS / "blocklist_solutions.txt"
    if not f.exists():
        return set()
    return {ln.strip().lower() for ln in f.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def load_tiers(pack: str) -> dict:
    tf = ASSETS / pack / "tiers.json"
    return json.loads(tf.read_text(encoding="utf-8")).get("tiers", {}) if tf.exists() else {}


def tier_of(pack: str, word: str) -> str | None:
    tiers = load_tiers(pack)
    return next((t for t in TIER_ORDER if word in tiers.get(t, [])), None)


def is_answer_word(word: str) -> bool:
    """True if the word can be served as a puzzle answer (it's in some pack's
    solution pool), vs. being only a valid guess in allowed_guesses."""
    w = word.strip().lower()
    for pack in packs():
        tiers = load_tiers(pack)
        if tiers:
            if any(w in ws for ws in tiers.values()):
                return True
        else:  # untiered pack (e.g. surprise): its word list is the answer pool
            for name in ("puzzle_words.txt", "words.txt"):
                f = ASSETS / pack / name
                if f.exists() and w in set(read_lines(f)):
                    return True
    return False
