import tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
CASES=[
 ("start (neutral)","rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
 ("double fianchetto (Bb7?? hangs)","rn1qkbnr/pbpppppp/1p6/8/8/6P1/PPPPPPBP/RNBQK1NR w KQkq - 2 3"),
 ("the +2.0 middlegame (Bxd5 was a false opp)","2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21"),
 ("Danish gambit (compensation)","rnbqkbnr/pppp1ppp/8/8/2B1P3/8/PB3PPP/RN1QK1NR b KQkq - 0 5"),
]
for label,fen in CASES:
    print(f"\n### {label}\n### {fen}")
    for l in ctx.analyze_and_show(fen, focus="analysis", board_push=False).get("analysis") or []: print("   ",l)
