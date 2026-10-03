#!/usr/bin/env python3
"""Resolve bare 'X of Y' reference definitions into real meanings.

Many entries define a word only by pointing elsewhere -- "cepes: plural of cepe",
"cepe: alternative form of cep" -- so the '?' popup never says what it means. The
base word is often sub-5-letter (cep) or itself another reference (cepe -> cep), so
it was never in our data and resolve_references had nothing to graft.

This follows the chain (multi-hop), fetches the base word's real definition from
English Wiktionary when needed (cached in the committed wiktionary_defs.json, so
rebuilds are offline), and APPENDS the resolved meaning as an extra sense -- keeping
the reference for context: "plural of cepe" + "(cep) an edible bolete mushroom".

Also emits --demote-out: reference answers that are PLURALS (cepes-like), to be made
guess-only (a plural shouldn't be served as a daily).

  python scripts/resolve_references_deep.py --assets <A> --cache data/cache/wiktionary_defs.json \
      --demote-out reference_plurals.txt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import USER_AGENT  # noqa: E402
import fill_gaps_wiktionary as fg  # noqa: E402

# "<kind> of <base>" — captures the base lemma.
_REF = re.compile(
    r"\b(plural|simple past|past participle|present participle|alternative form|"
    r"alternative spelling|obsolete form|obsolete spelling|misspelling|initialism|"
    r"abbreviation|third[- ]person singular|inflection|comparative|superlative|"
    r"diminutive)\b[^.]*?\bof\b\s+([a-z][a-z'\-]+)", re.I)
_PLURAL = re.compile(r"\bplural of\b", re.I)


def _base(defn: str) -> str | None:
    m = _REF.search(defn)
    return m.group(2).lower().strip(".'-") if m else None


def _is_ref(defn: str) -> bool:
    return bool(re.match(r"\s*(plural|simple past|past participle|present participle|"
                         r"alternative (form|spelling)|obsolete (form|spelling)|misspelling|"
                         r"initialism|abbreviation|third[- ]person singular|inflection|"
                         r"comparative|superlative|diminutive)\b.*\bof\b", defn, re.I))


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--cache", default=str(root / "pipeline" / "data" / "cache" / "wiktionary_defs.json"))
    ap.add_argument("--demote-out", default="reference_plurals.txt")
    ap.add_argument("--no-fetch", action="store_true", help="resolve only from cache, don't hit the network")
    args = ap.parse_args()
    assets = Path(args.assets)
    cache = json.loads(Path(args.cache).read_text("utf-8")) if Path(args.cache).exists() else {}
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    fetched = [0]

    def senses(word: str) -> list[dict]:
        if word not in cache and not args.no_fetch:
            fg.wiktionary_senses(word, session, cache)  # fills cache (black-hole)
            fetched[0] += 1
            if fetched[0] % 50 == 0:  # periodic save so a kill is resumable
                Path(args.cache).write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True), encoding="utf-8")
                print(f"  ...fetched {fetched[0]} bases (cache saved)", file=sys.stderr)
            time.sleep(0.3)
        return cache.get(word) or []

    def real_meaning(word: str, depth: int = 0) -> dict | None:
        """First non-reference sense, following 'X of Y' chains up to 3 hops."""
        if depth > 3:
            return None
        for sn in senses(word):
            d = sn.get("definition", "")
            if not d:
                continue
            if _is_ref(d):
                b = _base(d)
                if b and b != word:
                    got = real_meaning(b, depth + 1)
                    if got:
                        return got
            else:
                return sn
        return None

    files = [assets / p / "dictionary.jsonl" for p in ("subtlex-us", "subtlex-uk", "wordle", "arcane", "surprise")]
    files.append(assets / "extra_defs.jsonl")
    resolved = 0
    for f in files:
        if not f.exists():
            continue
        recs = [json.loads(ln) for ln in f.read_text("utf-8").splitlines() if ln.strip()]
        for rec in recs:
            ss = rec.get("senses", [])
            if not ss or not all(_is_ref(s.get("definition", "")) for s in ss):
                continue  # has a real sense already, or no senses
            base = next((_base(s["definition"]) for s in ss if _base(s.get("definition", ""))), None)
            if not base:
                continue
            got = real_meaning(base)
            if got and got.get("definition"):
                ss.append({"pos_label": got.get("pos_label", ""),
                           "definition": f"({base}) {got['definition']}", "source": "wiktionary"})
                resolved += 1
        with f.open("w", encoding="utf-8") as fh:
            for rec in recs:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  {f.parent.name}/{f.name}: resolved {resolved} so far", file=sys.stderr)

    Path(args.cache).write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    # Plural answers -> demote to guess-only (a plural isn't a good daily answer).
    sys.path.insert(0, str(root))
    import worddata.store as store  # local import; stdlib-only module
    demote = []
    for pack in ("subtlex-us", "subtlex-uk", "wordle", "arcane"):
        t = store.load_tiers(pack)
        ans = {w for k in store.TIER_ORDER for w in t.get(k, [])}
        f = assets / pack / "dictionary.jsonl"
        if not f.exists():
            continue
        for rec in (json.loads(ln) for ln in f.read_text("utf-8").splitlines() if ln.strip()):
            w = rec["word"].lower()
            ss = rec.get("senses", [])
            # PURE plural only: every sense is the 'plural of X' reference or its grafted
            # "(X) meaning". Words with an independent base sense (corgi, gules, specs,
            # neeps) keep answer status.
            pure_plural = bool(ss) and all(
                _PLURAL.search(s.get("definition", "")) or s.get("definition", "").strip().startswith("(")
                for s in ss) and any(_PLURAL.search(s.get("definition", "")) for s in ss)
            if w in ans and pure_plural:
                demote.append(w)
    demote = sorted(set(demote))
    Path(args.demote_out).write_text("\n".join(demote) + "\n", encoding="utf-8")
    print(f"resolved {resolved} reference entries; {len(demote)} plural answers to demote -> {args.demote_out}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
