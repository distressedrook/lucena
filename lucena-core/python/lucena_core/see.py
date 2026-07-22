"""Static exchange evaluation on python-chess bitboards.

A line-for-line port of the retired Rust implementation
(`lucena-engine/rust/src/see.rs`, cozy-chess era): swap algorithm with
least-valuable-attacker ordering and x-ray/battery re-inclusion — slider
attacks are recomputed against the shrinking occupancy, so a rook behind a
rook joins the exchange automatically. Promotions are valued as the moving
pawn (documented simplification: good enough for fact salience, not a search
heuristic). Pins are invisible by contract (a pinned defender still counts).

The port is gated by the original's 26 hand-minimaxed tests
(tests/test_see.py, tests/test_see_adversarial.py) and a differential run
against the Rust `see_move` over a tactical corpus slice
(lucena-tactics/research/experiments/differential.py) — see
lucena-tactics/docs/MIGRATION.md.
"""
from __future__ import annotations

import chess

VALUES = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300,
          chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20_000}


def _attackers_to(b: chess.Board, sq: int, occ: int) -> int:
    """All pieces (both colors) attacking `sq`, given occupancy `occ`.
    Sliders are computed against `occ`, which is what makes x-rays work as
    the exchange peels pieces off. Piece placement is read from the ORIGINAL
    board — pieces never move in the swap model, they only leave occupancy."""
    bishops = b.bishops | b.queens
    rooks = b.rooks | b.queens
    atk = 0
    # A white pawn standing on `sq` attacks exactly the squares from which
    # black pawns attack `sq` (mirror trick), and vice versa.
    atk |= chess.BB_PAWN_ATTACKS[chess.WHITE][sq] & b.pawns & b.occupied_co[chess.BLACK]
    atk |= chess.BB_PAWN_ATTACKS[chess.BLACK][sq] & b.pawns & b.occupied_co[chess.WHITE]
    atk |= chess.BB_KNIGHT_ATTACKS[sq] & b.knights
    atk |= chess.BB_KING_ATTACKS[sq] & b.kings
    atk |= chess.BB_DIAG_ATTACKS[sq][occ & chess.BB_DIAG_MASKS[sq]] & bishops
    atk |= (chess.BB_RANK_ATTACKS[sq][occ & chess.BB_RANK_MASKS[sq]]
            | chess.BB_FILE_ATTACKS[sq][occ & chess.BB_FILE_MASKS[sq]]) & rooks
    return atk & occ


def _least_valuable(b: chess.Board, mask: int) -> tuple[int, int] | None:
    """(square, piece_type) of the least valuable piece in `mask`; ascending
    square order breaks ties, matching the Rust iteration order."""
    best: tuple[int, int] | None = None
    for sq in chess.scan_forward(mask):
        p = b.piece_type_at(sq)
        if best is not None and VALUES[p] >= VALUES[best[1]]:
            continue
        best = (sq, p)
    return best


def _see_move(b: chess.Board, from_sq: int, to_sq: int) -> int:
    """SEE for moving the piece on `from_sq` to `to_sq`. Positive = the
    exchange wins material for the side to move (centipawns). Handles en
    passant, x-rays, and the king-can't-be-recaptured-into-check guard."""
    mover = b.piece_type_at(from_sq)
    if mover is None:
        raise ValueError(f"SEE: no piece on {chess.square_name(from_sq)}")
    us = b.color_at(from_sq)

    occ = b.occupied
    gain = [0] * 32
    d = 0

    # Initial capture value; en passant captures a pawn not on `to_sq`.
    victim = b.piece_type_at(to_sq)
    if victim is not None:
        gain[0] = VALUES[victim]
    elif mover == chess.PAWN and b.ep_square is not None and to_sq == b.ep_square:
        cap_sq = to_sq - 8 if us == chess.WHITE else to_sq + 8
        occ ^= chess.BB_SQUARES[cap_sq]      # remove the actual captured pawn
        gain[0] = VALUES[chess.PAWN]

    attacker_value = VALUES[mover]
    occ ^= chess.BB_SQUARES[from_sq]
    side = not us

    while True:
        atts = _attackers_to(b, to_sq, occ) & b.occupied_co[side]
        lv = _least_valuable(b, atts)
        if lv is None:
            break
        sq, piece = lv
        # A king may only take if the opponent has no remaining attacker
        # (it could not legally step into a defended square).
        if piece == chess.KING:
            opp = _attackers_to(b, to_sq, occ ^ chess.BB_SQUARES[sq]) \
                & b.occupied_co[not side]
            if opp & ~chess.BB_SQUARES[sq]:
                break
        d += 1
        gain[d] = attacker_value - gain[d - 1]
        # Pruning: if neither continuing nor stopping can help, stop.
        if max(-gain[d - 1], gain[d]) < 0:
            break
        attacker_value = VALUES[piece]
        occ ^= chess.BB_SQUARES[sq]
        side = not side

    while d > 0:
        gain[d - 1] = -max(-gain[d - 1], gain[d])
        d -= 1
    return gain[0]


def see(fen: str, move: str) -> int:
    """SEE in centipawns for `move` (UCI or SAN) in `fen`.

    The move must be legal — facts are only ever computed over legal
    candidates, so an illegal move raises ValueError (same contract as the
    Rust `see_move`)."""
    b = chess.Board(fen)
    if len(move) in (4, 5) and move[0] in "abcdefgh" and move[1] in "12345678" \
            and move[2] in "abcdefgh" and move[3] in "12345678":
        try:
            mv = chess.Move.from_uci(move)
        except ValueError as e:
            raise ValueError(f"illegal move {move!r} in {fen}") from e
    else:
        mv = b.parse_san(move)               # raises ValueError subclasses
    if mv not in b.legal_moves:
        raise ValueError(f"illegal move {move!r} in {fen}")
    return _see_move(b, mv.from_square, mv.to_square)
