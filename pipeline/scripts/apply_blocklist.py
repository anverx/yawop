#!/usr/bin/env python3
"""Purge blocklisted words from the shipped dictionary assets.

Two scopes, run after publishing the packs:

  --slurs FILE      Removed EVERYWHERE: answer sources (tiers.json, words.txt,
                    puzzle_words.txt), the lookup dictionary (dictionary.jsonl),
                    and the guess validator (allowed_guesses_all.txt). The word
                    ceases to exist in the game.

  --solutions FILE  Removed from ANSWER SOURCES ONLY (tiers.json, words.txt,
                    puzzle_words.txt). Kept in dictionary.jsonl and
                    allowed_guesses_all.txt, so these real-but-vulgar words stay
                    valid guesses (with working definitions) yet are never served
                    as a puzzle solution.

Idempotent: re-running on already-clean assets removes nothing. Reports what it
stripped so a rebuild's effect is visible.
"""
from __future__ import annotations

import argparse
import json
import pathlib


def load_blocklist(path: pathlib.Path | None) -> set[str]:
    if path is None:
        return set()
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.lower())
    return words


def _strip_lines(path: pathlib.Path, block: set[str]) -> int:
    if not path.exists() or not block:
        return 0
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    kept = [ln for ln in lines if ln.strip().lower() not in block]
    if len(kept) != len(lines):
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return len(lines) - len(kept)


def _strip_jsonl(path: pathlib.Path, block: set[str]) -> int:
    if not path.exists() or not block:
        return 0
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    kept = [ln for ln in lines if json.loads(ln)["word"].lower() not in block]
    if len(kept) != len(lines):
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return len(lines) - len(kept)


def _strip_tiers(path: pathlib.Path, block: set[str]) -> int:
    if not path.exists() or not block:
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    tiers = data.get("tiers", {})
    removed = 0
    for tier, words in tiers.items():
        kept = [w for w in words if w.lower() not in block]
        removed += len(words) - len(kept)
        tiers[tier] = kept
    if removed:
        if "counts" in data:
            data["counts"] = {t: len(tiers.get(t, [])) for t in data["counts"]}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return removed


def _strip_answer_sources(pack_dir: pathlib.Path, block: set[str]) -> int:
    """Remove from every place a word could be drawn as a puzzle solution."""
    return (_strip_tiers(pack_dir / "tiers.json", block)
            + _strip_lines(pack_dir / "words.txt", block)
            + _strip_lines(pack_dir / "puzzle_words.txt", block))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", required=True, help="dictionaries assets dir")
    ap.add_argument("--slurs", help="blocklist removed everywhere")
    ap.add_argument("--solutions", help="blocklist removed from answer sources only")
    args = ap.parse_args()

    assets = pathlib.Path(args.assets)
    slurs = load_blocklist(pathlib.Path(args.slurs) if args.slurs else None)
    solutions = load_blocklist(pathlib.Path(args.solutions) if args.solutions else None)
    if not slurs and not solutions:
        print("both blocklists empty; nothing to do")
        return

    total = 0
    for pack_dir in sorted(p for p in assets.iterdir() if p.is_dir()):
        n = _strip_answer_sources(pack_dir, slurs | solutions)  # both barred from answers
        n += _strip_jsonl(pack_dir / "dictionary.jsonl", slurs)  # only slurs lose lookups
        if n:
            print(f"  {pack_dir.name}: removed {n} occurrence(s)")
        total += n
    n = _strip_lines(assets / "allowed_guesses_all.txt", slurs)  # only slurs barred as guesses
    if n:
        print(f"  allowed_guesses_all.txt: removed {n}")
    total += n
    print(f"blocklist applied (slurs={len(slurs)}, solutions={len(solutions)}): "
          f"{total} occurrence(s) removed")


if __name__ == "__main__":
    main()
