# Reproduce coach._move_facts' describe_plan path with the REAL engine evaluate.
from lucena_engine import Engine
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.reasoning import describe_plan, pv_san_to_uci, undermines_defender
import tempfile

FEN = "4r1k1/2q2pbp/p2p2p1/3Qp3/P1r5/2n1P3/1B1N1PPP/R2R2K1 w - - 6 26"
UCI = "d5c4"  # Qxc4

with Engine(threads=1) as e:
    e.new_game()
    ctx = ToolContext(e, StateStore(tempfile.mkdtemp()))
    verdict = ctx.evaluate(FEN, [UCI])
    best = verdict.get("best") or {}
    pv_san = best.get("pv_san")
    cp = (verdict.get("eval") or {}).get("cp")
    print("eval.cp        :", cp)
    print("best.san       :", best.get("san"))
    print("best.pv_san    :", pv_san)
    pv_ucis = pv_san_to_uci(FEN, pv_san)
    print("pv_ucis        :", pv_ucis)
    print("guard pv[0]==uci:", bool(pv_ucis) and pv_ucis[0] == UCI)
    plan = describe_plan(FEN, pv_ucis, cp) if (pv_ucis and pv_ucis[0] == UCI) else None
    print("describe_plan  :", plan)
    print("undermine(1ply):", undermines_defender(FEN, UCI))
