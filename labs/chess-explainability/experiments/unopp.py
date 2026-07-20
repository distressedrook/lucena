import csv, tempfile, collections
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
VAL={'p':1,'n':3,'b':3,'r':5,'q':9,'k':0}

def best(b):
    v=ctx.evaluate(b.fen,[b.legal_moves()[0]]); bm=v.get('best') or {}
    san=bm.get('san')
    if not san: return None
    try: return b.uci(san)
    except Exception: return None

def plan(fen, cap=8):
    """Player moves, opponent PASSES. STOP the moment there's a mate or a secured material advantage."""
    b=Board(fen); moves=[]; won=0; outcome='none'
    for _ in range(cap):
        uci=best(b)
        if not uci: break
        dest=uci[2:4]
        c=next((p for p in b.piece_list() if p.square==dest and p.color!=b.side_to_move),None)
        if c: won+=VAL.get(c.piece.lower(),0)
        moves.append((uci, c.piece.lower() if c else None))
        b=b.apply(uci)
        if b.in_check:                                  # the move gave CHECK -> forcing; can't pass
            outcome='mate' if not b.legal_moves() else 'forcing_check'; break
        if won>=3:                                      # secured at least a minor piece
            outcome='material'; break
        try: b=b.null_move()
        except Exception: outcome='forcing_check'; break
    return moves, outcome, won

def load(n=100, band=(1200,2000)):
    out=[]
    for r in csv.DictReader(open('/Users/avismara/.claude/jobs/0e0eb085/tmp/pz.csv')):
        try: rt=int(r['Rating'])
        except: continue
        if band[0]<=rt<=band[1] and len((r.get('Moves') or '').split())>=2 and r.get('Themes'): out.append(r)
    return [out[i] for i in range(0,len(out),max(1,len(out)//n))][:n]

P=load(100); match=0; outc=collections.Counter(); tgt=collections.Counter(); lens=collections.Counter()
th_tot=collections.Counter(); th_material=collections.Counter()
for r in P:
    mv=r['Moves'].split()
    try: sfen=Board(r['FEN']).apply(mv[0]).fen
    except Exception: continue
    pl,outcome,won=plan(sfen)
    if pl and pl[0][0]==mv[1]: match+=1
    outc[outcome]+=1
    caps=[c for _,c in pl if c]
    tgt[max(caps,key=lambda c:VAL.get(c,0)) if caps else None]+=1
    lens[len(pl)]+=1
    for t in r['Themes'].split():
        th_tot[t]+=1
        if outcome in ('material','mate'): th_material[t]+=1
N=len(P)
print(f"POSITIONS: {N}")
print(f"unopposed first move == real solution first move: {match}/{N} ({100*match//N}%)")
print("\nOUTCOME (where the unopposed plan stopped):")
for k,v in outc.most_common(): print(f"  {k:15} {v}")
print("\nBY THEME — % ending in mate/material (the 'quiet-win' signal):")
for t,n in th_tot.most_common(14):
    print(f"  {t:20} {th_material[t]:3}/{n:3}  ({100*th_material[t]//max(1,n):3}%)")
print("\nTARGET WON:")
for t,v in tgt.most_common(): print(f"  {str(t):6} {v}")
print("\nLENGTH to stop:")
for l in sorted(lens): print(f"  {l}: {lens[l]}")
