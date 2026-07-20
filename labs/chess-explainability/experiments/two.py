import tempfile, asyncio
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.grounding_tools.drill import DrillState
from lucena_backend.coaching.grounding import _brief_reply
from lucena_backend.coaching.coach import CoachHandler, _color_to_move
from lucena_backend.coaching.mode_prompts import OpponentReplyPrompt, VerdictPrompt
from lucena_backend.llm import make_adapter
from lucena_backend.llm.interface import Message, GenerateOptions
FEN="1k5r/4q3/1pp5/3bNp2/6p1/P5P1/1P3P2/3QRK2 w - - 0 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
T=ctx.preview_drill(FEN)["tree"]; d=DrillState(T)
# play the first correct move Qxd5; the walker auto-plays the opponent reply
r=d.play("d8d5","Qxd5")
print("correct:", r["correct"], "| reply surfaced:", r.get("reply"))
reply=r["reply"]
print("\n=== _brief_reply grounding ===")
print(_brief_reply(reply["from_fen"], reply["san"]))
color=_color_to_move(FEN)  # player is White at the root
print("\nplayer color:", color)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
h=CoachHandler(ctx=object(),store=object(),llm=llm,model="gemini-flash-lite-latest",ground=ctx)
async def main():
    for i in range(3):
        t=await h._reply_text(reply, color)
        print(f"REPLY BEAT [{i}]:", t)
asyncio.run(main())
