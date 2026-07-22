"""lucena_core — Lucena's private board-truth package.

Extracted from lucena-engine in the 2026-07-23 core migration (see
lucena-tactics/docs/MIGRATION.md): the python-chess SEE (ported from the Rust
core, differential-gated), the compat Board, the board-truth modules (_fen,
reads, positional, detect, pgn, openings), and the gRPC surface — client
(`engine_client`, absorbed from /common) and server (`server`, Truth +
Behaviour). lucena-engine itself is the Stockfish/Maia wrapper this package
composes with; the dependency direction is core → engine, never the reverse.
"""
from .board import Board, PieceOn, STARTPOS
from .see import see
from ._fen import norm_fen

__all__ = ["Board", "PieceOn", "STARTPOS", "see", "norm_fen"]
