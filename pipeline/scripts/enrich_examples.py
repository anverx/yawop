#!/usr/bin/env python3
"""Add literary usage examples to a dictionary via Wikisource full-text search.

Usage:
    python3 scripts/enrich_examples.py --in data/arcane/dict.base.jsonl \
        --out data/arcane/dictionary.jsonl --cache data/cache/wikisource.json

For each word, searches Wikisource (public-domain texts) for a passage
containing it, and records the work, author (best-effort, from the work's page
header), the context sentence, and a URL as an "examples" entry:

    "examples": [{"work","author","text","url","source":"wikisource"}]

Results are cached by word (misses cached as []). No API key required.
Intended for the arcane pack, but works on any dictionary.jsonl.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import USER_AGENT, load_cache, read_jsonl, save_cache, write_jsonl

API = "https://en.wikisource.org/w/api.php"
DELAY = 0.3
TAG_RE = re.compile(r"<[^>]+>")
# Reference works are listings, not usage — skip them so examples are real prose/verse.
REFERENCE_RE = re.compile(
    r"dictionar|glossar|lexicon|thesaur|cyclop|vocabular|concordance|synonym|catalog|gazetteer|word.?list",
    re.IGNORECASE)  # 'cyclop' covers encyclop(a)edia + cyclop(a)edia; 'catalog' covers catalogue


def clean(html: str) -> str:
    text = TAG_RE.sub("", html)
    for a, b in [("&quot;", '"'), ("&#039;", "'"), ("&amp;", "&"), ("&nbsp;", " ")]:
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def author_of(work: str, session: requests.Session, cache: dict) -> str:
    """Best-effort author from a Wikisource work's page header template."""
    key = f"__author__:{work}"
    if key in cache:
        return cache[key]
    author = ""
    try:
        r = session.get(API, params={
            "action": "query", "prop": "revisions", "rvprop": "content",
            "rvslots": "main", "titles": work, "format": "json"}, timeout=20)
        pages = r.json().get("query", {}).get("pages", {})
        content = next(iter(pages.values())).get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")
        m = re.search(r"\|\s*author\s*=\s*([^\n]*)", content)
        if m:
            val = re.split(r"}}", m.group(1))[0]  # rest of the value, before template close
            # [[Author:William Shakespeare|Shakespeare]] / [[Author:Homer]] -> display name
            link = re.search(r"\[\[Author:[^|\]]*\|([^\]]+)\]\]", val) or re.search(r"\[\[Author:([^\]]+)\]\]", val)
            author = (link.group(1) if link else val.split("|")[0]).strip(" []")
    except (requests.RequestException, ValueError, StopIteration, KeyError):
        pass
    cache[key] = author
    return author


def example_for(word: str, session: requests.Session, cache: dict) -> list[dict]:
    if word in cache:
        return cache[word]
    result: list[dict] = []
    try:
        r = session.get(API, params={
            "action": "query", "list": "search", "srsearch": f'"{word}"',
            "srlimit": 10, "srprop": "snippet", "format": "json"}, timeout=20)
        hits = r.json().get("query", {}).get("search", [])
    except (requests.RequestException, ValueError):
        return None  # transient: don't cache, retry next run

    seen_works: set[str] = set()
    for h in hits:
        ctx = clean(h.get("snippet", ""))
        if word.lower() not in ctx.lower():
            continue
        if REFERENCE_RE.search(h["title"]):  # skip dictionaries/glossaries/etc.
            continue
        work = h["title"].split("/")[0]
        if work in seen_works:  # don't repeat the same work
            continue
        seen_works.add(work)
        result.append({
            "work": work,
            "author": author_of(work, session, cache),
            "text": ctx,
            "url": "https://en.wikisource.org/wiki/" + h["title"].replace(" ", "_"),
            "source": "wikisource",
        })
        if len(result) >= 3:  # keep up to 3 when the word is used more than once
            break
    cache[word] = result
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", required=True)
    args = ap.parse_args()

    records = read_jsonl(args.inp)
    Path(args.cache).parent.mkdir(parents=True, exist_ok=True)
    cache = load_cache(args.cache)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    found = calls = 0
    for i, rec in enumerate(records, 1):
        word = rec["word"]
        # Gutenberg full-text search link (via site-scoped Google) for every word,
        # so players can explore the source corpus the word list came from.
        rec["gutenberg_search_url"] = f"https://www.google.com/search?q=%22{word}%22+site%3Agutenberg.org"
        cached = word in cache
        ex = example_for(word, session, cache)
        if ex is None:
            ex = []
        if ex:
            rec["examples"] = ex
            found += 1
        if not cached:
            calls += 1
            if calls % 20 == 0:
                save_cache(args.cache, cache)
            time.sleep(DELAY)

    save_cache(args.cache, cache)
    write_jsonl(args.out, records)
    print(f"enrich: {len(records)} words -> {found} with a Wikisource example ({args.out})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
