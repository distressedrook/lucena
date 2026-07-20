import time, tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool

pool=EnginePool(size=1, threads=1, hash_mb=64)
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()), pool=pool, maia=None, player_rating=1500)

# Positions from a real opening walk: pre -> after each ply
PRE ="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFT ="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"   # after e4

def t(label, fn):
    s=time.perf_counter(); r=fn(); print(f"{label}: {time.perf_counter()-s:.2f}s", flush=True); return r

print("--- simulate move path ordering: analyze(AFT) THEN evaluate(PRE,[e2e4]) ---")
t("warmup evaluate(PRE) [cold]", lambda: ctx.evaluate(PRE,["e2e4"]))   # cold, warms PRE@mpv2 + AFT@mpv1
print("--- now steady state: analyze(AFT) then evaluate(PRE,[e2e4]) ---")
t("analyze_and_show(AFT)", lambda: ctx.analyze_and_show(AFT))          # AFT already @mpv1 from above -> upgrades to mpv2
t("evaluate(PRE,[e2e4]) warm", lambda: ctx.evaluate(PRE,["e2e4"]))     # PRE@mpv2 hit, AFT@mpv2>=1 hit -> ~0
t("evaluate(PRE,[e2e4]) warm #2", lambda: ctx.evaluate(PRE,["e2e4"]))
