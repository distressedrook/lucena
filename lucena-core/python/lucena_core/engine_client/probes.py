"""Engine truth layer — the only source of chess facts derived from this client.

Wraps the lucena-engine gRPC Truth service. Every call uses fixed nodes so
identical inputs give identical outputs (movetime is non-deterministic).
Nothing in this module interprets; it only fetches.

Extracted 2026-07-22 from chess-lab (now lucena-tactics) into /common: both
lucena-tactics and lucena-plans' research harness talked to the SAME Truth
service via independently-vendored copies of this file plus generated
protobuf stubs, reached across repos via ad hoc sys.path hacks (one of which
broke outright when chess-lab was renamed/moved). One canonical copy here,
imported by both via a sys.path append to this directory's parent — see each
consumer's own bootstrap for the exact relative-path computation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import grpc

from ._pb import engine_pb2 as pb
from ._pb import engine_pb2_grpc as rpc

ENGINE_ADDR = os.environ.get("LUCENA_ADDR", "127.0.0.1:50052")
NODES = int(os.environ.get("EXPLAINER_NODES", "2000000"))
THREAT_NODES = int(os.environ.get("EXPLAINER_THREAT_NODES", "800000"))


def _limit(nodes: int = NODES) -> pb.Limit:
    return pb.Limit(nodes=nodes, threads=1)


@dataclass
class Line:
    san: list[str]
    cp: int
    win_pct: float


@dataclass
class Threat:
    pv: list[str]
    cp: int
    is_mate: bool


class Probes:
    """One instance per process; channel is thread-safe."""

    def __init__(self, addr: str = ENGINE_ADDR):
        self._truth = rpc.TruthStub(grpc.insecure_channel(addr))

    # -- basic truth -----------------------------------------------------
    def validate(self, fen: str) -> tuple[bool, str]:
        r = self._truth.ValidateFen(pb.Position(fen=fen))
        return r.legal, r.error

    def analyze(self, fen: str, multipv: int = 3) -> list[Line]:
        r = self._truth.Analyze(
            pb.AnalyzeReq(fen=fen, limit=_limit(), multipv=multipv)
        )
        return [Line(list(l.pv_san), l.eval.cp, l.eval.win_pct) for l in r.lines]

    def evaluate(self, fen: str, move_san: str):
        """Play one move; returns (delta_win_pct, refutation_pv, eval_cp, win_pct)."""
        e = self._truth.Evaluate(
            pb.EvaluateReq(fen=fen, moves=[move_san], limit=_limit())
        )
        return e.delta_win_pct, list(e.refutation_pv), e.eval.cp, e.eval.win_pct

    def explore(self, fen: str, moves: list[str], nodes: int = NODES):
        """Walk a SAN line; returns (end_fen, eval_cp, mate_in, best_san, pv)."""
        x = self._truth.ExploreLine(
            pb.ExploreReq(fen=fen, moves=moves, analyze=True, limit=_limit(nodes))
        )
        return x.end_fen, x.eval.cp, x.mate_in, x.best_san, list(x.pv_san)

    # -- counterfactuals -------------------------------------------------
    def threat_if_pass(self, fen_after_move: str) -> Threat | None:
        """Null-move probe: what does the side that just moved threaten?"""
        parts = fen_after_move.split()
        parts[1] = "w" if parts[1] == "b" else "b"
        parts[3] = "-"
        try:
            r = self._truth.Analyze(
                pb.AnalyzeReq(fen=" ".join(parts), limit=_limit(THREAT_NODES), multipv=1)
            )
        except grpc.RpcError:
            return None
        if not r.lines:
            return None
        l = r.lines[0]
        return Threat(list(l.pv_san)[:4], l.eval.cp, abs(l.eval.cp) >= 1000)
