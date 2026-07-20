import json, tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
AFT="r1bq1rk1/2pn1p1p/p2b1np1/3Np3/2p1P3/5NB1/PPPQ1PPP/2KR3R w - - 0 2"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
a=ctx.analyze_and_show(AFT)
print(">>> a['facts'] (DROPPED by _brief):"); print(json.dumps(a.get("facts"), indent=2, default=str))
print("\n>>> a['lines'] (DROPPED by _brief):"); print(json.dumps(a.get("lines"), indent=2, default=str)[:900])
print("\n>>> a['eval']:", a.get("eval"))
