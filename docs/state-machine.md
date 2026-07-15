# State Machine — contract (v0, to lock)

> The single source of truth for all application/session state, lifted from
> `legacy/python/lucena/mcp/state.py` (`StateStore`) into the backend as an **in-process module**.
> **Behaviour and every invariant are unchanged**; the migration *hardens* it and **relationalises its
> persistence** (the one JSON-blob document → Postgres columns/tables — a storage change, not a logic
> change; see Persistence below). Mutated ONLY by the deterministic orchestrator — never by the LLM. The MCP wrapper is removed: the orchestrator calls `StateStore`
> directly; the client sees changes via the WebSocket (below).

## Invariants (the reason this module exists — keep them exactly)

1. **One board, derived — never a rival copy.** `_Workspace.last_board` is THE board. `board_view`
   (→ `board_fen`) is a pure derivation of it. Never resolve "the current board" through a priority
   chain across stored copies (the old `view.fen`-first ordering let a stale UI view outrank the
   coach's own paint — that class of bug stays dead).
2. **Projections, not duplicates.** The published board's `arrows/highlights/caption/eval` project
   from the durable `decorations` slot (shown only while the board sits at `decorations.for_fen`);
   `has_poisoned_line/poisoned_line` project from the durable `poisoned` slot. The trap/paint live on
   the document, never on the transient board.
3. **One monotonic `version`** per session document is the durability + ordering key — bumped on every
   mutation, persisted, restored on load. (The residual per-channel `*_seq`s are wire debt to collapse
   toward `version` during hardening — never to extend.)
4. **Per-session isolation.** State is keyed by session id; the input mailbox is per-session runtime,
   never persisted, so it can never leak across a switch.
5. **Single-writer, serialized.** Every mutation runs behind one lock (today `ctx._tool_lock` +
   `asyncio.to_thread`); the orchestrator is the sole writer.

## Canonical model

**`_Live` (per session):** `beats[]` + `beats_seq`, `gate_awaiting` + `gate_pending` (durable Socratic
gate), `version`, `status` (`active|complete`), `banked[]` (mastery concept ids this session),
`served_puzzles[]`, `drill_close`, `activities[]` (the activity stack; `[0]` = base), `input`
(per-session mailbox, **never persisted**). Workspace fields below are exposed as delegating
properties onto the top frame.

**`_Workspace` (per activity frame):** `last_board` (**SOT: board**), `decorations` (**SOT: coach
paint**), `poisoned` (**SOT: freeform trap**), `last_analysis`, `last_tree`, `drill_state`, `history`,
`view` (UI-authored display state — not a board source), + wire seqs (`board_seq`/`tree_seq`/… — debt).

**Persistence — Postgres, relational (no JSON-as-state).** The session is **not** stored as a canonical
JSON blob; it is **relationalised into columns/tables**, one Postgres from the start (decided
2026-07-14; see `architecture.md` "Persistence boundary"). Behaviour and every invariant are
unchanged — only the storage representation changes. JSON is allowed only as *configuration*, never as
state; there is no `session.json` file — **at most one session is `is_active`** (a DB flag, flipped
when the player clicks a session; a partial unique index enforces "at most one").

```
-- session level (_Live) ------------------------------------------------
session(id, name, status,               -- 'active' | 'complete'
        is_active bool, version bigint, created_at, updated_at)
        └─ unique index on (is_active) WHERE is_active     -- at most ONE active session
gate(session_id pk, awaiting, pending …)                   -- durable Socratic gate
beat(session_id, i, kind, tone, stops)  └─ beat_segment, beat_hint   -- beats + their lists
served_puzzle(session_id, puzzle_id)                       -- "give me another" never repeats
banked_concept(session_id, concept_id)                     -- mastery parked; table is a stub
drill_close(session_id pk, …)                              -- consume-once, survives relaunch
-- activity stack + per-frame workspace (_Frame / _Workspace) ----------
activity(session_id, idx, kind)                            -- idx 0 = base; one frame today, stack-ready
board(session_id, activity_idx, fen)                       -- last_board; side_to_move/terminal DERIVED
decoration(session_id, activity_idx, for_fen, caption, eval_cp, eval_win_pct)
   └─ decoration_mark(…, kind ['arrow'|'highlight'], from_sq, to_sq)
poisoned(session_id, activity_idx, for_fen, fatal, idea)   └─ poisoned_step(…, ply, san, fen)
ply(session_id, activity_idx, n, san, fen)                 -- history; SAN only (no uci)
view(session_id, activity_idx, fen, cursor, in_variation)  └─ view_move(…, ord, san)
```

**Not persisted:** `last_analysis` (cheap engine call — re-derived on resume); `last_tree` (the
forcing-line drill tree — a **precomputed, position-keyed cache** built offline, shared across
sessions/users, deterministic via `nodes`+`Threads=1`; parks with the content/drill cluster, never
per-session state); the per-channel `*_seq` counters (collapsed into `version`); the input mailbox
(runtime-only). `gate_pending`, `drill_state`, and the `beat` segment/hint columns are small
structured shapes to model exactly from their producers when the schema is implemented.

**Activity stack:** `push_activity(kind, seed?)` freezes the top workspace and starts a fresh one
(seed filtered to `_SEEDABLE` — a push can never smuggle in a cursor write); `pop_activity()` restores
the parent (false at base); session-level state (beats, gate, version) is continuous across a push.

## Public API (in-process, what the orchestrator calls)

Grouped; signatures verbatim from the lift. All mutators persist + publish unless noted.

- **Session lifecycle:** `ensure_session_id()`, `read_session_id()`, `write_session_id(id)`,
  `_switch_current(sid)`, `status`, `set_status("active"|"complete")`, `reset_session()`, `dump()`.
- **Board:** `write_board(fen, *, arrows, highlights, caption, eval) -> board_seq` (coach paint),
  `set_board_view(fen)` (the app reports its displayed fen; no publish), `board_view -> fen` (derived).
- **Beats / status:** `append_beats(list) -> [i]` (publishes a `beats` **delta**),
  `publish_status(text|None)` (transient phase line).
- **Gate:** `set_gate(awaiting, pending=None)`, `_gate_awaiting`, `_gate_pending`.
- **View:** `set_view(snapshot) -> view|None` (records fen+line+tree+cursor; not published live —
  replayed on connect), `view`.
- **Activities:** `frame_depth`, `top_kind`, `push_activity(kind, seed=)`, `pop_activity() -> bool`,
  `set_base_activity(kind)`.
- **Drill / trap:** `write_tree(tree) -> seq`, `clear_tree()`, `set_drill_state(state|None)`,
  `drill_state`, `write_history(plies) -> seq`, `write_analysis(fen, *, verdict, observations)`,
  `set_drill_close(info)`, `take_drill_close() -> info|None` (consume-once), `set_poisoned(...)`,
  `clear_poisoned(for_fen=)`, `poisoned`.
- **Mastery banking:** `add_banked(concept_id)`, `banked`, `mark_puzzle_served(id)`, `served_puzzles`.
- **Input mailbox:** `set_input(data)`, `read_input() -> dict` (read-AND-consume, one-shot; `{"kind":
  "none"}` when empty).
- **Pub/sub + snapshot:** `subscribe() -> Queue`, `unsubscribe(q)`, `snapshot() -> [(channel,
  payload)]`, `publish_engine_lines(payload)`.

> Note: the current `read_input` ALSO carries classification + `board_fen` + `load_skill`. In the new
> design, **classification is the orchestrator's concern** (it reads the mailbox + the board from the
> state machine and classifies); the state machine just owns the mailbox and the board. See
> `docs/orchestrator.md`.

## Change events → WebSocket

The backend's WebSocket handler is a `subscribe()`r: it streams the store's `(channel, payload)`
events to the client. Same event set as today's `/state` SSE, now over the WS. Every payload is
stamped with the document `version`.

- **Snapshot** (on connect / session switch / republish): full `board`, full `beats` (+ `cursor`),
  `analysis`, `tree`, `history` (`plies`), `view` (if it matches history), `sessions`, `activity` —
  all at the same `version` — then a `ready` marker.
- **Deltas** (live): `board` (full obj), `beats` (`appended` — only new), `analysis`, `tree`,
  `tree_cleared`, `history`, `status`, `engine_lines`, `reset`. (`view` is never a delta — the client
  is its source.)
- No separate `turn`/`drill` events: side-to-move rides inside `board`/`analysis`/`view`; the drill
  channel is `tree`/`tree_cleared`; drill-close is in-process (`take_drill_close`), not a wire event.

The full payload shapes are the WS message schemas — specified in `docs/backend-api.md`.

## Robustness hardening (behaviour identical; only sturdier)

- **Type the model** (dataclasses/pydantic for `_Live`/`_Workspace`/board/beat/gate) with validation
  at the boundaries — no loose dicts leaking through the API.
- **Collapse the residual per-channel `*_seq`s toward the one `version`** (pay down the wire debt the
  invariants already call out — never extend it).
- **Make the single-writer lock explicit** at the module boundary (not incidental to the MCP server).
- **Comprehensive tests** on the invariants: board-derivation, projection gating, gate durability
  across resume, activity push/pop continuity, per-session isolation, delta-vs-snapshot ordering.
  (Port the existing `legacy/tests` that cover these.)
