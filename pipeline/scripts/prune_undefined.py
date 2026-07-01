#!/usr/bin/env python3
"""Drop words with no definition; emit the final dictionary and word lists.

Usage:
    python3 scripts/prune_undefined.py --in data/subtlex-us/dict.filled.jsonl \
        --out-dict data/subtlex-us/dictionary.jsonl \
        --out-words data/subtlex-us/puzzle_words.txt \
        --out-undefined data/subtlex-us/undefined_words.txt

Outputs:
    dictionary.jsonl  : defined records, sorted alphabetically (index-friendly);
                        each keeps its "rank" so frequency order is not lost.
    puzzle_words.txt  : defined words in frequency order (the answer pool source).
    undefined_words.txt: dropped words, alphabetical (for reference).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl, write_jsonl, write_lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out-dict", required=True)
    ap.add_argument("--out-words", required=True)
    ap.add_argument("--out-undefined", required=True)
    args = ap.parse_args()

    records = read_jsonl(args.inp)  # frequency order
    defined = [r for r in records if r.get("senses")]
    undefined = [r["word"] for r in records if not r.get("senses")]

    write_jsonl(args.out_dict, sorted(defined, key=lambda r: r["word"]))
    write_lines(args.out_words, [r["word"] for r in defined])  # freq order preserved
    write_lines(args.out_undefined, sorted(undefined))

    print(f"prune: {len(records)} -> kept {len(defined)} defined, dropped {len(undefined)} ({args.out_dict})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
