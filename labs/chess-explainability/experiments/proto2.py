import tempfile
from lucena_engine.board import Board
from lucena_engine.positional import analyze_positional
from lucena_engine.analysis import _eval_line, _cap, assemble_analysis
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size

_COMP_EVAL = 100    # |eval| <= 1.00 pawn: the position is, on balance, level
_HUGE      = 150    # a single dimension worth >~1.5 pawns — a big enough edge to be "compensated"

def _white_cp(board, score):
    stm = "white" if board.fen.split()[1] == "w" else "black"
    return score.to_ceiled_cp() if stm == "white" else -score.to_ceiled_cp()

def assemble_v2(board, best_score, pos, facts, thresh=25):
    terms = pos["terms"]
    lines = [_eval_line(board, best_score)]
    eval_cp = _white_cp(board, best_score)
    ranked = [t for t in sorted(terms, key=lambda k: -abs(terms[k]["cp"])) if abs(terms[t]["cp"]) >= thresh]
    if not ranked:
        lines.append("Nothing sharp positionally — roughly balanced across the board.")
    else:
        top = ranked[0]; lead_pos = terms[top]["cp"] > 0
        other = "Black" if lead_pos else "White"
        opp = [t for t in ranked[1:] if (terms[t]["cp"] > 0) != lead_pos]
        rest = [t for t in ranked[1:] if (terms[t]["cp"] > 0) == lead_pos]
        is_comp = abs(eval_cp) <= _COMP_EVAL and abs(terms[top]["cp"]) >= _HUGE and opp
        lines.append(f"Main factor — {_cap(terms[top]['standing'])}.")
        if is_comp:
            lines.append(f"{other}'s compensation: " + "; ".join(terms[t]['standing'] for t in opp) + ".")
        else:
            for t in ranked[1:]:                 # eval is decisive → the others are just secondary context
                lines.append(_cap(terms[t]['standing']) + ".")
    op = [f for f in facts if f.kind == "opening"]; tac = [f for f in facts if f.kind != "opening"]
    if op: lines.append("Opening: " + " ".join(f.text for f in op))
    if tac: lines.append("Tactics: " + "; ".join(f.text for f in tac) + ".")
    return lines

ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
CASES=[("START","rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
       ("bxc4 — Black up a bishop, eval decisive","r1bq1rk1/2pn1p1p/p2b1np1/3Np3/2p1P3/5NB1/PPPQ1PPP/2KR3R w - - 0 2"),
       ("DANISH GAMBIT — White down 2 pawns, big activity","rnbqkbnr/pppp1ppp/8/8/2B1P3/8/PB3PPP/RN1QK1NR b KQkq - 0 5")]
for label,fen in CASES:
    b=Board(fen)
    with ctx._pool.lease() as eng: ev=eng.analyse(fen,multipv=1,movetime_ms=1000)
    score=ev.best.score; pos=analyze_positional(b)
    print("\n"+"#"*78); print("#",label); print("# eval(W-POV cp)=",_white_cp(b,score),"| terms:",{k:v['cp'] for k,v in pos['terms'].items()}); print("#"*78)
    print("--- AFTER (v2) ---")
    for l in assemble_v2(b,score,pos,[]): print("   ",l)
