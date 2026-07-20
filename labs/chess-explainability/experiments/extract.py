import tempfile, json
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.engine_io.enginepool import EnginePool, default_size
from lucena_engine.board import Board
from lucena_engine.positional import analyze_positional
FEN="2rq1rk1/R2n1ppp/4p3/2pb4/5B2/6P1/1Q2PPBP/3R2K1 w - - 0 21"
ctx=ToolContext(store=StateStore(tempfile.mkdtemp()),pool=EnginePool(size=default_size(),threads=1,hash_mb=64),maia=None,player_rating=1500)

print("="*70,"\nA) NL FACT SHEET (analyze_and_show focus=analysis) — the coach's briefing\n","="*70)
a=ctx.analyze_and_show(FEN, focus="analysis", board_push=False)
for l in a.get("analysis") or []: print("  ",l)

print("\n","="*70,"\nB) RAW STRUCTURED FACTS (kind / stance-source / squares / salience)\n","="*70)
with ctx._pool.lease() as e:
    from lucena_engine.facts import build_fact_sheet
    facts=build_fact_sheet(Board(FEN), e, movetime_ms=1000)
for f in facts:
    print(f"  [{f.kind:16}] {f.text}")
    print(f"     prov={f.provenance}  squares={f.squares}  salience={f.salience}")

print("\n","="*70,"\nC) POSITIONAL TERMS (cp, White POV)\n","="*70)
pos=analyze_positional(Board(FEN))
for k,v in sorted(pos["terms"].items(), key=lambda kv:-abs(kv[1]['cp'])):
    print(f"  {k:12} {v['cp']:>6}  {v['standing']}")

print("\n","="*70,"\nD) BEST MOVES (evaluate top candidates)\n","="*70)
with ctx._pool.lease() as e:
    r=e.analyse(FEN, multipv=3, movetime_ms=2000)
for i,ln in enumerate(r.lines):
    print(f"  {i+1}. score={ln.score} pv={ln.pv_san[:5] if hasattr(ln,'pv_san') else ln.pv[:5]}")
