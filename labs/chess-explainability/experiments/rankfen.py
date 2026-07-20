import sys
from lucena_engine.board import Board
from lucena_engine.positional import analyze_positional, _LEAD_THRESHOLD
fen=sys.argv[1]
pos=analyze_positional(Board(fen))
print(f"FEN: {fen}")
print(f"phase={pos['phase']}  _LEAD_THRESHOLD={_LEAD_THRESHOLD}\n")
print(f"{'term':<14}{'cp(W-POV)':>10}   standing")
print("-"*90)
for k,v in sorted(pos["terms"].items(), key=lambda kv: -abs(kv[1]['cp'])):
    print(f"{k:<14}{v['cp']:>10}   {v['standing']}")
print(f"\nleads (top2, |cp|>= {_LEAD_THRESHOLD}): {pos['leads']}")
