import csv, tempfile
from lucena_engine.board import Board
from lucena_backend.coaching.grounding import _undermines_defender

def load(tag, n=10, band=(1200,2100)):
    out=[]
    with open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv') as f:
        for r in csv.DictReader(f):
            th=(r.get('Themes') or '')
            if tag not in th.split(): continue
            try: rating=int(r['Rating'])
            except: continue
            if not (band[0]<=rating<=band[1]): continue
            if len((r.get('Moves') or '').split())<2: continue
            out.append(r)
    return [out[i] for i in range(0,len(out),max(1,len(out)//n))][:n]

for tag in ('capturingDefender','deflection'):
    pick=load(tag); fire=0
    print(f"\n######## TAG: {tag}  ({len(pick)} puzzles) ########")
    for i,r in enumerate(pick,1):
        mv=r['Moves'].split()
        solver_fen=Board(r['FEN']).apply(mv[0]).fen
        uci=mv[1]
        try: san=Board(solver_fen).san(uci)
        except Exception: san=uci
        und=_undermines_defender(solver_fen, uci)
        if und: fire+=1
        print(f"#{i} [{r['Rating']}] {san:6} ({','.join(t for t in r['Themes'].split() if t in ('capturingDefender','deflection','hangingPiece','fork','pin','sacrifice','discoveredAttack'))})")
        print(f"     {und or '— no fire'}")
    print(f"   >>> fired {fire}/{len(pick)}")
