import asyncio, tempfile, json
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _brief_move, _created_threat, _why_loses, _hint_line, _fallback_hint
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.llm import make_adapter, Message, GenerateOptions
MODEL="gemini-flash-lite-latest"; llm=make_adapter({"provider":"gemini","default_model":MODEL})
_JSON={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}
fen="k7/2K5/1P6/8/7p/1rR4p/7P/8 w - - 0 7"; uci="c3c4"; after=Board(fen).apply(uci).fen
async def main():
    with Engine(threads=1) as e:
        e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
        v=ctx.evaluate(fen,[uci])
        postA=ctx.analyze_and_show(after,focus='analysis',board_push=False).get('analysis') or []
        mr=_brief_move(v,hide_best=True); cr=_created_threat(postA,[],fen=after)
        hint=_hint_line(ctx.get_hints(fen).get('hints'),1) or _fallback_hint(fen,v)
        facts="\n".join(p for p in (mr,cr,hint) if p)
        print("THREAT FACT:", cr, "\n"+"-"*40)
        for i in range(2):
            c=await llm.generate([Message('system',VerdictPrompt.system(correct=False,player_color='white')),
                                  Message('user',VerdictPrompt.prompt(attempt='Rc4',facts=facts))],
                                 GenerateOptions(model=MODEL,schema=_JSON,max_tokens=400,temperature=0.4))
            print("GEN %d:"%(i+1), (json.loads(c.text).get('text') if c.text else '').strip())
asyncio.run(main())
