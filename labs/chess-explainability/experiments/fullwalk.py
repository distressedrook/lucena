import json
from lucena_backend.grounding_tools.drill import DrillState
lib=json.load(open('/Users/avismara/.lucena-run/lessons/library.json'))
TREE=None
for s in (lib.values() if isinstance(lib,dict) else lib):
    for b in s.get('bits',[]):
        t=(b.get('params') or {}).get('tree') or {}
        if t.get('poisoned_line_meta',{}).get('fatal')=='Nxc6+': TREE=t
d=DrillState(TREE)
for step in range(1,60):
    cur=d.current; k=cur.get('kind')
    if k=='solve':
        uci,san=cur.get('expect_uci'),cur.get('expect_san')
    elif k=='mate':
        o=(cur.get('options') or [{}])[0]; uci,san=o.get('uci'),o.get('san')
    else:
        print(f"step {step}: current is kind={k!r} (not playable) — STUCK"); break
    r=d.play(uci,san)
    ev=r['event'].get('event') or r['event'].get('kind')
    print(f"step {step}: played {san} -> correct={r['correct']} finished={r['finished']} event={ev} current_kind={d.current.get('kind')} stack={len(d.stack)}")
    if not r['correct']:
        print("  !! expected move scored WRONG — the tree's own solution fails adjudication (BUG)"); break
    if r['finished']:
        print("  == FINISHED after", step, "moves =="); break
else:
    print("did not finish in 60 moves")
