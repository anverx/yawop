"""Look up a word's entry across the shipped packs.

Runtime game logic (not part of the build pipeline). Reads assets/dictionaries/.

    from worddata import lookup_entry
    lookup_entry("quoth")   # -> {word, senses, examples, gutenberg_search_url, packs}

CLI:  python -m worddata.lookup quoth [--pack subtlex-us] [--json] [--no-color]
"""

from __future__ import annotations

import argparse
import json
import sys

from . import store

BOLD, DIM, ITAL, RESET = "\033[1m", "\033[2m", "\033[3m", "\033[0m"


def _sense_key(s: dict) -> tuple:
    return (s.get("pos_label"), s.get("definition"))


def lookup_entry(word: str, pack: str | None = None) -> dict | None:
    """Merged entry for a word across packs, or None if absent."""
    word = word.strip().lower()
    senses: list[dict] = []
    seen: set[tuple] = set()
    examples: list[dict] = []
    gutenberg_url = None
    found_in: list[dict] = []

    for name in store.packs():
        if pack and name != pack:
            continue
        for rec in store.read_jsonl(store.ASSETS / name / "dictionary.jsonl"):
            if rec["word"].lower() != word:
                continue
            found_in.append({"pack": name, "tier": store.tier_of(name, word)})
            for s in rec.get("senses", []):
                if _sense_key(s) not in seen:
                    seen.add(_sense_key(s))
                    senses.append(s)
            for ex in rec.get("examples", []):
                if ex not in examples:
                    examples.append(ex)
            gutenberg_url = rec.get("gutenberg_search_url", gutenberg_url)
            break

    if not found_in:
        return None
    return {"word": word, "senses": senses, "examples": examples,
            "gutenberg_search_url": gutenberg_url, "packs": found_in}


def format_entry(entry: dict, color: bool = True) -> str:
    b, d, i, r = (BOLD, DIM, ITAL, RESET) if color else ("", "", "", "")
    out = [f"\n{b}{entry['word'].upper()}{r}"]
    labels = [p["pack"] + (f" ({p['tier']})" if p["tier"] else "") for p in entry["packs"]]
    packs_str = ", ".join(labels)
    out.append(f"{d}in packs: {packs_str}{r}\n")

    if entry["senses"]:
        out.append(f"{b}Definitions{r}")
        for s in entry["senses"]:
            src = f" {d}[{s.get('source')}]{r}" if s.get("source") else ""
            out.append(f"  {i}{s.get('pos_label','')}{r}  {s.get('definition','')}{src}")
    else:
        out.append(f"{d}(no definition available){r}")

    if entry["examples"]:
        out.append(f"\n{b}Usage{r}")
        for ex in entry["examples"]:
            who = " — ".join(x for x in (ex.get("author"), ex.get("work")) if x)
            out.append(f"  {i}“{ex.get('text','')}”{r}")
            if who:
                out.append(f"    {d}{who}{r}")
            if ex.get("url"):
                out.append(f"    {d}{ex['url']}{r}")

    if entry.get("gutenberg_search_url"):
        out.append(f"\n{b}Explore in Project Gutenberg{r}\n  {entry['gutenberg_search_url']}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Look up a word's dictionary entry.")
    ap.add_argument("word")
    ap.add_argument("--pack", help="restrict to a single pack")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    entry = lookup_entry(args.word, args.pack)
    if entry is None:
        where = f" in pack '{args.pack}'" if args.pack else " in any pack"
        print(f"'{args.word.strip().lower()}' not found{where}.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
    else:
        print(format_entry(entry, color=not args.no_color and sys.stdout.isatty()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
