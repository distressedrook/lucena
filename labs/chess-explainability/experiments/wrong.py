from lucena_engine import Engine
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _why_loses, _draws_by_stalemate
import tempfile, json

FEN = "4r1k1/2q2pbp/p2p2p1/3Qp3/P1r5/2n1P3/1B1N1PPP/R2R2K1 w - - 6 26"
UCI = "d5c1"  # 26. Qc1 (blunder)

with Engine(threads=1) as e:
    e.new_game()
    ctx = ToolContext(e, StateStore(tempfile.mkdtemp()))
    print("=== best-move read of the POSITION (is it a forced win/mate?) ===")
    v0 = ctx.evaluate(FEN, ["d5c4"])   # the winning move Qxc4
    print("Qxc4 class:", v0.get("class"), " eval:", v0.get("eval"), " best:", (v0.get('best') or {}).get('san'), " best.eval:", (v0.get('best') or {}).get('eval'))
    print()
    print("=== the BLUNDER 26.Qc1 ===")
    v = ctx.evaluate(FEN, [UCI])
    print("class:", v.get("class"))
    print("eval (played, mover-POV):", v.get("eval"))
    print("best.san:", (v.get('best') or {}).get('san'), " best.eval:", (v.get('best') or {}).get('eval'))
    print("refutation_pv:", v.get("refutation_pv"))
    print()
    print("--- move_read (_brief_move, hide_best) ---")
    print(_brief_move(v, hide_best=True))
    print("--- _why_loses (freeform: no solution tree) ---")
    print(_why_loses(FEN, UCI, v.get("refutation_pv"), solution_ucis=[], single_solution=False))
    print("--- _why_loses (with solution=Qxc4, single) ---")
    print(_why_loses(FEN, UCI, v.get("refutation_pv"), solution_ucis=["d5c4"], single_solution=True))
