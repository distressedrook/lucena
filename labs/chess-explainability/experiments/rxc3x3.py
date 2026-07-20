import asyncio, tempfile, json
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _deep_tactics
from lucena_backend.reasoning import attacks_defender, describe_plan, pv_san_to_uci, undermines_defender
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.llm import make_adapter, Message, GenerateOptions
MODEL="gemini-flash-lite-latest"; llm=make_adapter({"provider":"gemini","default_model":MODEL})
_JSON={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}
b=Board('r4rk1/p2p2p1/3Np3/2p3R1/5p2/2n2P1P/b1P3PB/R5K1 w - - 0 2')
for u in ['g5c5','a8b8']: b=b.apply(u)
fen=b.fen; uci='c5c3'; after=Board(fen).apply(uci).fen
async def main():
    with Engine(threads=1) as e:
        e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
        v=ctx.evaluate(fen,[uci])
        preA=ctx.analyze_and_show(fen,focus='analysis',board_push=False).get('analysis') or []
        pv=pv_san_to_uci(fen,(v.get('best') or {}).get('pv_san'))
        plan=describe_plan(fen,pv,(v.get('eval') or {}).get('cp')) if (pv and pv[0]==uci) else None
        point=(attacks_defender(fen,uci) or plan or undermines_defender(fen,uci) or _deep_tactics(preA,[uci],live_fen=after))
        mr=_brief_move({k:val for k,val in v.items() if k!='refutation_pv'},hide_best=False)
        facts="\n".join(p for p in (point,mr) if p)
        print("FACTS SENT:\n"+facts+"\n"+"-"*50)
        for i in range(3):
            c=await llm.generate([Message('system',VerdictPrompt.system(correct=True,player_color='White')),
                                  Message('user',VerdictPrompt.prompt(attempt='Rxc3',facts=facts))],
                                 GenerateOptions(model=MODEL,schema=_JSON,max_tokens=400,temperature=0.4))
            print("GEN %d: %s" % (i+1, (json.loads(c.text).get('text') if c.text else '').strip()))
asyncio.run(main())
