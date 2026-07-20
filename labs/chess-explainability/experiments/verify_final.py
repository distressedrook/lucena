import tempfile
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_backend.grounding_tools.drill import DrillState
FEN="1k5r/4q3/1pp5/3bNp2/6p1/P5P1/1P3P2/3QRK2 w - - 0 1"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)
p=ctx.preview_drill(FEN); T=p["tree"]
def solves(n):
    c=1 if n.get('kind') in ('solve','mate') else 0
    if n.get('after'): c+=solves(n['after'])
    for d in (n.get('defenses') or []): c+=solves(d['then'])
    for o in (n.get('options') or []): c+=solves(o['then'])
    return c
print("drillable:", p.get("drillable"), "| solve nodes:", solves(T['root']))
print("poisoned  :", T.get("has_poisoned_line"), "| line:", [m.get('san') for m in (T.get('poisoned_line_moves') or [])])
d=DrillState(T); mv=[]
for _ in range(15):
    c=d.current;k=c.get('kind')
    u,s=(c.get('expect_uci'),c.get('expect_san')) if k=='solve' else ((c.get('options') or [{}])[0].get('uci'),(c.get('options') or [{}])[0].get('san'))
    r=d.play(u,s); mv.append(s)
    if r['finished']: print("CONCLUDES in", len(mv), "moves:", mv, "-> Solved + poisoned reveal fires"); break
