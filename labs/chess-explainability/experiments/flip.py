import tempfile, asyncio
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.grounding_tools.drill import DrillState
from lucena_backend.coaching.grounding import tiered_bit_grounding, _brief_move
from lucena_backend.coaching.coach import CoachHandler
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.coaching.loop import Input
from lucena_backend.llm import make_adapter
from lucena_backend.llm.interface import Message, GenerateOptions
FEN="1k5r/4q3/1pp5/3bNp2/6p1/P5P1/1P3P2/3QRK2 w - - 0 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
T=ctx.preview_drill(FEN)["tree"]
d=DrillState(T)
for u,s in [("d8d5","Qxd5"),("e5c6","Nc6+"),("c6e7","Nxe7")]:
    d.play(u,s)
cur_fen=d.current.get("fen")
print("position at move 4 (White to move):", cur_fen, "| expected:", d.current.get("expect_san"))
# a WRONG move: play something legal that isn't the solution
from lucena_engine.board import Board
b=Board(cur_fen)
legal=[m for m in b.legal_moves() if m!=d.current.get("expect_uci")]
wrong=legal[0]; wrong_san=b.san(wrong)
print("wrong move played:", wrong_san, wrong)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
h=CoachHandler(ctx=object(),store=object(),llm=llm,model="gemini-flash-lite-latest",ground=ctx)
g=tiered_bit_grounding(ctx.analyze_and_show(cur_fen,focus="analysis",board_push=False),T)
inp=Input(kind="move",uci=wrong,fen=cur_fen,san=wrong_san)
async def main():
    facts=await h._move_facts(inp, False, g)
    print("\n=== WRONG-verdict GROUNDING ===\n"+facts)
    c=await llm.generate([Message("system",VerdictPrompt.system(correct=False)),Message("user",VerdictPrompt.prompt(attempt=wrong_san,facts=facts))],GenerateOptions(model="gemini-flash-lite-latest",schema={"type":"object"},max_tokens=400,temperature=0.4))
    print("\n=== COACH WRONG VERDICT ===\n"+(c.json or {}).get("text",""))
asyncio.run(main())
