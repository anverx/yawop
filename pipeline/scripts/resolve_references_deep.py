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

Also grafts 'pertaining to X' adjectives ("seral: of or pertaining to a sere"): when EVERY
sense starts with a pertaining construct (the word has no meaning of its own, like the
'X of Y' references), X's first NOUN sense is inserted right after the first such sense
("(sere) a natural succession community..."). Noun senses come from their own cache
(wiktionary_nouns.json): the general cache keeps only the first few senses of each word, which for
sere are all the adjective 'dry' -- exactly the wrong meaning here.

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

# "of or pertaining to X", "relating to X", "of, relating to, or caused by X", ...
_PERTAIN = re.compile(r"^\s*(?:of\s*,?\s*)?(?:or\s+)?(?:pertaining|appertaining|relating|related|"
                      r"belonging|referring|connected)\s+(?:to|with)\b(.*)", re.I)
# Words skipped while looking for X ("of or relating to or produced by or being a gene").
_PERTAIN_SKIP = {"a", "an", "the", "or", "and", "to", "by", "from", "with", "of", "like", "in", "on",
                 "any", "some", "one", "its", "their", "his", "her", "many", "various", "certain",
                 "all", "such", "characteristic", "similar", "containing", "involving", "having",
                 "using", "causing", "designed", "derived", "produced", "resembling", "consisting",
                 "located", "situated", "occurring", "used", "suitable", "near", "for", "at"}
# Head nouns that carry no meaning of their own: "a kind of Y" -> Y. Without a following
# 'of' ("a racial group having...", "the genus Bos") there is nothing safe to graft.
_PERTAIN_HEADS = {"kind", "type", "sort", "form", "variety", "class", "genus", "family", "species",
                  "group", "member", "part", "style", "manner", "characteristic"}


def _pertain_bases(defn: str) -> list[str]:
    """Candidate X's for a 'pertaining to X' sense, best first: the head (last word) of each
    noun phrase after the construct, alternatives joined by or/and following."""
    m = _PERTAIN.match(defn)
    if not m:
        return []
    raw = re.findall(r"[A-Za-z][A-Za-z'\-]*|[^\sA-Za-z]", m.group(1))
    toks = [t.lower() for t in raw]

    def connective(i: int) -> bool:
        t = toks[i]
        if t in _PERTAIN_SKIP or not t[0].isalpha():
            return True
        # a participle leading into more words ("having many pines", "supporting Hinduism");
        # phrase-final it is the noun itself ("caused by burning.")
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        return t.endswith(("ing", "ed")) and nxt[:1].isalpha() and nxt not in ("or", "and")

    out, i = [], 0
    while i < len(toks):
        if connective(i):
            if not toks[i][0].isalpha() and toks[i] not in (",",) and out:
                break  # sentence/clause punctuation ends the alternatives
            i += 1
            continue
        j = i
        while j < len(toks) and not connective(j):
            j += 1
        phrase, nxt = toks[i:j], (toks[j] if j < len(toks) else "")
        if any(set(_singulars(t)) & _PERTAIN_HEADS for t in phrase):
            if nxt != "of":
                break
            i = j + 1
            continue
        if raw[j - 1][:1].isupper():
            break  # a proper noun (the Netherlands, Java): its page is the wrong meaning
        if len(phrase) > 1:  # a term first ("dura mater", "mucic acid"), then its head
            out.append(" ".join(phrase))
        out.append(phrase[-1].strip("'-"))
        i = j
    return out


def _singulars(word: str) -> list[str]:
    """word itself, then plausible singulars (kidneys -> kidney, pores -> pore, bodies -> body,
    setae -> seta). For a multi-word term only its last word is singularized."""
    if " " in word:
        head, last = word.rsplit(" ", 1)
        return [f"{head} {s}" for s in _singulars(last)]
    if word.endswith("ae"):  # Latin plural: the singular's page is the real one (zoeae -> zoea)
        return [word[:-1]]
    out = [word]
    if word.endswith("ies"):
        out.append(word[:-3] + "y")
    if word.endswith("s") and not word.endswith("ss"):
        out.append(word[:-1])
    if word.endswith("es"):
        out.append(word[:-2])
    return out


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
    nouns_path = Path(args.cache).with_name("wiktionary_nouns.json")
    nouns_cache = json.loads(nouns_path.read_text("utf-8")) if nouns_path.exists() else {}

    def noun_sense(word: str) -> dict | None:
        """First English NOUN sense of word (uncapped, unlike the general cache)."""
        if word not in nouns_cache and not args.no_fetch:
            try:
                resp = session.get(fg.REST_URL.format(word=word), timeout=20)
                data = resp.json() if resp.status_code == 200 else {}
            except (requests.RequestException, ValueError):
                return None  # transient: not cached, retried next run
            found = None
            for group in data.get("en", []) if isinstance(data, dict) else []:
                if (group.get("partOfSpeech") or "").lower() != "noun":
                    continue
                text = next((t for t in (fg.clean(d.get("definition", "")) for d in group.get("definitions", []))
                             if t and not fg.is_junk(t)), None)
                if text:
                    found = {"pos_label": "noun", "definition": text, "source": "wiktionary"}
                    break
            nouns_cache[word] = found
            time.sleep(0.3)
        return nouns_cache.get(word)

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
    resolved = pertained = 0
    for f in files:
        if not f.exists():
            continue
        recs = [json.loads(ln) for ln in f.read_text("utf-8").splitlines() if ln.strip()]
        for rec in recs:
            ss = rec.get("senses", [])
            # 'pertaining to X' only (no meaning of its own) -> insert X's noun meaning after
            # the first such sense.
            cands = [b for x in _pertain_bases(ss[0].get("definition", "")) if x != rec["word"].lower()
                     for b in _singulars(x)] if ss else []
            grafted = lambda d: any(d.startswith(f"({b}) ") for b in cands)  # noqa: E731
            if cands and all(_PERTAIN.match(sn.get("definition", "")) or grafted(sn.get("definition", ""))
                             for sn in ss) and not any(grafted(sn.get("definition", "")) for sn in ss):
                got = next(((b, n) for b in cands
                            if (n := noun_sense(b)) and not _is_ref(n["definition"])), None)
                if got:
                    ss.insert(1, dict(got[1], definition=f"({got[0]}) {got[1]['definition']}"))
                    pertained += 1
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
        print(f"  {f.parent.name}/{f.name}: resolved {resolved}, pertaining {pertained} so far", file=sys.stderr)

    nouns_path.write_text(json.dumps(nouns_cache, ensure_ascii=False, sort_keys=True), encoding="utf-8")
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
