import json, tempfile, asyncio
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.coaching.strategies import build_registry
from lucena_backend.coaching.bits import BitSpec, BitProgress
from lucena_backend.coaching.loop import Input
lib=json.load(open('/Users/avismara/.lucena-run/lessons/library.json'))
spec=[s for s in (lib.values() if isinstance(lib,dict) else lib) if '2rq1rk1' in (s.get('fen') or '')][0]
tree=[b for b in spec['bits'] if (b.get('params') or {}).get('tree')][0]['params']['tree']
FEN=spec['fen']
reg=build_registry(grade_fn=None); strat=reg["move_line"]
bs=BitSpec(strategy="move_line", params={"tree":tree}, challenge="x", grounding_req=None)
async def main():
    inp=Input(kind="move", uci="b2a1", fen=FEN, san="Qa1")
    correct,_,_=await strat.adjudicate(inp, None, bs, BitProgress())
    print("cached-tree adjudication of Qa1:", "correct" if correct else "WRONG")
    print("cached root expect:", (tree.get('root') or {}).get('expect_uci'), (tree.get('root') or {}).get('expect_san'))
asyncio.run(main())
