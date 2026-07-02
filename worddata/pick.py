"""Pick a word from a shipped pack — optionally by difficulty, repeatably by seed.

Runtime game logic (not part of the build pipeline). Reads assets/dictionaries/.

    from worddata import pick_word
    pick_word("subtlex-us")                       # random from all tiers
    pick_word("subtlex-uk", difficulty="hard")    # from one tier
    pick_word("arcane", seed="2026-07-01")         # same seed -> same word

CLI:  python -m worddata.pick --pack subtlex-us [--difficulty easy] [--seed 2026-07-01] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random

from . import store


def load_pool(pack: str, difficulty: str | None, allow_mature: bool = False) -> list[str]:
    """Candidate words for a pack (+ optional difficulty), deterministically ordered.

    Vulgar/anatomical words are excluded from the pool unless allow_mature is set,
    so they are never picked as a solution by default (they remain valid guesses).
    """
    pdir = store.ASSETS / pack
    if not pdir.is_dir():
        raise SystemExit(f"unknown pack '{pack}'. Available: {', '.join(store.packs())}")

    tiers = store.load_tiers(pack)
    if difficulty:
        if not tiers:
            raise SystemExit(f"pack '{pack}' has no difficulty tiers; drop --difficulty")
        if difficulty not in tiers:
            raise SystemExit(f"unknown difficulty '{difficulty}'. Choose from: {', '.join(store.TIER_ORDER)}")
        pool = list(tiers[difficulty])
    elif tiers:  # join all tiers, preserving easy->hard (frequency) order
        pool = [w for t in store.TIER_ORDER for w in tiers.get(t, [])]
    else:
        pool = next((store.read_lines(pdir / name)  # untiered pack (e.g. surprise)
                     for name in ("puzzle_words.txt", "words.txt") if (pdir / name).exists()), None)
        if pool is None:
            raise SystemExit(f"pack '{pack}' has no word list to draw from")

    if not allow_mature:
        blocked = store.solution_blocklist()
        pool = [w for w in pool if w.lower() not in blocked]
    return pool


def _seeded_rng(pack: str, difficulty: str | None, seed) -> random.Random:
    if seed is None:
        return random.Random()  # nondeterministic
    # Stable across processes (unlike hash()): derive an int from the string form.
    key = f"{pack}|{difficulty or 'all'}|{seed}".encode("utf-8")
    return random.Random(int(hashlib.sha256(key).hexdigest(), 16))


def pick_word(pack: str, difficulty: str | None = None, seed=None, allow_mature: bool = False) -> str:
    """Pick one word. Same (pack, difficulty, seed) -> same word; seed=None -> random.

    allow_mature=False (default) excludes vulgar/anatomical words from the draw.
    """
    pool = load_pool(pack, difficulty, allow_mature=allow_mature)
    if not pool:
        raise SystemExit(f"no words available for pack '{pack}'{f' / {difficulty}' if difficulty else ''}")
    return _seeded_rng(pack, difficulty, seed).choice(pool)


def main() -> int:
    ap = argparse.ArgumentParser(description="Pick a random (optionally repeatable) word from a pack.")
    ap.add_argument("--pack", required=True)
    ap.add_argument("--difficulty", choices=store.TIER_ORDER, help="omit to draw from all tiers")
    ap.add_argument("--seed", help="hash/seed: same value -> same word (e.g. a date for a daily word)")
    ap.add_argument("--allow-mature", action="store_true", help="include vulgar/anatomical words in the draw")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    word = pick_word(args.pack, args.difficulty, args.seed, allow_mature=args.allow_mature)
    if args.json:
        print(json.dumps({"word": word, "pack": args.pack, "difficulty": args.difficulty or "all",
                          "tier": store.tier_of(args.pack, word), "seed": args.seed}, ensure_ascii=False))
    else:
        print(word)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
