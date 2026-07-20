import sys; sys.path.insert(0,"python")
from lucena_engine.board import Board
from lucena_engine import Engine
from lucena_engine.evalmodel import win_pct_from_score
from lucena_engine.detectors.hanging import detect_hanging

# (label, fen, expected drop/keep, note)
CASES=[
 ("Bxd5-mistake",   "2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21","DROP","wins a pawn by SEE but throws away +1.6"),
 ("backrank-trap",  "4r1k1/5ppp/8/3b4/7B/8/5PPP/3R2K1 w - - 0 1","DROP","Rxd5 walks into Re1#"),
 ("clean-knight",   "6k1/5ppp/8/4n3/8/8/5PPP/4R1K1 w - - 0 1","KEEP","Rxe5 wins a clean knight (IS best)"),
 ("clean-queen",    "6k1/5ppp/3q4/1N6/8/8/5PPP/6K1 w - - 0 1","KEEP","Nxd6 wins the queen clean"),
]
def wp(sc): return win_pct_from_score(sc)
with Engine(threads=1) as e:
    for label,fen,exp,note in CASES:
        e.new_game()
        b=Board(fen)
        opp=[f for f in detect_hanging(b) if f.provenance.startswith("see:")]
        real=e.analyse(fen, movetime_ms=1500, multipv=1)
        best=real.best.pv[0]; bwin=wp(real.best.score)
        for f in opp:
            uci=f.provenance.split(":",1)[1]
            after=b.apply(uci)
            if not after.legal_moves():
                awin=100.0 if after.in_check else 50.0
            else:
                awin=wp(e.analyse(after.fen, movetime_ms=1500, multipv=1).best.score.negated())
            drop=bwin-awin
            isbest=(uci==best)
            print(f"  {label:16} {f.text[:38]:38} drop={drop:6.1f}%  is_best={isbest}  expect={exp}")
