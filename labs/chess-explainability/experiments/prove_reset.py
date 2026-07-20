import json, asyncio
from lucena_backend.grounding_tools.drill import DrillState
from lucena_backend.coaching.strategies import MoveLineStrategy
from lucena_backend.coaching.bits import BitProgress, BitSpec
from lucena_backend.coaching.loop import Input
lib=json.load(open('/Users/avismara/.lucena-run/lessons/library.json'))
spec=[s for s in (lib.values() if isinstance(lib,dict) else lib) if '2rq1rk1' in (s.get('fen') or '')][0]
TREE=[b for b in spec['bits'] if (b.get('params') or {}).get('tree')][0]['params']['tree']
first=TREE['root']['expect_uci']  # b2a1 (Qa1)
# simulate a prior attempt: play move 1, walker advances -> stale mid-line state
w=DrillState(TREE); w.play(first, None); stale=w.to_state()
print("first move:", first, "| stale walker state non-empty:", bool(stale), "| finished:", stale.get('finished'))
bs=BitSpec(strategy="move_line", params={"tree":TREE}, challenge="x", grounding_req=None)
strat=MoveLineStrategy()
async def adj(prog): return (await strat.adjudicate(Input(kind="move",uci=first,san="Qa1"), None, bs, prog))[0]
async def main():
    print("  play Qa1 with STALE state (the bug):   correct =", await adj(BitProgress(strategy_state=stale)))
    print("  play Qa1 with RESET state (the fix):    correct =", await adj(BitProgress()))
asyncio.run(main())
