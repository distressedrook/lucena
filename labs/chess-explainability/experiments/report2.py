import csv
from lucena_engine.board import Board
from lucena_backend.coaching.grounding import _undermines_defender

def load(tag, band=(1000,2200)):
    out=[]
    for r in csv.DictReader(open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv')):
        if tag in (r.get('Themes') or '').split():
            try: rt=int(r['Rating'])
            except: continue
            if band[0]<=rt<=band[1] and len((r.get('Moves') or '').split())>=2: out.append(r)
    return out

def puzzle_fires(r):
    """Replay the line; the coach grades each PLAYER move — fire if the reasoner explains ANY of them."""
    mv=r['Moves'].split()
    b=Board(r['FEN'])
    lead=note=False
    for i,u in enumerate(mv):
        if i%2==1:  # player's move (mv[0] is the opponent's setup)
            out=_undermines_defender(b.fen, u)
            if out:
                if out.startswith("The point"): lead=True
                else: note=True
        try: b=b.apply(u)
        except Exception: break
    return lead, note

for tag in ('capturingDefender',):
    P=load(tag); lead=note=0
    for r in P:
        l,n=puzzle_fires(r)
        if l: lead+=1
        elif n: note+=1
    covered=lead+note
    print(f"TAG {tag}: {len(P)} puzzles")
    print(f"  reasoner explains a PLAYER move in: {covered}/{len(P)}  ({100*covered//len(P)}%)")
    print(f"    - as THE POINT (lead):      {lead}  ({100*lead//len(P)}%)")
    print(f"    - as a SECONDARY note only: {note}")
    print(f"  (was 34% when only move-1 was graded and gap-2 dropped)")
