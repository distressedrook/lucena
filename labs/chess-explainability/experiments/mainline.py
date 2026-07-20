import json
from lucena_engine.board import Board
lib=json.load(open('/Users/avismara/.lucena-run/lessons/library.json'))
# find the fork puzzle by its poisoned meta / fen
spec=None
for s in (lib.values() if isinstance(lib,dict) else lib):
    for b in s.get('bits',[]):
        t=(b.get('params') or {}).get('tree') or {}
        if t.get('poisoned_line_meta',{}).get('fatal')=='Nxc6+':
            spec=s; TREE=t
if spec is None:
    print("not found"); raise SystemExit
def _is_student(n): return n.get("kind") in ("solve","mate")
# walk the MAIN line only (live[0] at each reply); count student moves to a terminal
n=TREE['root']; student_moves=[]; opp=[]
depth=0
while True:
    depth+=1
    if depth>50: print("DID NOT TERMINATE in 50"); break
    k=n.get('kind')
    if k=='solve':
        student_moves.append(n.get('expect_san'))
        aft=n.get('after')
        if not aft or aft.get('kind')!='reply':
            print("MAIN LINE ends after student move (no reply):", n.get('expect_san')); break
        live=[d for d in (aft.get('defenses') or []) if _is_student(d['then'])]
        if not live:
            print("MAIN LINE ends: student move", n.get('expect_san'),"was last (no live defense)"); break
        opp.append(live[0].get('san')); n=live[0]['then']
    else:
        print("terminal kind:", k); break
print("student moves (main line):", student_moves)
print("opponent replies:", opp)
print("=> main-line length:", len(student_moves), "student moves")
