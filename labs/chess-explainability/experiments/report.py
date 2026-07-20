import csv
from collections import Counter
from lucena_engine.board import Board
from lucena_backend.coaching.grounding import _undermines_defender, _sole_defender, _PIECE_VAL, _PIECE_WORD

def load(tag, band=(1000,2200)):
    out=[]
    for r in csv.DictReader(open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv')):
        if tag in (r.get('Themes') or '').split():
            try: rt=int(r['Rating'])
            except: continue
            if band[0]<=rt<=band[1] and len((r.get('Moves') or '').split())>=2: out.append(r)
    return out

def why_no_fire(pre, uci):
    dest, frm = uci[2:4], uci[:2]
    mover=next((p for p in pre.piece_list() if p.square==frm),None)
    if not mover: return "bad move"
    took=next((p for p in pre.piece_list() if p.square==dest and p.color!=mover.color),None)
    if not took: return "solver move is NOT a capture (attack/other)"
    opp=took.color
    defended=[v for v in pre.piece_list() if v.color==opp and v.square!=dest and dest in pre.defenders(v.square)]
    sole=[v for v in defended if _sole_defender(pre,v.square)==dest]
    pieces=[v for v in sole if v.piece.upper() in ('N','B','R','Q')]
    if not defended: return "captured piece defended nothing"
    if not sole:     return "victim had 2+ defenders (doesn't fall)"
    if not pieces:   return "sole-defends only a pawn"
    return "victim worth < captured guard (point is the bigger capture)"

for tag in ('capturingDefender','deflection'):
    P=load(tag); fired=0; reasons=Counter(); examples=[]
    for r in P:
        mv=r['Moves'].split()
        try: pre=Board(Board(r['FEN']).apply(mv[0]).fen)
        except Exception: reasons['illegal setup']+=1; continue
        out=_undermines_defender(pre.fen, mv[1])
        if out:
            fired+=1
            if len(examples)<4:
                try: san=pre.san(mv[1])
                except: san=mv[1]
                examples.append(f"    {san}: {out.replace('The point of this move: it ','')}")
        else:
            reasons[why_no_fire(pre, mv[1])]+=1
    print(f"\n===== TAG: {tag} =====")
    print(f"  puzzles: {len(P)}   FIRED: {fired}  ({100*fired//max(1,len(P))}%)")
    print("  non-fire breakdown:")
    for k,n in reasons.most_common(): print(f"    {n:4}  {k}")
    if examples:
        print("  sample derivations:")
        print("\n".join(examples))
