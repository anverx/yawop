#!/usr/bin/env python3
"""Add Wiktionary senses to WordNet-defined guessable words, so a lookup can show
BOTH sources. We only fetch Wiktionary to fill WordNet's gaps at build time, so a
WordNet-defined word never gets its everyday Wiktionary phrasing / extra senses.
This grafts them in, with care to stay clean:

  - only guessable words (in allowed_guesses_all.txt) that are currently WordNet-only,
  - skip pure-reference Wiktionary senses ("Alternative form of X", "plural of X", ...),
  - skip near-duplicates of what WordNet already says (case/punctuation-insensitive,
    substring either way),
  - cap the number of grafted senses per word.

Fetches are graceful (1/sec) and cached to the committed Wiktionary cache (the
"black hole"). Run with --apply to write the merges into the shipped dictionaries.

  python scripts/enrich_both_sources.py --assets <assets> \
      --wiktionary-cache data/cache/wiktionary_defs.json --fetch --apply
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

REFERENCE = re.compile(
    r"^\W*"
    r"((alternative|obsolete|archaic|dated|nonstandard|informal|eye|superseded|dialectal|common|rare|pronunciation)\s+)?"
    r"(spelling|form|letter[- ]case form)\s+of\b"
    r"|^\W*(misspelling|plural|clipping|abbreviation|initialism|acronym|synonym|inflection|genitive|"
    r"comparative|superlative|present participle|past tense|past participle|gerund|third[- ]person singular)"
    r"(\s+and\s+\w+)?\s+of\b", re.I)
PLACEHOLDER = re.compile(r"needs a definition|please help out|\brfdef\b|add a definition, then remove", re.I)
_MAX_ADD = 3


def norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def near_dup(cand: str, existing: list[str]) -> bool:
    c = norm(cand)
    if not c:
        return True
    for e in existing:
        e = norm(e)
        if c == e or (len(c) > 8 and c in e) or (len(e) > 8 and e in c):
            return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--wiktionary-cache", required=True)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    assets = pathlib.Path(args.assets)
    allowed = {w.strip().lower() for w in (assets / "allowed_guesses_all.txt").read_text().splitlines() if w.strip()}
    dict_files = list(assets.glob("*/dictionary.jsonl")) + [assets / "extra_defs.jsonl"]

    # per-word: existing sense definitions + the set of sources seen
    defs: dict[str, list[str]] = {}
    sources: dict[str, set] = {}
    for dj in dict_files:
        if not dj.exists():
            continue
        for ln in dj.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                w = r["word"].lower()
                for s in r.get("senses", []):
                    defs.setdefault(w, []).append(s.get("definition", "") or "")
                    src = s.get("source", "?")
                    sources.setdefault(w, set()).add("wiktionary" if src in ("wiktionary", "dictionaryapi.dev") else src)

    targets = sorted(w for w in defs if w in allowed and sources.get(w) == {"wordnet"})
    if args.limit:
        targets = targets[:args.limit]

    cache = json.loads(pathlib.Path(args.wiktionary_cache).read_text()) if pathlib.Path(args.wiktionary_cache).exists() else {}
    session = None
    if args.fetch:
        import requests
        from common import USER_AGENT
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

    from fill_gaps_wiktionary import wiktionary_senses

    grafts: dict[str, list[dict]] = {}
    net = 0
    for i, w in enumerate(targets, 1):
        if args.fetch and w not in cache:
            wiktionary_senses(w, session, cache)
            net += 1
            if net % 25 == 0:
                pathlib.Path(args.wiktionary_cache).write_text(json.dumps(cache))
            time.sleep(args.delay)
        wik = cache.get(w) or []
        add, have = [], list(defs.get(w, []))
        for s in wik:
            d = s.get("definition", "") or ""
            if not d or REFERENCE.search(d) or PLACEHOLDER.search(d) or near_dup(d, have):
                continue
            add.append({"pos_label": s.get("pos_label", "noun"), "definition": d, "source": "wiktionary"})
            have.append(d)
            if len(add) >= _MAX_ADD:
                break
        if add:
            grafts[w] = add
    if args.fetch:
        pathlib.Path(args.wiktionary_cache).write_text(json.dumps(cache))

    print(f"targets (WordNet-only, guessable): {len(targets)}   words gaining Wiktionary senses: {len(grafts)}"
          + (f"   (network fetches: {net})" if args.fetch else ""))

    if not args.apply:
        for w in sorted(grafts)[:12]:
            print(f"  {w}: + {grafts[w][0]['definition'][:56]}")
        print("(dry run; pass --apply to write)")
        return

    added = 0
    for dj in dict_files:
        if not dj.exists():
            continue
        out, changed = [], False
        for ln in dj.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            g = grafts.get(r["word"].lower())
            if g:
                have = {(s.get("pos_label"), s.get("definition")) for s in r.get("senses", [])}
                for s in g:
                    key = (s.get("pos_label"), s.get("definition"))
                    if key not in have:
                        r.setdefault("senses", []).append(s)
                        have.add(key)
                        added += 1
                        changed = True
            out.append(json.dumps(r, ensure_ascii=False))
        if changed:
            dj.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"grafted {added} Wiktionary sense(s) into {len(grafts)} entries")


if __name__ == "__main__":
    main()
