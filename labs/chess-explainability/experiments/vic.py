import tempfile, asyncio
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.grounding_tools.drill import DrillState
from lucena_backend.coaching.grounding import tiered_bit_grounding
from lucena_backend.coaching.coach import CoachHandler, _color_to_move
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.coaching.loop import Input
from lucena_backend.llm import make_adapter
from lucena_backend.llm.interface import Message, GenerateOptions
FEN="1k5r/4q3/1pp5/3bNp2/6p1/P5P1/1P3P2/3QRK2 w - - 0 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
T=ctx.preview_drill(FEN)["tree"]; d=DrillState(T)
for u,s in [("d8d5","Qxd5"),("e5c6","Nc6+"),("c6e7","Nxe7")]: d.play(u,s)
cur=d.current.get("fen"); color=_color_to_move(cur)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
h=CoachHandler(ctx=object(),store=object(),llm=llm,model="gemini-flash-lite-latest",ground=ctx)
g=tiered_bit_grounding(ctx.analyze_and_show(cur,focus="analysis",board_push=False),T)
inp=Input(kind="move",uci="f1g2",fen=cur,san="Kg2")
async def main():
    facts=await h._move_facts(inp, False, g)
    print("=== GROUNDING ===\n"+facts+"\n")
    for i in range(4):
        c=await llm.generate([Message("system",VerdictPrompt.system(correct=False,player_color=color)),Message("user",VerdictPrompt.prompt(attempt="Kg2",facts=facts))],GenerateOptions(model="gemini-flash-lite-latest",schema={"type":"object"},max_tokens=300,temperature=0.5))
        print(f"[{i}]",(c.json or {}).get("text",""))
asyncio.run(main())
