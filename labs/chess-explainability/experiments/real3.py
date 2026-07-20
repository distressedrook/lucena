import tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
for label,fen in [("START","rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
                  ("bxc4 (decisive)","r1bq1rk1/2pn1p1p/p2b1np1/3Np3/2p1P3/5NB1/PPPQ1PPP/2KR3R w - - 0 2"),
                  ("DANISH (compensation)","rnbqkbnr/pppp1ppp/8/8/2B1P3/8/PB3PPP/RN1QK1NR b KQkq - 0 5")]:
    a=ctx.analyze_and_show(fen,focus="analysis",board_push=False)
    print(f"\n### {label}")
    for l in a.get("analysis") or []: print("  ",l)
