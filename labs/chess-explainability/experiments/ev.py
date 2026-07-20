import tempfile, json
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
fen="8/1k2N3/1p6/3p1p2/6p1/P5P1/1P3P2/4RK1r w - - 1 4"  # White to move, Kg2 is the wrong move
v=ctx.evaluate(fen,["f1g2"])
print("top-level keys:", list(v.keys()))
print("refutation_pv:", v.get("refutation_pv"))
print("captured:", v.get("captured"), "| class:", v.get("class"), "| san:", v.get("san"))
# is there any per-move capture info?
for k in ("refutation","pv","line","best"):
    if k in v: print(k, "->", json.dumps(v[k])[:300])
