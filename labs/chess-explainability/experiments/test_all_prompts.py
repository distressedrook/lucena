import asyncio, tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.coaching.grounding import _brief_move, _brief
from lucena_backend.coaching.mode_prompts import PositionQueryPrompt, ReadPrompt, VerdictPrompt, TrapPrompt
from lucena_backend.llm import make_adapter
from lucena_backend.llm.interface import Message, GenerateOptions
FEN="r1bq1rk1/2pn1p1p/p2b1np1/1p1Np3/2B1P3/5NB1/PPPQ1PPP/2KR3R b - - 1 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
async def g(s,u):
    c=await llm.generate([Message("system",s),Message("user",u)],GenerateOptions(model="gemini-flash-lite-latest",schema={"type":"object"},max_tokens=400,temperature=0.4))
    return (c.json or {}).get("text","")
async def main():
    read=_brief(ctx.analyze_and_show(FEN))
    vr=ctx.evaluate(FEN,["b5c4"]); vr={k:x for k,x in vr.items() if k!="refutation_pv"}
    vw=ctx.evaluate(FEN,["f6e4"])
    print("PositionQuery(is Nxe4 good?):", await g(PositionQueryPrompt.system(freeform=False), PositionQueryPrompt.prompt(text="Is Nxe4 good here?", facts=read)))
    print("Read:", await g(ReadPrompt.system(), ReadPrompt.prompt(facts=read)))
    print("Verdict RIGHT:", await g(VerdictPrompt.system(correct=True), VerdictPrompt.prompt(attempt="bxc4", facts=_brief_move(vr,hide_best=False))))
    print("Verdict WRONG:", await g(VerdictPrompt.system(correct=False), VerdictPrompt.prompt(attempt="Nxe4", facts=_brief_move(vw,hide_best=True))))
    print("Trap REVEAL:", await g(TrapPrompt.system(reveal=True), TrapPrompt.prompt(facts="The tempting line Nxe4 Qe3 Nxg3 hxg3 bxc4 looks winning but loses; the catch is hxg3; the motif is a Nxg3.")))
asyncio.run(main())
