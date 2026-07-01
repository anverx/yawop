#!/usr/bin/env python3
"""Scrape a word list from the URLs in wordlist.url, keep only 5-letter words,
and write them to a text file preserving their original order.

wordlist.url format: one entry per line as "<index><TAB><url>". The URLs point
to Wiktionary PG frequency-list pages, where each word sits in the second column
(Rank | Word | Count) of an HTML table as a <a href="/wiki/word">word</a> link.
"""

from __future__ import annotations

import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
URL_FILE = HERE / "wordlist.url"
OUTPUT_FILE = HERE / "five_letter_words.txt"

USER_AGENT = "yawod-wordlist-scraper/1.0 (contact: anatoli.verkhovski@enkora.fi)"
WORD_RE = re.compile(r"^[a-z]{5}$")


def read_urls(path: Path) -> list[str]:
    """Return the URLs from wordlist.url in file order, ignoring blank lines."""
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        # Each line is "<index>\t<url>"; tolerate spaces and index-only lines.
        parts = line.split()
        for token in parts:
            if token.startswith("http://") or token.startswith("https://"):
                urls.append(token)
    return urls


class FrequencyTableParser(HTMLParser):
    """Pull the Word column out of the frequency table.

    The table rows look like:
        <tr><td>1</td><td><a href="/wiki/the">the</a></td><td>562...</td></tr>
    We only capture text inside the <a> of the second <td> of each row, which
    keeps navigation/section links out of the result.
    """

    def __init__(self) -> None:
        super().__init__()
        self.words: list[str] = []
        self._in_table = False
        self._td_index = -1  # -1 means "not inside a row"
        self._in_word_anchor = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._td_index = 0
        elif tag == "td" and self._td_index >= 0:
            self._td_index += 1
        elif tag == "a" and self._td_index == 2:
            # Second column = the word.
            self._in_word_anchor = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._in_word_anchor = False
        elif tag == "tr":
            self._td_index = -1
        elif tag == "table":
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_word_anchor:
            word = data.strip()
            if word:
                self.words.append(word)


def fetch(url: str, session: requests.Session) -> str:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def main() -> int:
    if not URL_FILE.exists():
        print(f"error: {URL_FILE} not found", file=sys.stderr)
        return 1

    urls = read_urls(URL_FILE)
    if not urls:
        print(f"error: no URLs found in {URL_FILE}", file=sys.stderr)
        return 1

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    five_letter: list[str] = []
    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] fetching {url}", file=sys.stderr)
        html = fetch(url, session)
        parser = FrequencyTableParser()
        parser.feed(html)
        page_words = parser.words
        kept = [w for w in page_words if WORD_RE.match(w)]
        five_letter.extend(kept)
        print(f"    {len(page_words)} words, {len(kept)} five-letter", file=sys.stderr)
        if i < len(urls):
            time.sleep(1)  # be polite to Wiktionary

    # Drop case-insensitive duplicates, keeping the first (highest-frequency)
    # occurrence so the original order is preserved.
    seen: set[str] = set()
    deduped: list[str] = []
    for word in five_letter:
        key = word.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(word)

    OUTPUT_FILE.write_text("\n".join(deduped) + "\n", encoding="utf-8")
    print(
        f"wrote {len(deduped)} five-letter words to {OUTPUT_FILE} "
        f"({len(five_letter) - len(deduped)} duplicates removed)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
