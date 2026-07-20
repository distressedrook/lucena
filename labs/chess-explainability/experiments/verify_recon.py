import sys; sys.path.insert(0,"python")
from lucena_engine.board import Board
from lucena_engine import Engine
from lucena_engine.evalmodel import win_pct_from_score
from lucena_engine.facts import build_fact_sheet, _OPP_DROP_THRESHOLD
from lucena_engine.detectors.hanging import detect_hanging
print("threshold now =", _OPP_DROP_THRESHOLD)
FEN="2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21"
b=Board(FEN)
with Engine(threads=1) as e:
    e.new_game()
    real=e.analyse(FEN, nodes=60000, multipv=1)
    bwin=win_pct_from_score(real.best.score)
    after=b.apply("g2d5")
    awin=win_pct_from_score(e.analyse(after.fen, nodes=60000, multipv=1).best.score.negated())
    print(f"Bxd5 drop @nodes=60000: {bwin-awin:.1f}%  (best={real.best.pv[0]})")
    e.new_game()
    sheet=build_fact_sheet(b, engine=e, nodes=60000, top_n=8)
    kept=any(f.provenance=="see:g2d5" for f in sheet)
    print("Bxd5 in sheet after reconciliation:", kept, "(want False = dropped)")
    print("sheet facts:", [f.text[:40] for f in sheet])
