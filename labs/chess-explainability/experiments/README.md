# Experiment scripts (archived from the 2026-07-19 session)

Raw throwaway scripts, preserved as-is. Most run against the backend venv:
`cd backend && PYTHONPATH=python .venv/bin/python <path>/<script>.py`
Some hit the live Gemini API (need `GEMINI_API_KEY`); the free tier is 15 req/min.

`pz.csv` (the 48k-row Lichess puzzle slice) is NOT archived (8.5M data). Regenerate:
`curl --range 0-2500000 https://database.lichess.org/lichess_db_puzzle.csv.zst | zstd -dc > pz.csv`
Solver position = `Board(FEN).apply(mv[0]).fen`; solver move = `mv[1]`.

## The load-bearing ones
- `valplan.py`   — describe_plan (multi-ply) scale validation on Lichess (final: 101/101, INDEPENDENT verifier)
- `valpos.py`    — positional five-term term-delta reasoner validation (tactical vs positional slices; cp-gate)
- `delta.py`     — the "unopposed grab − real-PV grab" delta hypothesis (fast persistent-Stockfish)
- `unopp.py`     — unopposed-plan primitive (opponent passes N moves) — blind to forcing lines
- `render.py` / `render_right.py` / `both.py` — real LLM verdict renders (wrong / right / a full drill)
- `live5.py` / `liveexact.py`  — the a8-hallucination isolation (0/15 from clean facts → model deduction)
- `sheet.py` / `factsheet.py`  — exact fact-sheet dumps sent to the model
- `fp.py` / `nc5.py` / `rxc3.py` — specific false-positive reproductions (Rxh3, Nc5, the pin)
Everything else: one-off debug/timing/repro probes.
