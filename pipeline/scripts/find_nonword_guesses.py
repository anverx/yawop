#!/usr/bin/env python3
"""List guessable words that have NO English definition -- i.e. every sense comes
from a non-English Wiktionary entry (Scots, French, Latin, Dutch, ...). These aren't
English words, so they shouldn't be valid guesses in an English word game.

The gap-filler falls back to other languages when neither WordNet nor the English
Wiktionary defines a 5-letter string, which arbitrarily drags in whatever foreign
word happens to share that spelling ('garre' = Galician, 'whaur' = Scots). A
borrowed word that has actually entered English (pizza, kebab, ...) has its OWN
English Wiktionary entry, so it keeps an English-labelled sense and is NOT listed.

Detection: English senses carry a lowercase part-of-speech label ('noun', 'verb',
'proper noun', ...); foreign senses carry a capitalized language name or an
uppercase code ('Scots', 'French', 'GL', 'OTHER'). A word with no lowercase-labelled
sense has no English entry. The output feeds apply_blocklist --proper-nouns.

  python scripts/find_nonword_guesses.py --assets <assets> --out non_english.txt
"""
from __future__ import annotations

import argparse
import json
import pathlib


def has_english_sense(senses: list[dict]) -> bool:
    for s in senses:
        label = (s.get("pos_label") or "").strip()
        if label and label.islower():   # WordNet + English-Wiktionary labels are lowercase
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    assets = pathlib.Path(args.assets)
    by: dict[str, list] = {}
    for dj in list(assets.glob("*/dictionary.jsonl")) + [assets / "extra_defs.jsonl"]:
        if dj.exists():
            for ln in dj.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    r = json.loads(ln)
                    by.setdefault(r["word"].lower(), []).extend(r.get("senses", []))

    hits = []
    for w, ss in by.items():
        ss = [s for s in ss if (s.get("definition", "") or "").strip()]
        if ss and not has_english_sense(ss):
            hits.append(w)

    pathlib.Path(args.out).write_text("".join(w + "\n" for w in sorted(hits)), encoding="utf-8")
    print(f"non-English guesses (no English sense -> removed everywhere): {len(hits)}")


if __name__ == "__main__":
    main()
