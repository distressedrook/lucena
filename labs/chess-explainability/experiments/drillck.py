import tempfile, json
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
FEN="2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
p=ctx.preview_drill(FEN)
print("drillable:", p.get("drillable"))
if isinstance(p,dict) and p.get("tree"):
    root=p["tree"].get("root") or {}
    print("expected first move:", root.get("expect_san"), "(", root.get("expect_uci"),")  win%=", root.get("win_pct"))
    print("side_to_solve:", p["tree"].get("side_to_solve"))
