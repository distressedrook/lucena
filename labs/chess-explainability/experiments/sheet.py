import tempfile
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import (_brief_move, _created_threat, _draws_by_stalemate,
    _why_loses, _hint_line, _fallback_hint)
# Exact coach._move_facts WRONG-branch assembly for Rc4 (White blunder). No drill tree here -> sols=[],
# single=False (as a freeform-pasted puzzle). Shown at attempts=1 (so the hint rung is visible).
fen="k7/2K5/1P6/8/7p/1rR4p/7P/8 w - - 0 7"; uci="c3c4"; after=Board(fen).apply(uci).fen
with Engine(threads=1) as e:
    e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
    verdict=ctx.evaluate(fen,[uci])
    postA=ctx.analyze_and_show(after,focus="analysis",board_push=False).get("analysis") or []
    move_read=_brief_move(verdict,hide_best=True)
    created=_created_threat(postA,[],fen=after)
    sols=[]; single=False
    why=(_draws_by_stalemate(fen,uci,verdict.get("refutation_pv"))
         or _why_loses(fen,uci,verdict.get("refutation_pv"),solution_ucis=sols,single_solution=single))
    hres=ctx.get_hints(fen).get("hints")
    hint=_hint_line(hres,1) or _fallback_hint(fen,verdict)   # attempts=1
    facts="\n".join(p for p in (move_read,created,why,hint) if p)
    print("="*78)
    print("EXACT FACT SHEET  ·  Rc4  (wrong branch, attempts=1)")
    print("="*78)
    print(facts)
