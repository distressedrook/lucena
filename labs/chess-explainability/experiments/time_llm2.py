import os, time, asyncio
from lucena_backend.llm import make_adapter
from lucena_backend.llm.interface import GenerateOptions, Message
from lucena_backend.coaching.prompts import NarratePrompt

llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
sysm=NarratePrompt.system(None)
print(f"NarratePrompt.system len = {len(sysm)} chars (~{len(sysm)//4} tokens)")
usr="narrate 1.e4, King's Pawn Game, in White's voice, 2 sentences"

async def one(label, system, u, schema=True):
    t=time.perf_counter()
    c=await llm.generate([Message("system",system),Message("user",u)],
        GenerateOptions(model="gemini-flash-lite-latest", schema=({"type":"object"} if schema else None), max_tokens=400, temperature=0.4))
    print(f"{label}: {time.perf_counter()-t:.2f}s  out={len(c.text)}ch", flush=True)

async def main():
    for i in range(3):
        await one(f"NarratePrompt #{i}", sysm, usr)
    for i in range(3):
        await one(f"short-sys #{i}", "You are a chess coach. Reply as JSON {\"text\":...}.", usr)
asyncio.run(main())
