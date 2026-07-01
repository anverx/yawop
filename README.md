# yawop

A cross-platform word puzzle game (Kivy). This repo separates the **game**, which
ships with its dictionaries built in, from the **build-time tooling** that produces
those dictionaries.

## Layout

```
yawod/
├── worddata/              # game-runtime: pick a word, look up an entry (stdlib only)
├── assets/
│   └── dictionaries/      # SHIPPED, built-in dictionaries the game bundles
│       ├── subtlex-us/    #   dictionary.jsonl + tiers.json
│       ├── subtlex-uk/
│       ├── wordle/        #   + allowed_guesses.txt
│       ├── arcane/
│       ├── surprise/      #   dictionary.jsonl + words.txt
│       └── allowed_guesses_all.txt
├── pipeline/              # build-time dictionary "massaging" — NOT shipped
│   └── (scripts, tests, Makefile, wordlist.url, data/ working dir + caches)
├── tests/                 # tests for worddata (game-runtime)
└── (Kivy game code + GUI library — added at the repo root; GUI factored from
     github.com/anverx/yaque)
```

The game and `worddata/` never import from `pipeline/` — the pipeline only *produces*
`assets/dictionaries/`, which the game reads at runtime.

## Word packs

Five selectable options (details in [`pipeline/README.md`](pipeline/README.md)):
`subtlex-us`, `subtlex-uk` (British), `wordle` (official), `surprise` (union), and
`arcane` (Gutenberg-minus-SUBTLEX — archaic, *properly horrible*, with cited
literary usage examples).

## Using the dictionaries (game-runtime)

```python
from worddata import pick_word, lookup_entry

pick_word("subtlex-us")                     # random word from all tiers
pick_word("subtlex-uk", difficulty="hard")  # from one difficulty tier
pick_word("arcane", seed="2026-07-01")       # repeatable: same seed -> same word

lookup_entry("quoth")   # merged definitions + usage examples + which packs/tiers
```

CLI equivalents:

```sh
python -m worddata.pick   --pack arcane --seed 2026-07-01 --json
python -m worddata.lookup quoth
```

## Rebuilding / updating the dictionaries

Only needed when changing sources or parameters — the built dictionaries are
committed under `assets/`.

```sh
cd pipeline
make setup      # one-time: install nltk + WordNet corpora
make all        # build every pack into pipeline/data/
make publish    # copy the shippable subset into ../assets/dictionaries/
```

## Tests

```sh
python3 -m unittest discover -s tests        # game-runtime (worddata)
make -C pipeline test                        # build-time pipeline
```
