import tempfile
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _deep_tactics, _why_loses
from lucena_backend.reasoning import attacks_defender, describe_plan, pv_san_to_uci, undermines_defender
def dump(ctx, fen, uci, san, correct):
    v=ctx.evaluate(fen,[uci]); after=Board(fen).apply(uci).fen
    print("\n########", san, "correct=%s ########"%correct)
    print("captured:", v.get("captured"), "| class:", v.get("class"), "| eval:", v.get("eval"),
          "| best:", (v.get('best') or {}).get('san'), "| best.eval:", (v.get('best') or {}).get('eval'))
    print("best.pv_san:", (v.get('best') or {}).get('pv_san'))
    postA=ctx.analyze_and_show(after,focus='analysis',board_push=False).get('analysis') or []
    print("created_threat:", _created_threat(postA,[]))
    if correct:
        preA=ctx.analyze_and_show(fen,focus='analysis',board_push=False).get('analysis') or []
        pv=pv_san_to_uci(fen,(v.get('best') or {}).get('pv_san'))
        plan=describe_plan(fen,pv,(v.get('eval') or {}).get('cp')) if (pv and pv[0]==uci) else None
        point=(attacks_defender(fen,uci) or plan or undermines_defender(fen,uci) or _deep_tactics(preA,[uci],live_fen=after))
        print("POINT:", point)
        print("move_read:", _brief_move({k:val for k,val in v.items() if k!='refutation_pv'},hide_best=False).replace(chr(10),' | '))
    else:
        print("why_loses:", _why_loses(fen,uci,v.get('refutation_pv'),solution_ucis=[],single_solution=False))
        print("move_read(hide):", _brief_move(v,hide_best=True).replace(chr(10),' | ')[:300])
with Engine(threads=1) as e:
    e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
    dump(ctx,"k7/2K5/1P6/8/7p/1rR4p/7P/8 w - - 0 7","c3h3","Rxh3",True)
    dump(ctx,"k7/2K5/1P6/8/7p/1rR4p/7P/8 w - - 0 7","c3c4","Rc4",False)
