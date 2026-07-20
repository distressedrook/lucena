import tempfile
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _deep_tactics
from lucena_backend.reasoning import describe_plan, pv_san_to_uci, undermines_defender
b=Board("r2qkb1r/pp2pppp/3p1n2/4n3/4b1PN/2PB3P/PP3P2/RNBQK2R w KQkq - 0 12")
for u in ["d3e4","f6e4","d1a4","e5c6"]: b=b.apply(u)
fen=b.fen; uci="a4e4"; after=Board(fen).apply(uci).fen
with Engine(threads=1) as e:
    e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
    v=ctx.evaluate(fen,[uci])
    preA=ctx.analyze_and_show(fen,focus="analysis",board_push=False).get("analysis") or []
    point=_deep_tactics(preA,[uci],live_fen=after)
    mr=_brief_move({k:val for k,val in v.items() if k!='refutation_pv'},hide_best=False)
    cr=_created_threat((ctx.analyze_and_show(after,focus='analysis',board_push=False).get('analysis') or []),[uci])
    print("POINT:", point); print("---\nMOVE_READ:", mr); print("---\nCREATED:", cr)
