import sys, tempfile
from lucena_engine.board import Board
from lucena_engine.positional import analyze_positional
from lucena_engine.analysis import _eval_line, _cap, assemble_analysis
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size

_LABEL={"material":"material","king_safety":"king safety","activity":"piece activity",
        "pawns":"pawn structure","center":"the centre"}

def assemble_v2(board, best_score, pos, facts, thresh=25):
    terms=pos["terms"]
    lines=[_eval_line(board,best_score)]
    ranked=[t for t in sorted(terms,key=lambda k:-abs(terms[k]["cp"])) if abs(terms[t]["cp"])>=thresh]
    if not ranked:
        lines.append("Nothing sharp positionally — roughly balanced across the board.")
    else:
        top=ranked[0]; lead_pos=terms[top]["cp"]>0
        lead="White" if lead_pos else "Black"; other="Black" if lead_pos else "White"
        lines.append(f"Main factor — {_cap(terms[top]['standing'])}.")
        also=[t for t in ranked[1:] if (terms[t]["cp"]>0)==lead_pos]
        comp=[t for t in ranked[1:] if (terms[t]["cp"]>0)!=lead_pos]
        for t in also: lines.append(_cap(terms[t]["standing"])+".")
        if comp:
            lines.append(f"{other}'s compensation: " + "; ".join(terms[t]["standing"] for t in comp) + ".")
    op=[f for f in facts if f.kind=="opening"]; tac=[f for f in facts if f.kind!="opening"]
    if op: lines.append("Opening: "+" ".join(f.text for f in op))
    if tac: lines.append("Tactics: "+"; ".join(f.text for f in tac)+".")
    return lines

ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
for label,fen in [("START","rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
                  ("AFTER bxc4 (Black up a bishop, White activity)","r1bq1rk1/2pn1p1p/p2b1np1/3Np3/2p1P3/5NB1/PPPQ1PPP/2KR3R w - - 0 2")]:
    b=Board(fen); a=ctx.analyze_and_show(fen,focus="analysis",board_push=False)
    # rebuild pos + facts + score the way tools does, via a fresh compute
    from lucena_engine.analysis import build_analysis
    pos=analyze_positional(b)
    # reuse the score from the analysis line by re-running build (needs engine) — simpler: grab via evaluate
    with ctx._pool.lease() as _eng:
        ev=_eng.analyse(fen, multipv=1, movetime_ms=800)
    score=ev.best.score
    facts=[]  # start/quiet: no tactic facts here
    print("\n"+"#"*80); print("#",label); print("#"*80)
    print("--- BEFORE (current assemble_analysis) ---")
    for l in assemble_analysis(b,score,pos,facts): print("   ",l)
    print("--- AFTER (salient-only, ranked, compensation) ---")
    for l in assemble_v2(b,score,pos,facts): print("   ",l)
