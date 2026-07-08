#!/usr/bin/env python3
"""Find proper-noun-only words (names + places) to remove from every list.

Candidates: words WordNet knows *only* as instances (proper nouns). Each is then
cross-checked against Wiktionary and KEPT if it has any common (non-proper-noun)
sense in any language -- so real words WordNet happens to know only as a proper
noun (e.g. 'arhat') survive. Everything else is a name/place and is written to the
output list for removal.

  python scripts/find_proper_nouns.py --allowed <assets>/allowed_guesses_all.txt \
      --cache data/cache/proper_noun_check.json --out proper_nouns.txt [--delay 1.0]
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

import requests
from nltk.corpus import wordnet as wn

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import USER_AGENT, load_cache, save_cache  # noqa: E402

REST_URL = "https://en.wiktionary.org/api/rest_v1/page/definition/{word}"


def has_common_sense(word, session, cache, max_retries=4, backoff=1.5):
    """True if Wiktionary lists a non-proper-noun sense in ENGLISH.

    English-only on purpose: many proper nouns (Accra, Andes) have unrelated
    common-noun homographs in other languages, which must not rescue them.
    Cached as bool; None (transient error) is not cached."""
    if word in cache:
        return cache[word]
    for attempt in range(max_retries):
        try:
            resp = session.get(REST_URL.format(word=word), timeout=20)
        except requests.RequestException:
            time.sleep(backoff * (2 ** attempt))
            continue
        if resp.status_code == 404:
            cache[word] = False   # no Wiktionary entry + WordNet proper-noun-only -> a name
            return False
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
        en = data.get("en", [])
        common = isinstance(en, list) and any(
            (g.get("partOfSpeech") or "").strip().lower() not in ("", "proper noun") and g.get("definitions")
            for g in en)
        cache[word] = common
        return common
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--allowed", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    allowed = {w.strip().lower() for w in pathlib.Path(args.allowed).read_text().splitlines() if w.strip()}
    candidates = sorted(w for w in allowed
                        if wn.synsets(w) and all(s.instance_hypernyms() for s in wn.synsets(w)))

    pathlib.Path(args.cache).parent.mkdir(parents=True, exist_ok=True)
    cache = load_cache(args.cache)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    remove, kept, net = [], [], 0
    for w in candidates:
        cached = w in cache
        common = has_common_sense(w, session, cache)
        if common:
            kept.append(w)
        else:
            remove.append(w)
        if not cached:
            net += 1
            if net % 25 == 0:
                save_cache(args.cache, cache)
            if common is not None:
                time.sleep(args.delay)
    save_cache(args.cache, cache)

    pathlib.Path(args.out).write_text("".join(w + "\n" for w in sorted(remove)), encoding="utf-8")
    print(f"candidates={len(candidates)}  removed(proper nouns)={len(remove)}  "
          f"kept(real words)={len(kept)}  ({net} network)")
    print("  kept as real words:", kept[:20])
    print("  removing:", remove[:20])


if __name__ == "__main__":
    main()
