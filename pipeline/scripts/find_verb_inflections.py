#!/usr/bin/env python3
"""Find verb-inflection answers that have no life beyond being a verb form.

Real Wordle answers are base forms, not verb tenses. A word is an inflection-only
answer if a sense marks it a verb form (simple past / past participle / present
participle / third-person singular) AND it has NO independent noun/adjective sense.

This keeps words the language has lexicalized beyond the bare tense -- baked (an
adjective: "baked beans"), broke (penniless), stole (a shawl), spoke (a wheel part)
-- and drops the pure verb pasts: arose, awoke, chose, wrote, crept, slept, threw...
(also nonstandard forms like buyed/maked). The metadata does the work: a dictionary
records a noun/adjective sense only where the form genuinely took on that life.

Output is a plain word list for apply_blocklist --solutions (removed from ANSWERS
only; the words stay valid guesses with their definitions).

  python scripts/find_verb_inflections.py --assets <assets> --out verb_inflections.txt
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TIERS = ("easy", "medium", "hard")
VFORM = re.compile(r"\b(simple past|past participle|present participle|past tense|"
                   r"third[- ]person singular)\b", re.I)
FORMOF = re.compile(r"\b(simple past|past participle|present participle|past tense|"
                    r"third[- ]person singular|plural) of\b", re.I)


def _read_jsonl(path: Path):
    return [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    assets = Path(args.assets)

    # English answer words (Cyrillic packs handle inflections at build time already).
    packs = [p.parent.name for p in assets.glob("*/tiers.json")]
    answers, senses = set(), {}
    for pack in packs:
        td = json.loads((assets / pack / "tiers.json").read_text("utf-8"))
        for t in TIERS:
            answers.update(td["tiers"].get(t, []))
    for pack in packs:
        f = assets / pack / "dictionary.jsonl"
        if f.exists():
            for rec in _read_jsonl(f):
                w = rec["word"].lower()
                if w in answers:
                    senses.setdefault(w, set()).update(
                        (sn.get("pos_label", ""), sn.get("definition", "")) for sn in rec.get("senses", []))
    extra = assets / "extra_defs.jsonl"
    if extra.exists():
        for rec in _read_jsonl(extra):
            w = rec["word"].lower()
            if w in answers and w not in senses:
                senses.setdefault(w, set()).update(
                    (sn.get("pos_label", ""), sn.get("definition", "")) for sn in rec.get("senses", []))

    def is_inflection(w: str) -> bool:
        ss = senses.get(w, set())
        verb_form = any(p == "verb" and VFORM.search(d) for p, d in ss)
        other_life = any(p in ("noun", "adjective") and not FORMOF.search(d) for p, d in ss)
        return verb_form and not other_life

    out = sorted(w for w in senses if is_inflection(w))
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"verb-inflection answers (no noun/adj life): {len(out)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
