import tempfile, asyncio
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.coaching.grounding import tiered_bit_grounding
from lucena_backend.coaching.coach import CoachHandler
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.coaching.loop import Input
from lucena_backend.llm import make_adapter
from lucena_backend.llm.interface import Message, GenerateOptions
FEN="2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
h=CoachHandler(ctx=object(), store=object(), llm=llm, model="gemini-flash-lite-latest", ground=ctx)
tree=ctx.preview_drill(FEN)["tree"]
grounding=tiered_bit_grounding(ctx.analyze_and_show(FEN,focus="analysis",board_push=False), tree)
inp=Input(kind="move", uci="b2a1", fen=FEN, san="Qa1")
async def main():
    facts=await h._move_facts(inp, True, grounding)   # correct=True
    print("=== VERDICT GROUNDING (correct=True) ===\n"+facts)
    c=await llm.generate([Message("system",VerdictPrompt.system(correct=True)),Message("user",VerdictPrompt.prompt(attempt="Qa1",facts=facts))],
        GenerateOptions(model="gemini-flash-lite-latest",schema={"type":"object"},max_tokens=400,temperature=0.4))
    print("\n=== COACH VERDICT ===\n"+(c.json or {}).get("text",""))
asyncio.run(main())
