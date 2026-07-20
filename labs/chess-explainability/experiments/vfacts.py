import tempfile, json
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.coaching.grounding import _brief_move
FEN="2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
v=ctx.evaluate(FEN,["b2a1"])   # Qa1, the correct move
print("evaluate(Qa1).facts:")
for f in v.get("facts") or []: print("   ",f.get("kind"),"|",f.get("text"),"| prov=",f.get("provenance"))
print("\n_brief_move(evaluate(Qa1)) — the verdict grounding:")
print(_brief_move(v, hide_best=False))
