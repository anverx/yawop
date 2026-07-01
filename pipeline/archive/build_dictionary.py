#!/usr/bin/env python3
"""Build a JSONL dictionary for the five-letter word list using WordNet.

Reads the alphabetically-sorted word list (index-friendly) and, for each word,
looks up its WordNet senses. Emits one JSON record per line:

    {"word": "abide", "senses": [{"pos": "v", "definition": "..."}, ...]}

Words with no WordNet entry are still emitted with an empty "senses" list so the
output stays 1:1 with the input list; they are also reported to stderr.

Requires: nltk, plus the 'wordnet' and 'omw-1.4' corpora
(nltk.download('wordnet'); nltk.download('omw-1.4')).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from nltk.corpus import wordnet as wn

HERE = Path(__file__).resolve().parent
INPUT_FILE = HERE / "five_letter_words_sorted.txt"
OUTPUT_FILE = HERE / "dictionary.jsonl"

# WordNet single-letter POS -> human-readable label.
POS_LABELS = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}


def senses_for(word: str) -> list[dict[str, str]]:
    """Return a list of {pos, pos_label, definition} for a word, order preserved.

    Duplicate (pos, definition) pairs are collapsed. WordNet applies its own
    morphological normalization, so inflected forms (e.g. "trees") resolve to
    the base lemma's senses.
    """
    senses: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for syn in wn.synsets(word):
        pos = syn.pos()
        definition = syn.definition()
        key = (pos, definition)
        if key in seen:
            continue
        seen.add(key)
        senses.append(
            {
                "pos": pos,
                "pos_label": POS_LABELS.get(pos, pos),
                "definition": definition,
            }
        )
    return senses


def main() -> int:
    if not INPUT_FILE.exists():
        print(f"error: {INPUT_FILE} not found", file=sys.stderr)
        return 1

    words = [w.strip() for w in INPUT_FILE.read_text(encoding="utf-8").splitlines() if w.strip()]

    defined = 0
    missing: list[str] = []
    with OUTPUT_FILE.open("w", encoding="utf-8") as out:
        for word in words:
            senses = senses_for(word)
            if senses:
                defined += 1
            else:
                missing.append(word)
            record = {"word": word, "senses": senses}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        f"wrote {len(words)} records to {OUTPUT_FILE}: "
        f"{defined} with definitions, {len(missing)} without",
        file=sys.stderr,
    )
    if missing:
        preview = ", ".join(missing[:20])
        more = f" (+{len(missing) - 20} more)" if len(missing) > 20 else ""
        print(f"no WordNet entry for: {preview}{more}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
