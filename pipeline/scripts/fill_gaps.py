#!/usr/bin/env python3
"""Fill definition gaps via the Free Dictionary API, bounded by --max-api.

Usage:
    python3 scripts/fill_gaps.py --in data/subtlex-us/dict.wordnet.jsonl \
        --out data/subtlex-us/dict.filled.jsonl \
        --cache data/cache/dictionaryapi.json --max-api 800

Gaps (records with empty "senses") are looked up in frequency order, so the
most common undefined words get real definitions first. At most --max-api *new*
network lookups are made per run; remaining gaps are left empty (and later
pruned). The count skipped is logged — no silent truncation. Cached words
(including prior 404s) don't count against the budget, so re-runs make progress.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import USER_AGENT, api_senses, load_cache, read_jsonl, save_cache, write_jsonl

REQUEST_DELAY = 0.4  # seconds between *network* calls


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--max-api", type=int, default=1500, help="max new network lookups this run")
    args = ap.parse_args()

    records = read_jsonl(args.inp)
    Path(args.cache).parent.mkdir(parents=True, exist_ok=True)
    cache = load_cache(args.cache)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    gaps = [r for r in records if not r.get("senses")]  # already in frequency order
    filled = still_missing = errored = network_calls = skipped = 0

    for rec in gaps:
        word = rec["word"]
        cached = word in cache
        if not cached and network_calls >= args.max_api:
            skipped += 1
            continue
        result = api_senses(word, session, cache)
        if not cached:
            network_calls += 1
            # Flush the cache periodically so an interrupted run keeps its lookups.
            if network_calls % 25 == 0:
                save_cache(args.cache, cache)
            time.sleep(REQUEST_DELAY)
        if result is None:
            errored += 1
        elif result:
            rec["senses"] = result
            filled += 1
        else:
            still_missing += 1

    save_cache(args.cache, cache)
    write_jsonl(args.out, records)
    print(
        f"fill: {len(gaps)} gaps | filled {filled}, no-entry {still_missing}, errored {errored}, "
        f"skipped(budget) {skipped} | {network_calls} network calls ({args.out})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
