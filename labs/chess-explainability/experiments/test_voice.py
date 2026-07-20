import json, asyncio, tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.llm import make_adapter
from lucena_backend.coaching.grounding import tiered_bit_grounding, _brief_move
from lucena_backend.coaching.mode_prompts import TrapPrompt, VerdictPrompt

FEN="r1bq1rk1/2pn1p1p/p2b1np1/1p1Np3/2B1P3/5NB1/PPPQ1PPP/2KR3R b - - 1 1"
lib=json.load(open('/Users/avismara/.lucena-run/lessons/library.json'))
spec=[s for s in (lib.values() if isinstance(lib,dict) else lib) if s.get('id')=='pos_6a880fcef85f'][0]
tree=[b for b in spec['bits'] if (b.get('params') or {}).get('tree')][0]['params']['tree']

store=StateStore(tempfile.mkdtemp()); pool=EnginePool(size=default_size(),threads=1,hash_mb=64)
ctx=ToolContext(store=store,pool=pool,maia=None,player_rating=1500)
llm=make_adapter({"provider":"gemini","default_model":"gemini-flash-lite-latest"})
async def gen(sys,usr):
    c=await llm.generate([__import__('lucena_backend.llm.interface',fromlist=['Message']).Message("system",sys),
                          __import__('lucena_backend.llm.interface',fromlist=['Message']).Message("user",usr)],
        __import__('lucena_backend.llm.interface',fromlist=['GenerateOptions']).GenerateOptions(model="gemini-flash-lite-latest",schema={"type":"object"},max_tokens=400,temperature=0.4))
    return (c.json or {}).get("text","")

async def main():
    tf=tiered_bit_grounding(None,tree)
    best_uci=(tree.get('root') or {}).get('expect_uci')
    # derive best uci from tree line (first real ply)
    print("best (solution) uci from tree:",best_uci)
    print("\n--- WARN (present) voiced ---")
    print(await gen(TrapPrompt.system(reveal=False), TrapPrompt.prompt(facts=tf.warn_text())))
    print("\n--- REVEAL (conclude) voiced [facts:", tf.reveal_text(),"] ---")
    print(await gen(TrapPrompt.system(reveal=True), TrapPrompt.prompt(facts=tf.reveal_text())))
    if best_uci:
        vr=await asyncio.to_thread(ctx.evaluate,FEN,[best_uci])
        print("\n--- VERDICT right (grounded on move) facts:",repr(_brief_move(vr,hide_best=False))[:160])
        print(await gen(VerdictPrompt.system(correct=True), VerdictPrompt.prompt(attempt=vr.get('san') or best_uci, facts=_brief_move(vr,hide_best=False))))
    # a WRONG move: the poisoned first move Nxe4
    pm=(tree.get('poisoned_line_moves') or [{}])[0].get('uci') or 'f6e4'
    vw=await asyncio.to_thread(ctx.evaluate,FEN,[pm])
    print("\n--- VERDICT wrong (hide_best) facts:",repr(_brief_move(vw,hide_best=True))[:200])
    print(await gen(VerdictPrompt.system(correct=False), VerdictPrompt.prompt(attempt=vw.get('san') or pm, facts=_brief_move(vw,hide_best=True))))
asyncio.run(main())
