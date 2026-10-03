#!/usr/bin/env python3
"""Resolve 'reference-only' dictionary entries into real meanings.

Many valid guesses are archaic/variant spellings or inflections whose whole
definition just points at another word ("Alternative spelling of abaca", "plural
of abac") with no meaning of its own -- a dead end in the lookup. This grafts the
BASE word's meaning onto such an entry (following short reference chains), so
'abaka' shows "Alternative spelling of abaca" PLUS abaca's actual meaning.

Base meanings are sourced in order: our own shipped dictionary, WordNet, the
committed Wiktionary cache, then (with --fetch) a graceful Wiktionary lookup.

  python scripts/resolve_references.py --assets <assets> \
      --wiktionary-cache data/cache/wiktionary_defs.json [--fetch] [--apply]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nltk.corpus import wordnet as wn  # noqa: E402

# A definition that BEGINS with a reference phrase (anchored, so "an impure form of
# quartz" is not a reference). Mirrors the classifier's reference test.
REF = re.compile(
    r"^\W*"
    r"((alternative|obsolete|archaic|dated|nonstandard|informal|eye|superseded|dialectal|common|rare|pronunciation)\s+)?"
    r"(spelling|form|letter[- ]case form)\s+of\b"
    r"|^\W*(misspelling|plural|clipping|abbreviation|initialism|acronym|synonym|inflection|genitive|"
    r"comparative|superlative|present participle|past tense|past participle|gerund|third[- ]person singular)"
    r"(\s+and\s+\w+)?\s+of\b", re.I)
_POS = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}
_MAX_GRAFT = 3


def is_ref(d: str) -> bool:
    return bool(REF.search(d or ""))


def base_of(defn: str) -> str | None:
    """The referenced word: the first word after the reference phrase's 'of'."""
    m = REF.search(defn or "")
    if not m:
        return None
    tail = defn[m.end():]
    bm = re.search(r"([a-z][a-z'\-]+)", tail, re.I)
    return bm.group(1).lower().strip("'-") if bm else None


def wn_senses(word: str) -> list[dict]:
    out = []
    for s in wn.synsets(word):
        if s.instance_hypernyms():          # skip proper nouns
            continue
        d = s.definition()
        if is_ref(d):
            continue
        out.append({"pos_label": _POS.get(s.pos(), s.pos()), "definition": d, "source": "wordnet"})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--wiktionary-cache", required=True)
    ap.add_argument("--fetch", action="store_true", help="allow graceful Wiktionary lookups for unresolved bases")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--apply", action="store_true", help="write grafts back into the dictionaries (else dry-run)")
    args = ap.parse_args()

    assets = pathlib.Path(args.assets)
    dict_files = list(assets.glob("*/dictionary.jsonl")) + [assets / "extra_defs.jsonl"]

    all_defs: dict[str, list[str]] = {}       # word -> every definition string
    substantive: dict[str, list[dict]] = {}   # word -> non-reference senses (our own data)
    for dj in dict_files:
        if not dj.exists():
            continue
        for ln in dj.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                w = r["word"].lower()
                for s in r.get("senses", []):
                    d = s.get("definition", "") or ""
                    all_defs.setdefault(w, []).append(d)
                    if d.strip() and not is_ref(d):
                        substantive.setdefault(w, []).append(s)

    wik = json.loads(pathlib.Path(args.wiktionary_cache).read_text()) if pathlib.Path(args.wiktionary_cache).exists() else {}
    session = None
    if args.fetch:
        import requests
        from common import USER_AGENT
        from fill_gaps_wiktionary import wiktionary_senses
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

    fetched = [0]

    def resolve(base: str, depth: int, seen: set) -> list[dict]:
        if not base or depth > 3 or base in seen:
            return []
        seen.add(base)
        if substantive.get(base):                                  # 1. our own dictionary
            return substantive[base][:_MAX_GRAFT]
        defs = all_defs.get(base)
        if defs and all(is_ref(d) for d in defs):                  # 2. base is itself a reference -> chain
            return resolve(base_of(defs[0]), depth + 1, seen)
        ws = wn_senses(base)                                       # 3. WordNet
        if ws:
            return ws[:_MAX_GRAFT]
        wc = [s for s in wik.get(base, []) if not is_ref(s.get("definition", ""))]  # 4. Wiktionary cache
        if wc:
            return wc[:_MAX_GRAFT]
        if args.fetch and base not in wik:                         # 5. graceful fetch
            from fill_gaps_wiktionary import wiktionary_senses
            ss = wiktionary_senses(base, session, wik)
            fetched[0] += 1
            if fetched[0] % 25 == 0:
                pathlib.Path(args.wiktionary_cache).write_text(json.dumps(wik))
            time.sleep(args.delay)
            wc = [s for s in (ss or []) if not is_ref(s.get("definition", ""))]
            if wc:
                return wc[:_MAX_GRAFT]
        return []

    # which words are reference-only dead-ends?
    dead = [w for w, defs in all_defs.items()
            if (dd := [d for d in defs if d.strip()]) and all(is_ref(d) for d in dd)]
    grafts: dict[str, list[dict]] = {}
    for w in dead:
        senses = resolve(base_of(all_defs[w][0]), 0, {w})
        if senses:
            grafts[w] = senses
    if args.fetch:
        pathlib.Path(args.wiktionary_cache).write_text(json.dumps(wik))

    print(f"reference-only entries: {len(dead)}   resolved: {len(grafts)}   still dead: {len(dead) - len(grafts)}"
          + (f"   (network fetches: {fetched[0]})" if args.fetch else ""))

    if not args.apply:
        for w in sorted(grafts)[:12]:
            print(f"  {w}: {all_defs[w][0][:40]}  ->  {grafts[w][0]['definition'][:48]}")
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
    print(f"grafted {added} base-meaning sense(s) into {len(grafts)} entries")


if __name__ == "__main__":
    main()
