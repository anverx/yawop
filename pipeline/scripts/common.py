"""Shared helpers for the yawod word-pack pipeline.

Every stage reads one file and writes another (no in-place mutation), so the
pipeline is reproducible and each step's output is inspectable. Dictionary
records are JSON objects, one per line (JSONL):

    {"word": "abide", "rank": 42, "senses": [{"pos","pos_label","definition","source"}]}

"rank" is the 1-based position in the pack's frequency order (1 = most frequent),
preserved through every stage so tiering can use it even after alphabetical sorts.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

USER_AGENT = "yawod-wordlist-scraper/1.0 (contact: anatoli.verkhovski@enkora.fi)"
FIVE_LETTER = re.compile(r"^[a-z]{5}$")

# WordNet single-letter POS -> label; Free Dictionary API uses full words.
POS_LABELS = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}
POS_CODE = {"noun": "n", "verb": "v", "adjective": "a", "adverb": "r"}


# --- plain-text list I/O -------------------------------------------------------

def read_lines(path: str | Path) -> list[str]:
    return [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def write_lines(path: str | Path, lines: list[str]) -> None:
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def dedupe_ci(words) -> list[str]:
    """Case-insensitive dedupe, keeping first occurrence (highest-frequency)."""
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        k = w.lower()
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def five_letter_only(words) -> list[str]:
    return [w for w in words if FIVE_LETTER.match(w.lower())]


# --- JSONL dictionary I/O ------------------------------------------------------

def read_jsonl(path: str | Path) -> list[dict]:
    return [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def write_jsonl(path: str | Path, records: list[dict]) -> None:
    with Path(path).open("w", encoding="utf-8") as out:
        for rec in records:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")


# --- WordNet -------------------------------------------------------------------

def wordnet_senses(word: str) -> list[dict]:
    """Return WordNet senses for a word; [] if none. Duplicates collapsed."""
    from nltk.corpus import wordnet as wn  # imported lazily so fetch steps don't need nltk

    senses: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for syn in wn.synsets(word):
        pos, definition = syn.pos(), syn.definition()
        key = (pos, definition)
        if key in seen:
            continue
        seen.add(key)
        senses.append(
            {"pos": pos, "pos_label": POS_LABELS.get(pos, pos), "definition": definition, "source": "wordnet"}
        )
    return senses


# --- Free Dictionary API (with on-disk cache) ----------------------------------

API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"


def load_cache(path: str | Path) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_cache(path: str | Path, cache: dict) -> None:
    Path(path).write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def api_senses(word: str, session: requests.Session, cache: dict,
               max_retries: int = 4, backoff: float = 1.5) -> list[dict] | None:
    """Senses from the Free Dictionary API. [] = no entry (404); None = error.

    Results are cached by word (including 404s, stored as []). None is never
    cached, so transient failures are retried on a later run.
    """
    if word in cache:
        return cache[word]

    for attempt in range(max_retries):
        try:
            resp = session.get(API_URL.format(word=word), timeout=20)
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
            entries = resp.json()
        except ValueError:
            return None

        senses: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for entry in entries if isinstance(entries, list) else []:
            for meaning in entry.get("meanings", []):
                label = (meaning.get("partOfSpeech") or "").strip()
                pos = POS_CODE.get(label.lower(), label)
                for d in meaning.get("definitions", []):
                    definition = (d.get("definition") or "").strip()
                    if not definition or (label, definition) in seen:
                        continue
                    seen.add((label, definition))
                    senses.append(
                        {"pos": pos, "pos_label": label, "definition": definition, "source": "dictionaryapi.dev"}
                    )
        cache[word] = senses
        return senses
    return None  # retries exhausted
