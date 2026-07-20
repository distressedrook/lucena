import tempfile
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _deep_tactics
from lucena_backend.reasoning import describe_plan, pv_san_to_uci, undermines_defender

start="r2qkb1r/pp2pppp/3p1n2/4n3/4b1PN/2PB3P/PP3P2/RNBQK2R w KQkq - 0 12"
b=Board(start)
for u in ["d3e4","f6e4","d1a4","e5c6"]:   # Bxe4 Nxe4 Qa4+ Nc6
    b=b.apply(u)
fen=b.fen; uci="a4e4"   # Qxe4
print("FEN before Qxe4:", fen)
with Engine(threads=1) as e:
    e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
    v=ctx.evaluate(fen,[uci]); after=Board(fen).apply(uci).fen
    pv=pv_san_to_uci(fen,(v.get("best") or {}).get("pv_san")); cp=(v.get("eval") or {}).get("cp")
    plan=describe_plan(fen,pv,cp) if (pv and pv[0]==uci) else None
    preA=ctx.analyze_and_show(fen,focus="analysis",board_push=False).get("analysis") or []
    point=plan or undermines_defender(fen,uci) or _deep_tactics(preA,[uci])
    v2={k:val for k,val in v.items() if k!="refutation_pv"}
    mr=_brief_move(v2,hide_best=False)
    cr=_created_threat((ctx.analyze_and_show(after,focus="analysis",board_push=False).get("analysis") or []),[uci])
    facts="\n".join(p for p in (point,mr,cr) if p)
    print("\n=== CORRECT-branch facts for Qxe4 ===")
    print(facts)
    print("\n'c5' present in facts?:", "c5" in facts, "| 'Nc5' present?:", "Nc5" in facts)

# --- with the fix: pass live_fen (after Qxe4) so stale null-move threats drop ---
with Engine(threads=1) as e2:
    e2.new_game(); ctx2=ToolContext(e2,StateStore(tempfile.mkdtemp()))
    from lucena_backend.coaching.grounding import _deep_tactics as DT
    preA2=ctx2.analyze_and_show(fen,focus="analysis",board_push=False).get("analysis") or []
    after2=Board(fen).apply("a4e4").fen
    fixed = DT(preA2, ["a4e4"], live_fen=after2)   # sols include Qxe4
    print("\n=== _deep_tactics WITH live_fen (fixed) ===")
    print(fixed)
    print("\n'Nc5' still present?:", "Nc5" in (fixed or ""))
