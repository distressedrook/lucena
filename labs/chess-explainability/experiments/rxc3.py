import tempfile
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _deep_tactics
from lucena_backend.reasoning import describe_plan, pv_san_to_uci, undermines_defender
START="r4rk1/p2p2p1/3Np3/2p3R1/5p2/2n2P1P/b1P3PB/R5K1 w - - 0 2"
# 2. Rxc5 Rab8, then 3. Rxc3
b=Board(START)
for u in ["g5c5","a8b8"]: b=b.apply(u)
fen=b.fen; uci="c5c3"   # Rxc3 takes the knight
print("FEN before Rxc3:", fen)
with Engine(threads=1) as e:
    e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
    v=ctx.evaluate(fen,[uci]); after=Board(fen).apply(uci).fen
    pv=pv_san_to_uci(fen,(v.get("best") or {}).get("pv_san")); cp=(v.get("eval") or {}).get("cp")
    print("captured:", v.get("captured"), "| class:", v.get("class"), "| best.pv_san:", (v.get('best') or {}).get('pv_san'))
    print("describe_plan   :", describe_plan(fen,pv,cp) if (pv and pv[0]==uci) else "(not PV head / None)")
    print("undermines_def  :", undermines_defender(fen,uci))
    # also the Rxc5 move (first move of the combo)
    v2=ctx.evaluate(START,["g5c5"]); pv2=pv_san_to_uci(START,(v2.get("best") or {}).get("pv_san"))
    print("\n[Rxc5] describe_plan:", describe_plan(START,pv2,(v2.get('eval') or {}).get('cp')) if (pv2 and pv2[0]=="g5c5") else "(none)")
    print("[Rxc5] best.pv_san :", (v2.get('best') or {}).get('pv_san'))
