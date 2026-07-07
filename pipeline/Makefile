# yawod word-pack pipeline
#
# Four game options (packs):
#   subtlex-us  frequency-tiered, American subtitle corpus
#   subtlex-uk  frequency-tiered, British subtitle corpus
#   wordle      official NYT list, tiered by borrowed SUBTLEX-US frequency
#   surprise    union of all packs, no tiers, no rank merge
#
# Each stage reads one file and writes another; re-running only redoes stages
# whose inputs changed. `make clean` removes generated data (keeps the API cache).
#
# Usage:  make setup   # one-time: install nltk + WordNet corpora
#         make all     # build every pack
#         make subtlex-us | subtlex-uk | wordle | surprise | guesses

PY    := python3
CACHE := data/cache/dictionaryapi.json

# Max NEW Free Dictionary API lookups per pack (cached words are free). Tune freely.
US_MAX_API        ?= 800
UK_MAX_API        ?= 1500
WORDLE_MAX_API    ?= 500
GUTENBERG_MAX_API ?= 500

# Difficulty tier boundaries (cumulative fractions): easy top 15%, medium up to 40%.
EASY   ?= 0.15
MEDIUM ?= 0.40

# Arcane pack: subtract only the top-N most frequent SUBTLEX words (so archaic
# words rarely seen in modern subtitles survive). ~4000 yields ~1000 clean words.
ARCANE_SUBTRACT_TOP ?= 4000

# Where the finished dictionaries are published for the game to ship with.
ASSETS := ../assets/dictionaries
TIERED_PACKS := subtlex-us subtlex-uk wordle arcane

.PHONY: all setup clean clean-cache help test publish \
        subtlex-us subtlex-uk wordle surprise guesses gutenberg arcane

test:
	$(PY) -m unittest discover -s tests -v

help:
	@echo "Game packs: subtlex-us | subtlex-uk | wordle | surprise | arcane"
	@echo "Targets:    setup | all | <pack> | guesses | gutenberg | publish | test | clean | clean-cache"
	@echo "Vars:       US_MAX_API=$(US_MAX_API) UK_MAX_API=$(UK_MAX_API) WORDLE_MAX_API=$(WORDLE_MAX_API) GUTENBERG_MAX_API=$(GUTENBERG_MAX_API) EASY=$(EASY) MEDIUM=$(MEDIUM)"

# Copy only the shippable files into assets/dictionaries/ (what the game bundles).
# Working intermediates and caches under data/ stay behind.
publish: all
	@mkdir -p $(ASSETS)
	@for p in $(TIERED_PACKS); do \
	  mkdir -p $(ASSETS)/$$p; \
	  cp data/$$p/dictionary.jsonl data/$$p/tiers.json $(ASSETS)/$$p/; \
	done
	@cp data/wordle/allowed_guesses.txt $(ASSETS)/wordle/
	@mkdir -p $(ASSETS)/surprise
	@cp data/surprise/dictionary.jsonl data/surprise/words.txt $(ASSETS)/surprise/
	@cp data/allowed_guesses_all.txt $(ASSETS)/
	$(PY) scripts/apply_blocklist.py --assets $(ASSETS) --slurs blocklist_slurs.txt
	@cp blocklist_solutions.txt $(ASSETS)/   # runtime filter: excluded from solutions unless the player opts in
	$(PY) scripts/build_extra_defs.py --allowed $(ASSETS)/allowed_guesses_all.txt --assets $(ASSETS) --wiktionary-cache data/cache/wiktionary_defs.json --out $(ASSETS)/extra_defs.jsonl
	@echo "published shipping dictionaries -> $(ASSETS)"

all: subtlex-us subtlex-uk wordle surprise arcane guesses

setup:
	$(PY) -m pip install --user --break-system-packages -q nltk
	$(PY) -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"

# ---- pack wrappers (depend on each pack's final artifact) --------------------
subtlex-us: data/subtlex-us/tiers.json
subtlex-uk: data/subtlex-uk/tiers.json
wordle:     data/wordle/tiers.json
surprise:   data/surprise/dictionary.jsonl
arcane:     data/arcane/tiers.json data/arcane/dictionary.jsonl
gutenberg:  data/gutenberg/dictionary.jsonl
guesses:    data/allowed_guesses_all.txt

# ---- SUBTLEX-US --------------------------------------------------------------
data/subtlex-us/words_ranked.txt:
	$(PY) scripts/fetch.py --pack subtlex-us --out-dir data/subtlex-us

data/subtlex-us/dict.wordnet.jsonl: data/subtlex-us/words_ranked.txt
	$(PY) scripts/build_dictionary.py --words $< --out $@

data/subtlex-us/dict.filled.jsonl: data/subtlex-us/dict.wordnet.jsonl
	$(PY) scripts/fill_gaps.py --in $< --out $@ --cache $(CACHE) --max-api $(US_MAX_API)

data/subtlex-us/dictionary.jsonl data/subtlex-us/puzzle_words.txt data/subtlex-us/undefined_words.txt &: data/subtlex-us/dict.filled.jsonl
	$(PY) scripts/prune_undefined.py --in $< \
	  --out-dict data/subtlex-us/dictionary.jsonl \
	  --out-words data/subtlex-us/puzzle_words.txt \
	  --out-undefined data/subtlex-us/undefined_words.txt

data/subtlex-us/tiers.json: data/subtlex-us/puzzle_words.txt
	$(PY) scripts/assign_tiers.py --words $< --out $@ --easy $(EASY) --medium $(MEDIUM)

# ---- SUBTLEX-UK --------------------------------------------------------------
data/subtlex-uk/words_ranked.txt:
	$(PY) scripts/fetch.py --pack subtlex-uk --out-dir data/subtlex-uk

data/subtlex-uk/dict.wordnet.jsonl: data/subtlex-uk/words_ranked.txt
	$(PY) scripts/build_dictionary.py --words $< --out $@

data/subtlex-uk/dict.filled.jsonl: data/subtlex-uk/dict.wordnet.jsonl
	$(PY) scripts/fill_gaps.py --in $< --out $@ --cache $(CACHE) --max-api $(UK_MAX_API)

data/subtlex-uk/dictionary.jsonl data/subtlex-uk/puzzle_words.txt data/subtlex-uk/undefined_words.txt &: data/subtlex-uk/dict.filled.jsonl
	$(PY) scripts/prune_undefined.py --in $< \
	  --out-dict data/subtlex-uk/dictionary.jsonl \
	  --out-words data/subtlex-uk/puzzle_words.txt \
	  --out-undefined data/subtlex-uk/undefined_words.txt

data/subtlex-uk/tiers.json: data/subtlex-uk/puzzle_words.txt
	$(PY) scripts/assign_tiers.py --words $< --out $@ --easy $(EASY) --medium $(MEDIUM)

# ---- Wordle (official) -------------------------------------------------------
data/wordle/answers.txt data/wordle/allowed_guesses.txt &:
	$(PY) scripts/fetch.py --pack wordle --out-dir data/wordle

data/wordle/dict.wordnet.jsonl: data/wordle/answers.txt
	$(PY) scripts/build_dictionary.py --words $< --out $@

data/wordle/dict.filled.jsonl: data/wordle/dict.wordnet.jsonl
	$(PY) scripts/fill_gaps.py --in $< --out $@ --cache $(CACHE) --max-api $(WORDLE_MAX_API)

data/wordle/dictionary.jsonl data/wordle/puzzle_words.txt data/wordle/undefined_words.txt &: data/wordle/dict.filled.jsonl
	$(PY) scripts/prune_undefined.py --in $< \
	  --out-dict data/wordle/dictionary.jsonl \
	  --out-words data/wordle/puzzle_words.txt \
	  --out-undefined data/wordle/undefined_words.txt

# Wordle has no frequency of its own: tier by SUBTLEX-US rank.
data/wordle/tiers.json: data/wordle/puzzle_words.txt data/subtlex-us/words_ranked.txt
	$(PY) scripts/assign_tiers.py --words $< --out $@ \
	  --rank-by data/subtlex-us/words_ranked.txt --easy $(EASY) --medium $(MEDIUM)

# ---- Gutenberg (internal ingredient for the arcane pack; not a game option) --
data/gutenberg/words_ranked.txt: wordlist.url
	$(PY) scripts/fetch.py --pack gutenberg --out-dir data/gutenberg

data/gutenberg/dict.wordnet.jsonl: data/gutenberg/words_ranked.txt
	$(PY) scripts/build_dictionary.py --words $< --out $@

data/gutenberg/dict.filled.jsonl: data/gutenberg/dict.wordnet.jsonl
	$(PY) scripts/fill_gaps.py --in $< --out $@ --cache $(CACHE) --max-api $(GUTENBERG_MAX_API)

data/gutenberg/dictionary.jsonl data/gutenberg/puzzle_words.txt data/gutenberg/undefined_words.txt &: data/gutenberg/dict.filled.jsonl
	$(PY) scripts/prune_undefined.py --in $< \
	  --out-dict data/gutenberg/dictionary.jsonl \
	  --out-words data/gutenberg/puzzle_words.txt \
	  --out-undefined data/gutenberg/undefined_words.txt

# ---- Arcane (Gutenberg MINUS SUBTLEX) : properly horrible --------------------
# Subtracts from Gutenberg's pre-prune WordNet dict: NO definition pruning, so
# even words WordNet/the API can't define survive (that's the point). No API
# fill needed here either.
data/arcane/dict.base.jsonl data/arcane/puzzle_words.txt &: data/gutenberg/dict.wordnet.jsonl data/subtlex-us/words_ranked.txt data/subtlex-uk/words_ranked.txt data/wordle/allowed_guesses.txt
	$(PY) scripts/subtract.py --minuend data/gutenberg/dict.wordnet.jsonl \
	  --subtract data/subtlex-us/words_ranked.txt data/subtlex-uk/words_ranked.txt \
	  --subtract-top $(ARCANE_SUBTRACT_TOP) \
	  --keep-in data/wordle/allowed_guesses.txt --keep-defined \
	  --out-dict data/arcane/dict.base.jsonl --out-words data/arcane/puzzle_words.txt

# Enrich with literary usage (Wikisource: work + author + context) + a Gutenberg link.
data/arcane/dictionary.jsonl: data/arcane/dict.base.jsonl
	$(PY) scripts/enrich_examples.py --in $< --out $@ --cache data/cache/wikisource.json

data/arcane/tiers.json: data/arcane/puzzle_words.txt
	$(PY) scripts/assign_tiers.py --words $< --out $@ --easy $(EASY) --medium $(MEDIUM)

# ---- Surprise me (union, no tiers) -------------------------------------------
data/surprise/dictionary.jsonl data/surprise/words.txt &: data/subtlex-us/dictionary.jsonl data/subtlex-uk/dictionary.jsonl data/wordle/dictionary.jsonl
	@mkdir -p data/surprise
	$(PY) scripts/combine_surprise.py --dicts $^ \
	  --out-dict data/surprise/dictionary.jsonl --out-words data/surprise/words.txt

# ---- Allowed-guess validation set --------------------------------------------
# Union of the DEFINED pack words (puzzle_words, post def-prune) plus Wordle's
# curated allowed-guess list. Deliberately NOT the raw words_ranked lists: those
# subtitle/OCR corpora carry proper nouns and junk (e.g. 'malet', a surname) that
# are never real playable words. 'palet' etc. survive via Wordle's curated list.
data/allowed_guesses_all.txt: data/subtlex-us/puzzle_words.txt data/subtlex-uk/puzzle_words.txt data/arcane/puzzle_words.txt data/wordle/allowed_guesses.txt
	sort -u $^ > $@

clean:
	rm -rf data/subtlex-us data/subtlex-uk data/wordle data/surprise data/arcane data/gutenberg data/allowed_guesses_all.txt

clean-cache:
	rm -f $(CACHE)
