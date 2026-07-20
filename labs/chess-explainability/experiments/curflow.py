import json, asyncio, tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.grounding_tools.drill import DrillState
from lucena_backend.coaching.strategies import MoveLineStrategy
from lucena_backend.coaching.bits import BitProgress, BitSpec
from lucena_backend.coaching.grounding import tiered_bit_grounding
from lucena_backend.coaching.coach import CoachHandler
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.coaching.loop import Input
from lucena_backend.llm import make_adapter
from lucena_backend.llm.interface import Message, GenerateOptions
lib=json.load(open('/Users/avismara/.lucena-run/lessons/library.json'))
spec=[s for s in (lib.values() if isinstance(lib,dict) else lib) if '2rq1rk1' in (s.get('fen') or '')][0]
TREE=[b for b in spec['bits'] if (b.get('params') or {}).get('tree')][0]['params']['tree']
FEN=spec['fen']
# is it multi-ply? walk the solution line
w=DrillState(TREE)
r1=w.play("b2a1","Qa1")
print("Qa1 on FRESH walker: correct=",r1.get("correct")," finished=",w.finished," (finished=True => 1-move drill)")
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
h=CoachHandler(ctx=object(),store=object(),llm=llm,model="gemini-flash-lite-latest",ground=ctx)
g=tiered_bit_grounding(ctx.analyze_and_show(FEN,focus="analysis",board_push=False), TREE)
inp=Input(kind="move",uci="b2a1",fen=FEN,san="Qa1")
async def main():
    facts=await h._move_facts(inp, True, g)
    print("\nRIGHT-verdict grounding:\n"+facts)
    for i in range(3):
        c=await llm.generate([Message("system",VerdictPrompt.system(correct=True)),Message("user",VerdictPrompt.prompt(attempt="Qa1",facts=facts))],GenerateOptions(model="gemini-flash-lite-latest",schema={"type":"object"},max_tokens=300,temperature=0.4))
        print(f"[{i}]",(c.json or {}).get("text",""))
asyncio.run(main())
