#!/usr/bin/env python3
"""Build the Russian ('russian') word pack — Phase 1 (playable, no definitions yet).

Russian can't use the English chain (WordNet + English dictionary API), so this is
a self-contained, lighter build from three public sources:

  * frequency  — hermitdave/FrequencyWords ru_50k (OpenSubtitles): ranks words so
                 ANSWERS are common and tiers are meaningful.
  * valid dict — mediahope/Wordle-Russian-Dictionary: the set of real 5-letter
                 words a player may GUESS (includes inflected forms).
  * comprehensive — danakt/russian-words (cp1251): extra guess coverage.

Proper nouns are excluded by the morphological analyzer (pymorphy: Surn/Name/Patr/
Geox grammemes + is_known), NOT by danakt's surname file — that file is far too
broad (24k five-letter entries) and wrongly lists common nouns like песня, книга,
школа, кость as "surnames", which would delete them from the game entirely.

Conventions (see the yawop pipeline README): ё is folded to е everywhere (32-key
board), words are lowercased, 5 Cyrillic letters only.

BASE FORMS ONLY: we keep only dictionary headwords, no inflected forms — nouns in
the nominative singular, base (masc. nom. sg.) adjectives, and verbs ONLY as the
infinitive (никаких склонений/спряжений). This needs a Russian morphological
analyzer at BUILD TIME only (never shipped in the APK):

    pip install pymorphy3 pymorphy3-dicts-ru
    # (isolated, no venv:  pip install --break-system-packages --target=LIB ...  then PYTHONPATH=LIB)

Outputs under assets/dictionaries/russian/:
  * allowed_guesses.txt — every base-form 5-letter word (per-pack guess validator)
  * tiers.json          — ANSWERS = frequency-ranked base forms, split easy/med/hard
  * dictionary.jsonl    — one {word, senses:[]} line per answer (registers the pack;
                          lookups gracefully show 'no definition' until Phase 2)

Run:  python3 scripts/build_russian.py [--easy 0.15 --medium 0.40]
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import letter_blend_order  # noqa: E402

FREQ_URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/ru/ru_50k.txt"
VALID_URL = "https://raw.githubusercontent.com/mediahope/Wordle-Russian-Dictionary/main/Russian.txt"
DANAKT_URL = "https://raw.githubusercontent.com/danakt/russian-words/master/russian.txt"
# Canonical Lyashevskaya & Sharov RNC frequency dictionary (genre-balanced: fiction +
# news + non-fiction, 92M tokens). Modern surface lemmas (огонь, not the stem огнь that
# Sharoff's reprocessed list uses), with per-million frequencies -> the daily difficulty base.
RNC_ZIP_URL = "http://dict.ruslang.ru/Freq2011.zip"

FIVE = re.compile(r"^[а-я]{5}$")  # ё already folded to е, so the alphabet is а-я


def fold(w: str) -> str:
    return w.strip().lower().replace("ё", "е")


def get(url: str, encoding: str = "utf-8") -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 yawop"})
    return urllib.request.urlopen(req, timeout=90).read().decode(encoding, "replace")


def subtitle_ipm(text: str) -> dict[str, float]:
    """5-letter word -> instances-per-million from the OpenSubtitles frequency file.
    ipm (not raw count) so it blends on the same scale as the RNC dictionary."""
    counts: dict[str, float] = {}
    total = 0
    for line in text.splitlines():
        p = line.split()
        if len(p) == 2 and p[1].isdigit():
            total += int(p[1])
            w = fold(p[0])
            if FIVE.match(w):
                counts[w] = counts.get(w, 0.0) + int(p[1])
    return {w: c / total * 1e6 for w, c in counts.items()} if total else {}


def rnc_ipm() -> dict[str, float]:
    """5-letter lemma -> ipm from the canonical RNC frequency dictionary (summed over
    parts of speech). Fetched as a zip; reads freqrnc2011.csv (Lemma, PoS, Freq(ipm), ...)."""
    req = urllib.request.Request(RNC_ZIP_URL, headers={"User-Agent": "Mozilla/5.0 yawop"})
    data = urllib.request.urlopen(req, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        csv = z.read("freqrnc2011.csv").decode("utf-8", "replace")
    out: dict[str, float] = {}
    for line in csv.splitlines():
        p = line.split("\t")
        if len(p) < 3 or p[0] == "Lemma":
            continue
        w = fold(p[0])
        if FIVE.match(w):
            try:
                out[w] = out.get(w, 0.0) + float(p[2])
            except ValueError:
                pass
    return out


def five_letter_set(text: str) -> set[str]:
    return {w for w in (fold(t) for t in re.split(r"[\s,]+", text)) if FIVE.match(w)}


def five_letter_ranked(text: str) -> list[str]:
    """Frequency file is 'word count' per line, already sorted most-frequent first."""
    out, seen = [], set()
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        w = fold(parts[0])
        if FIVE.match(w) and w not in seen:
            seen.add(w)
            out.append(w)
    return out


# Base-form gate: keep only dictionary headwords. Verbs kept as INFINITIVE (INFN)
# only, so no conjugated forms. Proper nouns excluded. Words here are ё-folded, but
# pymorphy's dictionary uses ё, so we compare FOLDED lemmas (else актёр->актер dies).
_KEEP_POS = {"NOUN", "ADJF", "INFN"}
_PROPER = {"Name", "Surn", "Patr", "Geox"}


def _make_morph_predicates():
    try:
        import pymorphy3
    except ImportError as e:
        raise SystemExit(
            "build_russian needs a Russian morphological analyzer (build-time only):\n"
            "  pip install pymorphy3 pymorphy3-dicts-ru\n"
            "  # or isolated: pip install --break-system-packages --target=LIB pymorphy3 "
            "pymorphy3-dicts-ru  (then run with PYTHONPATH=LIB)") from e
    morph = pymorphy3.MorphAnalyzer()

    def is_base_form(w: str) -> bool:
        for p in morph.parse(w):
            if not p.is_known:                          # real dictionary word, not a guess
                continue                                # (drops many transliterated names)
            if p.normal_form.replace("ё", "е") != w:    # must itself be the base form
                continue
            if p.tag.POS not in _KEEP_POS:              # noun / adjective / infinitive
                continue
            if _PROPER & set(p.tag.grammemes):          # no proper nouns pymorphy recognizes
                continue
            return True
        return False

    def is_known(w: str) -> bool:
        """True if pymorphy recognizes w as a real Russian wordform (any form/POS).
        Used to keep the guess list to real words, dropping subtitle/danakt junk
        (ааааа, foreign names, typos) that aren't in the curated dictionary either."""
        return any(p.is_known for p in morph.parse(w))

    def is_verb_past_dominant(w: str) -> bool:
        """True if the word reads most naturally as a masculine-singular PAST-TENSE verb
        (погиб='perished', надел='put on', выпал='fell out') rather than the rare noun it
        also happens to spell. These are homograph traps: the frequency that tiers them
        comes from the common verb, but the only base-form reason they're kept is an
        archaic/technical noun (погиб='изгиб'). Demote them from ANSWERS (still valid
        guesses). Rule: the summed score of masc-sg-past parses >= the best noun parse."""
        ps = morph.parse(w)
        past = sum(p.score for p in ps
                   if p.tag.POS == "VERB" and {"past", "masc", "sing"} <= set(p.tag.grammemes))
        noun = max([p.score for p in ps if p.tag.POS == "NOUN"] + [0.0])
        return past > 0 and past >= noun

    def is_proper_only(w: str) -> bool:
        """True if every known reading of w is a proper noun (name/surname/patronymic/
        toponym): аарон, айова, бетси. Dropped from guesses -- a word game shouldn't
        accept names -- unless the curated dict lists it or it's an answer."""
        ps = [p for p in morph.parse(w) if p.is_known]
        return bool(ps) and all(_PROPER & set(p.tag.grammemes) for p in ps)

    def is_smuggled_plural(w: str) -> bool:
        """True if w is ONLY a 5-letter word by virtue of pluralising a <=4-letter word
        (стол->столы, факт->факты): every known reading is a plural whose lemma is shorter
        than 5 letters. Disallowed as a guess so you can't probe 4-letter words through a
        plural ending. Genuine 5-letter plurals (книги<-книга, 5 letters) are kept, as is
        any word with a standalone 5-letter reading."""
        ps = [p for p in morph.parse(w) if p.is_known]
        return bool(ps) and all("plur" in p.tag and len(p.normal_form.replace("ё", "е")) < 5 for p in ps)

    return is_base_form, is_verb_past_dominant, is_known, is_proper_only, is_smuggled_plural


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", default=str(Path(__file__).resolve().parents[2] / "assets" / "dictionaries"))
    ap.add_argument("--easy", type=float, default=0.15)
    ap.add_argument("--medium", type=float, default=0.40)
    ap.add_argument("--min-ipm", type=float, default=0.0,
                    help="optional either-corpus floor: drop answers below this ipm in BOTH RNC and "
                         "subtitles. Default 0 (keep every real word; rare legit words like коала/фарси "
                         "just land in hard). Eligibility already removes non-words/names.")
    args = ap.parse_args()

    print("fetching frequency (OpenSubtitles)...", file=sys.stderr)
    sub_text = get(FREQ_URL)
    sub_ipm = subtitle_ipm(sub_text)
    print("fetching curated valid dictionary (mediahope)...", file=sys.stderr)
    valid = five_letter_set(get(VALID_URL))
    print("fetching comprehensive dictionary (danakt, cp1251)...", file=sys.stderr)
    comprehensive = five_letter_set(get(DANAKT_URL, "cp1251"))
    print("fetching balanced frequency dictionary (RNC, Lyashevskaya-Sharov)...", file=sys.stderr)
    rnc = rnc_ipm()

    print("filtering to base forms (pymorphy3: nouns/adjectives + verb infinitives only)...", file=sys.stderr)
    is_base_form, is_verb_past_dominant, is_known, is_proper_only, is_smuggled_plural = _make_morph_predicates()
    candidates = set(sub_ipm) | valid | comprehensive | set(rnc)
    base_forms = {w for w in candidates if is_base_form(w)}

    # Answers: base-form headwords that appear in EITHER corpus, ranked by a blended
    # frequency = geometric mean of RNC ipm and subtitle ipm (both per-million, so the
    # scales match). A word missing from one corpus gets a FLOOR there (half the rarest
    # ipm that corpus recorded), NOT zero: absence from the balanced/older corpus lowers
    # a word mildly instead of dumping it to the bottom or being ignored entirely. Every
    # real word stays a candidate -- rare legit words (коала, фарси) just rank into hard;
    # eligibility (enrich_russian) removes non-words/names. Then demote masc-past verb-form
    # homograph traps and letter-blend so difficulty tracks how hard the word is to SOLVE.
    pool = [w for w in base_forms if w in rnc or w in sub_ipm]
    if args.min_ipm > 0:
        pool = [w for w in pool if rnc.get(w, 0.0) >= args.min_ipm or sub_ipm.get(w, 0.0) >= args.min_ipm]
    verb_traps = sorted(w for w in pool if is_verb_past_dominant(w))
    pool = [w for w in pool if w not in set(verb_traps)]
    floor_rnc = min((rnc[w] for w in pool if w in rnc), default=1.0) / 2
    floor_sub = min((sub_ipm[w] for w in pool if w in sub_ipm), default=1.0) / 2

    def blended(w: str) -> float:
        return math.sqrt(rnc.get(w, floor_rnc) * sub_ipm.get(w, floor_sub))

    answers = letter_blend_order(sorted(pool, key=blended, reverse=True))
    print(f"  demoted {len(verb_traps)} masc-past verb-form traps from answers: {' '.join(verb_traps)}",
          file=sys.stderr)

    # Guesses: every REAL common 5-letter word = a pymorphy-known wordform that is NOT a
    # proper noun, plus the answers. We do NOT trust the raw dictionaries here: mediahope
    # and danakt are riddled with junk pymorphy rejects -- truncated fragments (вокру,
    # упорн, зажгл), typos (ааааа), and names/toponyms (иван, дубай, таити). Smuggled
    # plurals of <=4-letter words (столы, факты) are disallowed; answers are always kept.
    answer_set = set(answers)
    allowed = sorted(w for w in candidates
                     if (w in answer_set or (is_known(w) and not is_proper_only(w)))
                     and (w in answer_set or not is_smuggled_plural(w)))

    n = len(answers)
    easy_end, medium_end = round(n * args.easy), round(n * args.medium)
    tiers = {"easy": answers[:easy_end], "medium": answers[easy_end:medium_end], "hard": answers[medium_end:]}

    out = Path(args.assets) / "russian"
    out.mkdir(parents=True, exist_ok=True)
    (out / "allowed_guesses.txt").write_text("\n".join(allowed) + "\n", encoding="utf-8")
    # Dictionary headwords to define/eligibility-check in Phase 2 (bounded, unlike the
    # full guess list): the base forms. enrich_russian reads this, not allowed_guesses.
    (out / "base_forms.txt").write_text("\n".join(sorted(base_forms)) + "\n", encoding="utf-8")
    (out / "tiers.json").write_text(json.dumps(
        {"boundaries": {"easy_fraction": args.easy, "medium_fraction": args.medium, "total": n},
         "counts": {k: len(v) for k, v in tiers.items()}, "tiers": tiers},
        ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "dictionary.jsonl").open("w", encoding="utf-8") as f:
        for w in sorted(base_forms):  # minimal entries: register the pack; defs come in Phase 2
            f.write(json.dumps({"word": w, "senses": []}, ensure_ascii=False) + "\n")

    print(f"russian: guesses={len(allowed)}  base_forms={len(base_forms)}  answers={n} "
          f"(easy {len(tiers['easy'])}, medium {len(tiers['medium'])}, hard {len(tiers['hard'])})",
          file=sys.stderr)
    print(f"  wrote {out}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
