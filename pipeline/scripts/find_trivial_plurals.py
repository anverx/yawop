#!/usr/bin/env python3
"""List trivial -s inflections in the answer pools, to exclude from being served
as puzzle SOLUTIONS (mirroring Wordle, which avoids -s answers). They stay valid
guesses and keep their definitions.

A word qualifies if it is 5 letters, ends in 's' (but not 'ss'), and its singular
stem is a real word (a WordNet lemma) -- e.g. cakes->cake, mesas->mesa, ladies->lady.
Base words ending in s (bonus, chaos, virus, glass) don't match (no real stem).

  python scripts/find_trivial_plurals.py --assets <assets> --out trivial_plurals.txt
"""
from __future__ import annotations

import argparse
import json
import pathlib

from nltk.corpus import wordnet as wn


def _stems(w: str) -> list[str]:
    out = [w[:-1]]
    if w.endswith("es"):
        out.append(w[:-2])
    if w.endswith("ies"):
        out.append(w[:-3] + "y")
    return out


def is_trivial_plural(w: str) -> bool:
    if len(w) != 5 or not w.endswith("s") or w.endswith("ss"):
        return False
    return any(wn.synsets(s) for s in _stems(w))


def answer_pool(assets: pathlib.Path) -> set[str]:
    """Every word that can currently be served as an answer, across all packs."""
    words: set[str] = set()
    for pack in sorted(p for p in assets.iterdir() if p.is_dir()):
        tj = pack / "tiers.json"
        if tj.exists():
            for ws in json.loads(tj.read_text()).get("tiers", {}).values():
                words |= {w.lower() for w in ws}
        else:  # untiered pack (surprise): its word list is the answer pool
            for name in ("puzzle_words.txt", "words.txt"):
                f = pack / name
                if f.exists():
                    words |= {ln.strip().lower() for ln in f.read_text().splitlines() if ln.strip()}
    return words


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    pool = answer_pool(pathlib.Path(args.assets))
    triv = sorted(w for w in pool if is_trivial_plural(w))
    pathlib.Path(args.out).write_text("".join(w + "\n" for w in triv), encoding="utf-8")
    print(f"trivial -s answers: {len(triv)} of {len(pool)} answer-pool words -> {args.out}")


if __name__ == "__main__":
    main()
