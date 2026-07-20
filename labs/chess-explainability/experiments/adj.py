import tempfile, asyncio
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.coaching.strategies import build_registry
from lucena_backend.coaching.bits import BitSpec, BitProgress
from lucena_backend.coaching.loop import Input
FEN="2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
tree=ctx.preview_drill(FEN)["tree"]
reg=build_registry(grade_fn=None)
strat=reg["move_line"]
spec=BitSpec(strategy="move_line", params={"tree":tree}, challenge="x", grounding_req=None)
prog=BitProgress()
async def main():
    for uci,san in [("b2a1","Qa1"),("g2d5","Bxd5")]:
        inp=Input(kind="move", uci=uci, fen=FEN, san=san)
        p=BitProgress()
        correct,newp,eff=await strat.adjudicate(inp, None, spec, p)
        print(f"  play {san:5} ({uci}): correct={correct}")
asyncio.run(main())
