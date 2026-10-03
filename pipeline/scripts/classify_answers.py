#!/usr/bin/env python3
"""Rule-based answer-eligibility classifier (metadata-driven, no hand-lists).

Decides, from definition METADATA alone, which answer-pool words may be served as
puzzle SOLUTIONS. Everything stays a valid guess with its definition regardless;
this only touches answer-eligibility. Reads the published assets, WordNet, and a
committed Wiktionary raw-response cache, and writes two lists:

  --out-names    proper-noun / reference-only words. Removed from ANSWER sources
                 (tiers.json, *words.txt) at build time, UNCONDITIONALLY (adult
                 mode never resurrects a name). Fed to apply_blocklist --solutions.

  --out-obscene  obscene-dominant/only words, UNION the curated obscene list.
                 This becomes the RUNTIME, mature-gated solution filter
                 (blocklist_solutions.txt): hidden from answers by default, served
                 only when the player opts into adult mode (random games only).

The rule -- a word is ANSWER-ELIGIBLE iff it has >=1 sense that is:
  1. not a proper noun     (WordNet instance_hypernyms, or Wiktionary POS "proper noun")
  2. not a mere reference  ("(alt/obsolete) spelling/form of X", "plural of", "misspelling
                            of", "clipping of", "letter-case form of X", ...)
  3. clean-dominant        its best clean sense strictly outranks its best obscene sense
                           by WordNet lemma frequency. TIES (incl. 0/0) -> obscene wins.
Not eligible + has an obscene sense  -> obscene (mature-gated).
Not eligible + only proper/reference -> name    (removed from answers).

Curated obscene entries always win (the one sanctioned hand-list, for the rare
connotation-only tail WordNet can't tag: e.g. 'twat'='fool', 'cunt'='despicable person').
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re

from nltk.corpus import wordnet as wn

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
# A definition marks the WORD ITSELF as obscene only when it frames it as an
# offensive/obscene TERM/word/phrase/slur -- e.g. "obscene terms for penis",
# "offensive term for a lesbian", "an offensive or indecent word or phrase". A bare
# mention of offensiveness ("offensive line", "highly offensive", "rude or vulgar
# fool") describes the referent, not the word, and must NOT match.
OBSCENE = re.compile(
    r"\b(obscene|vulgar|offensive|indecent|derogatory|disparaging|insulting|profane)\b"
    r"[\w\s,]{0,24}?\b(terms?|words?|phrases?|expressions?|slurs?|names?)\b"
    r"|\b(ethnic|racial)\s+slurs?\b|\bterms?\s+of\s+(abuse|contempt)\b", re.I)
# Degenerate "reference" senses that point at another word rather than carry meaning.
REFERENCE = re.compile(
    r"\b(alternative|obsolete|archaic|dated|nonstandard|informal|eye|superseded|dialectal|common|rare)?\s*"
    r"(spelling|form|letter[- ]case form|letter case)\s+of\b"
    r"|\b(misspelling|plural|clipping|abbreviation|initialism|acronym|synonym|inflection|"
    r"genitive|comparative|superlative|present participle|past tense|past participle|gerund)\s+of\b"
    r"|\bof\s+the\s+ICAO\b", re.I)


def clean_html(h: str) -> str:
    return _WS.sub(" ", _TAGS.sub("", h)).strip()


def lemma_freq(syn, word: str) -> int:
    return max([l.count() for l in syn.lemmas() if l.name().lower() == word] or [0])


_MAX_SIDE = 2  # how many rescued side senses to graft onto an entry


def wiktionary_side(word: str, cache: dict) -> tuple[list[dict], bool, bool]:
    """From the Wiktionary raw cache, return (genuine_senses, saw_obscene, had_english).
    genuine_senses are non-proper, non-reference, non-obscene English senses (the
    'learnable side meanings'); saw_obscene if the only non-proper senses were obscene;
    had_english if there was any English data at all (to tell 'name' from 'unknown')."""
    en = (cache.get(word) or {}).get("en")
    if not isinstance(en, list):
        return ([], False, False)
    senses, saw_obscene = [], False
    for group in en:
        pos = (group.get("partOfSpeech") or "").strip().lower()
        if pos in ("proper noun", "name"):
            continue
        for d in group.get("definitions", []):
            t = clean_html(d.get("definition", ""))
            if not t or REFERENCE.search(t):
                continue
            if OBSCENE.search(t):
                saw_obscene = True
                continue
            senses.append({"pos_label": pos or "noun", "definition": t, "source": "wiktionary"})
    return (senses, saw_obscene, True)


def classify(word: str, cache: dict, curated: set[str]) -> tuple[str, list[dict]]:
    """Return (verdict, rescued_senses). verdict is 'eligible' | 'obscene' | 'name';
    rescued_senses is non-empty only when eligibility was rescued from Wiktionary (a
    proper-noun word kept alive by a real side meaning that must be grafted into its
    entry). A word is only 'name' with POSITIVE proper-noun evidence; absent any
    evidence it stays eligible (it was defined by some source; we never strip a guess)."""
    if word in curated:
        return ("obscene", [])
    syns = wn.synsets(word)
    clean = [s for s in syns if not s.instance_hypernyms() and not OBSCENE.search(s.definition())]
    obsc = [s for s in syns if OBSCENE.search(s.definition())]
    cf = max((lemma_freq(s, word) for s in clean), default=0)
    of = max((lemma_freq(s, word) for s in obsc), default=0)
    if clean and (not obsc or cf > of):   # WordNet-clean sense strictly outranks obscene
        return ("eligible", [])
    if obsc:                              # obscene present, clean doesn't dominate (ties included)
        return ("obscene", [])
    side, saw_obscene, had_en = wiktionary_side(word, cache)
    if side:                              # proper/unknown to WordNet, but a real side meaning exists
        return ("eligible", side[:_MAX_SIDE])
    if saw_obscene:
        return ("obscene", [])
    if syns or had_en:                    # WordNet instance-only, or Wiktionary proper/reference-only
        return ("name", [])
    return ("eligible", [])               # no evidence anywhere -> keep


def augment_dictionaries(assets: pathlib.Path, rescued: dict[str, list[dict]]) -> int:
    """Graft each rescued word's side senses into its record in every pack
    dictionary.jsonl, so the learnable meaning actually shows in the lookup."""
    added = 0
    for dj in assets.glob("*/dictionary.jsonl"):
        out, changed = [], False
        for ln in dj.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            rec = json.loads(ln)
            extra = rescued.get(rec["word"].lower())
            if extra:
                have = {(s.get("pos_label"), s.get("definition")) for s in rec.get("senses", [])}
                for s in extra:
                    if (s["pos_label"], s["definition"]) not in have:
                        rec.setdefault("senses", []).append(s)
                        have.add((s["pos_label"], s["definition"]))
                        added += 1
                        changed = True
            out.append(json.dumps(rec, ensure_ascii=False))
        if changed:
            dj.write_text("\n".join(out) + "\n", encoding="utf-8")
    return added


def answer_pool(assets: pathlib.Path) -> set[str]:
    words: set[str] = set()
    for pack in sorted(p for p in assets.iterdir() if p.is_dir()):
        tj = pack / "tiers.json"
        if tj.exists():
            for ws in json.loads(tj.read_text()).get("tiers", {}).values():
                words |= {w.lower() for w in ws}
        else:
            for name in ("puzzle_words.txt", "words.txt"):
                f = pack / name
                if f.exists():
                    words |= {ln.strip().lower() for ln in f.read_text().splitlines() if ln.strip()}
    return words


def load_words(path: pathlib.Path | None) -> set[str]:
    if not path or not path.exists():
        return set()
    return {ln.strip().lower() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--wiktionary-cache", required=True, help="raw Wiktionary responses (committed)")
    ap.add_argument("--curated-obscene", help="the one sanctioned hand-list of obscene words")
    ap.add_argument("--out-names", required=True)
    ap.add_argument("--out-obscene", required=True)
    ap.add_argument("--augment", metavar="ASSETS",
                    help="graft rescued side meanings into the pack dictionaries at this path")
    args = ap.parse_args()

    assets = pathlib.Path(args.assets)
    cache = json.loads(pathlib.Path(args.wiktionary_cache).read_text()) if pathlib.Path(args.wiktionary_cache).exists() else {}
    curated = load_words(pathlib.Path(args.curated_obscene) if args.curated_obscene else None)

    names, obscene, rescued = [], set(curated), {}
    for w in sorted(answer_pool(assets)):
        verdict, side = classify(w, cache, curated)
        if verdict == "name":
            names.append(w)
        elif verdict == "obscene":
            obscene.add(w)
        elif side:
            rescued[w] = side

    if args.augment:
        added = augment_dictionaries(pathlib.Path(args.augment), rescued)
        print(f"grafted {added} rescued side-sense(s) into {len(rescued)} entries")

    pathlib.Path(args.out_names).write_text("".join(w + "\n" for w in sorted(names)), encoding="utf-8")
    header = ("# Obscene solution filter (RUNTIME, mature-gated): valid guesses with\n"
              "# definitions, never a default answer; served only when adult mode is on\n"
              "# (random games only). Generated by classify_answers.py = curated UNION\n"
              "# WordNet-obscene-marked pool words. One lowercase word per line.\n")
    pathlib.Path(args.out_obscene).write_text(header + "".join(w + "\n" for w in sorted(obscene)), encoding="utf-8")
    print(f"answer pool classified: names(removed from answers)={len(names)}  "
          f"obscene(mature-gated)={len(obscene)} [{len(curated)} curated]")


if __name__ == "__main__":
    main()
