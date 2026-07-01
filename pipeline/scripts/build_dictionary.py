#!/usr/bin/env python3
"""Build a WordNet dictionary (JSONL) from a frequency-ordered word list.

Usage:
    python3 scripts/build_dictionary.py --words data/subtlex-us/words_ranked.txt \
        --out data/subtlex-us/dict.wordnet.jsonl

Each output record: {"word", "rank", "senses": [...]}. "rank" is the 1-based
position in the input (frequency) order. Words with no WordNet entry get an
empty "senses" list (filled later by fill_gaps.py, then dropped by prune).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_lines, wordnet_senses, write_jsonl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--words", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    words = read_lines(args.words)
    records = []
    defined = 0
    for rank, word in enumerate(words, 1):
        senses = wordnet_senses(word)
        if senses:
            defined += 1
        records.append({"word": word, "rank": rank, "senses": senses})
    write_jsonl(args.out, records)
    print(f"build: {len(words)} words -> {defined} WordNet-defined, {len(words)-defined} gaps ({args.out})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
