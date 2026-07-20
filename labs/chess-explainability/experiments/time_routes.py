import time, tempfile, asyncio, os
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.llm import make_adapter
from lucena_backend.coaching.freeform import FreeformHandler
from lucena_backend.coaching.loop import Input

store=StateStore(tempfile.mkdtemp())
pool=EnginePool(size=default_size(), threads=1, hash_mb=64)
ctx=ToolContext(store=store, pool=pool, maia=None, player_rating=1500)
ground=ToolContext(store=store, pool=pool, maia=None, player_rating=1500)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
T0=[0.0]; orig=store.append_beats
def spy(b):
    print(f"  [beat @ {time.perf_counter()-T0[0]:.2f}s] {(b[0].get('segments') or [{}])[0].get('text','')[:70]!r}", flush=True); return orig(b)
store.append_beats=spy
h=FreeformHandler(ctx=ctx, store=store, llm=llm, model="gemini-flash-lite-latest", ground=ground)
async def mv(sid, uci, fen, label):
    with store.bound(sid):
        store.set_board_view(fen); T0[0]=time.perf_counter(); print(f"{label}: {uci} on {fen[:25]}...", flush=True)
        await h.handle(Input(kind="move", uci=uci, fen=fen)); print(f"  TOTAL: {time.perf_counter()-T0[0]:.2f}s", flush=True)
async def main():
    # COACH route: an out-of-book midgame position (never in openings table) -> must GROUND + ReadPrompt
    await mv("c1","d2d4","r1bq1rk1/ppp2ppp/2n2n2/3pp3/1b1P4/2N1PN2/PPPQ1PPP/R3KB1R w KQ - 0 8","COACH(midgame)")
    # A blatant blunder in a quiet spot -> swing -> full evaluate path
    await mv("c2","d1h5","rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2","swing?")
asyncio.run(main())
