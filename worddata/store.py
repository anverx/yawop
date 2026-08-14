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


def pack_allowed_guesses(pack: str) -> set[str]:
    """Valid-guess set for a single pack (its own allowed_guesses.txt). Empty if the
    pack has no per-pack list (English packs share the global allowed_guesses_all.txt;
    a language pack like 'russian' ships its own so guesses stay in that alphabet)."""
    f = ASSETS / pack / "allowed_guesses.txt"
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


_PACK_LABEL = {"subtlex-us": "SUBTLEX-US", "subtlex-uk": "SUBTLEX-UK",
               "wordle": "Official Wordle", "arcane": "Arcane", "surprise": "Surprise"}
_PACK_ORDER = ["subtlex-us", "subtlex-uk", "wordle", "arcane", "surprise"]


def answer_packs(word: str) -> list[str]:
    """Labels of the packs where the word can be served as an ANSWER (it's in that
    pack's solution pool). Empty means it's only a valid guess, never an answer."""
    w = word.strip().lower()
    out = []
    for pack in [p for p in _PACK_ORDER if p in packs()]:
        tiers = load_tiers(pack)
        if tiers:
            hit = any(w in ws for ws in tiers.values())
        else:  # untiered pack (e.g. surprise): its word list is the answer pool
            hit = any((ASSETS / pack / n).exists() and w in set(read_lines(ASSETS / pack / n))
                      for n in ("puzzle_words.txt", "words.txt"))
        if hit:
            out.append(_PACK_LABEL.get(pack, pack))
    return out


def is_answer_word(word: str) -> bool:
    """True if the word can be served as a puzzle answer in any pack."""
    return bool(answer_packs(word))
