import time, tempfile, asyncio, os
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.llm import make_adapter
from lucena_backend.coaching.freeform import FreeformHandler
from lucena_backend.coaching.loop import Input

os.environ.setdefault("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY",""))
store=StateStore(tempfile.mkdtemp())
pool=EnginePool(size=default_size(), threads=1, hash_mb=64)
ctx=ToolContext(store=store, pool=pool, maia=None, player_rating=1500)
ground=ToolContext(store=store, pool=pool, maia=None, player_rating=1500)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})

# instrument beat timing
T0=[0.0]
orig=store.append_beats
def spy(beats):
    print(f"  [beat @ {time.perf_counter()-T0[0]:.2f}s] {(beats[0].get('segments') or [{}])[0].get('text','')[:60]!r}", flush=True)
    return orig(beats)
store.append_beats=spy

h=FreeformHandler(ctx=ctx, store=store, llm=llm, model="gemini-flash-lite-latest", ground=ground)

async def move(sid, uci, fen, label):
    with store.bound(sid):
        store.set_board_view(fen)
        T0[0]=time.perf_counter()
        print(f"{label}: play {uci}", flush=True)
        await h.handle(Input(kind="move", uci=uci, fen=fen))
        print(f"  TOTAL _on_move: {time.perf_counter()-T0[0]:.2f}s", flush=True)

async def main():
    # a real opening walk on one chat (warms cache across plies)
    seq=[("e2e4","rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
         ("g1f3","rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"),
         ("f1b5","r1bqkbnr/pp1ppppp/2n5/2p5/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")]
    for i,(u,f) in enumerate(seq):
        await move("c1", u, f, f"move#{i+1}")
asyncio.run(main())
