"""Read-only access to the shipped dictionaries under assets/dictionaries/.

Stdlib only — the game depends on this, not on the build-time pipeline. The
pipeline publishes the finished per-pack dictionary.jsonl + tiers.json here
(see `make -C pipeline publish`).
"""

from __future__ import annotations

import json
from pathlib import Path

# assets/dictionaries/ lives next to this package at the repo root.
ASSETS = Path(__file__).resolve().parent.parent / "assets" / "dictionaries"
TIER_ORDER = ("easy", "medium", "hard")


def read_lines(path) -> list[str]:
    return [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def read_jsonl(path) -> list[dict]:
    return [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def packs() -> list[str]:
    """Names of all shipped packs (those with a dictionary.jsonl)."""
    return sorted(p.parent.name for p in ASSETS.glob("*/dictionary.jsonl"))


def load_tiers(pack: str) -> dict:
    tf = ASSETS / pack / "tiers.json"
    return json.loads(tf.read_text(encoding="utf-8")).get("tiers", {}) if tf.exists() else {}


def tier_of(pack: str, word: str) -> str | None:
    tiers = load_tiers(pack)
    return next((t for t in TIER_ORDER if word in tiers.get(t, [])), None)
