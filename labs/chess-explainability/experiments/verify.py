import tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
FEN="rn1qkbnr/pbpppppp/1p6/8/8/6P1/PPPPPPBP/RNBQK1NR w KQkq - 2 3"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
with ctx._pool.lease() as e:
    r=e.analyse(FEN, multipv=2, movetime_ms=3000)
print("deep eval (White POV):", r.best.score, "| best line:", r.best.pv_san[:4] if hasattr(r.best,'pv_san') else r.best.pv[:4])
# does Bxb7 actually win a clean bishop? is b7 defended?
ev=ctx.evaluate(FEN,["Bxb7"])
print("evaluate(Bxb7): class=",ev.get("class"),"| eval after=",ev.get("eval"),"| delta_win%=",ev.get("delta_win_pct"))
