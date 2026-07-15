# docs — design & locked contracts

Design-first, no vibe-coding. This is where each layer's **API contract is locked before code is
written**. Planned documents:

- `architecture.md` — the layer topology (grounding engine · backend/orchestrator · mac-client),
  the open/closed boundary, and the hard invariants (state machine pristine & read-only; LLM never
  tool-calls or sets the board; deterministic-first).
- `grounding-engine-api.md` — the open engine's contract (validators, Stockfish, Maia3; stateless?).
- `backend-api.md` — the client ↔ backend contract (turns, beats, board stream, auth).
- `orchestrator.md` — the deterministic coaching pipeline, flow by flow.

Older design docs are archived in `legacy/docs/`.
