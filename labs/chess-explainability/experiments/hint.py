from lucena_engine import Engine
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _why_loses, _squandered_win, _hint_line
from lucena_engine.board import Board
import tempfile

FEN = "4r1k1/2q2pbp/p2p2p1/3Qp3/P1r5/2n1P3/1B1N1PPP/R2R2K1 w - - 6 26"
UCI = "d5b5"  # 26. Qb5?? (blunder; Qxc4 is the only win)
with Engine(threads=1) as e:
    e.new_game()
    ctx = ToolContext(e, StateStore(tempfile.mkdtemp()))
    verdict = ctx.evaluate(FEN, [UCI])
    single = True   # Qxc4 is only_move -> single solution
    print("=== squandered-win fact ===")
    print(_squandered_win(single, verdict))
    print()
    print("=== hint ladder (get_hints) ===")
    hres = ctx.get_hints(FEN)
    hints = hres.get("hints")
    for h in hints:
        print("  rung %s: %s" % (h.get("rung"), h.get("text")))
    print()
    print("=== _hint_line at attempts 0,1,2 (escalation) ===")
    for a in (0,1,2):
        print(" attempts=%d -> %s" % (a, _hint_line(hints, a)))
    print()
    print("=== full assembled wrong-branch facts (attempt 0) ===")
    move_read = _brief_move(verdict, hide_best=True)
    squ = _squandered_win(single, verdict)
    hint = _hint_line(hints, 0)
    why = _why_loses(FEN, UCI, verdict.get("refutation_pv"), solution_ucis=["d5c4"], single_solution=True)
    print("\n".join(p for p in (squ, move_read, None, why, hint) if p))
