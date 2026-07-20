import asyncio, tempfile, time
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.llm import make_adapter
from lucena_backend.coaching.loop import ConversationLoop, Input
from lucena_backend.coaching.freeform import FreeformHandler
from lucena_backend.coaching.coach import CoachHandler

FEN="r1bq1rk1/2pn1p1p/p2b1np1/1p1Np3/2B1P3/5NB1/PPPQ1PPP/2KR3R b - - 1 1"
store=StateStore(tempfile.mkdtemp())
pool=EnginePool(size=default_size(),threads=1,hash_mb=64)
ctx=ToolContext(store=store,pool=pool,maia=None,player_rating=1500)
ctx._poisoned_line_engine_factory=lambda: __import__('lucena_engine.uci',fromlist=['Engine']).Engine(threads=1)
ground=ToolContext(store=store,pool=pool,maia=None,player_rating=1500)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
model="gemini-flash-lite-latest"

# spy on beats + board writes
ob=store.append_beats
def sb(b):
    for x in b:
        t="".join(s.get("text","") for s in (x.get("segments") or []))
        print(f"    BEAT[{x.get('kind')}]: {t[:90]!r}",flush=True)
    return ob(b)
store.append_beats=sb
owb=store.write_board
def swb(fen,*a,**k):
    print(f"    write_board -> {fen[:30]}...",flush=True); return owb(fen,*a,**k)
store.write_board=swb

loop=ConversationLoop(store=store,
    freeform=FreeformHandler(ctx=ctx,store=store,llm=llm,model=model,ground=ground),
    coach=CoachHandler(ctx=ctx,store=store,llm=llm,model=model,ground=ground))

async def main():
    print("== paste puzzle ==")
    await loop.handle_input("c1", Input(kind="position", text=FEN))
    lz=store.active_lesson()
    print("  active lesson after paste:", (lz.spec.id if lz else None))
    print("== play RIGHT move b5c4 (bxc4) ==")
    from lucena_backend.coaching.coach import move_result
    move_result.set(None)
    await loop.handle_input("c1", Input(kind="move", uci="b5c4", fen=FEN))
    print("  move_result:", move_result.get())
asyncio.run(main())
