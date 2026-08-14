#!/usr/bin/env python3
"""Phase 2 for the Russian pack: ru.wiktionary definitions + answer-eligibility.

Russian has no WordNet, so meaning/sense data comes from Russian Wiktionary via the
MediaWiki API. Two jobs, both driven by that one lookup (mirrors the English chain
of WordNet+Wiktionary senses):

  1. Definitions -> assets/dictionaries/russian/dictionary.jsonl gets real senses,
     so the in-game '?' shows a gloss instead of 'no definition'. Covers every
     allowed guess (a player can guess any valid word).
  2. Answer eligibility -> filter tiers.json. A word is answer-eligible iff it has a
     RUSSIAN part-of-speech category (существительное/прилагательное/глагол/наречие/
     числительное) AND is not obscene. This keeps real words that merely look like
     names (карла='карлик', стоун=unit of mass) while dropping proper-noun-only
     entries (москва = Топонимы only, no Russian-noun category; lowercase names are
     simply absent from Wiktionary) and gating мат/vulgar terms. Words stay valid
     GUESSES either way — only the ANSWER pool is filtered.

Results are cached in data/cache/ru_wiktionary.json (committed, so rebuilds are
offline and don't re-hit Wikimedia). Re-run to fetch only newly-added words.

Run:  python3 scripts/enrich_russian.py [--assets DIR] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://ru.wiktionary.org/w/api.php"
UA = "yawop-dict/0.2 (personal Wordle-style game; https://github.com/anverx/yawop)"
BATCH = 40

# --- category signals for eligibility ---
def _russian_pos(cats: list[str]) -> str:
    """The word's Russian part of speech (label) if it has a Russian POS category."""
    pos = [("существительное", "существительн"), ("прилагательное", "прилагательн"),
           ("глагол", "глагол"), ("наречие", "наречи"), ("числительное", "числительн")]
    for c in cats:
        if "Русск" in c:
            for label, key in pos:
                if key in c:
                    return label
    return ""


_OBSCENE = re.compile(r"Бранные|Вульгаризм|Обсценн|Русский мат|Оскорблени|Табуированн")


def is_obscene(cats: list[str]) -> bool:
    return any(_OBSCENE.search(c) for c in cats)


# --- wikitext -> clean glosses (the 'Значение' section of the Russian entry) ---
def _clean(s: str) -> str:
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)  # [[a|b]] -> b
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)            # [[a]] -> a
    for _ in range(3):                                   # nested {{...}}
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"''+", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s*\[\d+\]", "", s)                     # trailing sense refs [1]
    s = re.sub(r"\s*\{\{.*$", "", s)                     # dangling unclosed {{template
    s = re.sub(r"\s*\}\}.*$", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .,;—- ")


def glosses(wikitext: str) -> list[str]:
    parts = re.split(r"\n=\s*\{\{-ru-\}\}", wikitext)
    body = parts[1] if len(parts) > 1 else wikitext
    m = re.search(r"=+\s*Значение\s*=+(.*?)(\n=+[^=]|\Z)", body, re.S)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith("#") and not line.startswith("#*") and not line.startswith("#:"):
            g = _clean(line.lstrip("# ").strip())
            if g and len(g) > 1:
                out.append(g)
    return out


_last_continue: dict | None = None


def _api(params: dict) -> dict:
    """One query request; stash any continuation block for the caller to resume."""
    global _last_continue
    params = dict(params, format="json", action="query")
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=60))
            _last_continue = data.get("continue")
            return data.get("query", {})
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def _title_map(q: dict, batch: list[str]) -> dict:
    """word -> resolved page title (following normalize + redirect, e.g. актер->актёр)."""
    norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
    redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
    return {w: redir.get(norm.get(w, w), norm.get(w, w)) for w in batch}


def _fetch_glosses(batch: list[str]) -> dict:
    q = _api(dict(redirects=1, prop="revisions", rvprop="content", rvslots="main",
                  titles="|".join(batch)))
    tmap = _title_map(q, batch)
    pages = {p["title"]: p for p in q.get("pages", {}).values()}
    out = {}
    for w in batch:
        p = pages.get(tmap[w])
        try:
            out[w] = glosses(p["revisions"][0]["slots"]["main"]["*"]) if p and "revisions" in p else []
        except Exception:  # noqa: BLE001
            out[w] = []
    return out


def _fetch_categories(batch: list[str]) -> dict:
    """Categories per word, FOLLOWING continuation — a batched prop=categories query
    caps total categories per response, so without this most pages come back empty."""
    by_title: dict[str, list[str]] = {}
    params = dict(redirects=1, prop="categories", cllimit="max", titles="|".join(batch))
    tmap = None
    while True:
        q = _api(params)
        if tmap is None:
            tmap = _title_map(q, batch)
        for p in q.get("pages", {}).values():
            by_title.setdefault(p["title"], []).extend(
                c["title"].replace("Категория:", "") for c in p.get("categories", []))
        if _last_continue:
            params.update(_last_continue)
        else:
            break
    return {w: by_title.get(tmap[w], []) for w in batch}


def fetch(words: list[str], cache: dict) -> None:
    need_gloss = [w for w in words if "glosses" not in cache.get(w, {})]
    need_cats = [w for w in words if not cache.get(w, {}).get("cats_done")]
    print(f"ru.wiktionary: {len(words)} words | {len(need_gloss)} glosses, {len(need_cats)} categories to fetch",
          file=sys.stderr)
    for i in range(0, len(need_gloss), BATCH):
        batch = need_gloss[i:i + BATCH]
        gl = _fetch_glosses(batch)
        for w in batch:
            cache.setdefault(w, {})["glosses"] = gl[w]
        time.sleep(0.3)
        if i % (BATCH * 10) == 0:
            print(f"  glosses {min(i + BATCH, len(need_gloss))}/{len(need_gloss)}", file=sys.stderr)
    for i in range(0, len(need_cats), BATCH):
        batch = need_cats[i:i + BATCH]
        cats = _fetch_categories(batch)
        for w in batch:
            e = cache.setdefault(w, {})
            e["cats"] = cats[w]
            e["cats_done"] = True
        time.sleep(0.3)
        if i % (BATCH * 10) == 0:
            print(f"  categories {min(i + BATCH, len(need_cats))}/{len(need_cats)}", file=sys.stderr)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assets", default=str(root / "assets" / "dictionaries"))
    ap.add_argument("--cache", default=str(root / "pipeline" / "data" / "cache" / "ru_wiktionary.json"))
    ap.add_argument("--limit", type=int, default=0, help="fetch at most N new words (0 = all)")
    args = ap.parse_args()

    pack = Path(args.assets) / "russian"
    allowed = [w.strip() for w in (pack / "allowed_guesses.txt").read_text("utf-8").splitlines() if w.strip()]
    tiers_data = json.loads((pack / "tiers.json").read_text("utf-8"))

    cache_path = Path(args.cache)
    cache = json.loads(cache_path.read_text("utf-8")) if cache_path.exists() else {}
    words = allowed if not args.limit else allowed[:args.limit]
    fetch(words, cache)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    # 1. dictionary.jsonl — real senses for every guessable word that has them.
    with (pack / "dictionary.jsonl").open("w", encoding="utf-8") as f:
        for w in allowed:
            info = cache.get(w, {})
            pos = _russian_pos(info.get("cats", []))
            # re-run _clean: cached glosses predate the dangling-template hardening
            senses = [{"pos_label": pos, "definition": d, "source": "ru.wiktionary"}
                      for d in (_clean(g) for g in info.get("glosses", [])) if len(d) > 1]
            f.write(json.dumps({"word": w, "senses": senses}, ensure_ascii=False) + "\n")

    # 2. tiers.json — keep only answer-eligible words (Russian POS, not obscene).
    def eligible(w: str) -> bool:
        cats = cache.get(w, {}).get("cats", [])
        return bool(_russian_pos(cats)) and not is_obscene(cats)

    dropped_name = dropped_obscene = 0
    new_tiers = {}
    for tier, ws in tiers_data["tiers"].items():
        kept = []
        for w in ws:
            if eligible(w):
                kept.append(w)
            elif is_obscene(cache.get(w, {}).get("cats", [])):
                dropped_obscene += 1
            else:
                dropped_name += 1
        new_tiers[tier] = kept
    was = sum(len(v) for v in new_tiers.values()) + dropped_name + dropped_obscene
    tiers_data["tiers"] = new_tiers
    tiers_data["counts"] = {t: len(v) for t, v in new_tiers.items()}
    (pack / "tiers.json").write_text(json.dumps(tiers_data, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(v) for v in new_tiers.values())
    defined = sum(1 for w in allowed if cache.get(w, {}).get("glosses"))
    print(f"russian: answers {total} (was {was}); "
          f"dropped {dropped_name} non-eligible (names/toponyms/absent) + {dropped_obscene} obscene",
          file=sys.stderr)
    print(f"  definitions: {defined}/{len(allowed)} guessable words have a gloss", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
