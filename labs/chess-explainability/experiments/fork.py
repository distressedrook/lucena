import tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
# Black to move: ...Nc2+ forks Ke1 and Ra1 (royal fork). Classic knight fork shape.
FEN="r3k3/8/8/8/8/8/2n5/R3K3 b - - 0 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
a=ctx.analyze_and_show(FEN, focus="analysis", board_push=False)
print("analysis sheet:")
for l in a.get("analysis") or []: print("   ", l)
