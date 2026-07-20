import tempfile
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.reasoning import describe_plan, pv_san_to_uci
with Engine(threads=1) as e:
    e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
    for fen,san in [("4r1k1/2q2pbp/p2p2p1/3Qp3/P1r5/2n1P3/1B1N1PPP/R2R2K1 w - - 6 26","Qxc4"),
                    ("r2qkb1r/pp2pppp/3p1n2/4n3/4b1PN/2PB3P/PP3P2/RNBQK2R w KQkq - 0 12","Bxe4")]:
        b=Board(fen); u=b.uci(san); v=ctx.evaluate(fen,[u])
        pv=pv_san_to_uci(fen,(v.get("best") or {}).get("pv_san")); cp=(v.get("eval") or {}).get("cp")
        print(san, "->", describe_plan(fen,pv,cp) if (pv and pv[0]==u) else "(guard: not PV head)")
