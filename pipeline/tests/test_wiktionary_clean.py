"""Tests for Wiktionary definition cleaning + junk detection (no network)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

try:
    from fill_gaps_wiktionary import clean, is_junk
    HAVE = True
except Exception:
    HAVE = False


@unittest.skipUnless(HAVE, "fill_gaps_wiktionary import failed (requests missing?)")
class TestClean(unittest.TestCase):
    def test_decodes_entities(self):
        self.assertEqual(clean("Greek letter (Α,&nbsp;α)"), "Greek letter (Α, α)")

    def test_strips_css_leak(self):
        self.assertEqual(clean("Sixpence coin. .mw-parser-output .defdate{font-size:smaller}"),
                          "Sixpence coin.")

    def test_strips_simple_latex(self):
        self.assertEqual(clean("The complex number a + b i {\\displaystyle a+bi} here"),
                          "The complex number a + b i here")

    def test_plain_text_untouched(self):
        self.assertEqual(clean("a small island"), "a small island")


@unittest.skipUnless(HAVE, "fill_gaps_wiktionary import failed")
class TestIsJunk(unittest.TestCase):
    def test_placeholder_is_junk(self):
        self.assertTrue(is_junk("This term needs a definition. Please help out ... {{rfdef}}"))

    def test_latex_residue_is_junk(self):
        self.assertTrue(is_junk("a set of tuples \\ldots \\in \\mathbb"))

    def test_stray_brace_is_junk(self):
        self.assertTrue(is_junk("the anion ( N=N }}} )"))

    def test_real_definition_is_not_junk(self):
        self.assertFalse(is_junk("having three dimensions"))
        self.assertFalse(is_junk("a linguistic element added to a word"))


if __name__ == "__main__":
    unittest.main()
