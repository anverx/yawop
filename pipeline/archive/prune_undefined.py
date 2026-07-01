#!/usr/bin/env python3
"""Prune words that have no definition from the dictionary and the word lists.

Keeps everything consistent across the three artifacts:
  - dictionary.jsonl              (records with non-empty "senses" only)
  - five_letter_words.txt         (rank order preserved, undefined words dropped)
  - five_letter_words_sorted.txt  (regenerated alphabetically from the kept set)

Undefined words are written to undefined_words.txt for reference.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DICT_FILE = HERE / "dictionary.jsonl"
RANK_FILE = HERE / "five_letter_words.txt"
SORTED_FILE = HERE / "five_letter_words_sorted.txt"
UNDEFINED_FILE = HERE / "undefined_words.txt"


def main() -> int:
    records = [json.loads(l) for l in DICT_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]

    defined = {r["word"] for r in records if r.get("senses")}
    undefined = [r["word"] for r in records if not r.get("senses")]

    # Rewrite dictionary with defined records only, preserving order.
    kept = [r for r in records if r.get("senses")]
    with DICT_FILE.open("w", encoding="utf-8") as out:
        for r in kept:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Filter the rank-ordered list, keeping its original order.
    rank_words = [w.strip() for w in RANK_FILE.read_text(encoding="utf-8").splitlines() if w.strip()]
    rank_kept = [w for w in rank_words if w in defined]
    RANK_FILE.write_text("\n".join(rank_kept) + "\n", encoding="utf-8")

    # Regenerate the sorted list from the kept set.
    SORTED_FILE.write_text("\n".join(sorted(defined)) + "\n", encoding="utf-8")

    UNDEFINED_FILE.write_text("\n".join(sorted(undefined)) + "\n", encoding="utf-8")

    print(f"kept {len(kept)} defined words, pruned {len(undefined)} undefined")
    print(f"rank list: {len(rank_words)} -> {len(rank_kept)}")
    print(f"undefined words saved to {UNDEFINED_FILE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
