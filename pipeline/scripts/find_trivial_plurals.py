#!/usr/bin/env python3
"""List -s inflections in the answer pools, to exclude from being served as puzzle
SOLUTIONS (mirroring Wordle, which avoids -s answers). They stay valid guesses and
keep their definitions.

A word is excluded only when it is *purely an inflection*: it is 5 letters, ends in
's' (but not 'ss'), and EVERY one of its dictionary senses is an inflection form
('plural of X', 'third-person singular ... of X', 'past participle of X', ...).
Words whose -s form carries its own meaning (means, goods, news, odds, arms, pants)
keep at least one non-inflection sense and are NOT excluded. Undefined -s words fall
back to a morphological check (their singular is a real word).

  python scripts/find_trivial_plurals.py --assets <assets> --out trivial_plurals.txt
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re

from nltk.corpus import wordnet as wn

_INFLECTION = re.compile(
    r"\b(plural of|third[- ]person singular|present participle of|past participle of|"
    r"simple past|present tense of|inflection of|genitive|dative|accusative|nominative|vocative|ablative)\b",
    re.I)


def _stems(w: str) -> list[str]:
    out = [w[:-1]]
    if w.endswith("es"):
        out.append(w[:-2])
    if w.endswith("ies"):
        out.append(w[:-3] + "y")
    return out


def load_defs(assets: pathlib.Path) -> dict[str, list]:
    defs: dict[str, list] = {}
    for dj in list(assets.glob("*/dictionary.jsonl")) + [assets / "extra_defs.jsonl"]:
        if dj.exists():
            for ln in dj.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    r = json.loads(ln)
                    defs.setdefault(r["word"].lower(), []).extend(r.get("senses", []))
    return defs


def answer_pool(assets: pathlib.Path) -> set[str]:
    words: set[str] = set()
    for pack in sorted(p for p in assets.iterdir() if p.is_dir()):
        tj = pack / "tiers.json"
        if tj.exists():
            for ws in json.loads(tj.read_text()).get("tiers", {}).values():
                words |= {w.lower() for w in ws}
        else:
            for name in ("puzzle_words.txt", "words.txt"):
                f = pack / name
                if f.exists():
                    words |= {ln.strip().lower() for ln in f.read_text().splitlines() if ln.strip()}
    return words


def is_trivial_plural(w: str, defs: dict[str, list]) -> bool:
    if len(w) != 5 or not w.endswith("s") or w.endswith("ss"):
        return False
    syns = wn.synsets(w)
    if syns:
        # WordNet knows it. Keep it if it's a lemma in its own right (its own meaning,
        # e.g. means/goods/news/odds/arms/pants). Exclude if its synsets are only the
        # morphological base (paths->path, sulks->sulk) -- i.e. a pure inflection.
        return not any(w == lem.lower() for s in syns for lem in s.lemma_names())
    senses = defs.get(w)  # WordNet doesn't know it: use our stored 'plural of X' senses
    if senses:
        return all(_INFLECTION.search(s.get("definition", "") or "") for s in senses)
    return any(wn.synsets(s) for s in _stems(w))  # last resort: singular is a real word


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    assets = pathlib.Path(args.assets)
    defs = load_defs(assets)
    pool = answer_pool(assets)
    triv = sorted(w for w in pool if is_trivial_plural(w, defs))
    pathlib.Path(args.out).write_text("".join(w + "\n" for w in triv), encoding="utf-8")
    print(f"pure -s inflections excluded from answers: {len(triv)} of {len(pool)} answer-pool words")


if __name__ == "__main__":
    main()
