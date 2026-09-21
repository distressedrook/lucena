"""probe_directive — CAN this reader apply a directive description at all?

The crux left open by P11: the curation variants were null, but that is
uninterpretable until we know whether the reader can map plan-like prose onto
a move in the FIRST place. A 7.5B model that cannot use "the best move is
with your knight" cannot possibly be moved by "rook activation: put a rook on
the open file" — and then every editorial variant is null BY CONSTRUCTION on
this reader, and only the human calibration can score them.

So: a hint ladder, from the crudest directive description to the full
recommendation, each auto-generated from ground truth (the banked answer
move), each carefully NOT naming the move:

  H1  "The best move here is a <piece-name> move."
      — only on pairs where answer and distractor piece classes DIFFER.
  H2  "The best move here lands on the <file>-file."
      — only on pairs where destination files differ (no square named,
        or the H2 text would just be BM in disguise).
  BM  (known from P11: 0.992) — the ceiling of directive-ness.

Readout:
  * H1 lift ≈ 0  → the reader cannot apply even piece-class descriptions.
    The P11 curation nulls say nothing about the read; gate all further
    editorial variants on the human calibration.
  * H1 lift large → the reader CAN follow descriptions, and the plan-prose
    null (P10) is evidence about the READ — its prose does not point at
    moves, even implicitly, for this reader.
"""
from __future__ import annotations

import math

import chess

import bank
import score
from student import Student

PIECE_NAME = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
              chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}


def pmc(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    def pmf(i): return math.comb(n, i) * 0.5 ** n
    obs = pmf(k)
    return min(1.0, sum(pmf(i) for i in range(n + 1) if pmf(i) <= obs))


def piece_and_file(fen: str, uci: str) -> tuple[str, str]:
    board = chess.Board(fen)
    move = chess.Move.from_uci(uci)
    return (PIECE_NAME[board.piece_at(move.from_square).piece_type],
            chess.square_name(move.to_square)[0])


def main(limit: int = 400) -> None:
    bench = bank.benchmark()
    eng = bank.engine_lines()
    rolls = bank.rollouts("2400v2400")
    ids = sorted(set(bench) & set(eng) & set(rolls))
    pairs = []
    for pid in ids:
        p = score.build_pair(pid, bench[pid]["fen"], eng[pid])
        if p:
            pairs.append(p)
        if len(pairs) >= limit:
            break

    s = Student("google/gemma-4-e4b")
    conds: dict[str, dict[str, int]] = {}

    for pr in pairs:
        fen = pr["fen"]
        ap, af = piece_and_file(fen, pr["answer_uci"])
        dp, df = piece_and_file(fen, pr["distractor_uci"])
        hints = {}
        if ap != dp:
            hints["H1:piece"] = f"The best move here is a {ap} move."
        if af != df:
            hints["H2:file"] = f"The best move here lands on the {af}-file."
        if not hints:
            continue
        base_ok = s.choose(fen, pr["a"], pr["b"]).value == pr["answer"]
        for cond, note in hints.items():
            ok = s.choose(fen, pr["a"], pr["b"], note).value == pr["answer"]
            d = conds.setdefault(cond, {"n": 0, "base": 0, "hint": 0,
                                        "n01": 0, "n10": 0})
            d["n"] += 1
            d["base"] += base_ok
            d["hint"] += ok
            d["n01"] += base_ok and not ok
            d["n10"] += ok and not base_ok

    print(f"{'condition':10s} {'n':>4s} {'base':>6s} {'hint':>6s} "
          f"{'lift':>7s} {'net':>5s} {'p':>9s}")
    for cond, d in sorted(conds.items()):
        n = d["n"]
        print(f"{cond:10s} {n:4d} {d['base']/n:6.3f} {d['hint']/n:6.3f} "
              f"{(d['hint']-d['base'])/n:+7.3f} {d['n10']-d['n01']:+5d} "
              f"{pmc(d['n10'], d['n01']+d['n10']):9.3g}")


if __name__ == "__main__":
    main()
