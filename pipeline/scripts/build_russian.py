#!/usr/bin/env python3
"""Build the Russian ('russian') word pack — Phase 1 (playable, no definitions yet).

Russian can't use the English chain (WordNet + English dictionary API), so this is
a self-contained, lighter build from three public sources:

  * frequency  — hermitdave/FrequencyWords ru_50k (OpenSubtitles): ranks words so
                 ANSWERS are common and tiers are meaningful.
  * valid dict — mediahope/Wordle-Russian-Dictionary: the set of real 5-letter
                 words a player may GUESS (includes inflected forms).
  * comprehensive + surnames — danakt/russian-words (cp1251): extra guess coverage,
                 and a surname stoplist to keep proper nouns out of ANSWERS.

Conventions (see the yawop pipeline README): ё is folded to е everywhere (32-key
board), words are lowercased, 5 Cyrillic letters only.

Outputs under assets/dictionaries/russian/:
  * allowed_guesses.txt — union of all real 5-letter words (per-pack guess validator)
  * tiers.json          — ANSWERS = frequency-ranked ∩ valid − surnames, split easy/med/hard
  * dictionary.jsonl    — one {word, senses:[]} line per answer (registers the pack;
                          lookups gracefully show 'no definition' until Phase 2)

Run:  python3 scripts/build_russian.py [--easy 0.15 --medium 0.40]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

FREQ_URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/ru/ru_50k.txt"
VALID_URL = "https://raw.githubusercontent.com/mediahope/Wordle-Russian-Dictionary/main/Russian.txt"
DANAKT_URL = "https://raw.githubusercontent.com/danakt/russian-words/master/russian.txt"
SURNAMES_URL = "https://raw.githubusercontent.com/danakt/russian-words/master/russian_surnames.txt"

FIVE = re.compile(r"^[а-я]{5}$")  # ё already folded to е, so the alphabet is а-я


def fold(w: str) -> str:
    return w.strip().lower().replace("ё", "е")


def get(url: str, encoding: str = "utf-8") -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 yawop"})
    return urllib.request.urlopen(req, timeout=90).read().decode(encoding, "replace")


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", default=str(Path(__file__).resolve().parents[2] / "assets" / "dictionaries"))
    ap.add_argument("--easy", type=float, default=0.15)
    ap.add_argument("--medium", type=float, default=0.40)
    args = ap.parse_args()

    print("fetching frequency (OpenSubtitles)...", file=sys.stderr)
    freq_ranked = five_letter_ranked(get(FREQ_URL))
    print("fetching curated valid dictionary (mediahope)...", file=sys.stderr)
    valid = five_letter_set(get(VALID_URL))
    print("fetching comprehensive dictionary + surnames (danakt, cp1251)...", file=sys.stderr)
    comprehensive = five_letter_set(get(DANAKT_URL, "cp1251"))
    surnames = five_letter_set(get(SURNAMES_URL, "cp1251"))

    freq_set = set(freq_ranked)
    allowed = sorted(freq_set | valid | comprehensive)

    # Answers: frequency order (common first), must be a real valid word, not a surname.
    answers = [w for w in freq_ranked if w in valid and w not in surnames]

    n = len(answers)
    easy_end, medium_end = round(n * args.easy), round(n * args.medium)
    tiers = {"easy": answers[:easy_end], "medium": answers[easy_end:medium_end], "hard": answers[medium_end:]}

    out = Path(args.assets) / "russian"
    out.mkdir(parents=True, exist_ok=True)
    (out / "allowed_guesses.txt").write_text("\n".join(allowed) + "\n", encoding="utf-8")
    (out / "tiers.json").write_text(json.dumps(
        {"boundaries": {"easy_fraction": args.easy, "medium_fraction": args.medium, "total": n},
         "counts": {k: len(v) for k, v in tiers.items()}, "tiers": tiers},
        ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "dictionary.jsonl").open("w", encoding="utf-8") as f:
        for w in answers:  # minimal entries: register the pack; definitions come in Phase 2
            f.write(json.dumps({"word": w, "senses": []}, ensure_ascii=False) + "\n")

    print(f"russian: allowed={len(allowed)}  answers={n} "
          f"(easy {len(tiers['easy'])}, medium {len(tiers['medium'])}, hard {len(tiers['hard'])})",
          file=sys.stderr)
    print(f"  wrote {out}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
