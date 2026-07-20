import tempfile
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
FEN="2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21"
b=Board(FEN)
print("SEE(g2d5) =", b.see("g2d5"), "  (>0 means the detector treats it as winning material)")
print("is d5 attacked by black e6 pawn? legal Black recapture exd5 exists after Bxd5:")
after=b.apply("g2d5")
print("  Black legal caps to d5:", [m for m in after.legal_moves() if m.endswith("d5")])
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
v=ctx.evaluate(FEN,["Bxd5"])
print("evaluate(Bxd5): class=",v.get("class")," eval_after=",v.get("eval")," delta_win%=",v.get("delta_win_pct")," best=",(v.get('best') or {}).get('san'))
