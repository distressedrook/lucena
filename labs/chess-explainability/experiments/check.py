from lucena_engine import Engine
from lucena_backend.grounding_tools.tools import ToolContext
from lucena_backend.persistence.state import StateStore
from lucena_backend.coaching.grounding import _hint_line, _squandered_win
import tempfile
FEN = "r2qkb1r/pp2pppp/3p1n2/4n3/4b1PN/2PB3P/PP3P2/RNBQK2R w KQkq - 0 12"  # the Bxe4 puzzle
with Engine(threads=1) as e:
    e.new_game()
    ctx = ToolContext(e, StateStore(tempfile.mkdtemp()))
    h = ctx.get_hints(FEN)
    print("best:", h.get("best"))
    print("hints ladder:", [ (r.get('rung'), r.get('text')) for r in (h.get('hints') or []) ] or "EMPTY")
    v = ctx.evaluate(FEN, ["f2f4"])  # f4 blunder
    print("squandered fires:", bool(_squandered_win(True, v)))
    print("hint rung0:", _hint_line(h.get('hints'), 0))
