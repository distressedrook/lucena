# Full-Codebase Review — Backend + Engine

**Date:** 2026-07-17 · **Scope:** all of `backend/` and `engine/` except `coaching/orchestrator.py` and `coaching/prompts.py` · **Dimensions:** correctness, design, performance, scale.
Five parallel reviewers (grounding tools, persistence+HTTP, coaching/LLM/engine-IO, engine analysis, engine infra); top findings spot-verified against source.

**GPL hygiene: clean.** No `python-chess` import anywhere in the engine; Rust core depends only on MIT/Apache `cozy-chess`; Stockfish/Maia are subprocess-only.

---

## P0 — Fix first (availability / correctness of core loop)

### P0.1 One DB error bricks the whole backend
`backend/persistence/db.py:153-164` — `_ex` handles only `psycopg.OperationalError`; there is **no rollback** for any other `psycopg.Error` (the only `rollback()` in the file is `set_active_session`'s at :280). A single constraint violation — e.g. two registrations of the same email → `UniqueViolation` — leaves the one process-wide connection in an aborted transaction; **every query thereafter fails with `InFailedSqlTransaction` until restart**.
**Fix:** wrap every public method (or `_ex`) with `except psycopg.Error: self._conn.rollback(); raise`, or use `with self._conn.transaction():` per operation. Pair with P1.9 (map `UniqueViolation` → `email_taken`).

### P0.2 Reconnect-retry can commit half a document write
`db.py:157-164` — if the connection drops mid-`save_document` (a multi-statement transaction), `_ex` reconnects and executes only the *remaining* statements, then commits the tail: stale `session_doc.version`, fresh `banked`/`activity`/`beat` rows — exactly the beats/document consistency `append_beats` promises.
**Fix:** track a transaction-in-progress flag; on reconnect mid-transaction, raise instead of retrying so the caller's whole operation re-runs.

### P0.3 Gemini calls have no timeout at all
`backend/llm/gemini.py:40-51` — `GenerateOptions.timeout_s` (default 30s) is declared in `interface.py:24` but **never applied**; no timeout of any kind is set on `generate_content`. A stalled Gemini call hangs the coaching turn forever (the exact ADK-hang lesson the module docstring cites), leaving the client's "Thinking…" halo up permanently.
**Fix:** `asyncio.wait_for(..., opts.timeout_s)` around the await, or `http_options=types.HttpOptions(timeout=...)`.

### P0.4 Engine has a lifetime budget of exactly one restart
`engine/lucena_engine/uci.py:222` — `_restarts` is incremented on restart and **never reset after success**. In a long-lived backend, Stockfish crashes once (recovered), crashes again later → every subsequent `analyse` raises `EngineError` forever. Compounded by `server/serve.py:36-42`, where `EngineHolder` caches the dead `Engine` forever and `acquire()` calls `new_game()` — which bypasses the restart wrapper entirely (uci.py:166-169) — so the gRPC Truth service bricks permanently on the first post-crash RPC.
**Fix:** reset `self._restarts = 0` after a successful call; route `new_game()` through `_with_restart` and `self._lock`; in `EngineHolder.acquire`, drop and rebuild on `EngineError`.

### P0.5 Restart path leaks processes and misfires on checkmate positions
`uci.py:225` — restart sets `self._proc = None` **without closing the old process** (leaks Stockfish + 3 pipe fds whenever the error wasn't process death). And `_parse_analysis`'s `EngineError("no legal moves…")` on a terminal FEN is routed through the restart path: every checkmate/stalemate query abandons a healthy engine, leaks it, spawns a new one, and raises the same error again. `puzzle.py:40-42` and `server/truth.py:126,186,200,241` call `analyse` on positions that can be terminal, so this is reachable from normal traffic.
**Fix:** `self.close()` before `_start()`; separate exception types for "process dead" vs "protocol/semantic error" and only restart on the former; check `legal_moves()` before `analyse` at the call sites.

### P0.6 A checkmating move is scored as *losing* in multi-move evaluation
`engine/lucena_engine/server/truth.py:243` — a move that delivers mate is scored `Score(mate=0)`, whose semantics are "side to move is mated" → `to_ceiled_cp() = -1000`, win% ≈ 3. In `_evaluate_many`, **Qh7# ranks last in the verdict**. Root cause: `evalmodel.py:62-66` — `Score(mate=0).negated()` is a silent no-op; the class can't represent "just delivered mate".
**Fix:** short-circuit the delivered-mate case to `win_pct=100 / cp=+1000` (as the single-move path at truth.py:195-196 and gamepass.py already do); make `Score.negated()` raise on `mate == 0`.

### P0.7 Blocking pipe reads with no timeout — one hung engine deadlocks everything behind it
`uci.py:150` and `maia.py:104-112` — `_readlines` iterates the pipe with no deadline. A wedged Stockfish (alive but silent) or a stalled torch model load blocks the caller **forever while holding `self._lock`** — every thread that touches that engine wedges, with no recovery (`poll()` never fires because the process is alive). Amplified by `grounding_tools/tools.py:984`, where `poisoned_line_fut.result()` also has no timeout and is awaited while holding the per-chat lock + leased engine.
**Fix:** drain-thread + `queue.get(timeout=movetime+margin)`, kill on expiry; generous first-call timeout for Maia model load; `result(timeout=...)` on the poisoned-line future, treating timeout as no-detection.

---

## P1 — High

### Backend

1. **Schema never sent to Gemini** — `llm/gemini.py:45-46`: `opts.schema` only toggles `response_mime_type="application/json"`; `response_schema` is never set, so "force structured JSON" doesn't happen — the model can return wrong-shaped JSON that parses fine and silently loses fields. **Fix:** `cfg_kwargs["response_schema"] = opts.schema`.
2. **Empty completions returned as success** — `gemini.py:42,53,57`: no check of `finish_reason`; with thinking-enabled models, a 200-token cap (QuickCoach) routinely yields `MAX_TOKENS` with empty text → blank coach bubble. `json.loads(text or "{}")` turns empty text into a "valid" `{}` instead of the documented `json=None`. **Fix:** set `thinking_budget=0` for flash-class models, inspect `finish_reason`, raise on empty; only parse non-empty text.
3. **`write_analysis` publishes without `_wlock`** — `persistence/state.py:1294-1305`: unlike every sibling writer (`write_board`:1221, `append_beats`:1232, `write_tree`:1268, `write_history`:1279), the persist+publish pair is unlocked — a concurrent writer's bump+publish can interleave, and the app's ordered-delta guard drops an event (the frozen-screen failure the `_wlock` comment at :300 describes). **Fix:** wrap in `with self._wlock:`.
4. **Blocking DB queries on the event loop** — `httpserver.py:215-216` (WS connect calls `store.snapshot()` → `db.list_sessions()` directly on the loop; `sessions.py:21-27`'s "no I/O" docstring is false) and `httpserver.py:184-189` (error path does a full `save_document` on the loop), plus `auth.py:83` (`get_user_by_email` sync on the loop). Every WS connect / LLM failure / registration stalls **all** sockets for a Postgres round trip. **Fix:** `asyncio.to_thread` for all of these; fix the sessions.py docstring.
5. **`_wlock` held across DB I/O while the loop also takes it** — `state.py:917-923, 435-440` vs `publish_status` at :1089 called from the loop (httpserver :135, :184): a thread mid-save makes the event loop block synchronously on a threading lock for the duration of a Postgres write. **Fix:** never take `_wlock` on the loop; shrink critical sections to exclude DB I/O.
6. **O(N²) write amplification** — `db.py:407-427` + `state.py:430-440`: every beat/repaint/`/view` message rewrites the *entire* decomposed document (9 DELETEs + re-INSERT of every activity/ply/decoration, one statement per row). A 60-move game re-inserts ~120 ply rows per persist, all behind the single connection's RLock. **Fix:** delta persistence (header always; lists only when dirty) + `executemany`/`COPY`.
7. **`_live` never evicts** — `state.py:293,361-365`: every chat ever touched stays in memory forever with its full beats list; same for `tools.py:516-521` (`_tool_locks`, `_sctx` — the latter pins drill trees) and `httpserver.py:107-140` (`_coach_chain` keeps the last task per session forever). **Fix:** evict on no-subscribers+unbound after TTL / LRU; pop chain entry in the done callback.
8. **Grounding hook misses `evaluate_and_show`** — `tools.py:389-391` (verified): `must_ground` matches exact tool name, so on DRILL_WRONG/MOVE_EXPLORE turns a successful `evaluate_and_show` doesn't count as grounding and the subsequent `push_beat` is refused `ungrounded`, forcing a redundant `evaluate` on an already-searched position. **Fix:** treat `_and_show` variants as grounding-equivalent.
9. **Register TOCTOU → 500 → triggers P0.1** — `auth.py:83-87`: concurrent same-email registrations both pass the check; the second `INSERT` raises `UniqueViolation` (not mapped) → 500 *and* aborts the shared connection. **Fix:** catch `UniqueViolation` → `RegisterError("email_taken")`.
10. **`ToolContext` god class** — `tools.py` (2,521 lines): ~40 tools + drill lifecycle + activity stack + Maia narration + poisoned-line orchestration + puzzle selection + mastery banking, reaching into `StateStore` privates throughout (`_current`, `_history`, `_last_board`, `_last_tree`, `_gate_awaiting`). Any StateStore refactor silently breaks these. **Fix (incremental):** give StateStore a public read surface first, then split drill adjudication / poisoned-line service / evaluation tools / turn gate.
11. **`gamepass --out` writes nothing** — `engine/gamepass.py:261-292,314-317` (verified): `out_path` is accepted and documented ("writes progressively") but no code writes any file; the CLI prints `"… -> analysis.json"` and exits 0 with no file. **Fix:** JSON-dump after the fast pass and again after the complete pass (atomic tmp+rename).
12. **MultiPV cache goes stale across engine restarts** — `uci.py:101-103,193-195`: `_start()` sends `MultiPV 1` but doesn't reset `_cur_multipv`; after a crash+restart, a retry that thinks MultiPV=3 is set silently gets 1 line — `puzzle.py`'s `a.lines[1]` fallback then misclassifies "only move". **Fix:** `self._cur_multipv = 1` inside `_start()`.

---

## P2 — Medium (grouped by theme)

### Concurrency & locking
- `enginepool.py:66` + `tools.py:237` — `lease(timeout=None)` blocks forever by default while the caller holds its per-chat lock; sustained pool exhaustion starves the whole default `to_thread` executor (≈32 threads). Fix: finite default timeout → `EngineError("engine pool busy")` so `_guarded` returns structured `engine_unavailable`.
- `enginepool.py:74-81` — only `EngineError` triggers discard; any other exception returns a possibly-desynced engine to the pool → next lease inherits stale UCI output. Fix: discard (or `isready` health-check) on *any* exception.
- `uci.py:166-169` — `new_game()` takes no lock and skips the restart wrapper (part of P0.4). `uci.py:114-121` — `close()` takes no lock; racing an in-flight analyse can trigger a pointless restart *after* close.
- `tools.py:704-707` — poisoned-line engine spawned while holding `_tool_locks_meta`, the mutex every guarded call needs → all chats' tool entry stalls for the spawn. Fix: dedicated init lock.
- `state.py:874-877` (`open_chat`) and `:593-599` (`_republish`) — unlocked reset+snapshot pairs; a concurrent writer between them produces the delta-ahead-of-baseline race `open_chat_for`'s docstring documents and fixes. Fix: locked batch enqueue, same as `open_chat_for`.
- `httpserver.py:221-233,266-273` — if `pump()`'s `send_json` raises (half-open TCP), the sender dies unobserved while the receive loop keeps the subscription alive; its unbounded queue grows until the OS notices. Fix: race pump/receive with `FIRST_EXCEPTION`; bounded queues (`state.py:929,1008` — on overflow drop + enqueue one "resync").
- `serve.py:64-76` — 8 gRPC workers funnel into one lock-guarded engine with no `maximum_concurrent_rpcs` and no `context.is_active()` checks: abandoned searches still run to completion, amplifying backlog. `behaviour.py:57-87` — the Stockfish lock is held across the entire Maia poisoned-line walk, so one Behaviour call stalls all Truth RPCs (and a hung Maia deadlocks Truth too).

### Correctness — chess/coaching logic
- `coaching/grounding.py:67-76` — `_move_phrase` mangles castling ("O-O" → "a pawn moves to -O") and promotions ("e8=Q" → dest "=Q") in refutation briefings — the confabulation guard itself confabulates. Fix: special-case `O-O`/`O-O-O` and strip `=X`.
- `coaching/quick.py:75` (verified) — `json.dumps(facts)[:1500]` hard-truncates the grounding; `refutation_pv` sorts after `best` and is frequently what's cut, on exactly the wrong-move case QuickCoach exists for — plus raw-JSON dumping contradicts `grounding.py:150`'s own "never a raw JSON dump" rule and leaks eval numbers/glyphs the prompts elsewhere withhold. Fix: compose the briefing from `_brief_move` / whitelist fields.
- `drill.py:22` (verified) — `exp_uci.startswith(in_uci)` accepts *any* non-empty prefix: `"e7"` matches `"e7e8q"`; an underpromotion sent as `"e7e8"` is credited as the queen promotion. Fix: require from/to equality, prefix-tolerance only for the 5th (promotion) char.
- `tools.py:1087-1092` — `_resolve_move`'s UCI-prefix fallback resolves `"d2"` to whichever legal move sorts first. Same fix shape as drill.py.
- `tools.py:1983-1985` — idempotent replay in `read_input` consumes and discards a one-shot `board_changed` mailbox signal, then returns the stale pre-change classification — defeating the backstop `_signal_board_change` exists for. Fix: exempt inputs carrying more than `kind` from the replay short-circuit.
- `tools.py:2240-2260` — freeform `play_move` appends to history without verifying the tip matches `pre`: navigate back 3 plies, play a different move → corrupt persisted line. Fix: truncate history to the ply matching `pre` before appending.
- `tools.py:1812-1836` — `set_board_from_paste` doesn't retire an active drill (`_drill`, persisted `drill_state`, `_last_tree` all survive) → misclassification via `_in_poisoned_context` and post-restart rehydration over the pasted position. Fix: `_reset_drill_line(fen)`.
- `tools.py:1996-1997` — poisoned-context override rewrites *any* non-drill class (even GAME_REVIEW with `game_id` set) to DRILL_POISONED_LINE. Fix: restrict to OPEN/MOVE_EXPLORE/DRILL_SOLVED.
- `detectors/defender.py:37-43` — "only defender" counts the enemy **king** as a removable defender (a deflection that doesn't exist) and, via full-occupancy `attackers()`, misses battery defenders (Rd1 behind Rd4). This detector is never engine-reconciled downstream. Fix: skip king-only defenders; use the SEE-style x-ray attacker set.
- `pgn.py:141-142` — `[FEN]` header ignored without `[SetUp "1"]`; many real exporters omit SetUp → game silently parsed from STARTPOS with a misleading "illegal move #1". Fix: honor FEN whenever present.
- `puzzle.py:40-42` — `_solver_node` analyses before checking `legal_moves()` → `EngineError` (and P0.5's leak) on terminal defense lines; also no `new_game()` per node (`:40,74`), so node-limited results depend on traversal history, breaking the reproducibility promise.
- `server/truth.py:126,186,200,240-243` — terminal FENs raise UNKNOWN instead of FAILED_PRECONDITION (inconsistent with `Analyze`); `_evaluate_many` re-analyses the unchanged root inside the per-move loop (up to 4 identical 1500ms searches per RPC — hoist it).
- `server/behaviour.py:29,58` — bare `Board(request.fen)` → `ValueError` → UNKNOWN instead of INVALID_ARGUMENT (truth.py's `_board` helper exists and isn't used).
- `auth.py:96-98` — the unknown-email timing-equalizer verifies against a hand-typed dummy argon2 hash; if argon2-cffi rejects it, `InvalidHashError` isn't caught (`:44-51`) → unknown-email logins 500 *fast*, reintroducing the enumeration signal the code exists to prevent. Fix: compute the dummy via `PasswordHasher().hash()` at import; add `InvalidHashError` to the except tuple.
- `state.py:1101-1126` — `reset_session` rewinds `version` to 0 and clears beats in memory only (never touches the DB, still unlinks JSON-era files) — version-order violations for connected apps + resurrection on restart. Delete or make it persist.
- `state.py:841-855` + `httpserver.py:313-326` — every GET durably mutates state (`_activate` upserts, bumps `updated_at`, flips the active-chat pointer): a stale tab polling `?session=` silently switches which chat resumes on next launch. Fix: reads resolve, only explicit opens activate.

### Performance
- `facts.py:107-119` + `analysis.py:92-94` — the root position is analysed with identical limits **up to 5×** per briefing (null-move probe, combination, two reconcilers, build_analysis) ≈ 1.2s duplicate Stockfish time per evaluate. Fix: analyse once in `build_fact_sheet`, pass the `Analysis` down.
- `tools.py:800-830` — `_maia_block` runs its own 250ms search whose cache key (limit-inclusive) never hits the 1500ms analysis just computed for the same fen — an extra search on nearly every tool response, and the shallow probe can name a *different* best move than the response's own `best` (contradictory grounding). Fix: reuse the existing analysis.
- `tools.py:2306-2316` — every adjudicated drill move runs `assess_move` (two more searches, ~1s) inside the per-chat lock even when `meaning` is usually None. Fix: compute maia rank first, search only for likely-mistake candidates.
- `db.py:199-210` — `user_for_token` does an UPDATE+COMMIT (`last_used_at`) on every authenticated request. Fix: update only if >5 min stale.
- `detectors/fork.py:54-76` + `board.py` — every Board method is a stateless FFI call re-parsing the FEN; `detect_fork` can trigger 500+ parses per position, `positional._attack_maps` +128. Fix: batched Rust calls (`attack_map`, apply-and-report); pass `occ` into `defenders()`.
- `rust/lib.rs:209-218` — `san_to_uci` is O(n²) movegens per conversion (full SAN rendering per legal move, regenerating the move list per rendering) and rejects over-disambiguated input. Fix: generate once, match by piece/target/promotion.
- `poisoned_line_detector.py:134,297` — rollouts re-analyse transpositions at 200k nodes with no intra-call memoisation; `find_practical_tries` doesn't forward `cache`. Also `:172-177` — the caller-owned cache dict grows unboundedly (fix: bounded LRU).
- `live_analysis.py:41-52` — `set_target` with an unchanged fen bumps `_gen` and throws away a depth-25 search. Fix: no-op on identical target.
- `engine_io/engine_client.py:34-78` — no gRPC deadlines anywhere (test-only today, but a wedged server hangs the thread forever). Its module docstring also claims to be "the ONLY way the backend reaches chess truth", contradicting the in-process architecture — rewrite it.

### Scale / robustness
- `live_analysis.py:86` — `_publish` outside any try: one exception kills the daemon thread and live analysis is silently dead for the process. Fix: try/except+log around the deepen/publish.
- `serve.py:56-61` — dead Maia cached forever (`is_alive` exists, unused); `maia.py` has no restart wrapper at all (one torch OOM → every Behaviour RPC fails until host restart); `maia.py:49-67` — failed handshake leaks the half-started torch process (retried by the holder → memory exhaustion in a handful of retries).
- `scripts/maia_policy_uci.py:31-51` — unpinned monkeypatch of maia3 internals; a renamed `"policy"` key silently degrades every move's policy to 0.0, corrupting the load-bearing probability products. Fix: assert version/shape at startup, fail loudly on missing key.
- `line_tree.py:239-253` — worst case ~5^6 nodes × full-width searches with no global budget; a sharp middlegame can run for hours. Fix: global node/wall-clock budget terminating branches as `_done(..., "budget")`.
- `gemini_models.py:18-53` — `resolve_model` has zero callers (dead code) and, if ever wired in, does serial billed probes with no timeout and treats network blips as "gated". Wire it or delete it.
- `auth.py:148-151` — WS tokens ride in the URL query string → bearer tokens in uvicorn/proxy access logs (30-day credential). The SwiftUI client *can* set headers — the browser rationale doesn't apply. Fix: header or first-frame auth; scrub access-log query.
- `tools.py:1639` — `set_puzzle` burns the puzzle (`mark_puzzle_served`) even when the drill comes back `drillable: False`, and leaves the pushed activity frame. Fix: pop + skip mark (or try next candidate).
- `puzzle_content.py:84-85` — default `puzzles_dir()` resolves to `backend/content/puzzles`, which doesn't exist anywhere in the tree; without `LUCENA_PUZZLES` every `set_puzzle` is `no_puzzles`. Verify the intended default; fail loudly at startup.

---

## P3 — Low (compressed, by file)

**backend/llm/** — retry covers only 429/503, not 5xx/transport (`gemini.py:23`); no client `aclose()`, QuickCoach builds a second client (`:15-31`); `factory.py:16` bare `KeyError` on missing `default_model`; `interface.py:25` `timeout_s` dead until P0.3.

**backend/engine_io/** — `queue.Empty` leaks raw through `lease` (`enginepool.py:66`); `close()` closes leased engines and leaves stale slots (`:94-101`); `SingleEnginePool.lease` ignores `timeout` (`:119-121`); `engine_client._limit` drops `threads` on the movetime branch (`:17-20`).

**backend/coaching/** — PV truncated to 6 plies with no ellipsis while the prompt says "ONLY through this line" (`grounding.py:141-145`); `book_voice.py:116,156` unguarded `name=None` at psn>0 → "opening called None" (cheap guard); `quick.py:61` tone `"correct"` means "corrective" (inversion trap); `quick.py:80-84` empty completion appended as a blank beat with `ok: True`.

**backend/persistence & http** — `auth_token` table grows forever (`db.py:51-55`); anonymous active-chat race + no ORDER BY (`db.py:65,267-282`); f-string table names one refactor from injection-shaped (`:339-357` — assert allowlist); `_authorize_chat`/`_activate` TOCTOU leaves a foreign `updated_at` bump (`state.py:796-855`); `_enqueue_locked` can do a DB load under `_live_lock` (`:1004`); `fen.split()[1]` IndexError on malformed client FENs (`:655,686`); stale `/dump`/SSE docstring (`:7`); `_guarded` doesn't catch `CancelledError` from prior task (`httpserver.py:126-131`); `"Bearer "` (trailing space) → IndexError → 500 on logout (`:302`); disconnect hard-cancels in-flight turns — audit gate cancel-safety (`:266`); register accepts near-anything as email, no length cap (`auth.py:81`); unauth argon2 endpoints un-rate-limited (known RELEASE_CHECKLIST item, `auth.py:137`); `sessions.py:26` redundant re-sort that TypeErrors on NULL `updated_at`.

**backend/grounding_tools/** — `R.pv_san(...)[0]` IndexError, sibling sites guard with `or [""]` (`tools.py:1071`); mate hardcoded as `cp:1000` with no mate marker (`:1193`); `_captured_piece` ignores color (`:128`); thread-restore reads engine privates and can raise in `finally` (`:1504`); stale comments (`:231`, `:87`); double gate-check convention split (`:943` vs `_scoped`); dead `move=` kwarg (`:1169`); beats after the first `ask` still render (`:1917`); `push_beat` assumes dict beats (`:1868`); `push_beat` board escape skips the drill-divergence reset (`:1910`); `push_analysis` compares un-normalized fens (`:1949`); `undo_move` writes board before history, violating its own documented order (`:2467`); `errors.log` unbounded (`:648`); one poisoned-line engine serializes all chats (`:91,533` — acceptable, watch latency); `_compare_many` validates moves lazily after spending searches (`:1354`); `_in_poisoned_context` matches placement only — transpositions misclassify (`:2029`); `_rehydrate_drill` failure half-initializes `_sctx` → drill silently freeform (`:582,2353` — clear persisted state loudly); unknown string `kind` while probe pending clears the gate (`:1986`); `_SyncCache` locks only 4 methods (`:55-85` — document the contract); `drill.py:29-38` `_solve_count` undercounts mate nodes; `puzzle_content._cache` never evicts old deck versions (`:75`); `sorted(...)[0]` → `min` (`:192`); `enforce_budget` can't trim `analysis`/`moves`/`refutation` shapes — the "hard guarantee" overclaims (`response.py:155-186`); `MAX_TOKENS=400` vs docstring's 300 (`:16`); `pv_san` silently truncates on conversion failure — journal it (`:115`); `live_analysis` stop/close race (`:54`), stale one-frame publish after target switch (`:83`), single shared target if instance shared across chats (`:20` — verify per-chat instantiation).

**engine/** — `uci.py:120` kill without `wait()` (zombies); `:234-244` accepts `lowerbound`/`upperbound` info lines as final scores (aspiration jitter at band thresholds); `maia.py:38` `.split()` breaks paths with spaces (`shlex.split`); `:137` option caches updated before confirmation (latent); `serve.py:79` Maia never closed on shutdown; `:70` `maia_available` false negative (env-var check instead of PATH probe); `:23` hardcoded version string; `truth.py:207` hardcoded fact `movetime_ms=300` defeats nodes-based reproducibility; `:234` `moves[:4]` silent truncation; `pool.py` (shelved) leaks on partial-failure construction and recirculates dead engines — delete or fix before unshelving; `pgn.py:68-84` stray `}` leaks `c}` into the token stream; `:188` result token inside comments wins over the real terminator; `:116` spaced move numbers (`12 .`) unhandled; `openings.py:30` library `print()` → use `logging`; `:59` mid-file import; `cli.py:117` engine leaked on invalid-FEN exit path; `:138` over-broad ImportError → misleading "install grpc extra"; `server/_map.py:34` `eval_from_block` dead; `gamepass.py:193,213` dead `pos_eval` params; `:90` mate-delivering moves can never be "brilliant" (skips the sac check — decide and document); `hints.py:113` "king on None" f-string (unreachable, cheap guard); `evalmodel.py:27` wrong provenance comment; `detectors/combination.py:49` only-move announced as "wins by force"; `:52` SEE-literal "sacrifices" mislabel (reuse `brilliant.is_material_sacrifice`); `facts.py:299` `_dedupe` is a no-op (key never collides); `:189` documented false-negative window on danger hangs; `detectors/_util.py:32` dead `piece_at`; `:98` unguarded `victim=None`; `pin.py:26` helpers duplicate positional's; salience magic numbers quadruplicated across detectors (one `salience()` helper); `detect.py:50` SAN regex misses double disambiguation; `:24` castling-field regex admits duplicates (backstopped by cozy); `line_tree.py` vs `puzzle.py` — two overlapping tree builders with different constants; deprecate or extract the shared core.

**Verified clean:** `statefile.py`, `drill_feedback.py`, `analysis.py`, `positional.py` (PeSTO verified), `_pesto.py`, `nnue.py`, `reads.py`, `brilliant.py`, `null_move.py`, `hanging.py`, `pin.py` (geometry), `board.py`, `_fen.py`, `see.rs` (swap-list, x-ray, en-passant, king-recapture all verified). Also verified as **non-issues**: no chat-lock↔pool deadlock (strict lock order), pool slot accounting sound on all paths, `_numbered_line` arithmetic correct for both colors, auth middleware fail-closed with no bypass.

---

## Suggested fix order

1. **P0.1 + P1.9** — rollback wrapper + `UniqueViolation` mapping (small, availability).
2. **P0.3 + P1.1 + P1.2** — Gemini timeout, response_schema, finish_reason (one file).
3. **P0.4 + P0.5 + P0.7 + P1.12** — uci.py lifecycle batch: restart reset, close-before-restart, terminal-vs-crash exception split, read timeouts, MultiPV reset, locked `new_game`. Then the serve.py holders become one-line fixes.
4. **P0.6** — the mate=0 sign bug (truth.py + evalmodel guard).
5. **P1.3–P1.5** — state.py locking + event-loop I/O batch.
6. **P0.2 + P1.6** — transaction retry flag + delta persistence (bigger; can trail).
7. **P2 correctness cluster in tools.py/drill.py** (prefix matching, board_changed swallow, paste-vs-drill, poisoned override) — these are player-visible coaching wrongness.
8. Everything else opportunistically, P2 performance items when latency budgets demand.

Each item above names exact `file:line`; run `REVIEW_ONLY=1 REVIEW_DIR=<layer> ./review-loop.sh` per batch to get Codex verification per the project's two-agent loop.
