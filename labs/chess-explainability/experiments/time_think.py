import os, time, asyncio
from google import genai
from google.genai import types

async def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model="gemini-flash-lite-latest"
    sys="You are a chess conversation assistant. Answer briefly."
    usr="What's the idea behind the London System? Two sentences."
    for label, tc in [("default (thinking auto)", None), ("thinking_budget=0", types.ThinkingConfig(thinking_budget=0))]:
        for i in range(2):
            cfg=types.GenerateContentConfig(system_instruction=sys, max_output_tokens=400, temperature=0.4,
                                            **({"thinking_config":tc} if tc is not None else {}))
            t=time.perf_counter()
            r=await client.aio.models.generate_content(model=model, contents=usr, config=cfg)
            print(f"{label} #{i}: {time.perf_counter()-t:.2f}s len={len(r.text or '')}")

asyncio.run(main())
