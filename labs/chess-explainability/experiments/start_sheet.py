import json, tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.coaching.grounding import _brief
START="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
a=ctx.analyze_and_show(START, focus="analysis", board_push=False)
print(">>> analysis fact sheet (the LLM's input):")
for line in a.get("analysis") or []: print("   ", line)
print("\n>>> _brief(a) -> ReadPrompt (what shapes the beat the app sees):")
print("   ", _brief(a).replace("\n","\n    "))
print("\n>>> keys sent onward:", list(a.keys()))
print(">>> eval object (feeds the app's eval readout):", a.get("eval"))
