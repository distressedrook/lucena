"""Compat Board — the old Rust-core wrapper API on a python-chess substrate.

The one place migrated product code touches board logic. This class preserves
the retired Rust wrapper's public API byte-for-byte (`lucena-engine
board.py`): same methods, same semantics, same error class (every python-chess
parse/legality error is a ValueError subclass). Its contract is pinned by the
ported adversarial suite (tests/test_board*.py) — constructor validation
depth, disambiguation hard cases, suffix rules, en-passant emission, the
UCI/SAN auto-detector boundary.

Deliberate conventions carried over:
- `.fen` stores the constructor input verbatim (round-trip stable).
- FENs produced by apply()/null_move() emit the en-passant square whenever a
  double push just occurred (cozy-chess convention; python-chess
  `en_passant="fen"`), keeping norm_fen position-identity keys stable.
- `attackers()` works at FULL occupancy: a battery's rear slider is not an
  attacker here — x-rays are a SEE concept, not an attackers() concept.
- New code should use python-chess directly; this class exists so migrated
  consumers flip with an import rewrite, not a logic rewrite (the seam is
  documented in lucena-tactics/docs/MIGRATION.md).
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from .see import _see_move

STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@dataclass(frozen=True)
class PieceOn:
    square: str
    piece: str  # P N B R Q K
    color: str  # white | black


class Board:
    """Immutable position; every mutation returns a new Board.

    Moves are accepted as UCI or SAN everywhere; detection is by shape (4-5
    chars of coordinates = UCI), so UCI-shaped-but-illegal strings raise the
    UCI error, not the SAN no-match error.
    """

    def __init__(self, fen: str = STARTPOS):
        # Validate eagerly so a bad FEN fails at construction, not first use —
        # to the same depth as the Rust core: structurally broken boards
        # (missing king, pawn on a back rank) and impossible states (the side
        # NOT to move in check) are rejected, not just unparseable strings.
        b = chess.Board(fen)                 # raises ValueError on bad syntax
        if not b.is_valid():
            raise ValueError(f"invalid position: {fen!r} ({b.status()!r})")
        self.fen = fen
        self._b = b

    # -- reads ------------------------------------------------------------
    @property
    def side_to_move(self) -> str:
        return "white" if self._b.turn == chess.WHITE else "black"

    @property
    def in_check(self) -> bool:
        return self._b.is_check()

    def piece_list(self) -> list[PieceOn]:
        return [PieceOn(chess.square_name(sq), p.symbol().upper(),
                        "white" if p.color == chess.WHITE else "black")
                for sq, p in self._b.piece_map().items()]

    def legal_moves(self) -> list[str]:
        """Standard UCI, castling as e1g1."""
        return [m.uci() for m in self._b.legal_moves]

    def attackers(self, square: str, color: str) -> list[str]:
        """Squares of `color` pieces attacking `square` (full occupancy).

        Sorted for determinism. Full occupancy means batteries do NOT appear:
        a rook behind a rook is not an attacker here (x-rays are a SEE
        concept, not an attackers() concept).
        """
        sq = chess.parse_square(square)      # raises ValueError on bad name
        if color == "white":
            c = chess.WHITE
        elif color == "black":
            c = chess.BLACK
        else:
            raise ValueError(f"color must be 'white' or 'black', not {color!r}")
        return sorted(chess.square_name(a) for a in self._b.attackers(c, sq))

    def defenders(self, square: str) -> list[str]:
        """Squares of same-color pieces defending the piece on `square`."""
        sq = chess.parse_square(square)
        p = self._b.piece_at(sq)
        if p is None:
            raise ValueError(f"no piece on {square}")
        return self.attackers(square, "white" if p.color == chess.WHITE else "black")

    # -- conversions -------------------------------------------------------
    def san(self, uci: str) -> str:
        mv = self._parse_uci(uci)
        return self._b.san(mv)

    def uci(self, san: str) -> str:
        s = san.replace(" e.p.", "").rstrip("!?")
        return self._b.parse_san(s).uci()    # raises ValueError subclasses

    # -- judgments ----------------------------------------------------------
    def see(self, move: str) -> int:
        """Static exchange eval in centipawns; accepts UCI or SAN. The move
        must be legal (facts are only computed over legal candidates)."""
        mv = self._parse_uci(self._as_uci(move))
        return _see_move(self._b, mv.from_square, mv.to_square)

    # -- mutations (returning new boards) -----------------------------------
    def apply(self, move: str) -> "Board":
        mv = self._parse_uci(self._as_uci(move))
        nxt = self._b.copy(stack=False)
        nxt.push(mv)
        # en-passant square emitted whenever a double push just occurred
        # (cozy-chess convention), not only when an ep capture is legal.
        return Board(nxt.fen(en_passant="fen"))

    def null_move(self) -> "Board":
        """Side to move passes. Raises ValueError if in check."""
        if self._b.is_check():
            raise ValueError("null move while in check")
        nxt = self._b.copy(stack=False)
        nxt.push(chess.Move.null())
        return Board(nxt.fen(en_passant="fen"))

    # -- internals -----------------------------------------------------------
    def _as_uci(self, move: str) -> str:
        if (
            len(move) in (4, 5)
            and move[0] in "abcdefgh"
            and move[1] in "12345678"
            and move[2] in "abcdefgh"
            and move[3] in "12345678"
        ):
            return move
        return self.uci(move)

    def _parse_uci(self, uci: str) -> chess.Move:
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError as e:
            raise ValueError(f"illegal move {uci!r} in {self.fen}") from e
        if mv not in self._b.legal_moves:
            raise ValueError(f"illegal move {uci!r} in {self.fen}")
        return mv

    def __repr__(self) -> str:  # pragma: no cover
        return f"Board({self.fen!r})"
