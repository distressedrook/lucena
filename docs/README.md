# docs — design & locked contracts

Design-first, no vibe-coding. This is where each layer's **API contract is locked before code is
written**. Planned documents:

- `architecture.md` — the layer topology (grounding engine · backend/conversation-loop · mac-client),
  the open/closed boundary, and the hard invariants (state machine pristine & read-only; LLM never
  tool-calls or sets the board; deterministic-first).
- `grounding-engine-api.md` — the open engine's contract (validators, Stockfish, Maia3; stateless?).
- `backend-api.md` — the client ↔ backend contract (turns, beats, board stream, auth).
- `orchestrator.md` — the (now-historical) deterministic coaching-pipeline design, flow by flow.
  **Superseded** by the `ConversationLoop` (mode routing, not free-text intent classification); see
  `LLD.md`.
- `opening-annotator/` — the engine's `openings.tsv` converted into an explicit tree
  (`openings_tree.json`), plus schema + content rules (`SPEC.md`) for `openings_annotations.json`
  and `openings_socratic.json`, the curated LLM/hand-written commentary + teaching-Q&A layers over
  it. Also holds the curated worklist, a validation script, `CLAUDE.md` (auto-loaded instructions
  for a Claude Code session executing the worklist), and its own `AGENTS.md` + `review.sh` for a
  Codex content-review pass (quality, duplicate questions, coverage) separate from the root
  `AGENTS.md`'s code review.

Older design docs are archived in `legacy/docs/`.
