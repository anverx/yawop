#!/usr/bin/env python3
"""Split a frequency-ordered word list into easy/medium/hard difficulty tiers.

Usage:
    python3 scripts/assign_tiers.py --words data/subtlex-us/puzzle_words.txt \
        --out data/subtlex-us/tiers.json --easy 0.15 --medium 0.40

Boundaries are cumulative fractions of the list: easy = top --easy, medium =
up to --medium, hard = the rest. Defaults: easy top 15%, medium next 25%
(up to 40%), hard bottom 60%.

--rank-by FILE reorders the words by a reference frequency list before tiering
(used for the Wordle pack, whose curated list has no frequency of its own).
Words absent from the reference are treated as least frequent (hardest),
keeping their original relative order.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--words", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--easy", type=float, default=0.15)
    ap.add_argument("--medium", type=float, default=0.40)
    ap.add_argument("--rank-by", help="reference frequency-ordered word list")
    args = ap.parse_args()

    words = read_lines(args.words)

    if args.rank_by:
        ref = {w: i for i, w in enumerate(read_lines(args.rank_by))}
        big = len(ref)
        # Stable sort by reference rank; unknown words sink to the bottom in order.
        words = sorted(words, key=lambda w: (ref.get(w, big + 1),))

    n = len(words)
    easy_end = round(n * args.easy)
    medium_end = round(n * args.medium)
    tiers = {
        "easy": words[:easy_end],
        "medium": words[easy_end:medium_end],
        "hard": words[medium_end:],
    }
    payload = {
        "boundaries": {"easy_fraction": args.easy, "medium_fraction": args.medium, "total": n},
        "counts": {k: len(v) for k, v in tiers.items()},
        "tiers": tiers,
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"tiers: {n} words -> easy {len(tiers['easy'])}, medium {len(tiers['medium'])}, "
          f"hard {len(tiers['hard'])} ({args.out})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
