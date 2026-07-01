#!/usr/bin/env python3
"""Build the "arcane" pack: Gutenberg words MINUS the modern SUBTLEX vocabularies.

Usage:
    python3 scripts/subtract.py \
        --minuend data/gutenberg/dictionary.jsonl \
        --subtract data/subtlex-us/words_ranked.txt data/subtlex-uk/words_ranked.txt \
        --out-dict data/arcane/dictionary.jsonl \
        --out-words data/arcane/puzzle_words.txt

Keeps the Gutenberg words that appear in NONE of the SUBTLEX corpora, i.e. words
common in century-old books but absent from modern film/TV subtitles: archaic,
literary, properly horrible. Frequency order is preserved.

Note: this deliberately does NOT prune undefined words — feed it Gutenberg's
pre-prune dictionary so words WordNet/the API can't define survive too (they are
the most horrible ones). Words keep whatever senses the minuend had, empty or not.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import read_jsonl, read_lines, write_jsonl, write_lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minuend", required=True, help="Gutenberg dictionary.jsonl")
    ap.add_argument("--subtract", nargs="+", required=True, help="word lists to remove")
    ap.add_argument("--out-dict", required=True)
    ap.add_argument("--out-words", required=True)
    ap.add_argument("--subtract-top", type=int, default=0,
                    help="use only the top-N (most frequent) words of each --subtract list; 0 = all")
    ap.add_argument("--keep-in", nargs="*", default=[],
                    help="whitelist word lists: keep a word only if it is a real word "
                         "(present here or WordNet-defined). Junk filter.")
    ap.add_argument("--keep-defined", action="store_true",
                    help="with --keep-in, also keep WordNet-defined words not in the whitelist")
    args = ap.parse_args()

    # Modern vocabulary to remove — optionally only the most frequent slice of it,
    # so archaic words that appear only rarely in modern subtitles survive.
    modern: set[str] = set()
    for path in args.subtract:
        ws = read_lines(path)
        if args.subtract_top > 0:
            ws = ws[:args.subtract_top]
        modern.update(w.lower() for w in ws)

    whitelist: set[str] = set()
    for path in args.keep_in:
        whitelist.update(w.lower() for w in read_lines(path))
    filtering = bool(args.keep_in) or args.keep_defined

    def keep(rec: dict) -> bool:
        w = rec["word"].lower()
        if w in modern:
            return False
        if not filtering:                       # no junk filter: keep all survivors
            return True
        if args.keep_defined and rec.get("senses"):
            return True
        return w in whitelist

    records = read_jsonl(args.minuend)  # frequency order
    survivors = [r for r in records if r["word"].lower() not in modern]
    kept = [r for r in records if keep(r)]

    Path(args.out_dict).parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dict, sorted(kept, key=lambda r: r["word"]))
    write_lines(args.out_words, [r["word"] for r in kept])  # freq order preserved

    junk = len(survivors) - len(kept)
    print(f"arcane: {len(records)} Gutenberg - {len(modern)} modern = {len(survivors)} survive"
          f"{f', junk filter drops {junk} -> {len(kept)} kept' if filtering else ''} ({args.out_dict})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
