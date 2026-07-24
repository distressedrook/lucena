"""Opening theory from Wikibooks *Chess Opening Theory* — a bundled,
FEN-keyed snapshot (`data/wikibooks_theory.json`, produced by
`tools/wikibooks_harvest.py`).

The coach shows this VERBATIM with attribution (`source_url`) — the text
is CC BY-SA and is never model-adapted, so share-alike stays clear of our
code. Presence of an entry is also the gate the caller uses to prefer book
theory over the positional read ("if it has a Wikibooks entry, show the
theory, not the analysis").

FEN identity is shared with `openings.py`: exact on the first four FEN
fields (`_fen.norm_fen`), then an en-passant-stripped fallback so a FEN
written with the legal-only ep convention (Lichess/chess.com/python-chess)
still resolves. Same reasoning as `openings._ep_stripped_table`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ._fen import norm_fen as _norm

_PATH = Path(__file__).resolve().parent / "data" / "wikibooks_theory.json"


@lru_cache(maxsize=1)
def _entries() -> dict[str, dict]:
    """FEN (4-field identity) -> theory entry. A missing/broken file
    degrades to "no theory" LOUDLY rather than breaking the coach — the
    same failure discipline as openings._table."""
    try:
        raw = json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"[theory] table not readable at {_PATH} — opening theory "
              "disabled", flush=True)
        return {}
    out: dict[str, dict] = {}
    for fen, entry in (raw.get("entries") or {}).items():
        out[_norm(fen)] = entry
    return out


@lru_cache(maxsize=1)
def _ep_stripped() -> dict[str, dict]:
    """Fallback index keyed WITHOUT ep (first three FEN fields). Ambiguous
    keys (two positions differing only by ep) are EXCLUDED rather than
    guessed — mirrors openings._ep_stripped_table."""
    by_stripped: dict[str, list[dict]] = {}
    for key, entry in _entries().items():
        by_stripped.setdefault(" ".join(key.split()[:3]), []).append(entry)
    return {k: v[0] for k, v in by_stripped.items() if len(v) == 1}


def theory_for(fen: str) -> dict | None:
    """The Wikibooks theory entry for a position, or None.

    Entry shape: ``{name, eco, description, responses, moves, source_url}``.
    `description` is the verbatim lead prose; `source_url` is its CC BY-SA
    attribution and MUST be shown wherever the text is. Exact match first,
    then ep-stripped (see module docstring)."""
    key = _norm(fen)
    hit = _entries().get(key)
    if hit is not None:
        return hit
    return _ep_stripped().get(" ".join(key.split()[:3]))


def has_theory(fen: str) -> bool:
    """Whether a position has a Wikibooks theory entry — the gate a caller
    uses to suppress the positional read in favour of the book."""
    return theory_for(fen) is not None
