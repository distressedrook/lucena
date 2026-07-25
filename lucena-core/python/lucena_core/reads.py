"""Board-truth reads — pure functions of a position.

The deterministic facts the coach must never compute itself (piece roster,
material standing, eval-in-words, PV in SAN), plus the shared board-scan
primitives (PIECE_NAME, occupancy, king_square) absorbed from the old
detectors/_util during the 2026-07-23 core extraction — `positional` imports
them from here now, so the dependency direction (core never reaches into the
tactic layer) is correct forever. Moved from lucena-engine to lucena-core in
the same extraction; `poisoned_line_detector` (lucena-tactics) imports this
module externally.
"""

from __future__ import annotations

import chess as _c

from .board import Board
from lucena_engine.evalmodel import Score, win_pct_from_score

# Piece letters are SF/FEN convention, colour-stripped (Board.PieceOn.piece).
PIECE_NAME = {"P": "pawn", "N": "knight", "B": "bishop",
              "R": "rook", "Q": "queen", "K": "king"}


def occupancy(board) -> dict[str, object]:
    """square -> PieceOn for every occupied square (one piece_list scan)."""
    return {p.square: p for p in board.piece_list()}


def king_square(board, color: str) -> str | None:
    for p in board.piece_list():
        if p.piece == "K" and p.color == color:
            return p.square
    return None


_PIECE_ORDER = "KQRBNP"


def piece_list(board: Board) -> str:
    """Compact two-line roster: 'White: Ke1,Qd1,…\\nBlack: …' (fewest tokens)."""
    white, black = [], []
    for p in board.piece_list():
        (white if p.color == "white" else black).append(p)
    key = lambda p: (_PIECE_ORDER.index(p.piece), p.square)
    fmt = lambda ps: ",".join(f"{p.piece}{p.square}" for p in sorted(ps, key=key))
    return f"White: {fmt(white)}\nBlack: {fmt(black)}"


def eval_block(score: Score) -> dict:
    """Eval from the scored side's POV: `{cp, win_pct}` (win_pct 1 dp)."""
    return {
        "cp": score.to_ceiled_cp(),
        "win_pct": round(win_pct_from_score(score), 1),
    }


_MATERIAL_VALUE = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 0}
_VALUE_ORDER = ["Q", "R", "B", "N", "P"]     # heaviest first, for reading order
_PIECE_WORD = {"Q": "queen", "R": "rook", "B": "bishop", "N": "knight", "P": "pawn"}
_COUNT_WORD = {2: "two", 3: "three", 4: "four", 5: "five",
               6: "six", 7: "seven", 8: "eight"}


def material(board: Board) -> dict:
    """Deterministic material balance so the coach never *counts* (LLMs miscount —
    they'll claim "up a rook" with rooks on both sides). Returns each side's point
    total, the net (White POV, in pawns), and a plain-English `standing` the coach
    reads verbatim — the *exact* imbalance ("up a rook for two pawns"), never a
    number or a fuzzy bucket it has to interpret or hedge around."""
    white = black = 0
    counts = {"white": {pc: 0 for pc in _VALUE_ORDER},
              "black": {pc: 0 for pc in _VALUE_ORDER}}
    for p in board.piece_list():
        white += _MATERIAL_VALUE.get(p.piece, 0) if p.color == "white" else 0
        black += _MATERIAL_VALUE.get(p.piece, 0) if p.color == "black" else 0
        if p.piece in _PIECE_WORD:
            counts[p.color][p.piece] += 1
    net = white - black
    return {"white": white, "black": black, "net": net, "standing": _standing(counts)}


def _pieces_phrase(surplus: list[tuple[str, int]]) -> str:
    """"a rook", "two pawns", "a rook and a pawn", "a rook, a knight, and a pawn"."""
    parts = []
    for pc, n in surplus:
        word = _PIECE_WORD[pc]
        parts.append(f"a {word}" if n == 1 else f"{_COUNT_WORD.get(n, str(n))} {word}s")
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _standing(counts: dict) -> str:
    """The exact material imbalance in plain English. Cancels an even knight↔bishop
    trade (both minors, both 3) so a N-for-B swap reads as level rather than
    cluttering the phrase, then names precisely what each side has extra — a clean
    surplus ("up a rook"), the exchange ("up the exchange"), or an imbalance ("up a
    rook for two pawns")."""
    w, b = counts["white"], counts["black"]
    dw = {pc: max(0, w[pc] - b[pc]) for pc in _VALUE_ORDER}
    db = {pc: max(0, b[pc] - w[pc]) for pc in _VALUE_ORDER}
    for a, c in (("N", "B"), ("B", "N")):   # a minor-for-minor swap is even; cancel it
        t = min(dw[a], db[c])
        dw[a] -= t
        db[c] -= t
    w_up = [(pc, dw[pc]) for pc in _VALUE_ORDER if dw[pc] > 0]
    b_up = [(pc, db[pc]) for pc in _VALUE_ORDER if db[pc] > 0]
    if not w_up and not b_up:
        return "material is even"
    if not b_up:
        return f"White is up {_pieces_phrase(w_up)}"
    if not w_up:
        return f"Black is up {_pieces_phrase(b_up)}"
    # both sides have surplus -> an imbalance; lead with whoever is ahead on points
    pts = (sum(_MATERIAL_VALUE[pc] * n for pc, n in w_up)
           - sum(_MATERIAL_VALUE[pc] * n for pc, n in b_up))
    is_exchange = lambda more, less: more == [("R", 1)] and less in ([("N", 1)], [("B", 1)])
    if pts == 0:
        return (f"material is level but imbalanced — White has {_pieces_phrase(w_up)} "
                f"for Black's {_pieces_phrase(b_up)}")
    lead, comp, side = (w_up, b_up, "White") if pts > 0 else (b_up, w_up, "Black")
    if is_exchange(lead, comp):
        return f"{side} is up the exchange"
    return f"{side} is up {_pieces_phrase(lead)} for {_pieces_phrase(comp)}"


def pv_san(fen: str, pv: list[str], max_plies: int = 6) -> list[str]:
    out, b = [], Board(fen)
    for uci in pv[:max_plies]:
        try:
            out.append(b.san(uci))
            b = b.apply(uci)
        except Exception:
            break
    return out


# ---- game phase ------------------------------------------------------------
# (2026-07-23, owner-ratified design; REDEFINED 2026-07-25): the three
# boundaries are different KINDS of events, so the classifier is a hybrid —
# ENDGAME is a material event (max side non-pawn material, the plans layer's
# own threshold); OPENING is a DEVELOPMENT event; MIDDLEGAME is everything
# else. Single-FEN and deterministic; stream callers add hysteresis
# themselves (a game never returns to an earlier phase).
#
# The 2026-07-25 redefinition (owner: "the ply 20 isn't working ... be
# concrete about what opening means") dropped three things the old rule
# leaned on: the fullmove <= 20 window (a home bishop is undeveloped on move
# 30 too), book membership (being in the book is a fact about theory, not
# about this position's development), and the rooks-unconnected tell
# ("sometimes the rook may not be connected at all" — rooks get traded or go
# to open files and never connect). What is left is concrete geometry:
# minors on their original squares, and an uncastled king with rights.

_PHASE_NPM = {"Q": 9, "R": 5, "B": 3, "N": 3}
ENDGAME_NPM = 13          # same bar as lucena_backend.plans.service

# A minor's own ORIGINAL square — the concrete, unambiguous "undeveloped"
# test. Keyed by (color, piece type), not by back rank: a bishop that has
# come out to b1 is DEVELOPED even though b1 is a knight's home square.
_HOME_MINORS = {
    (_c.WHITE, _c.KNIGHT): {_c.B1, _c.G1},
    (_c.WHITE, _c.BISHOP): {_c.C1, _c.F1},
    (_c.BLACK, _c.KNIGHT): {_c.B8, _c.G8},
    (_c.BLACK, _c.BISHOP): {_c.C8, _c.F8},
}


def development_debts(board, color) -> dict:
    """One side's CONCRETE, ply-independent development debts: the minor
    pieces (knights/bishops) still on their ORIGINAL squares, plus an
    uncastled king that still holds castling rights.

    Deliberately NO rook-connection tell (owner 2026-07-25: "sometimes the
    rook may not be connected at all") — rooks get traded, or go to open
    files and never "connect", so back-rank connection is not a reliable
    development signal. And no ply cap: a home bishop is undeveloped whether
    it is move 8 or move 30.

    Returns {"minors": ["Bc8", ...], "uncastled": bool} — each minor as
    "<letter><square>", sorted, the same spelling every consumer prints;
    `board` is a python-chess Board.
    """
    minors = sorted(
        f"{board.piece_at(s).symbol().upper()}{_c.square_name(s)}"
        for pt in (_c.KNIGHT, _c.BISHOP)
        for s in board.pieces(pt, color)
        if s in _HOME_MINORS[(color, pt)])
    k = board.king(color)
    back = 0 if color == _c.WHITE else 7
    uncastled = (k is not None and _c.square_rank(k) == back
                 and _c.square_file(k) == 4
                 and board.has_castling_rights(color))
    return {"minors": minors, "uncastled": uncastled}


def _developed(board, color) -> bool:
    """A side has COMPLETED development when it has no minor on its home
    square and its king is castled or committed (no debts)."""
    d = development_debts(board, color)
    return not d["minors"] and not d["uncastled"]


def game_phase(fen: str) -> dict:
    """{'phase': 'opening'|'middlegame'|'endgame', 'why': str,
        'developed': {'white': bool, 'black': bool}}.

    Opening vs middlegame is decided by DEVELOPMENT — concretely, per side,
    and with NO ply cap (owner 2026-07-25: "the ply 20 isn't working ... be
    concrete about what opening means"). The game reaches the MIDDLEGAME the
    moment EITHER side has finished developing; the other side may still be
    developing, which `developed` reports per side so a lagging side's debt
    is still surfaced (owner: "the other team may not have completed the
    development"). Endgame is still material-gated and takes precedence.
    """
    b = _c.Board(fen)
    sym = {_c.QUEEN: "Q", _c.ROOK: "R", _c.BISHOP: "B", _c.KNIGHT: "N"}
    npm = {color: sum(_PHASE_NPM[s] * len(b.pieces(pt, color))
                      for pt, s in sym.items())
           for color in (_c.WHITE, _c.BLACK)}
    dev = {"white": _developed(b, _c.WHITE), "black": _developed(b, _c.BLACK)}
    if max(npm.values()) <= ENDGAME_NPM:
        return {"phase": "endgame", "developed": dev,
                "why": (f"max side non-pawn material "
                        f"{max(npm.values())} <= {ENDGAME_NPM}")}
    if dev["white"] or dev["black"]:
        still = [s for s in ("white", "black") if not dev[s]]
        why = ("both sides developed" if not still
               else " and ".join(s.capitalize() for s in still)
               + " still developing")
        return {"phase": "middlegame", "why": why, "developed": dev}
    return {"phase": "opening", "developed": dev,
            "why": "both sides still developing"}
