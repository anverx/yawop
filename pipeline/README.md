# yawod — dictionary build pipeline

Build-time tooling that produces the word data for the game. **Not shipped** — it
fetches each source, attaches definitions, prunes words it can't define, assigns
difficulty tiers, and (`make publish`) copies the shippable subset into
`../assets/dictionaries/`, which the game bundles. The game and its `worddata/`
runtime package never import from here.

Run all commands from this `pipeline/` directory.

## Packs (game options)

| Pack | Source | Character | Difficulty tiers |
|------|--------|-----------|------------------|
| `subtlex-us` | [SUBTLEX-US](https://github.com/words/subtlex-word-frequencies) subtitle frequency (American) | everyday, occasionally slangy | by frequency |
| `subtlex-uk` | [SUBTLEX-UK](https://github.com/JackEdTaylor/Codeword-Solver)-derived Zipf frequency (British) | British spellings & slang | by frequency |
| `wordle` | Official NYT [answers](https://gist.github.com/cfreshman/a03ef2cba789d8cf00c08f767e0fad7b) + [allowed guesses](https://gist.github.com/cfreshman/cdcdf777450c5b5301e439061d29694c) | conventional, curated, safe | by borrowed SUBTLEX-US frequency |
| `surprise` | Union of the three packs above | everything | none (flat pool, no rank merge) |
| `arcane` | Gutenberg **minus** the most-frequent SUBTLEX words | archaic/literary — *properly horrible* | by Gutenberg frequency |

**`arcane`** is the nightmare pack (~1,000 words): words common in century-old
Project Gutenberg books but rare/absent in modern speech. Two knobs shape it:

- **Junk filter** — a word is kept only if it's a *real* word (in the Wordle
  allowed-guess list, or WordNet-defined). This drops proper nouns, abbreviations,
  and OCR noise (`chios`, `afaik`, `akkub`) while keeping horrible-but-real words
  (`quoth`, `wroth`, `aboon`, `ayont`) even when WordNet can't define them.
- **`ARCANE_SUBTRACT_TOP`** — subtract only the top-N most frequent SUBTLEX words
  (default 4,000) rather than all ~20k, so archaic words that appear only rarely in
  subtitles survive. Raise N to shrink the pack, lower it to grow it.

Each arcane word is enriched with **literary usage** (see the `enrich` step).
`surprise` is the union of the three *normal* packs only; it does not include `arcane`.

## The two-list model

Wordle-style games need **two** lists, and this pipeline produces both:

- **Answer pool** (`puzzle_words.txt`, and `tiers.json`) — words that can be the
  solution, split into easy/medium/hard. Tiers are **disjoint** frequency bands
  so an "easy" puzzle is genuinely easy.
- **Allowed guesses** (`data/allowed_guesses_all.txt`) — every valid word a
  player may type. This is the **union of all packs**, always accepted regardless
  of the chosen pack/difficulty, so no real word is ever rejected.

Difficulty boundaries are **percentiles**, not fixed counts, so they survive
source changes: `EASY=0.15` (top 15%), `MEDIUM=0.40` (up to 40%), hard = the rest.

## Requirements

- Python 3, `requests`, `nltk` + the `wordnet` and `omw-1.4` corpora.
- `make setup` installs these (into the user site; no venv/root needed).

## Usage

```sh
make setup          # one-time: install nltk + WordNet corpora
make all            # build all four packs
make subtlex-us     # or build one pack
make clean          # remove generated data (keeps the API cache)
```

Tunables (pass on the command line, e.g. `make all UK_MAX_API=2000`):

| Var | Default | Meaning |
|-----|---------|---------|
| `US_MAX_API` / `UK_MAX_API` / `WORDLE_MAX_API` | 800 / 1200 / 500 | max **new** Free Dictionary API lookups per pack per run |
| `EASY` / `MEDIUM` | 0.15 / 0.40 | difficulty tier boundaries (cumulative fractions) |
| `ARCANE_SUBTRACT_TOP` | 4000 | subtract only the top-N SUBTLEX words from Gutenberg (higher → smaller arcane pack) |

## Publishing to the game

`make publish` copies only the shippable files into `../assets/dictionaries/`
(per pack: `dictionary.jsonl` + `tiers.json`; plus Wordle's `allowed_guesses.txt`,
the `surprise` list, and `allowed_guesses_all.txt`). Working intermediates and
caches under `data/` stay behind.

Word **selection and lookup at runtime** are not part of this pipeline — they live
in the game's `worddata/` package (see the top-level `README.md`), which reads the
published assets with no dependency on this tooling.

## Tests

```sh
make test        # or: python3 -m unittest discover -s tests -v
```

Hermetic (no network, no WordNet): pure logic — the junk filter, tiering,
pruning, union, the picker's seed determinism, the API cache behaviour, the HTML
parser, and the Wikisource reference-work filter — is covered via synthetic
fixtures and mocked HTTP. Suitable for CI as-is (`pytest tests` also works).

## Pipeline

Each stage reads one file and writes another — **nothing is mutated in place** —
so any stage can be re-run in isolation and every intermediate is inspectable.

```
fetch ─► words_ranked.txt ─► build ─► dict.wordnet.jsonl ─► fill ─► dict.filled.jsonl
                                                                        │
                          tiers.json ◄─ assign_tiers ◄─ puzzle_words.txt ◄─ prune
                                                        dictionary.jsonl  ◄─┘
```

| Step | Script | In → Out | What it does |
|------|--------|----------|--------------|
| fetch | `fetch.py` | source URL → `words_ranked.txt` (or `answers.txt` + `allowed_guesses.txt`) | download source, keep clean 5-letter words, dedupe case-insensitively, preserve frequency order |
| build | `build_dictionary.py` | `words_ranked.txt` → `dict.wordnet.jsonl` | attach WordNet senses; words with none get empty senses |
| fill | `fill_gaps.py` | `dict.wordnet.jsonl` → `dict.filled.jsonl` | fill gaps (freq order) via Free Dictionary API, bounded by `*_MAX_API`; **cached** |
| prune | `prune_undefined.py` | `dict.filled.jsonl` → `dictionary.jsonl` + `puzzle_words.txt` + `undefined_words.txt` | drop still-undefined words; dictionary is alphabetical, puzzle list stays in frequency order |
| tiers | `assign_tiers.py` | `puzzle_words.txt` → `tiers.json` | split into easy/medium/hard by percentile |
| combine | `combine_surprise.py` | 3 × `dictionary.jsonl` → `surprise/` | case-insensitive union, merged senses, no tiers |
| subtract | `subtract.py` | Gutenberg `dict.wordnet.jsonl` − top-N SUBTLEX → `arcane/dict.base.jsonl` | keep real Gutenberg-only words (junk filter), preserve frequency order |
| enrich | `enrich_examples.py` | `arcane/dict.base.jsonl` → `arcane/dictionary.jsonl` | add 1–3 Wikisource usage examples (work, author, sentence) + a Gutenberg search link per word; **cached** |

### Definition cache

Free Dictionary API responses (including 404s) are cached in
`data/cache/dictionaryapi.json`, keyed by word, and flushed incrementally during
a run. Cached words cost no network call, so re-runs never repeat a request and
raising a `*_MAX_API` budget only fetches the *new* words. `make clean` keeps the
cache; `make clean-cache` clears it.

Definitions are built only for **answer pools**, not the ~12.9k Wordle
allowed-guess list (which only needs validity-checking) — avoiding thousands of
needless API calls.

## Output layout

```
data/
  subtlex-us/  words_ranked.txt  dict.wordnet.jsonl  dict.filled.jsonl
               dictionary.jsonl  puzzle_words.txt  undefined_words.txt  tiers.json
  subtlex-uk/  (same shape)
  wordle/      answers.txt  allowed_guesses.txt  dictionary.jsonl  puzzle_words.txt  tiers.json  …
  surprise/    dictionary.jsonl  words.txt
  allowed_guesses_all.txt        # union of every valid word (the guess validator)
  cache/dictionaryapi.json       # shared, persistent API cache
```

Dictionary record shape (JSONL, one per line):

```json
{"word": "abide", "rank": 42, "senses": [{"pos": "v", "pos_label": "verb", "definition": "dwell", "source": "wordnet"}]}
```

`rank` is the 1-based frequency position, preserved through every stage. Arcane
records additionally carry `gutenberg_search_url` and, where found, `examples`:

```json
{"word": "quoth", "rank": 12, "senses": [...],
 "gutenberg_search_url": "https://www.google.com/search?q=%22quoth%22+site%3Agutenberg.org",
 "examples": [{"work": "...", "author": "...", "text": "...", "url": "https://en.wikisource.org/...", "source": "wikisource"}]}
```

## Results

Latest `make all` (`US_MAX_API=800 UK_MAX_API=1200 WORDLE_MAX_API=500`):

| Pack | Source words (5-letter) | Answer pool (defined) | Easy / Medium / Hard |
|------|------------------------:|----------------------:|:--------------------:|
| `subtlex-us` | 6,779 | 5,480 | 822 / 1,370 / 3,288 |
| `subtlex-uk` | 19,151 | 6,594 | 989 / 1,649 / 3,956 |
| `wordle` | 2,315 answers (12,972 allowed) | 2,309 | 346 / 578 / 1,385 |
| `surprise` | union | 6,895 | — (no tiers) |
| `arcane` | 4,128 Gutenberg − top-4,000 SUBTLEX (junk-filtered) | 1,009 | 151 / 253 / 605 |

- **Arcane usage examples**: 984 of 1,009 words (97.5%) have ≥1 Wikisource literary citation (dictionaries, cyclopaedias, catalogues, etc. are filtered out — only prose/verse).
- **Allowed-guess validator** (`data/allowed_guesses_all.txt`): 25,154 distinct valid words.
- **Caches**: `dictionaryapi.json` ~2,050 words; `wikisource.json` ~1,000 words. Re-runs hit zero network for cached lookups.

Answer-pool coverage is bounded by the per-pack `*_MAX_API` budgets (unfilled gaps
are pruned); raise a budget and re-run to grow a pool — cached words are free, so
only genuinely new lookups cost anything.

## Notes

- Gutenberg is no longer a standalone game option (its 1800s corpus misses modern
  vocabulary, and merging its frequency scale with SUBTLEX was not meaningful), but
  it lives on as the **internal ingredient** for the `arcane` pack — built by the
  pipeline into `data/gutenberg/` (not offered directly). The original ad-hoc
  Gutenberg scripts remain in `archive/` for reference.
