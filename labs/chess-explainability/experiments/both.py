import asyncio, tempfile, json
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _deep_tactics
from lucena_backend.reasoning import attacks_defender, describe_plan, pv_san_to_uci, undermines_defender
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.llm import make_adapter, Message, GenerateOptions
MODEL="gemini-flash-lite-latest"; llm=make_adapter({"provider":"gemini","default_model":MODEL})
_JSON={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}
async def render(ctx, fen, uci, san):
    v=ctx.evaluate(fen,[uci]); after=Board(fen).apply(uci).fen
    pv=pv_san_to_uci(fen,(v.get('best') or {}).get('pv_san')); cp=(v.get('eval') or {}).get('cp')
    plan=describe_plan(fen,pv,cp) if (pv and pv[0]==uci) else None
    preA=ctx.analyze_and_show(fen,focus='analysis',board_push=False).get('analysis') or []
    point=(attacks_defender(fen,uci) or plan or undermines_defender(fen,uci) or _deep_tactics(preA,[uci],live_fen=after))
    mr=_brief_move({k:val for k,val in v.items() if k!='refutation_pv'},hide_best=False)
    facts="\n".join(p for p in (point,mr) if p)
    c=await llm.generate([Message('system',VerdictPrompt.system(correct=True,player_color='White')),
                          Message('user',VerdictPrompt.prompt(attempt=san,facts=facts))],
                         GenerateOptions(model=MODEL,schema=_JSON,max_tokens=400,temperature=0.4))
    return (json.loads(c.text).get('text') if c.text else '').strip()
async def main():
    with Engine(threads=1) as e:
        e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
        START="r4rk1/p2p2p1/3Np3/2p3R1/5p2/2n2P1P/b1P3PB/R5K1 w - - 0 2"
        print("MOVE 1 (Rxc5):", await render(ctx, START, "g5c5", "Rxc5"))
        b=Board(START)
        for u in ["g5c5","a8b8"]: b=b.apply(u)
        print("MOVE 2 (Rxc3):", await render(ctx, b.fen, "c5c3", "Rxc3"))
asyncio.run(main())
