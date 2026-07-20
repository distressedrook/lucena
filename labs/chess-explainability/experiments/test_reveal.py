import asyncio
from lucena_backend.coaching.mode_prompts import TrapPrompt
from lucena_backend.llm import make_adapter
from lucena_backend.llm.interface import Message, GenerateOptions
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
FACTS="The tempting line Nxe4 Qe3 Nxg3 hxg3 bxc4 looks winning but loses; the catch is hxg3; the motif is a Nxg3."
async def gen(sys,usr):
    c=await llm.generate([Message("system",sys),Message("user",usr)],GenerateOptions(model="gemini-flash-lite-latest",schema={"type":"object"},max_tokens=400,temperature=0.4))
    return (c.json or {}).get("text","")
async def main():
    for i in range(4):
        print(f"[reveal {i}]", await gen(TrapPrompt.system(reveal=True), TrapPrompt.prompt(facts=FACTS)))
    print("[warn]", await gen(TrapPrompt.system(reveal=False), TrapPrompt.prompt(facts="There's a natural-looking move that loses — calculate carefully.")))
asyncio.run(main())
