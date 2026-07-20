import asyncio, tempfile, json
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import (_brief_move, _created_threat, _draws_by_stalemate,
    _why_loses, _hint_line, _fallback_hint)
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.llm import make_adapter, Message, GenerateOptions
MODEL="gemini-flash-lite-latest"; llm=make_adapter({"provider":"gemini","default_model":MODEL})
_JSON={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}
fen="k7/2K5/1P6/8/7p/1rR4p/7P/8 w - - 0 7"; uci="c3c4"; after=Board(fen).apply(uci).fen
async def main():
    with Engine(threads=1) as e:
        e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
        v=ctx.evaluate(fen,[uci])
        postA=ctx.analyze_and_show(after,focus="analysis",board_push=False).get("analysis") or []
        mr=_brief_move(v,hide_best=True); cr=_created_threat(postA,[])
        why=(_draws_by_stalemate(fen,uci,v.get("refutation_pv")) or _why_loses(fen,uci,v.get("refutation_pv"),solution_ucis=[],single_solution=False))
        hint=_hint_line(ctx.get_hints(fen).get("hints"),1) or _fallback_hint(fen,v)
        facts="\n".join(p for p in (mr,cr,why,hint) if p)
        assert "a8" not in facts, "FACT SHEET CONTAINS a8!"
        print("FACT SHEET HAS a8:", "a8" in facts, "| has Ra4#:", "Ra4#" in facts)
        sys=VerdictPrompt.system(correct=False, player_color="white")
        print("SYSTEM PROMPT HAS a8:", "a8" in sys)
        usr=VerdictPrompt.prompt(attempt="Rc4", facts=facts)
        n_a8=0
        for i in range(6):
            c=await llm.generate([Message("system",sys),Message("user",usr)],
                                 GenerateOptions(model=MODEL,schema=_JSON,max_tokens=400,temperature=0.4))
            t=(json.loads(c.text).get("text") if c.text else "").strip()
            says=("a8" in t); n_a8+=says
            print("GEN %d [%s]: %s"%(i+1,"a8!" if says else "ok", t[:170]))
        print("\n>>> a8 appeared in %d/6 generations"%n_a8)
asyncio.run(main())
