import asyncio, tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.coaching.grounding import _brief_move
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.llm import make_adapter
from lucena_backend.llm.interface import Message, GenerateOptions
FEN="r1bq1rk1/2pn1p1p/p2b1np1/1p1Np3/2B1P3/5NB1/PPPQ1PPP/2KR3R b - - 1 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
async def gen(sys,usr):
    c=await llm.generate([Message("system",sys),Message("user",usr)],GenerateOptions(model="gemini-flash-lite-latest",schema={"type":"object"},max_tokens=400,temperature=0.4))
    return (c.json or {}).get("text","")
async def main():
    v=await asyncio.to_thread(ctx.evaluate,FEN,["f6e4"])
    facts=_brief_move(v,hide_best=True)
    print("FACTS:\n"+facts+"\n"+"="*60)
    for i in range(3):
        print(f"[{i}]", await gen(VerdictPrompt.system(correct=False), VerdictPrompt.prompt(attempt="Nxe4", facts=facts)))
asyncio.run(main())
