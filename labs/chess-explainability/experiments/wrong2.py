from lucena_engine import Engine
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _why_loses
from lucena_engine.board import Board
import tempfile

FEN = "4r1k1/2q2pbp/p2p2p1/3Qp3/P1r5/2n1P3/1B1N1PPP/R2R2K1 w - - 6 26"
with Engine(threads=1) as e:
    e.new_game()
    ctx = ToolContext(e, StateStore(tempfile.mkdtemp()))
    b = Board(FEN)
    # try a few legal queen retreats that abandon the winning Qxc4
    for san in ["Qb3","Qd7","Qb5","Qf5","Qd6"]:
        try: uci = b.uci(san)
        except Exception as ex: print(san,"illegal",ex); continue
        v = ctx.evaluate(FEN, [uci])
        print("=== %s (%s) ===" % (san, uci))
        print("  class:", v.get("class"), " played eval:", v.get("eval"), " best:", (v.get('best') or {}).get('san'), (v.get('best') or {}).get('eval'))
        print("  move_read:", _brief_move(v, hide_best=True).replace("\n"," | "))
        print("  why_loses:", _why_loses(FEN, uci, v.get("refutation_pv"), solution_ucis=["d5c4"], single_solution=True))
