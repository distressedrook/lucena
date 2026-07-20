from lucena_engine.board import Board
from lucena_engine.positional import analyze_positional, _LEAD_THRESHOLD
AFT="r1bq1rk1/2pn1p1p/p2b1np1/3Np3/2p1P3/5NB1/PPPQ1PPP/2KR3R w - - 0 2"
pos=analyze_positional(Board(AFT))
print(f"phase={pos['phase']}  _LEAD_THRESHOLD={_LEAD_THRESHOLD}\n")
print(f"{'term':<14}{'cp(W-POV)':>10}   standing")
print("-"*80)
for k,v in sorted(pos["terms"].items(), key=lambda kv: -abs(kv[1]['cp'])):
    print(f"{k:<14}{v['cp']:>10}   {v['standing']}")
print(f"\nleads (|cp|>= {_LEAD_THRESHOLD}, top2): {pos['leads']}")
