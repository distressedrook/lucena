"""book_voice._book_route — the freeform opening-narration cadence policy (pure, no LLM/engine).

`_book_route` is a pure function: the cadence is tested by REPLAYING real openings through it and
asserting the exact fire sequence. This is where the coarsening regressions are pinned (the Open
Sicilian going silent, the shallow-family hand-off). Salvaged from the retired test_opening_narration
when the Orchestrator was deleted; the book-route logic itself is unchanged.
"""

from __future__ import annotations

from lucena_backend.coaching.book_voice import (
    _book_route, _is_swing, _NARRATE, _ENDBOOK, _COACH, _OFF_BOOK_AT, _MIN_FAMILY_SIZE,
)
from lucena_backend.coaching.freeform import _mover
from lucena_engine.board import Board
from lucena_engine import openings


def _fens(*ucis: str) -> list:
    """Replay a line from the start position, returning [start, ...after each ply] — through the REAL
    board core (not FEN literals), so the test stays pinned to the core's en-passant convention that
    keys the opening table."""
    b = Board(START)
    out = [START]
    for u in ucis:
        b = b.apply(u)
        out.append(b.fen)
    return out


def _routes(ucis: list, swing: bool = False) -> list:
    """The route for each ply of a line, as (uci, route, name)."""
    fens = _fens(*ucis)
    return [(ucis[i - 1],) + _book_route(fens[: i + 1], swing)[:2] for i in range(1, len(fens))]

