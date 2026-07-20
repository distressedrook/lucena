import asyncio, tempfile, json
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import (_brief_move, _created_threat, _draws_by_stalemate,
    _why_loses, _hint_line, _fallback_hint, _node_at, _node_solutions)
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.llm import make_adapter, Message, GenerateOptions
MODEL="gemini-flash-lite-latest"; llm=make_adapter({"provider":"gemini","default_model":MODEL})
_JSON={"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}
ROOT="k7/2K5/1P6/8/7p/1rR4p/7P/8 w - - 0 7"; uci="c3c4"; after=Board(ROOT).apply(uci).fen
async def main():
    with Engine(threads=1) as e:
        e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
        # === reproduce the REAL drill tree the paste creates ===
        prev=ctx.preview_drill(ROOT)
        tree=prev.get("tree") if isinstance(prev,dict) else None
        sols=_node_solutions(_node_at(tree, ROOT)) if tree else []
        print("drillable:", isinstance(prev,dict) and prev.get("drillable"), "| solution moves at root:", sols)
        v=ctx.evaluate(ROOT,[uci])
        postA=ctx.analyze_and_show(after,focus="analysis",board_push=False).get("analysis") or []
        mr=_brief_move(v,hide_best=True); cr=_created_threat(postA,sols)
        single=(len(sols)==1)
        why=(_draws_by_stalemate(ROOT,uci,v.get("refutation_pv")) or _why_loses(ROOT,uci,v.get("refutation_pv"),solution_ucis=sols,single_solution=single))
        hint=_hint_line(ctx.get_hints(ROOT).get("hints"),1) or _fallback_hint(ROOT,v)
        facts="\n".join(p for p in (mr,cr,why,hint) if p)
        print("\n===== EXACT LIVE FACT SHEET (with real drill tree) =====")
        print(facts)
        print("\n>>> 'a8' in the live fact sheet:", "a8" in facts)
        # === now stress-test: 15 generations, count a8 ===
        sys=VerdictPrompt.system(correct=False, player_color="white")
        usr=VerdictPrompt.prompt(attempt="Rc4", facts=facts)
        n=0
        for i in range(15):
            c=await llm.generate([Message("system",sys),Message("user",usr)],GenerateOptions(model=MODEL,schema=_JSON,max_tokens=300,temperature=0.4))
            t=(json.loads(c.text).get("text") if c.text else "")
            if "a8" in t: n+=1; print("  a8 in gen %d: ...%s..."%(i+1, t[max(0,t.find('a8')-40):t.find('a8')+6]))
        print(">>> a8 appeared in %d/15 generations from the pure facts"%n)
asyncio.run(main())
