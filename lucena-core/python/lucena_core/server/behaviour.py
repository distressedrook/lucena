"""Behaviour service — Maia human-move prediction. Optional; never returns an eval
to the player. Degrades to UNAVAILABLE when LUCENA_MAIA is not configured.
"""

from __future__ import annotations

import grpc

from ..board import Board
from .._pb import engine_pb2 as pb
from .._pb import engine_pb2_grpc as pbg


class BehaviourServicer(pbg.BehaviourServicer):
    def __init__(self, engines, maia):
        self._engines = engines
        self._maia = maia    # MaiaHolder (lazy)

    def _get_maia(self, context):
        try:
            return self._maia.get()
        except Exception as e:  # noqa: BLE001 — no LUCENA_MAIA / wrapper missing
            context.abort(grpc.StatusCode.UNAVAILABLE, f"Maia unavailable: {e}")

    def TopHumanMoves(self, request, context):
        maia = self._get_maia(context)
        b = Board(request.fen)
        n = request.n or 5
        oppo = request.oppo_rating or None
        try:
            picks = maia.top_human_moves(request.fen, request.rating, n=n, oppo_rating=oppo)
        except Exception as e:  # noqa: BLE001
            context.abort(grpc.StatusCode.UNAVAILABLE, f"Maia query failed: {e}")
        moves = []
        for m in picks:
            mm = pb.MaiaMove(san=b.san(m["uci"]), rank=m.get("rank", 0), policy=m.get("policy", 0.0))
            if "wdl" in m:
                mm.wdl.extend(m["wdl"])
            if "mate" in m:
                mm.eval.mate = m["mate"]
            elif "cp" in m:
                mm.eval.cp = m["cp"]
            moves.append(mm)
        return pb.MaiaResp(moves=moves)

    def CommonMistakes(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED,
                      "CommonMistakes not yet ported (see docs/grounding-engine-api.md)")

    # PoisonedLine RPC retired 2026-07-23 (Phase 7): the detector lives in
    # lucena-tactics and the backend calls it in-process; the RPC had no live
    # callers (verified). CommonMistakes above remains the unported skeleton.
