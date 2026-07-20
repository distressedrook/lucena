import tempfile, re
from lucena_engine.board import Board
from lucena_engine.positional import analyze_positional
from lucena_engine.analysis import _eval_line, _cap
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.coaching.mode_prompts import ReadPrompt

_COMP_EVAL=100; _HUGE=150
def _trim(s): return re.sub(r";\s*\w+.s least active piece is the [^;.]+","",s)
def _white_cp(board,score):
    stm="white" if board.fen.split()[1]=="w" else "black"
    return score.to_ceiled_cp() if stm=="white" else -score.to_ceiled_cp()
def assemble_v2(board,best_score,pos,facts,thresh=50):
    terms=pos["terms"]; lines=[_eval_line(board,best_score)]; eval_cp=_white_cp(board,best_score)
    ranked=[t for t in sorted(terms,key=lambda k:-abs(terms[k]["cp"])) if abs(terms[t]["cp"])>=thresh]
    if not ranked:
        lines.append("Nothing sharp positionally — roughly balanced across the board.")
    else:
        top=ranked[0]; lp=terms[top]["cp"]>0; other="Black" if lp else "White"
        opp=[t for t in ranked[1:] if (terms[t]["cp"]>0)!=lp]
        is_comp=abs(eval_cp)<=_COMP_EVAL and abs(terms[top]["cp"])>=_HUGE and opp
        lines.append(f"Main factor — {_cap(_trim(terms[top]['standing']))}.")
        if is_comp: lines.append(f"{other}'s compensation: "+"; ".join(_trim(terms[t]['standing']) for t in opp)+".")
        else:
            for t in ranked[1:]: lines.append(_cap(_trim(terms[t]['standing']))+".")
    return lines

START="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
b=Board(START)
with ctx._pool.lease() as eng: ev=eng.analyse(START,multipv=1,movetime_ms=1000)
facts="\n".join(assemble_v2(b,ev.best.score,analyze_positional(b),[]))
print("="*72); print("SYSTEM (verbatim):"); print("="*72); print(ReadPrompt.system())
print("\n"+"="*72); print("USER (verbatim) — the NEW sheet:"); print("="*72)
print(ReadPrompt.prompt(facts=facts))
