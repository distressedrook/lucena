# Backend API — client ↔ backend contract (v0, to lock)

> How the mac client talks to the backend. **WebSocket** for the live coaching loop (input up,
> the full state stream down); **REST** for everything not in the hot path (auth, library, history,
> config). Hosting-friendly: SSE was rejected (one-way HTTP, awkward to host); the WS is the one live
> channel.

## WebSocket — the live loop  `wss://…/session/{session_id}`

One socket per active session. Player input goes up; the state machine's change stream comes down.
Every message is a JSON envelope `{type, ...payload}`. Server→client payloads are **version-stamped**
(the monotonic document `version`); the client applies deltas in order and re-syncs on a gap.

**Client → server** (the app's actions; these drive the loop / state machine):

| type | payload | effect |
|---|---|---|
| `turn` | `{text}` | the player's typed message → a coaching turn (the loop routes by mode and responds; a FEN-shaped text is a position set-up). |
| `move` | `{uci, fen}` | a played move → routed by the loop (coach mode adjudicates it; freeform mode explains it). |
| `position` | `{fen}` | the board the client is displaying → `set_board_view` (the reported board; navigation, not a turn). |
| `view` | `{fen, line, tree, cursor}` | full display state → `set_view` (navigation; replayed on resume). |
| `input` | `{kind, ...}` | structured input into the mailbox: `drill_event` / `drill_solved` / `done`. |

**Server → client** (the state machine's stream — see `docs/state-machine.md` for field detail):

- **On connect — snapshot, then `ready`:** `board`, `beats` (full list + `cursor`), `analysis`,
  `tree`, `history` (`plies`), `view`, `sessions`, `activity` — all at the same `version` — then
  `ready`.
- **Live deltas:** `board` (full board obj), `beats` (`{appended:[…new]}`), `analysis`, `tree`,
  `tree_cleared`, `history`, `status` (transient coach-working line), `engine_lines` (transient live
  multi-PV), `reset` (drop & re-render, followed by a fresh snapshot).

Payload shapes (canonical, from the state machine):
- `board`: `{seq, fen, side_to_move, terminal, arrows, highlights, caption, eval, has_poisoned_line, poisoned_line, version}`
- `beats`: snapshot `{beats:[{i, kind, tone?, segments, stops, hints?, board_seq}], cursor, version}` · delta `{appended:[…], version}`
- `analysis`: `{fen, side_to_move, verdict, observations, board_seq, version}`
- `tree`: `{…forcing-line tree, version}` · `tree_cleared`: `{version}`
- `history`: `{plies:[{n, san, fen}], version}`   *(SAN only — no UCI on the wire; see architecture.md rule)*
- `view`: `{session, fen, side_to_move, cursor, in_variation, line, tree, version}`  *(snapshot only)*
- `sessions`: `{sessions:[{session_id, name, updated_at}], current, version}`
- `activity`: `{depth, kind, version}` · `status`: `{text|null, version}` · `ready`: `{}`

## REST — everything else  `https://…`

Not in the live loop → plain HTTP.

- **Auth:** `POST /auth/login` → session token; token authorizes the WS upgrade + REST calls.
  *(Mechanism — token type, refresh — TBD; auth detail deferred with the memory system.)*
- **Library / sessions:** `GET /sessions` (rail list) · `POST /sessions` (new) ·
  `POST /sessions/{id}/resume` · `DELETE /sessions/{id}`. (The live board/beats for a session arrive
  over the WS on connect, not here.)
- **Games:** `POST /games/import` (PGN → the import pass) · `GET /games/{id}/analysis`
  (`get_game_analysis` digests, for the game-review flow).
- **Config:** `GET /config` (client-visible settings).

## Rules

1. **Hot path = WebSocket, everything else = REST.** The live coaching loop (input + the whole state
   stream) is the socket; auth/library/history/config are REST.
2. **The client is thin and holds no chess truth** — it renders `board`/`beats` and sends actions; it
   never validates moves or decides coaching (the backend + engine do).
3. **Ordering is by `version`** — the client tracks the document version, applies deltas in order, and
   re-requests a snapshot (`reset`) on a gap. `view` is client-authored and never echoed as a delta.
4. **One socket per session**; a session switch is a new connect (snapshot + `ready`).
5. **SAN only on the wire** — no move payload (`history` plies, board, beats) ever carries UCI (see
   `architecture.md` / `grounding-engine-api.md` design rule 1).
6. **Client→server commands carry an idempotency key** (`turn`/`move`/`input`) so that on a
   **WebSocket reconnect** a resubmitted command is not double-applied — the key plus the monotonic
   `version` guard the resume. (This is the client→backend boundary the failure design relies on; see
   `architecture.md` "Failure & degradation".)
