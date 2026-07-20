import tempfile
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _why_loses, _hint_line, _fallback_hint
fen="k7/2K5/1P6/8/7p/1rR4p/7P/8 w - - 0 7"; uci="c3c4"   # Rc4 (blunder), White
after=Board(fen).apply(uci).fen
with Engine(threads=1) as e:
    e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
    v=ctx.evaluate(fen,[uci])
    postA=ctx.analyze_and_show(after,focus='analysis',board_push=False).get('analysis') or []
    mr=_brief_move(v,hide_best=True)
    cr=_created_threat(postA,[])
    why=_why_loses(fen,uci,v.get('refutation_pv'),solution_ucis=[],single_solution=False)
    hint=_hint_line(ctx.get_hints(fen).get('hints'),1) or _fallback_hint(fen,v)
    facts="\n".join(p for p in (mr,cr,why,hint) if p)
    print("===== FULL WRONG-BRANCH FACTS (Rc4) =====")
    print(facts)
    print("\n>>> occurrences of 'a8':", facts.count("a8"), "| 'a4':", facts.count("a4"))
    import re
    for line in facts.split("\n"):
        if "a8" in line: print("  a8-LINE:", line[:160])
