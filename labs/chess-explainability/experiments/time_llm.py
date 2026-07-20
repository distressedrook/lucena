import os, time, asyncio
from lucena_backend.llm import make_adapter as _make_adapter
import lucena_backend.httpserver as H

async def main():
    llm = _make_adapter({"provider": "gemini", "default_model": os.environ.get("LUCENA_MODEL","gemini-flash-lite-latest")})
    from lucena_backend.llm.interface import GenerateOptions, Message
    sys = "You are a chess conversation assistant. Answer briefly."
    usr = "What's the idea behind the London System? Two sentences."
    for i in range(3):
        t=time.perf_counter()
        c = await llm.generate([Message("system",sys),Message("user",usr)],
                               GenerateOptions(model=None, schema={"type":"object"} if i==2 else None, max_tokens=400, temperature=0.4))
        dt=time.perf_counter()-t
        print(f"call {i} ({'json' if i==2 else 'text'}): {dt:.2f}s  len={len(c.text)}")

asyncio.run(main())
