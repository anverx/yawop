#!/usr/bin/env python3
"""Fill definitions for still-undefined allowed-guess words from Wiktionary.

Targets the obscure tail that no pack and WordNet cover. Uses Wiktionary's REST
definition endpoint, English senses only. Results are cached to a committed,
append-only cache (the "black hole": a word looked up once — found OR confirmed
absent — is never queried again; only transient errors retry).

  python scripts/fill_gaps_wiktionary.py --allowed <assets>/allowed_guesses_all.txt \
      --assets <assets> --cache data/cache/wiktionary.json [--limit 100] [--delay 1.0]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import USER_AGENT, load_cache, save_cache  # noqa: E402

REST_URL = "https://en.wiktionary.org/api/rest_v1/page/definition/{word}"
_MAX_SENSES = 3
_STYLE = re.compile(r"<style.*?</style>", re.S)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean(html: str) -> str:
    txt = _STYLE.sub("", html)
    txt = _TAGS.sub("", txt)
    txt = txt.replace("&quot;", '"').replace("&amp;", "&")
    return _WS.sub(" ", txt).strip()


# Many valid Wordle/Scrabble words only have a Wiktionary entry under another
# language (Scots especially: whaur=where, tauld=told). Prefer English, then Scots,
# then any language, labelling non-English senses so the popup stays honest.
LANG_NAMES = {"sco": "Scots", "la": "Latin", "fr": "French", "it": "Italian",
              "es": "Spanish", "de": "German", "nl": "Dutch", "ca": "Catalan",
              "cy": "Welsh", "ga": "Irish", "gd": "Scottish Gaelic", "gv": "Manx",
              "nrm": "Norman", "fur": "Friulian", "et": "Estonian", "tl": "Tagalog",
              "ceb": "Cebuano", "pt": "Portuguese", "ro": "Romanian", "sv": "Swedish",
              "da": "Danish", "no": "Norwegian", "fi": "Finnish", "pl": "Polish",
              "cs": "Czech", "hu": "Hungarian", "tr": "Turkish", "af": "Afrikaans"}


def extract_senses(data: dict) -> list[dict]:
    """Senses from the best available language: English, then Scots, then any."""
    if not isinstance(data, dict):
        return []
    langs = [L for L, v in data.items() if isinstance(v, list) and v]  # only language->[groups]
    pick = next((L for L in ("en", "sco") if L in langs), None) or (langs[0] if langs else None)
    if pick is None:
        return []
    senses, seen = [], set()
    for group in data[pick]:
        pos = (group.get("partOfSpeech") or "").lower()
        label = pos if pick == "en" else LANG_NAMES.get(pick, pick.upper())
        for d in group.get("definitions", []):
            text = clean(d.get("definition", ""))
            if not text or (label, text) in seen:
                continue
            seen.add((label, text))
            senses.append({"pos_label": label, "definition": text, "source": "wiktionary"})
            if len(senses) >= _MAX_SENSES:
                return senses
    return senses


def wiktionary_senses(word, session, cache, refetch_empty=False, max_retries=4, backoff=1.5):
    """Senses (best language), [] if no page (404), or None on transient error.
    [] and non-empty results are cached; None is never cached (retries later).
    refetch_empty re-queries words previously cached as [] (e.g. to widen from
    English-only to all languages)."""
    if word in cache and (cache[word] or not refetch_empty):
        return cache[word]
    for attempt in range(max_retries):
        try:
            resp = session.get(REST_URL.format(word=word), timeout=20)
        except requests.RequestException:
            time.sleep(backoff * (2 ** attempt))
            continue
        if resp.status_code == 404:
            cache[word] = []
            return []
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = resp.headers.get("Retry-After")
            time.sleep(float(wait) if wait and wait.isdigit() else backoff * (2 ** attempt))
            continue
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        senses = extract_senses(data)
        cache[word] = senses
        return senses
    return None


def defined_words(assets: pathlib.Path) -> set[str]:
    words = set()
    for dj in list(assets.glob("*/dictionary.jsonl")) + [assets / "extra_defs.jsonl"]:
        if dj.exists():
            for line in dj.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    words.add(json.loads(line)["word"].lower())
    return words


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--allowed", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between network calls")
    ap.add_argument("--refetch-empty", action="store_true",
                    help="re-query words previously cached as no-entry (to widen to all languages)")
    args = ap.parse_args()

    assets = pathlib.Path(args.assets)
    allowed = {w.strip().lower() for w in pathlib.Path(args.allowed).read_text().splitlines() if w.strip()}
    todo = sorted(allowed - defined_words(assets))
    if args.limit:
        todo = todo[:args.limit]

    pathlib.Path(args.cache).parent.mkdir(parents=True, exist_ok=True)
    cache = load_cache(args.cache)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    hits = misses = errors = net = 0
    for i, word in enumerate(todo, 1):
        cached = word in cache and (cache[word] or not args.refetch_empty)
        senses = wiktionary_senses(word, session, cache, refetch_empty=args.refetch_empty)
        if senses is None:
            errors += 1
        elif senses:
            hits += 1
        else:
            misses += 1
        if not cached:
            net += 1
            if net % 25 == 0:
                save_cache(args.cache, cache)
            if senses is not None:  # only sleep after an actual network resolution
                time.sleep(args.delay)
    save_cache(args.cache, cache)

    total = len(todo)
    print(f"probed {total} words ({net} network, {total - net} from cache)")
    print(f"  hits={hits}  misses(no entry)={misses}  errors={errors}")
    if total:
        print(f"  HIT RATE: {100 * hits / total:.0f}%")
    sample = [(w, cache[w][0]['definition'][:60]) for w in todo if cache.get(w)][:8]
    for w, d in sample:
        print(f"    {w}: {d}")


if __name__ == "__main__":
    main()
