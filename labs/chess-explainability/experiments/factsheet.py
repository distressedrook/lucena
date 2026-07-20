from lucena_engine import Engine
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.reasoning import describe_plan, pv_san_to_uci, undermines_defender
from lucena_backend.coaching.grounding import (_brief_move, _created_threat, _why_loses,
    _squandered_win, _hint_line, _deep_tactics)
import tempfile

FEN = "4r1k1/2q2pbp/p2p2p1/3Qp3/P1r5/2n1P3/1B1N1PPP/R2R2K1 w - - 6 26"
BAR = "─" * 78

def an(ctx, fen):
    return ctx.analyze_and_show(fen, focus="analysis", board_push=False)

with Engine(threads=1) as e:
    e.new_game()
    ctx = ToolContext(e, StateStore(tempfile.mkdtemp()))
    from lucena_engine.board import Board

    # ===== RIGHT: play Qxc4 (the solution) =====
    UCI = "d5c4"
    verdict = ctx.evaluate(FEN, [UCI])
    after = Board(FEN).apply(UCI).fen
    pv = pv_san_to_uci(FEN, (verdict.get("best") or {}).get("pv_san"))
    cp = (verdict.get("eval") or {}).get("cp")
    plan = describe_plan(FEN, pv, cp) if (pv and pv[0] == UCI) else None
    point = plan or undermines_defender(FEN, UCI) or _deep_tactics((an(ctx,FEN).get("analysis") or []), ["d5c4"])
    v2 = {k:v for k,v in verdict.items() if k != "refutation_pv"}
    move_read = _brief_move(v2, hide_best=False)
    created = _created_threat((an(ctx, after).get("analysis") or []), ["d5c4"])
    print(BAR); print("FACT SHEET  ·  CORRECT move  (26. Qxc4)"); print(BAR)
    print("\n".join(p for p in (point, move_read, created) if p))
    print("   …plus the five-term positional read (the 'always' tier) appended after.")

    # ===== WRONG: play Qb5 (blunder), first miss =====
    UCI = "d5b5"
    verdict = ctx.evaluate(FEN, [UCI])
    after = Board(FEN).apply(UCI).fen
    squ = _squandered_win(True, verdict)
    mr = _brief_move(verdict, hide_best=True)
    cr = _created_threat((an(ctx, after).get("analysis") or []), ["d5c4"])
    why = _why_loses(FEN, UCI, verdict.get("refutation_pv"), solution_ucis=["d5c4"], single_solution=True)
    hint = _hint_line(ctx.get_hints(FEN).get("hints"), 0)   # attempts=0 → first rung
    print(); print(BAR); print("FACT SHEET  ·  WRONG move  (26. Qb5??, first miss)"); print(BAR)
    print("\n".join(p for p in (squ, mr, cr, why, hint) if p))
