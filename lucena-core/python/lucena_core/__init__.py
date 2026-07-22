"""lucena_core — Lucena's private board-truth package.

Phase 1 of the engine-slim migration (see lucena-tactics/docs/MIGRATION.md):
the python-chess SEE (ported from the Rust core) and the compat Board. The
board-truth modules (_fen, reads, positional, detect, pgn, openings) and the
gRPC client/server arrive in Phase 2.
"""
from .board import Board, PieceOn, STARTPOS
from .see import see

__all__ = ["Board", "PieceOn", "STARTPOS", "see"]
