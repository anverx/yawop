#!/usr/bin/env python3
"""Build extra_defs.jsonl: definitions for allowed-guess words no pack defines.

Combines two offline sources so it is safe to run in CI (no network):
  - WordNet (via nltk), and
  - the committed Wiktionary cache populated by fill_gaps_wiktionary.py.

Wiktionary senses come first (better coverage/phrasing), then WordNet fills any
gaps, deduped by (pos, definition). The runtime lookup_entry reads this file as a
fallback for otherwise-undefined words; each sense keeps its `source`.

  python scripts/build_extra_defs.py --allowed <assets>/allowed_guesses_all.txt \
      --assets <assets> --wiktionary-cache data/cache/wiktionary_defs.json \
      --out <assets>/extra_defs.jsonl
"""
from __future__ import annotations

import argparse
import json
import pathlib

from nltk.corpus import wordnet as wn

_POS = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}
_MAX_SENSES = 4


def defined_words(assets: pathlib.Path) -> set[str]:
    """Words a pack already defines (excludes extra_defs, which we're rebuilding)."""
    words = set()
    for dj in assets.glob("*/dictionary.jsonl"):
        for line in dj.read_text(encoding="utf-8").splitlines():
            if line.strip():
                words.add(json.loads(line)["word"].lower())
    return words


def wordnet_senses(word: str) -> list[dict]:
    out, seen = [], set()
    for syn in wn.synsets(word):
        key = (_POS.get(syn.pos(), ""), syn.definition())
        if key in seen:
            continue
        seen.add(key)
        out.append({"pos_label": _POS.get(syn.pos(), ""), "definition": syn.definition(),
                    "source": "wordnet"})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--allowed", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--wiktionary-cache")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    assets = pathlib.Path(args.assets)
    allowed = {w.strip().lower() for w in pathlib.Path(args.allowed).read_text().splitlines() if w.strip()}
    undefined = sorted(allowed - defined_words(assets))

    wik: dict[str, list] = {}
    if args.wiktionary_cache and pathlib.Path(args.wiktionary_cache).exists():
        wik = json.loads(pathlib.Path(args.wiktionary_cache).read_text(encoding="utf-8"))

    records, from_wik, from_wn = [], 0, 0
    for w in undefined:
        senses, seen = [], set()
        for s in wik.get(w, []):                       # Wiktionary first
            key = (s.get("pos_label"), s.get("definition"))
            if key not in seen:
                seen.add(key)
                senses.append(s)
        for s in wordnet_senses(w):                    # WordNet fills gaps
            if len(senses) >= _MAX_SENSES:
                break
            key = (s["pos_label"], s["definition"])
            if key not in seen:
                seen.add(key)
                senses.append(s)
        senses = senses[:_MAX_SENSES]
        if senses:
            records.append({"word": w, "senses": senses, "examples": []})
            if any(s.get("source") == "wiktionary" for s in senses):
                from_wik += 1
            else:
                from_wn += 1

    out = pathlib.Path(args.out)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    print(f"wrote {len(records)}/{len(undefined)} extra definitions to {out} "
          f"({100 * len(records) / len(undefined):.0f}% of undefined) "
          f"[wiktionary: {from_wik}, wordnet-only: {from_wn}]")


if __name__ == "__main__":
    main()
