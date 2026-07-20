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

async def render(sys,usr):
    c=await llm.generate([Message("system",sys),Message("user",usr)],GenerateOptions(model=MODEL,schema=_JSON,max_tokens=400,temperature=0.4))
    return (json.loads(c.text).get("text") if c.text else "").strip()

def right_facts(ctx, fen, san):
    b=Board(fen); uci=b.uci(san); after=b.apply(uci).fen
    v=ctx.evaluate(fen,[uci])
    pv=pv_san_to_uci(fen,(v.get("best") or {}).get("pv_san")); cp=(v.get("eval") or {}).get("cp")
    plan=describe_plan(fen,pv,cp) if (pv and pv[0]==uci) else None
    preA=ctx.analyze_and_show(fen,focus="analysis",board_push=False).get("analysis") or []
    point=plan or undermines_defender(fen,uci) or _deep_tactics(preA,[uci])
    v2={k:val for k,val in v.items() if k!="refutation_pv"}
    mr=_brief_move(v2,hide_best=False)
    cr=_created_threat((ctx.analyze_and_show(after,focus="analysis",board_push=False).get("analysis") or []),[uci])
    return "\n".join(p for p in (point,mr,cr) if p)

async def main():
    with Engine(threads=1) as e:
        e.new_game(); ctx=ToolContext(e,StateStore(tempfile.mkdtemp()))
        cases=[("r2qkb1r/pp2pppp/3p1n2/4n3/4b1PN/2PB3P/PP3P2/RNBQK2R w KQkq - 0 12","Bxe4"),
               ("4r1k1/2q2pbp/p2p2p1/3Qp3/P1r5/2n1P3/1B1N1PPP/R2R2K1 w - - 6 26","Qxc4"),
               ("1k1r4/p4R1p/B5p1/2p1N3/3p4/3K4/PB4PP/4q3 w - - 3 35","Nxc6+")]
        for fen,san in cases:
            f=right_facts(ctx,fen,san)
            txt=await render(VerdictPrompt.system(correct=True,player_color="White"),VerdictPrompt.prompt(attempt=san,facts=f))
            print("\n### RIGHT: %s" % san); print("facts:", f.replace("\n"," | ")[:160]); print("->", txt)
asyncio.run(main())
