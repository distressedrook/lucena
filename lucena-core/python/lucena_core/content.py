"""Authored content accessors — quotes, trivia, opening annotations/Socratic Q&A.

The authoring source of truth is the superrepo's /content (fact-checked by a
research agent, every entry sourced); this package ships synced copies in
data/ and exposes them read-only. All lookups are deterministic; the quote
pick is SEEDED so a session keeps its epigraph (book behavior, not a
slot machine). Validated on load-elsewhere: 112 opening entries, 0 bad fens,
0 name-table mismatches; 235 quotes + 295 trivia, all sourced (2026-07-24).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=1)
def _load(name: str) -> dict:
    with open(_DATA / name, encoding="utf-8") as fh:
        return json.load(fh)


def annotation_for(opening_name: str) -> str | None:
    """Authored prose for a named opening (112 covered), or None."""
    e = _load("openings_annotations.json").get(opening_name)
    return e.get("text") if e else None


def socratic_for(opening_name: str) -> list[dict] | None:
    """Authored Socratic Q&A beats for a named opening, or None."""
    e = _load("openings_socratic.json").get(opening_name)
    return e.get("qa") if e else None


def quotes() -> list[dict]:
    """All fact-checked quotes: {quote, author, author_role, source, year}."""
    return _load("chess_quotes_trivia.json")["quotes"]


def trivia() -> list[dict]:
    """All fact-checked trivia: {fact, category, source}."""
    return _load("chess_quotes_trivia.json")["trivia"]


def epigraph(seed: str) -> dict:
    """A deterministic quote pick for `seed` (game id / date string) — the
    move-1 epigraph. Same seed, same quote: a book keeps its epigraph."""
    qs = quotes()
    return qs[sum(seed.encode()) % len(qs)]


def trivium(seed: str, category: str | None = None) -> dict:
    """A deterministic trivia pick, optionally category-scoped."""
    ts = trivia()
    if category:
        ts = [t for t in ts if t["category"] == category] or trivia()
    return ts[sum(seed.encode()) % len(ts)]
