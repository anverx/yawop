#!/usr/bin/env python3
"""Fetch a pack's raw word list from its source, in frequency order.

Usage:
    python3 scripts/fetch.py --pack subtlex-us   --out-dir data/subtlex-us
    python3 scripts/fetch.py --pack subtlex-uk   --out-dir data/subtlex-uk
    python3 scripts/fetch.py --pack wordle       --out-dir data/wordle

Outputs (per pack):
    subtlex-us / subtlex-uk : words_ranked.txt   (5-letter, deduped, freq order)
    wordle                  : answers.txt (curated) + allowed_guesses.txt (full)
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import USER_AGENT, dedupe_ci, five_letter_only, write_lines

# Gutenberg: Wiktionary PG frequency-list pages, listed one URL per line here.
GUTENBERG_URL_FILE = "wordlist.url"

# SUBTLEX-US: JSON list of {word, count}, sorted by count desc (74,286 entries).
SUBTLEX_US_URL = "https://raw.githubusercontent.com/words/subtlex-word-frequencies/master/index.json"
# SUBTLEX-US text version (UGent), tab-separated. Adds FREQlow = occurrences that
# START LOWERCASE, i.e. common-word (non-proper-noun) usage. Ranking difficulty by
# FREQlow instead of the case-folded total stops proper names ("Brock", "Angus")
# from inflating a rare word into an easy/medium tier. Used only for tiering.
SUBTLEX_US_LC_ZIP = "https://www.ugent.be/pp/experimentele-psychologie/en/research/documents/subtlexus/subtlexus2.zip"
SUBTLEX_US_LC_MEMBER = "SUBTLEXus74286wordstextversion.txt"
# SUBTLEX-UK derived CSV (Spelling, nchar, LogFreq_Zipf, DomPoS); CC-licensed mirror.
SUBTLEX_UK_URL = "https://raw.githubusercontent.com/JackEdTaylor/Codeword-Solver/HEAD/zipfFreqs.csv"
# Official Wordle lists (cfreshman gists).
WORDLE_ANSWERS_URL = "https://gist.githubusercontent.com/cfreshman/a03ef2cba789d8cf00c08f767e0fad7b/raw"
WORDLE_GUESSES_URL = "https://gist.githubusercontent.com/cfreshman/cdcdf777450c5b5301e439061d29694c/raw"


def get(url: str) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    return resp


def fetch_subtlex_us(out_dir: Path) -> None:
    data = get(SUBTLEX_US_URL).json()  # already frequency-sorted
    words = dedupe_ci(five_letter_only(e["word"] for e in data))
    write_lines(out_dir / "words_ranked.txt", words)
    print(f"subtlex-us: {len(data)} entries -> {len(words)} five-letter words", file=sys.stderr)
    _fetch_subtlex_us_lowercase(out_dir)


def _fetch_subtlex_us_lowercase(out_dir: Path) -> None:
    """words_lc_ranked.txt: 5-letter words ordered by FREQlow (lowercase-start
    frequency). This is the reference ranking assign_tiers uses so difficulty
    reflects common-word usage, not proper-noun frequency (see SUBTLEX_US_LC_ZIP)."""
    raw = get(SUBTLEX_US_LC_ZIP).content
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(SUBTLEX_US_LC_MEMBER).decode("latin-1").splitlines()
    header = text[0].split("\t")
    wi, fli = header.index("Word"), header.index("FREQlow")
    scored: list[tuple[str, int]] = []
    for line in text[1:]:
        cells = line.split("\t")
        if len(cells) <= fli:
            continue
        try:
            scored.append((cells[wi].strip(), int(cells[fli])))
        except ValueError:
            continue
    scored.sort(key=lambda x: -x[1])  # highest lowercase frequency first
    words = dedupe_ci(five_letter_only(w for w, _ in scored))
    write_lines(out_dir / "words_lc_ranked.txt", words)
    print(f"subtlex-us: {len(scored)} POS rows -> {len(words)} five-letter words (FREQlow order)",
          file=sys.stderr)


def fetch_subtlex_uk(out_dir: Path) -> None:
    text = get(SUBTLEX_UK_URL).text
    rows = list(csv.reader(io.StringIO(text)))
    header = [h.strip().lower() for h in rows[0]]
    wi = next(i for i, h in enumerate(header) if "spell" in h or "word" in h)
    fi = next(i for i, h in enumerate(header) if "zipf" in h or "freq" in h)
    scored: list[tuple[str, float]] = []
    for r in rows[1:]:
        if len(r) <= max(wi, fi):
            continue
        w = r[wi].strip().lower()
        try:
            f = float(r[fi])
        except ValueError:
            continue
        scored.append((w, f))
    scored.sort(key=lambda x: -x[1])  # highest frequency first
    words = dedupe_ci(five_letter_only(w for w, _ in scored))
    write_lines(out_dir / "words_ranked.txt", words)
    print(f"subtlex-uk: {len(rows)-1} rows -> {len(words)} five-letter words", file=sys.stderr)


def fetch_wordle(out_dir: Path) -> None:
    answers = dedupe_ci(five_letter_only(get(WORDLE_ANSWERS_URL).text.split()))
    guesses = dedupe_ci(five_letter_only(get(WORDLE_GUESSES_URL).text.split()))
    # The allowed-guess set should be a superset of the answers.
    guesses = dedupe_ci(guesses + answers)
    write_lines(out_dir / "answers.txt", answers)
    write_lines(out_dir / "allowed_guesses.txt", guesses)
    print(f"wordle: {len(answers)} answers, {len(guesses)} allowed guesses", file=sys.stderr)


class _FreqTableParser(HTMLParser):
    """Extract the Word column (2nd <td>, as a link) from Wiktionary PG tables."""

    def __init__(self) -> None:
        super().__init__()
        self.words: list[str] = []
        self._in_table = self._in_word = False
        self._td = -1

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._td = 0
        elif tag == "td" and self._td >= 0:
            self._td += 1
        elif tag == "a" and self._td == 2:
            self._in_word = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_word = False
        elif tag == "tr":
            self._td = -1
        elif tag == "table":
            self._in_table = False

    def handle_data(self, data):
        if self._in_word and data.strip():
            self.words.append(data.strip())


def fetch_gutenberg(out_dir: Path) -> None:
    urls = [ln.strip() for ln in Path(GUTENBERG_URL_FILE).read_text(encoding="utf-8").splitlines()
            if ln.strip().startswith("http")]
    all_words: list[str] = []
    for url in urls:
        parser = _FreqTableParser()
        parser.feed(get(url).text)
        all_words.extend(parser.words)
    words = dedupe_ci(five_letter_only(all_words))
    write_lines(out_dir / "words_ranked.txt", words)
    print(f"gutenberg: {len(urls)} pages, {len(all_words)} words -> {len(words)} five-letter", file=sys.stderr)


FETCHERS = {"subtlex-us": fetch_subtlex_us, "subtlex-uk": fetch_subtlex_uk,
            "wordle": fetch_wordle, "gutenberg": fetch_gutenberg}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True, choices=sorted(FETCHERS))
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    FETCHERS[args.pack](out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
