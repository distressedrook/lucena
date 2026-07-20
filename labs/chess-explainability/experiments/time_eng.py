import time, tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool

home=tempfile.mkdtemp()
store=StateStore(home)
pool=EnginePool(size=1, threads=1, hash_mb=64)
ctx=ToolContext(store=store, pool=pool, maia=None, player_rating=1500)
ctx._poisoned_line_engine_factory = None

MID="r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
TAC="r2qkb1r/pp2nppp/3p4/2pNN1B1/2B1P3/3P4/PPP2PPP/R2bK2R w KQkq - 1 10"
START="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

def timeit(label, fn, n=1):
    t=time.perf_counter()
    r=None
    for _ in range(n): r=fn()
    print(f"{label}: {(time.perf_counter()-t)/n:.2f}s", flush=True)
    return r

timeit("analyze_and_show(MID)", lambda: ctx.analyze_and_show(MID))
timeit("analyze_and_show(MID) cached", lambda: ctx.analyze_and_show(MID))
timeit("evaluate(START,[e2e4])", lambda: ctx.evaluate(START,["e2e4"]))
try: timeit("preview_drill(TAC)", lambda: ctx.preview_drill(TAC))
except Exception as e: print("preview_drill err", repr(e))
