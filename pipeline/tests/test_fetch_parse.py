"""Tests for the Wiktionary/Gutenberg frequency-table HTML parser (no network)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch  # noqa: E402

SAMPLE = """
<table>
<tbody>
<tr><td><b>Rank</b></td><td><b>Word</b></td><td><b>Count</b></td></tr>
<tr><td>1</td><td><a href="/wiki/the" title="the">the</a></td><td>999</td></tr>
<tr><td>2</td><td><a href="/wiki/mulct" title="mulct">mulct</a></td><td>12</td></tr>
<tr><td>3</td><td><a href="/wiki/quoth" title="quoth">quoth</a></td><td>7</td></tr>
</tbody>
</table>
"""


class TestFreqTableParser(unittest.TestCase):
    def test_extracts_word_column_only(self):
        p = fetch._FreqTableParser()
        p.feed(SAMPLE)
        # Rank/Count columns and the header must not leak in; only the 2nd-column links.
        self.assertEqual(p.words, ["the", "mulct", "quoth"])

    def test_ignores_links_outside_word_column(self):
        html = ('<table><tr><td><a href="/x">nav</a></td>'
                '<td><a href="/wiki/vaunt">vaunt</a></td></tr></table>')
        p = fetch._FreqTableParser()
        p.feed(html)
        self.assertEqual(p.words, ["vaunt"])


if __name__ == "__main__":
    unittest.main()
