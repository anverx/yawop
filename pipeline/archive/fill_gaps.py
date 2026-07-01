#!/usr/bin/env python3
"""Fill gaps in dictionary.jsonl using the Free Dictionary API (dictionaryapi.dev).

Reads dictionary.jsonl, and for every record whose "senses" list is empty, queries
https://api.dictionaryapi.dev/api/v2/entries/en/<word>. Parsed definitions are added
as senses tagged with source "dictionaryapi.dev"; pre-existing WordNet senses are
tagged source "wordnet". The file is rewritten in place (through a temp file).

Re-running only re-queries records that are still empty (e.g. previous 404s / errors),
so it is safe to run repeatedly.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
DICT_FILE = HERE / "dictionary.jsonl"
TMP_FILE = HERE / "dictionary.jsonl.tmp"

API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
USER_AGENT = "yawod-wordlist-scraper/1.0 (contact: anatoli.verkhovski@enkora.fi)"

# Free Dictionary API part-of-speech -> WordNet-style single-letter code, to stay
# consistent with the WordNet-sourced senses already in the file.
POS_CODE = {"noun": "n", "verb": "v", "adjective": "a", "adverb": "r"}

REQUEST_DELAY = 0.4       # seconds between calls, to be polite
MAX_RETRIES = 4           # for 429 / 5xx / network errors
BACKOFF_BASE = 1.5        # seconds, exponential


def api_senses(word: str, session: requests.Session) -> list[dict[str, str]] | None:
    """Return senses for a word, [] if the API has no entry (404), or None on error.

    None means "could not determine" (network/rate-limit failure after retries) so the
    caller leaves the record untouched for a future run instead of marking it resolved.
    """
    url = API_URL.format(word=word)
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, timeout=20)
        except requests.RequestException:
            time.sleep(BACKOFF_BASE * (2 ** attempt))
            continue

        if resp.status_code == 404:
            return []
        if resp.status_code == 429 or resp.status_code >= 500:
            # Rate-limited or server error: honor Retry-After if present, else backoff.
            wait = resp.headers.get("Retry-After")
            time.sleep(float(wait) if wait and wait.isdigit() else BACKOFF_BASE * (2 ** attempt))
            continue
        if resp.status_code != 200:
            return None

        try:
            entries = resp.json()
        except ValueError:
            return None

        senses: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for entry in entries if isinstance(entries, list) else []:
            for meaning in entry.get("meanings", []):
                pos_label = meaning.get("partOfSpeech", "") or ""
                pos = POS_CODE.get(pos_label.lower(), pos_label)
                for d in meaning.get("definitions", []):
                    definition = (d.get("definition") or "").strip()
                    if not definition:
                        continue
                    key = (pos_label, definition)
                    if key in seen:
                        continue
                    seen.add(key)
                    senses.append(
                        {
                            "pos": pos,
                            "pos_label": pos_label,
                            "definition": definition,
                            "source": "dictionaryapi.dev",
                        }
                    )
        return senses
    return None  # exhausted retries


def tag_wordnet(senses: list[dict]) -> list[dict]:
    """Ensure existing (WordNet) senses carry a source tag."""
    for s in senses:
        s.setdefault("source", "wordnet")
    return senses


def main() -> int:
    if not DICT_FILE.exists():
        print(f"error: {DICT_FILE} not found", file=sys.stderr)
        return 1

    records = [json.loads(line) for line in DICT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    gaps = [r for r in records if not r.get("senses")]
    print(f"{len(records)} records, {len(gaps)} to look up via Free Dictionary API", file=sys.stderr)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    filled = still_missing = errored = 0
    for i, rec in enumerate(gaps, 1):
        word = rec["word"]
        result = api_senses(word, session)
        if result is None:
            errored += 1
            status = "ERROR (kept empty)"
        elif result:
            rec["senses"] = result
            filled += 1
            status = f"{len(result)} senses"
        else:
            still_missing += 1
            status = "no entry (404)"
        print(f"  [{i}/{len(gaps)}] {word}: {status}", file=sys.stderr)
        time.sleep(REQUEST_DELAY)

    # Tag every record's senses with a source so the file is self-describing.
    for rec in records:
        tag_wordnet(rec.get("senses", []))

    with TMP_FILE.open("w", encoding="utf-8") as out:
        for rec in records:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    TMP_FILE.replace(DICT_FILE)

    print(
        f"done: filled {filled}, still no entry {still_missing}, errored {errored}. "
        f"Rewrote {DICT_FILE}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
