import os, tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_engine.uci import Engine
from lucena_engine.maia import MaiaEngine
FEN="1k5r/4q3/1pp5/3bNp2/6p1/P5P1/1P3P2/3QRK2 w - - 0 1"
maia=MaiaEngine(os.environ["LUCENA_MAIA"])
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=maia,player_rating=1500)
ctx._poisoned_line_engine_factory = lambda: Engine(threads=1)
T=ctx.preview_drill(FEN)["tree"]
print("with MAIA -> has_poisoned_line:", T.get("has_poisoned_line"), "| line:", [m.get('san') for m in (T.get('poisoned_line_moves') or [])], "| meta:", T.get("poisoned_line_meta"))
maia.close()
