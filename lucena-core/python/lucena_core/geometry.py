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


# ---- the SEE discount (2026-07-24) -----------------------------------------
# Owner-found bug: every geometric read that COUNTS ATTACKERS credited
# pieces that are not going to be on the board. The motivating case was a
# king-safety score of 254 (near the top of the observed range) driven by
# a queen on d3 that was simply hanging — White was in check and Kxd3
# (SEE +900) won it outright on the very next move. The "danger" had a
# one-move lifespan; the formula priced it like a permanent siege.
#
# The fix is one primitive, applied everywhere pressure is counted: a
# piece the enemy can win outright (SEE > 0) does not get full credit for
# the pressure it currently exerts.
#
#   owner NOT to move -> weight 0.0   (the enemy simply takes it now)
#   owner IS to move  -> weight 0.5   (it survives, but must spend its
#                                      move fleeing — the pressure it
#                                      exerts right now is transient)
LOOSE_WEIGHT_TO_MOVE = 0.5


def loose_map(b: chess.Board) -> dict[int, float]:
    """square -> pressure weight in [0, 1] for the piece standing there.

    Only LOOSE pieces (best enemy capture has SEE > 0) appear; everything
    absent from the map is worth its full weight. Kings are never in the
    map (they cannot be captured).

    Uses `see._see_move` directly, which derives the capturing side from
    the piece's own color — so this needs no null move and works while in
    check (where a null move is illegal, and where the motivating bug
    actually lived)."""
    from .see import _see_move

    out: dict[int, float] = {}
    for sq in chess.scan_forward(b.occupied):
        pc = b.piece_at(sq)
        if pc is None or pc.piece_type == chess.KING:
            continue
        best = 0
        for a in b.attackers(not pc.color, sq):
            v = _see_move(b, a, sq)
            if v > best:
                best = v
        if best > 0:
            out[sq] = LOOSE_WEIGHT_TO_MOVE if b.turn == pc.color else 0.0
    return out


def loose_weight(loose: dict[int, float] | None, sq: int) -> float:
    """Pressure weight for the piece on `sq`; 1.0 when undiscounted (or
    when no map was supplied — every caller stays correct by default)."""
    return 1.0 if loose is None else loose.get(sq, 1.0)


# ---- mobility: the Stockfish model, verbatim (2026-07-24) ------------------
# Owner ruling: "do the right thing / what engines actually do". ACTIVITY is
# mobility, and Stockfish is the reference implementation — PeSTO has no
# mobility term ON PURPOSE (it folds positional knowledge into the PSTs
# precisely so it never has to compute one), so asking PeSTO for activity
# asks it for the thing it opted out of.
#
# `MobilityBonus` below is Stockfish's own table (evaluate.cpp), copied
# verbatim as (mg, eg) per mobility count — never re-tuned here, same
# discipline as the PeSTO constants. The non-linearity IS the knowledge:
# the first few safe squares are worth far more than the twentieth.
MOBILITY_BONUS = {
    "N": [(-62, -79), (-53, -57), (-12, -31), (-3, -17), (3, 7), (12, 13),
          (21, 16), (28, 21), (37, 26)],
    "B": [(-47, -59), (-20, -25), (14, -8), (29, 12), (39, 21), (53, 40),
          (53, 56), (60, 58), (62, 65), (69, 72), (78, 78), (83, 87),
          (91, 88), (96, 98)],
    "R": [(-60, -82), (-24, -15), (0, 17), (3, 43), (4, 72), (14, 100),
          (20, 102), (30, 122), (41, 133), (41, 139), (41, 153), (45, 160),
          (57, 165), (58, 170), (67, 175)],
    "Q": [(-29, -49), (-16, -29), (-8, -8), (-8, 17), (18, 39), (25, 54),
          (23, 59), (37, 73), (41, 76), (54, 95), (65, 95), (68, 101),
          (69, 124), (70, 128), (70, 132), (70, 133), (71, 136), (72, 140),
          (74, 147), (76, 149), (90, 153), (104, 169), (105, 171),
          (106, 171), (112, 178), (114, 185), (114, 187), (119, 221)],
}
_SYM = {chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R",
        chess.QUEEN: "Q"}


def mobility_area(b: chess.Board, color: bool) -> chess.SquareSet:
    """Stockfish's mobility area for `color`: every square EXCEPT those
    attacked by enemy pawns, occupied by our own blocked pawns or pawns on
    our 2nd/3rd rank, or occupied by our king or queen.

    That exclusion set is the whole point — raw "squares attacked" counts
    squares a piece cannot actually use, which is why bare attack-counting
    reads a cramped position as active."""
    excluded = chess.SquareSet()
    # our pawns that are blocked, or sitting on our low ranks
    for s in b.pieces(chess.PAWN, color):
        ahead = s + (8 if color == chess.WHITE else -8)
        blocked = 0 <= ahead <= 63 and b.piece_at(ahead) is not None
        if blocked or side_rank(s, color) in (1, 2):
            excluded.add(s)
    for pt in (chess.KING, chess.QUEEN):
        for s in b.pieces(pt, color):
            excluded.add(s)
    for s in b.pieces(chess.PAWN, not color):       # enemy pawn attacks
        excluded |= b.attacks(s)
    return ~excluded


def piece_mobility(b: chess.Board, sq: int, color: bool,
                   area: chess.SquareSet | None = None) -> int:
    """Safe squares this piece attacks (Stockfish's `mob`)."""
    if area is None:
        area = mobility_area(b, color)
    return len(b.attacks(sq) & area)


def mobility_bonus(piece: str, mob: int, phase: float) -> float:
    """The tapered Stockfish MobilityBonus for `mob` safe squares."""
    tbl = MOBILITY_BONUS[piece]
    mg, eg = tbl[min(mob, len(tbl) - 1)]
    return mg * phase + eg * (1.0 - phase)


def mobility_norm(piece: str, mob: int, phase: float) -> float:
    """Mobility as 0-1 inside this piece type's OWN bonus table — 0 = fully
    smothered, 1 = the most Stockfish's table rewards. Normalizing within
    the type is what makes a knight and a rook comparable at all."""
    tbl = MOBILITY_BONUS[piece]
    vals = [mg * phase + eg * (1.0 - phase) for mg, eg in tbl]
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (mobility_bonus(piece, mob, phase) - lo)
                        / (hi - lo)))


def control_share(b: chess.Board, sq: int,
                  loose: dict[int, float] | None = None) -> float:
    """White's control share of one square: attacker counts + occupation
    (a pawn counts double — the cheapest, most permanent controller).
    0.5 = contested/empty. The one copy behind region_control and
    color_complex.

    `loose` (from `loose_map`) discounts attackers/occupiers that are
    themselves hanging — control asserted by a doomed piece is not
    control. Omit it to get the raw pre-2026-07-24 reading."""
    w = sum(loose_weight(loose, a) for a in b.attackers(chess.WHITE, sq))
    blk = sum(loose_weight(loose, a) for a in b.attackers(chess.BLACK, sq))
    pc = b.piece_at(sq)
    if pc is not None:
        bonus = 2 if pc.piece_type == chess.PAWN else 1
        bonus *= loose_weight(loose, sq)
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
