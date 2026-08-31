#!/usr/bin/env python3
"""Find proper-noun answers that WordNet's instance check missed.

classify_answers drops proper nouns via WordNet instance_hypernyms, but WordNet
gives composers/artists a second sense "the music of X" (haydn.n.02) and places a
"native of X" gloss -- not instances -- so a name like `haydn` kept answer status.

Rule: a word is a proper-noun leak if it is a WordNet instance AND its only
NON-instance senses are self-referential ("... of <word>" / "<word>'s ..."). That
catches composers (haydn/bizet/gluck), places (ghana/texas/malta), and first
names/surnames (doris/jones/kelly), while a genuine common sense keeps the word.

Guard against WordNet quirks that label a common noun as an instance (isle/islet =
"a small island"; arhat = "a Buddhist ...") via --keep, so real words survive.

Output is a plain word list for apply_blocklist --proper-nouns (removed EVERYWHERE:
proper nouns aren't playable words, not even as guesses -- matching nonanswer_names).

  python scripts/find_proper_leaks.py --assets <assets> --out proper_leaks.txt \
      --keep islet corse arhat melba linux
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TIERS = ("easy", "medium", "hard")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep", nargs="*", default=[],
                    help="words to protect (WordNet mislabels them as instances, but they're common)")
    args = ap.parse_args()
    from nltk.corpus import wordnet as wn  # English-only; same dep as the rest of the pipeline

    assets = Path(args.assets)
    keep = {w.lower() for w in args.keep}
    answers = set()
    for p in assets.glob("*/tiers.json"):
        td = json.loads(p.read_text("utf-8"))
        for t in TIERS:
            answers.update(td["tiers"].get(t, []))

    def is_leak(w: str) -> bool:
        syns = wn.synsets(w)
        if not syns or not any(sy.instance_hypernyms() for sy in syns):
            return False
        selfref = re.compile(r"\bof " + re.escape(w) + r"\b|\b" + re.escape(w) + r"'s\b")
        for sy in syns:
            if sy.instance_hypernyms():
                continue
            if not selfref.search(sy.definition().lower()):
                return False  # a genuine, non-name-derived common sense -> keep the word
        return True

    out = sorted(w for w in answers if w not in keep and is_leak(w))
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"proper-noun leaks: {len(out)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
