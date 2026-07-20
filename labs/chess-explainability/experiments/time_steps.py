import time, tempfile, asyncio, os
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.llm import make_adapter

store=StateStore(tempfile.mkdtemp())
pool=EnginePool(size=default_size(), threads=1, hash_mb=64)
print(f"pool size = {default_size()}", flush=True)
ctx=ToolContext(store=store, pool=pool, maia=None, player_rating=1500)
ground=ToolContext(store=store, pool=pool, maia=None, player_rating=1500)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})

PRE="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

async def t(label, coro):
    s=time.perf_counter(); r=await coro; print(f"{label}: {time.perf_counter()-s:.2f}s", flush=True); return r

async def main():
    with store.bound("c1"):
        store.set_board_view(PRE)
        await t("play_move(e2e4)", asyncio.to_thread(ctx.play_move, "e2e4", PRE, push_feedback=False))
        fen=store.board_view
        await t("_ground=analyze_and_show(fen)", asyncio.to_thread(ground.analyze_and_show, fen, focus="analysis", board_push=False))
        await t("evaluate(PRE,[e2e4])", asyncio.to_thread(ground.evaluate, PRE, ["e2e4"]))
        await t("human_replies(fen)", asyncio.to_thread(ctx.human_replies, fen, 1500, 3))
        from lucena_backend.coaching.prompts import NarratePrompt
        from lucena_backend.llm.interface import GenerateOptions, Message
        sysm=NarratePrompt.system(None)
        await t("NarratePrompt LLM", llm.generate([Message("system",sysm),Message("user","narrate 1.e4, King's Pawn Game, 2 sentences")], GenerateOptions(model="gemini-flash-lite-latest", schema={"type":"object"}, max_tokens=400, temperature=0.4)))
asyncio.run(main())
