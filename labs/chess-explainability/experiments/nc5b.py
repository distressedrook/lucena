import asyncio, tempfile, json
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _deep_tactics
from lucena_backend.reasoning import describe_plan, pv_san_to_uci, undermines_defender
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.llm import make_adapter, Message, GenerateOptions
MODEL="gemini-flash-lite-latest"; llm=make_adapter({"provider":"gemini","default_model":MODEL})
_JSON={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}
b=Board("r2qkb1r/pp2pppp/3p1n2/4n3/4b1PN/2PB3P/PP3P2/RNBQK2R w KQkq - 0 12")
for u in ["d3e4","f6e4","d1a4","e5c6"]: b=b.apply(u)
fen=b.fen; uci="a4e4"; after=Board(fen).apply(uci).fen
async def main():
    with Engine(threads=1) as e:
        e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
        v=ctx.evaluate(fen,[uci])
        preA=ctx.analyze_and_show(fen,focus="analysis",board_push=False).get("analysis") or []
        point=(describe_plan(fen,pv_san_to_uci(fen,(v.get('best') or {}).get('pv_san')),(v.get('eval') or {}).get('cp'))
               or undermines_defender(fen,uci) or _deep_tactics(preA,[uci],live_fen=after))
        mr=_brief_move({k:val for k,val in v.items() if k!='refutation_pv'},hide_best=False)
        cr=_created_threat((ctx.analyze_and_show(after,focus='analysis',board_push=False).get('analysis') or []),[uci])
        facts="\n".join(p for p in (point,mr,cr) if p)
        print("POINT fact:", (point or "(none)")[:120]); print("'ignores' in facts:", "ignores" in facts, "| 'Nc5':", "Nc5" in facts)
        c=await llm.generate([Message("system",VerdictPrompt.system(correct=True,player_color="White")),
                              Message("user",VerdictPrompt.prompt(attempt="Qxe4",facts=facts))],
                             GenerateOptions(model=MODEL,schema=_JSON,max_tokens=400,temperature=0.4))
        print("\nRENDERED:", (json.loads(c.text).get("text") if c.text else "").strip())
asyncio.run(main())
