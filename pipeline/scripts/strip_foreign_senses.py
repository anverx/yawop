#!/usr/bin/env python3
"""Drop redundant foreign-language senses from English dictionary entries.

fill_gaps_wiktionary labels non-English senses with the language (Scots, Latin,
"AST"=Asturian, ...) so a word defined only in another language still gets a gloss.
But when a word ALSO has an English sense, the foreign sense is just clutter -- e.g.
`causa` shows the WordNet legal noun PLUS two Asturian verb-inflection lines tagged
"AST". This removes foreign senses from any entry that has at least one English
(standard-POS) sense; entries defined ONLY in another language keep their gloss.

  python scripts/strip_foreign_senses.py --assets <assets>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Standard English part-of-speech labels (WordNet + Wiktionary). Anything else a
# sense is labelled with is a language name/code (Scots, Latin, AST, SQ, OTHER, ...).
ENGLISH_POS = {
    "noun", "verb", "adjective", "adverb", "interjection", "preposition",
    "conjunction", "pronoun", "numeral", "determiner", "article", "particle",
    "prefix", "suffix", "contraction", "symbol", "proper noun", "",
}


def _is_english(sense: dict) -> bool:
    return sense.get("pos_label", "").lower() in ENGLISH_POS


def _clean_file(path: Path) -> int:
    if not path.exists():
        return 0
    out, removed = [], 0
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        senses = rec.get("senses", [])
        if any(_is_english(s) for s in senses):
            kept = [s for s in senses if _is_english(s)]
            removed += len(senses) - len(kept)
            rec["senses"] = kept
        out.append(json.dumps(rec, ensure_ascii=False))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", required=True)
    args = ap.parse_args()
    assets = Path(args.assets)
    total = 0
    # English packs + the global fallback; skip Cyrillic packs (russian labels differ).
    targets = [assets / p / "dictionary.jsonl" for p in ("subtlex-us", "subtlex-uk", "wordle", "arcane", "surprise")]
    targets.append(assets / "extra_defs.jsonl")
    for f in targets:
        n = _clean_file(f)
        if n:
            print(f"  {f.parent.name}/{f.name}: dropped {n} foreign senses")
        total += n
    print(f"stripped {total} redundant foreign-language senses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
