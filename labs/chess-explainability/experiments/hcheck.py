import tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.coaching.grounding import _brief
# after 1.g3 b6 2.Bg2 Bb7, White to move
FEN="rn1qkbnr/pbpppppp/1p6/8/8/6P1/PPPPPPBP/RNBQK1NR w KQkq - 2 3"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
a=ctx.analyze_and_show(FEN, focus="analysis", board_push=False)
print("=== FACT SHEET (what the coach was grounded on) ===")
for l in a.get("analysis") or []: print("  ", l)
print("\n=== beat #7 CLAIMED: 'White is winning. White can capture the bishop on b7 with Bxb7 or capture the bishop on g2 with Bxg2.' ===")
