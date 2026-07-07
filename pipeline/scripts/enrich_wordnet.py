#!/usr/bin/env python3
"""Fill definitions for allowed-guess words that no pack defines, using WordNet.

The allowed-guess set includes Wordle's curated list, ~half of which are obscure
words with no entry in our packs (so the in-game '?' shows blank). WordNet covers
a slice of them offline; this writes those as extra_defs.jsonl, which the runtime
lookup consults as a fallback. The rest stay legitimately undefined (they're valid
but obscure) and the popup shows their source pack instead.

Usage:
  python scripts/enrich_wordnet.py --allowed <assets>/allowed_guesses_all.txt \
      --assets <assets> --out <assets>/extra_defs.jsonl
"""
from __future__ import annotations

import argparse
import json
import pathlib

from nltk.corpus import wordnet as wn

_POS = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}
_MAX_SENSES = 3


def defined_words(assets: pathlib.Path) -> set[str]:
    words = set()
    for dj in assets.glob("*/dictionary.jsonl"):
        for line in dj.read_text(encoding="utf-8").splitlines():
            if line.strip():
                words.add(json.loads(line)["word"].lower())
    return words


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--allowed", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    assets = pathlib.Path(args.assets)
    allowed = {w.strip().lower() for w in pathlib.Path(args.allowed).read_text().splitlines() if w.strip()}
    undefined = sorted(allowed - defined_words(assets))

    records = []
    for w in undefined:
        senses, seen = [], set()
        for syn in wn.synsets(w):
            key = (_POS.get(syn.pos(), ""), syn.definition())
            if key in seen:
                continue
            seen.add(key)
            senses.append({"pos_label": _POS.get(syn.pos(), ""), "definition": syn.definition(),
                           "source": "wordnet"})
            if len(senses) >= _MAX_SENSES:
                break
        if senses:
            records.append({"word": w, "senses": senses, "examples": []})

    out = pathlib.Path(args.out)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    print(f"wrote {len(records)} extra definitions to {out} "
          f"({len(records)}/{len(undefined)} of undefined allowed words)")


if __name__ == "__main__":
    main()
