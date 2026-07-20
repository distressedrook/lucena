import csv
from lucena_engine.board import Board
from lucena_backend.coaching.grounding import _undermines_defender, _sole_defender, _PIECE_VAL, _PIECE_WORD

def load(tag,n=10,band=(1200,2100)):
    out=[]
    with open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv') as f:
        for r in csv.DictReader(f):
            if tag not in (r.get('Themes') or '').split(): continue
            try: rating=int(r['Rating'])
            except: continue
            if band[0]<=rating<=band[1] and len((r.get('Moves') or '').split())>=2: out.append(r)
    return [out[i] for i in range(0,len(out),max(1,len(out)//n))][:n]

for r in load('capturingDefender'):
    mv=r['Moves'].split(); pre=Board(Board(r['FEN']).apply(mv[0]).fen); uci=mv[1]
    try: san=pre.san(uci)
    except: san=uci
    if _undermines_defender(pre.fen,uci): 
        print(f"{san:6} FIRED"); continue
    # diagnose: solver move captures on dest; what did the captured piece defend?
    dest=uci[2:4]; frm=uci[:2]
    mover=next((p for p in pre.piece_list() if p.square==frm),None)
    took=next((p for p in pre.piece_list() if p.square==dest and mover and p.color!=mover.color),None)
    why=""
    if not took: why="not a capture (or captured own?)"
    else:
        opp=took.color
        defended=[v for v in pre.piece_list() if v.color==opp and v.square!=dest and dest in pre.defenders(v.square)]
        sole=[v for v in defended if _sole_defender(pre,v.square)==dest]
        pieces=[v for v in sole if v.piece.upper() in ('N','B','R','Q')]
        richer=[v for v in pieces if _PIECE_VAL.get(v.piece.upper(),0)>=_PIECE_VAL.get(took.piece.upper(),0)]
        if not defended: why=f"captured {_PIECE_WORD.get(took.piece.upper())} defended nothing (deflection/other motif)"
        elif not sole: why=f"defended {[ _PIECE_WORD.get(v.piece.upper()) for v in defended]} but NOT sole defender"
        elif not pieces: why=f"sole-defends only a pawn"
        else: why=f"sole-defends {[_PIECE_WORD.get(v.piece.upper()) for v in pieces]} but V<took value (took a {_PIECE_WORD.get(took.piece.upper())})"
    print(f"{san:6} no-fire: {why}")
