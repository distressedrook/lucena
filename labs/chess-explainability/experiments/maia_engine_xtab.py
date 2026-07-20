import os, sys; sys.path.insert(0,"engine/python")
from lucena_engine.board import Board
from lucena_engine import Engine
from lucena_engine.maia import MaiaEngine
from lucena_engine.facts import build_fact_sheet

RATINGS=[1100,1500,1900]
FENS=[
 "6k1/5ppp/8/4n3/8/8/5PPP/4R1K1 w - - 0 1",
 "6k1/5ppp/3q4/1N6/8/8/5PPP/6K1 w - - 0 1",
 "rn1qkbnr/pbpppppp/1p6/8/8/6P1/PPPPPPBP/RNBQK1NR w KQkq - 2 3",
 "7k/8/8/4n3/3K4/8/8/8 w - - 0 1",
 "r3k3/8/8/8/8/5n2/6P1/B3K3 w - - 0 1",
 "r2q1rk1/pp3ppp/2p1b3/2R5/2P5/3P1Q1P/P1P2PP1/R1B3K1 b - - 2 15",
 "2r4r/4kpp1/p3p2p/7n/Bq3P2/2N2Q1P/1PP3P1/4R1K1 w - - 2 28",
 "2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21",
 "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
 "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
]
maia=MaiaEngine(os.environ["LUCENA_MAIA"]); mcache={}
def mtop(fen,r,k):
    if (fen,r) not in mcache: mcache[(fen,r)]=[m["uci"] for m in maia.top_human_moves(fen,r,n=5)]
    return set(mcache[(fen,r)][:k])

recs=[]  # (kind, fen_to_query, uci, engine_top3_set)
with Engine(threads=1) as e:
    for fen in FENS:
        e.new_game(); b=Board(fen)
        facts=build_fact_sheet(b, e, movetime_ms=800)
        et3=set(ln.pv[0] for ln in e.analyse(fen, movetime_ms=800, multipv=3).lines)
        pf=None; pt3=set()
        try:
            pb=b.null_move(); pf=pb.fen
            pt3=set(ln.pv[0] for ln in e.analyse(pf, movetime_ms=800, multipv=3).lines)
        except Exception: pass
        for f in facts:
            if f.provenance.startswith(("see:","fork:")):
                recs.append(("OPP", fen, f.provenance.split(":",1)[1], et3))
            elif f.provenance.startswith(("nullsee:","nullmove:")) and pf:
                recs.append(("THREAT", pf, f.provenance.split(":",1)[1], pt3))

for kind in ("OPP","THREAT"):
    rs=[r for r in recs if r[0]==kind]
    print(f"\n=== {kind}  (n={len(rs)}) ===")
    for r in RATINGS:
        inM=[u in mtop(f,r,3) for _,f,u,_ in rs]
        notE=[u not in e3 for _,f,u,e3 in rs]
        m_and_note=sum(1 for i in range(len(rs)) if inM[i] and notE[i])
        print(f"  @{r}: in Maia top3 = {sum(inM)}/{len(rs)} | NOT in engine top3 = {sum(notE)}/{len(rs)} "
              f"| human-reachable AND not-engine-top3 = {m_and_note}/{len(rs)}")
maia.close()
