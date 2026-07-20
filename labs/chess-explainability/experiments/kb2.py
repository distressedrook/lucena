import tempfile, asyncio, types
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.coaching.grounding import tiered_bit_grounding
from lucena_backend.coaching.coach import CoachHandler, _color_to_move
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.coaching.loop import Input
from lucena_backend.llm import make_adapter
from lucena_backend.llm.interface import Message, GenerateOptions
FEN='8/kPK5/8/8/7p/7r/7P/8 w - - 1 9'
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
h=CoachHandler(ctx=object(),store=object(),llm=llm,model="gemini-flash-lite-latest",ground=ctx)
g=tiered_bit_grounding(ctx.analyze_and_show(FEN,focus="analysis",board_push=False),{})
inp=Input(kind="move",uci="b7b8q",fen=FEN,san="b8=Q+")
color=_color_to_move(FEN)
async def main():
    facts=await h._move_facts(inp, True, g)
    print("=== GROUNDING ===\n"+facts+"\n")
    for i in range(4):
        c=await llm.generate([Message("system",VerdictPrompt.system(correct=True,player_color=color)),Message("user",VerdictPrompt.prompt(attempt="b8=Q+",facts=facts))],GenerateOptions(model="gemini-flash-lite-latest",schema={"type":"object"},max_tokens=200,temperature=0.4))
        print(f"[{i}]",(c.json or {}).get("text",""))
asyncio.run(main())
