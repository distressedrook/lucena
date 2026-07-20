import asyncio, tempfile
from lucena_engine import Engine
from lucena_engine.board import Board
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import (_brief_move, _created_threat, _why_loses,
    _fallback_hint, _hint_line, _node_solutions)
from lucena_backend.coaching.mode_prompts import VerdictPrompt
from lucena_backend.llm import make_adapter, Message, GenerateOptions

MODEL = "gemini-flash-lite-latest"
llm = make_adapter({"provider": "gemini", "default_model": MODEL})
_JSON = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

async def render(sys, usr):
    c = await llm.generate([Message("system", sys), Message("user", usr)],
                           GenerateOptions(model=MODEL, schema=_JSON, max_tokens=400, temperature=0.4))
    import json
    return (json.loads(c.text).get("text") if c.text else "").strip()

def wrong_facts(ctx, fen, san, attempts):
    b = Board(fen); uci = b.uci(san)
    v = ctx.evaluate(fen, [uci]); after = b.apply(uci).fen
    mr = _brief_move(v, hide_best=True)
    cr = _created_threat((ctx.analyze_and_show(after, focus="analysis", board_push=False).get("analysis") or []), [])
    why = _why_loses(fen, uci, v.get("refutation_pv"), solution_ucis=[], single_solution=False)
    hint = _hint_line(ctx.get_hints(fen).get("hints"), attempts) or (_fallback_hint(fen, v) if attempts>=1 else None)
    return "\n".join(p for p in (mr, cr, why, hint) if p)

async def main():
    with Engine(threads=1) as e:
        e.new_game()
        ctx = ToolContext(e, StateStore(tempfile.mkdtemp()))
        PUZZLE = "r2qkb1r/pp2pppp/3p1n2/4n3/4b1PN/2PB3P/PP3P2/RNBQK2R w KQkq - 0 12"
        for san, att in [("f4",0), ("Qa4+",1), ("g5",2)]:
            facts = wrong_facts(ctx, PUZZLE, san, att)
            sys = VerdictPrompt.system(correct=False, player_color="White")
            usr = VerdictPrompt.prompt(attempt=san, facts=facts)
            txt = await render(sys, usr)
            print("\n### WRONG: %s   (attempt #%d)" % (san, att+1))
            print(txt)

asyncio.run(main())
