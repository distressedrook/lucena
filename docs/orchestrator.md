# Orchestrator — contract (v0, to lock)

> **SUPERSEDED.** The single-pipeline Orchestrator described below was replaced by `ConversationLoop`
> (`backend/python/lucena_backend/coaching/loop.py`), which routes every turn by mode (freeform vs
> coach) instead of by a free-text intent classifier. See `LLD.md` and `coaching/loop.py`. The flow
> catalog below is retained as historical design context.

> The deterministic coaching pipeline. It owns the control flow; the LLM is a pure generator. Every
> turn: **classify → ground → generate → act**. No LLM tool-calling; the model never decides which
> tool to run or what the board is. Reuses the prototype in `legacy/agent/orchestrator.py` +
> `legacy/agent/quick.py`.

## Dependencies (all injected — testable)

- **State machine** (in-process): read the input mailbox + board (to classify), push beats, set the
  gate (bank mastery — parked this cycle; seam kept). The orchestrator is its ONLY writer.
- **Grounding engine** (gRPC client): `Analyze`, `Evaluate`, `Hints`, `ExploreLine`, `TopHumanMoves`,
  `CommonMistakes`, `PoisonedLine`, `ValidateFen`, `ParsePgn`.
- **LLM adapter** (in-process): `generate(messages, opts)` — provider-agnostic.
- ~~**Mastery**~~ — **PARKED this cycle** (first-class for v1). Flows run without recording/reading
  mastery for now; `probe_answer` gives feedback but records no observation. The seams stay in the
  contract so mastery drops in later without reshaping the pipeline.

## The pipeline

1. **Classify** (deterministic, no LLM). Read the mailbox + current board from the state machine.
   Turn class from the app's input `kind` + gate state — the `read_input` logic moves HERE (it is
   orchestrator concern, not state-machine concern): `OPEN` · `PROBE_ANSWER` · `DRILL_EVENT` /
   `DRILL_WRONG` / `DRILL_SOLVED` · `MOVE_EXPLORE` · `SESSION` · `GAME_REVIEW`. Free-text intent
   ("give me a puzzle", "start a study") is resolved by **one small LLM classification** into a closed
   intent enum (robust to phrasing — never keyword matching).
2. **Ground** (deterministic). Call the grounding engine over gRPC for exactly the facts this flow
   needs (analysis, hints, refutation, Maia, …), against the board the state machine holds. Also
   compute the **deterministic frame** the model must not infer: whose move it is, who the opponent
   is, the material standing.
3. **Generate** (ONE LLM call). A small per-flow prompt (see `docs/backend-flows` / the templates that
   replace the 23KB contract) + the grounded facts + the frame → text, or a small JSON verdict via
   `opts.schema`. The model calls no tools and sees no provider specifics.
4. **Act** (deterministic). Write to the state machine: push beats (`say`/`ask`; an `ask` sets the
   gate), mark a puzzle served, etc. (*record a mastery observation — parked this cycle; the seam
   stays*). The state machine streams the new beats/board to the client over the WebSocket.

## Flows (ported → to port)

| Flow | Class / trigger | Ground | Generate | Act |
|---|---|---|---|---|
| **coach** ✅ | `OPEN` | `Analyze` + `Hints` | one JSON call `{mode: ask\|tell, text}` — model interprets intent | `ask` beat (+ grounded hint ladder, stops→gate) or `say` beat |
| **probe_answer** ✅ | `PROBE_ANSWER` | `Analyze` | one JSON call `{correct, quality, feedback, concept}` graded vs engine | feedback beat (mastery recording parked this cycle) |
| **explain** ✅ | "Why?" (on-demand) | `Evaluate(move)` | one text call from the refutation | `say` beat |
| **move_explore** ▢ | `MOVE_EXPLORE` | model proposes moves (JSON) → `ExploreLine` grounds → | interpret the grounded line | `say` beat (the structured-output template for "model directs, runner grounds") |
| **drill events** ▢ | `DRILL_*` | per event | coach the move | beat |
| **game_review** ▢ | `GAME_REVIEW` | `get_game_analysis` (backend) | walk the mistakes | beats |
| **session** ▢ | `SESSION` | `get_mastery` | orient in one line | beat |
| **intent routing** ▢ | free-text | — | intent classify → dispatch | `set_puzzle` / load study (deterministic) |

✅ prototyped in `legacy/agent/orchestrator.py`; ▢ to port in M1.

## Invariants

1. **The model never tool-calls, never sets the board, never mutates state.** It returns text/JSON;
   the orchestrator does every tool call (engine gRPC) and every state write.
2. **One bounded LLM call per hot-path turn.** Ask-vs-tell and intent fold into the generation or a
   single tiny classification — never a multi-round agentic loop.
3. **Ground the frame, not just the facts.** Perspective (you = side to move; opponent = other
   colour), evals-in-words, and moves are supplied by the runner — the model can't garble whose
   threat is whose (the bug that motivated this rule).
4. **Deterministic control flow** — classification, dispatch, and the act step are plain code, covered
   by a no-LLM harness (like today's `legacy/tools/gate_state_harness.py`); only *generation quality*
   needs a real model.
5. **When mastery lands (v1), it is recorded by the runner, not the model** — honest measurement is
   guaranteed, not pleaded. (Mastery is parked this cycle; the seam stays in the pipeline.)
6. **The orchestrator enforces failure handling** — every engine (gRPC) and LLM (HTTP) call is
   deadline-bounded; on LLM failure it chooses the degraded path (**truth-without-voice** from the
   grounded fact sheet), on engine failure it pauses new grounding with a bounded retry. The full
   ladder + the minimal LLM breaker live in `architecture.md` "Failure & degradation"; the orchestrator
   is where they're applied.
