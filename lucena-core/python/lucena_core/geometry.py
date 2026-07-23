"""Shared board-geometry primitives — the consolidation layer
(docs/METRICS_AUDIT.md, 2026-07-23): the six concepts that had grown 2-3
implementations across core and lucena-plans now live HERE, once. The
plans layer re-exports from this module (verbatim moves — the audited
definitions came from there); core's score family calls it directly.

Everything is python-chess-native (int squares, bool colors), pure and
deterministic.
"""
from __future__ import annotations

import chess


def side_rank(sq: int, side: bool) -> int:
    """Rank from `side`'s point of view (0 = home rank)."""
    r = chess.square_rank(sq)
    return r if side == chess.WHITE else 7 - r


def is_hole(b: chess.Board, sq: int, side: bool) -> bool:
    """No `side` pawn can EVER attack sq (own pawns attack toward higher
    side-relative ranks): no own pawn on an adjacent file strictly behind.
    Verbatim from lucena-plans weaknesses.py (the corpus-audited
    definition — outpost family lift 2.85)."""
    f, r = chess.square_file(sq), side_rank(sq, side)
    return not any(chess.square_file(p) in (f - 1, f + 1)
                   and side_rank(p, side) < r
                   for p in b.pieces(chess.PAWN, side))


def passers(b: chess.Board, side: bool) -> list[int]:
    """Passed pawns of `side`. Verbatim from lucena-plans
    plan_diff._passers."""
    enemy = b.pieces(chess.PAWN, not side)
    out = []
    for sq in b.pieces(chess.PAWN, side):
        f, r = chess.square_file(sq), side_rank(sq, side)
        if not any(abs(chess.square_file(s) - f) <= 1
                   and side_rank(s, not side) < 7 - r for s in enemy):
            out.append(sq)
    return out


def control_share(b: chess.Board, sq: int) -> float:
    """White's control share of one square: attacker counts + occupation
    (a pawn counts double — the cheapest, most permanent controller).
    0.5 = contested/empty. The one copy behind region_control and
    color_complex."""
    w = len(b.attackers(chess.WHITE, sq))
    blk = len(b.attackers(chess.BLACK, sq))
    pc = b.piece_at(sq)
    if pc is not None:
        bonus = 2 if pc.piece_type == chess.PAWN else 1
        if pc.color == chess.WHITE:
            w += bonus
        else:
            blk += bonus
    return w / (w + blk) if (w + blk) else 0.5


CENTRAL_FILES = (2, 3, 4, 5)


def center_skeleton(b: chess.Board) -> tuple[int, int]:
    """(central_rams, central_tension) on files c..f — the closed_v0
    skeleton, center-scoped (verbatim semantics from
    lucena-plans closed_v0.center_locked)."""
    wp = b.pieces(chess.PAWN, chess.WHITE)
    bp = b.pieces(chess.PAWN, chess.BLACK)
    rams = tension = 0
    for sq in wp:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        if sq + 8 < 64 and (sq + 8) in bp and f in CENTRAL_FILES:
            rams += 1
        for df in (-1, 1):
            if 0 <= f + df <= 7 and r + 1 <= 7 \
                    and chess.square(f + df, r + 1) in bp \
                    and (f in CENTRAL_FILES or f + df in CENTRAL_FILES):
                tension += 1
    return rams, tension


def center_locked(b: chess.Board) -> bool:
    """>= 2 central rams and ZERO central tension — no pawn capture can
    open a central file. The KEEP_KING_UNCASTLED trigger and the wing-
    attack precondition."""
    rams, tension = center_skeleton(b)
    return rams >= 2 and tension == 0


def king_zone(ek: int, defender: bool) -> set[int]:
    """The attack zone around `defender`'s king at `ek`: the ring plus two
    ranks toward the attacker (int-square twin of the CPW zone in
    positional._king_zone; attack_viability's zone, extracted)."""
    kf, kr = chess.square_file(ek), chess.square_rank(ek)
    fwd = -1 if defender == chess.WHITE else 1     # toward the defender's home
    zone = set()
    for df in (-1, 0, 1):
        for dr in (-1, 0, 1, 2 * -fwd):
            f, r = kf + df, kr + dr
            if 0 <= f <= 7 and 0 <= r <= 7 and (df or dr):
                zone.add(chess.square(f, r))
    return zone
