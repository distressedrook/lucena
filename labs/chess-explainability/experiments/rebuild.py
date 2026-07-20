import tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.grounding_tools.drill import DrillState
FEN="1k5r/4q3/1pp5/3bNp2/6p1/P5P1/1P3P2/3QRK2 w - - 0 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
p=ctx.preview_drill(FEN)
TREE=p["tree"]
def count(n):
    c=1
    if n.get('after'): c+=count(n['after'])
    for d in (n.get('defenses') or []): c+=count(d['then'])
    for o in (n.get('options') or []): c+=count(o['then'])
    return c
def solves(n):
    c=1 if n.get('kind') in ('solve','mate') else 0
    if n.get('after'): c+=solves(n['after'])
    for d in (n.get('defenses') or []): c+=solves(d['then'])
    for o in (n.get('options') or []): c+=solves(o['then'])
    return c
print("BOUNDED tree: total nodes =", count(TREE['root']), "| solve/mate nodes =", solves(TREE['root']))
# full walk to conclusion
d=DrillState(TREE); moves=[]
for step in range(1,40):
    cur=d.current;k=cur.get('kind')
    if k=='solve': uci,san=cur.get('expect_uci'),cur.get('expect_san')
    elif k=='mate': o=(cur.get('options') or [{}])[0]; uci,san=o.get('uci'),o.get('san')
    else: print("stuck kind",k); break
    r=d.play(uci,san); moves.append(san)
    if r['finished']: print(f"FINISHED after {step} moves:", moves); break
else: print("did not finish in 40")
