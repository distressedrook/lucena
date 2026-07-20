import tempfile, json
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
FEN="r1bq1rk1/2pn1p1p/p2b1np1/1p1Np3/2B1P3/5NB1/PPPQ1PPP/2KR3R b - - 1 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
v=ctx.evaluate(FEN,["f6e4"])  # Nxe4, the poisoned move
print("evaluate(Nxe4) keys:", list(v.keys()))
for k in ("san","class","best","refutation_pv","delta_wp","win_pct","side_to_move"):
    print(f"  {k} = {v.get(k)}")
