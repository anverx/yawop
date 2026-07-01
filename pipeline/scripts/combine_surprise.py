#!/usr/bin/env python3
"""Build the "Surprise me" pack: union of all packs, no tiers, no rank merge.

Usage:
    python3 scripts/combine_surprise.py \
        --dicts data/subtlex-us/dictionary.jsonl data/subtlex-uk/dictionary.jsonl data/wordle/dictionary.jsonl \
        --out-dict data/surprise/dictionary.jsonl --out-words data/surprise/words.txt

Merges the defined words from every input dictionary (case-insensitive union),
combining their senses and de-duplicating identical (source, pos, definition)
entries. Deliberately carries no "rank" or tiers: this pack is a flat pool for
random selection across everything, with no attempt to reconcile the different
sources' frequency scales.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl, write_jsonl, write_lines


def sense_key(s: dict) -> tuple:
    return (s.get("source"), s.get("pos_label"), s.get("definition"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dicts", nargs="+", required=True)
    ap.add_argument("--out-dict", required=True)
    ap.add_argument("--out-words", required=True)
    args = ap.parse_args()

    merged: dict[str, dict] = {}
    for path in args.dicts:
        for rec in read_jsonl(path):
            word = rec["word"]
            entry = merged.setdefault(word, {"word": word, "sources": [], "senses": []})
            pack = Path(path).parent.name
            if pack not in entry["sources"]:
                entry["sources"].append(pack)
            have = {sense_key(s) for s in entry["senses"]}
            for s in rec.get("senses", []):
                if sense_key(s) not in have:
                    have.add(sense_key(s))
                    entry["senses"].append(s)

    words = sorted(merged)
    write_jsonl(args.out_dict, [merged[w] for w in words])
    write_lines(args.out_words, words)
    print(f"surprise: union of {len(args.dicts)} packs -> {len(words)} words ({args.out_dict})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
