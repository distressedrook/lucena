import os, sys; sys.path.insert(0,"engine/python")
from lucena_engine.board import Board
from lucena_engine import Engine
from lucena_engine.maia import MaiaEngine
from lucena_engine.facts import build_fact_sheet

MAIA_CMD=os.environ["LUCENA_MAIA"]
RATINGS=[1100,1500,1900]
FENS=[
 "6k1/5ppp/8/4n3/8/8/5PPP/4R1K1 w - - 0 1",           # Rxe5 hangs
 "6k1/5ppp/3q4/1N6/8/8/5PPP/6K1 w - - 0 1",           # Nxd6 wins queen
 "rn1qkbnr/pbpppppp/1p6/8/8/6P1/PPPPPPBP/RNBQK1NR w KQkq - 2 3",  # Bxb7 (diagonal)
 "7k/8/8/4n3/3K4/8/8/8 w - - 0 1",                    # Kxe5
 "r3k3/8/8/8/8/5n2/6P1/B3K3 w - - 0 1",               # gxf3
 "r2q1rk1/pp3ppp/2p1b3/2R5/2P5/3P1Q1P/P1P2PP1/R1B3K1 b - - 2 15", # fork pos
 "2r4r/4kpp1/p3p2p/7n/Bq3P2/2N2Q1P/1PP3P1/4R1K1 w - - 2 28",      # fork pos
 "2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21",     # the +2.0 (Bxd5 dropped)
 "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",      # start (quiet)
 "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", # Italian (quiet)
]
maia=MaiaEngine(MAIA_CMD)
cache={}
def top(fen,r,k):
    key=(fen,r)
    if key not in cache:
        cache[key]=[m["uci"] for m in maia.top_human_moves(fen,r,n=5)]
    return set(cache[key][:k])

opps=[]   # (fen, uci)  mover's opportunity
dangs=[]  # (passed_fen, uci) opponent's threat
with Engine(threads=1) as e:
    for fen in FENS:
        e.new_game()
        b=Board(fen)
        facts=build_fact_sheet(b, e, movetime_ms=800)
        for f in facts:
            if f.provenance.startswith("see:") or f.provenance.startswith("fork:"):
                opps.append((fen, f.provenance.split(":",1)[1]))
            elif f.provenance.startswith(("nullsee:","nullmove:")):
                try: pf=b.null_move().fen
                except Exception: continue
                dangs.append((pf, f.provenance.split(":",1)[1]))

print(f"surfaced: {len(opps)} opportunities, {len(dangs)} threats, across {len(FENS)} positions\n")
for label,items in [("OPPORTUNITIES (mover's move)",opps),("THREATS (opponent's move)",dangs)]:
    print(label)
    if not items: print("   (none)"); continue
    for r in RATINGS:
        for k in (3,5):
            hit=sum(1 for fen,u in items if u in top(fen,r,k))
            print(f"   rating {r}, top-{k}: {hit}/{len(items)} = {100*hit/len(items):.0f}% human-reachable")
    print()
maia.close()
