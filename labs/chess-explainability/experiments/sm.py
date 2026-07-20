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
FEN='k7/2K5/1P6/8/7p/1rR4p/7P/8 w - - 0 7'
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
T=ctx.preview_drill(FEN)["tree"]
color=_color_to_move(FEN)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
h=CoachHandler(ctx=object(),store=object(),llm=llm,model="gemini-flash-lite-latest",ground=ctx)
g=tiered_bit_grounding(ctx.analyze_and_show(FEN,focus="analysis",board_push=False),T)
bit=types.SimpleNamespace(spec=types.SimpleNamespace(params={"tree":T}))
inp=Input(kind="move",uci="c3c1",fen=FEN,san="Rc1")
async def main():
    facts=await h._move_facts(inp, False, g, bit)
    print("=== GROUNDING ===\n"+facts+"\n")
    for i in range(2):
        c=await llm.generate([Message("system",VerdictPrompt.system(correct=False,player_color=color)),Message("user",VerdictPrompt.prompt(attempt="Rc1",facts=facts))],GenerateOptions(model="gemini-flash-lite-latest",schema={"type":"object"},max_tokens=450,temperature=0.4))
        print(f"=== OUTPUT [{i}] ===\n"+(c.json or {}).get("text","")+"\n")
asyncio.run(main())
