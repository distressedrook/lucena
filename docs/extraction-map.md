# Extraction Map — `/legacy` → monorepo

> **Historical (2026-07-14 plan).** The `orchestrator` extraction target became `ConversationLoop`; see `LLD.md`.

> What reusable code lives in `/legacy` and where it belongs in the new tree. Produced 2026-07-14 by a
> four-way read-only scan (engine · backend · mac-client · tooling/content/misc). This is the plan for
> the extraction pass; **nothing is moved until this map is signed off.** Rule of the pass: extract
> anything reusable, **even a single function** — the truth-cores buried in the coach layer are the
> clearest case.

## One execution decision to confirm first

**Copy or move?** `/legacy` is the archive. Recommendation: **copy** the reusable pieces into
`engine/` · `backend/` · `mac-client/` · `infra/`, leaving `/legacy` intact and runnable as the
reference until the new tree is proven, then delete `/legacy` in one commit. (Moving now would break
the legacy app mid-migration.) The couplings/splits below are done **in the copies**, never in legacy.

## Where everything lands (summary)

| Destination | What | Rough count |
|---|---|---|
| **`engine/`** (open, AGPL) | Rust board core + `engine/` package + `board.py` + reference data + lifted truth-cores | ~30 files + 5 lifted fns |
| **`backend/`** (closed) | state machine, orchestrator, drill/session/puzzle logic, persistence (→ Postgres) | ~12 files |
| **`mac-client/`** | the whole SwiftUI layer; transport reworked in 3 files | ~28 files, 2 dropped |
| **`infra/`** | no-LLM harnesses, build/gen tooling, their guard tests | ~15 files |
| **`docs/`** | design mockups, README/CLAUDE (rewritten) | a few |
| **PARKED** | content cluster, mastery, ADK path, 23KB coach contract, domain memory | — |
| **drop-retire** | MCP wrapper, local-process spawners, ADK/MCP tooling, cruft | ~12 files + cruft |

---

## `engine/` (open, stateless chess-truth)

**Clean whole-file moves** (no surgery):
- **Rust:** `rust/Cargo.toml`, `Cargo.lock`, `src/lib.rs`, `src/see.rs` (drop `target/`).
- **Board + engine pkg:** `board.py`; all of `engine/`: `__init__`, `uci`, `evalmodel`, `facts`, `nnue`,
  `maia`, `analysis`, `brilliant`, `positional`, `hints`, `gamepass`, `pool` (shelved/dormant),
  `line_tree`, `detect`, `pgn`, `_pesto`; all of `engine/detectors/` (`_util`, `hanging`, `defender`,
  `fork`, `pin`, `combination`, `null_move`).
- **Reference data + lookups:** `data/openings.tsv` (Lichess CC0), `mcp/openings.py` (pure FEN→name
  lookup — move to sit beside the data), `mcp/poisoned_line_detector.py` (Stockfish×Maia trap detector).
- **Maia runtime:** `tools/maia_policy_uci.py` — the production `LUCENA_MAIA` policy-emitting wrapper;
  **ships with the engine**, not infra.
- **Tests:** 19 engine unit tests (`test_board*`, `test_see*`, `test_evalmodel`, `test_facts`,
  `test_uci`, `test_maia`, `test_nnue`, `test_hints`, `test_line_tree`, `test_detect`, `test_brilliant`,
  `test_combination`, `test_fork`, `test_pin`, `test_analysis`, `test_engine_reconcile`).

**Truth-cores to LIFT out of the coach layer** (single functions — the surgical part):
- from `mcp/response.py`: `material` (+ helpers `_standing`, `_pieces_phrase`, and the
  `_MATERIAL_VALUE`/`_VALUE_ORDER`/`_PIECE_WORD`/`_COUNT_WORD` tables), `piece_list`, `eval_block`,
  `pv_san`.
- from `mcp/tools.py`: `_row_squares`, `_captured_piece`, `_norm_fen`, `_num`, `_pgn_line`.

**Couplings to sever** (both auto-resolve once `material()` is engine-side):
- `engine/gamepass.py` → `..statefile.write_state` — drop the `out_path` progressive write; keep the
  pure `run_pass` return path.
- `engine/positional.py` and `mcp/poisoned_line_detector.py` → `..mcp.response.material`.

**Flags:** ① **Rust license mismatch** — `Cargo.toml` says `AGPL-3.0-or-later`, `lib.rs` header says
"MIT foundations"; settle before the engine goes public. ② **Collapse the 3–4 duplicate normalized-FEN
helpers** (`response`/`openings`/`poisoned`/`tools._norm_fen`) into one engine util. ③ Preserve env/
determinism knobs: `LUCENA_STOCKFISH`, `LUCENA_MAIA`, SF18 pin, movetime(prod)/nodes+threads=1(test).
④ GPL hygiene: never `import chess`; Stockfish/Maia subprocess-only.

---

## `backend/` (closed: orchestrator + state + LLM)

**Reused (hot path):**
- **State machine** — `mcp/state.py` (`StateStore`, `_Live`/`_Frame`/`_Workspace`) — lifted intact;
  behaviour unchanged, **persistence relationalised to Postgres**.
- **Orchestrator** — `agent/orchestrator.py` + `agent/quick.py` (classify→ground→generate→act; LLM
  writes prose/JSON only). `agent/server.py`'s `/turn`+`/explain` HTTP surface (strip ADK + mock
  branches). `agent/__main__.py`. `agent/model.py` → **rework behind the LLM adapter** (it's all
  Gemini-specific model probing).
- **Drill/session/puzzle** — `mcp/drill.py` (`DrillState` walker, pure), `mcp/drill_feedback.py`
  (deterministic beats), `mcp/puzzle_content.py` (selection — leans backend; only FEN-validation is
  engine), `mcp/sessions.py` (rail list from DB).
- **Persistence** — `db.py` reused **as the spec** (its `save_document`/`load_document`/`upsert_session`
  + beats-sidecar API is the contract) but **rewritten to Postgres relational** (no json-blob).
- **Tests:** `test_mcp`, `test_tool_surface` (retarget MCP→orchestrator names), `test_db`,
  `test_drill_history`, `test_import`, `test_poisoned_line*`, `test_session_view`. `test_classification`
  straddles engine+backend (light decouple).

**Rework required:** cut `google.genai` imports behind the LLM-adapter interface (orchestrator, quick,
model); replace `statefile`/json persistence with Postgres; re-home the delivery glue (below) off MCP.

---

## `mac-client/` (SwiftUI)

**The whole visual layer moves** — presentation is reused as-is; **all transport funnels through 3
files:**
- `Support/StateStream.swift` — **SSE `/state` → WS** (keep the typed dispatch, version-ordering,
  reconnect logic verbatim; replace only the `event:`/`data:` SSE parse).
- `Support/CoachBridge.swift` — **HTTP → WS** for the live loop (`sendTurn`/`playMove`/`submit`/
  `setBoardPosition`/`setView`); keep `explain`/`setAnalysis`/`session`/`reset` as **REST**; delete the
  `/turn` + `agentPort` path.
- `LucenaApp.swift` — remove the two spawners; point at WS/REST.

**Reuse-as-is UI:** `SessionBoardView`, `BeatsColumnView`, `ChatInputPaneView` (retarget send),
`MoveListView`, `MoveNavigatorView`, `AnalysisView`, `ModeRailView`, `EvalBarView` (note: it lives in
the misnamed `MastheadView.swift`), `SettingsMenu`, `CoachThinkingHalo`, `VariationModel`, `Theme`,
`Strings`, all `Models/*`, `ChessMove`, `StudySessionScreen` (the one shell), the app test + samples.
**Rendering assets:** the cburnett piece SVGs from `design/hero-annotated-board/pieces/`.

**DROP (terminal/local-agent era):** `Support/AgentHost.swift`, `Support/MCPServerHost.swift` (local
process spawners). *No SwiftTerm / CoachActivityWatcher remain — already gone.* Residual
"terminal"/"claude" mentions are comments + theme token names + `Strings.…Terminal` keys → **rename
during the move**, not code to drop.

---

## `infra/` (dev tooling + its tests)

- **No-LLM harnesses (keep-forever):** `tools/gate_state_harness.py`, `tools/eval_harness.py`,
  `tools/puzzle_harness.py` + their guard tests (`test_eval_harness`, `test_puzzle_harness` + fixtures,
  `evalharness/` cases, `test_license_hygiene`).
- **Build/gen:** `tools/gen_pesto.py`, `tools/build_openings.py`, top-level `build.py`, `log.py`,
  `build_transcript.py` (verify it's build tooling, not Claude-transcript capture).
- **Coach-runtime tooling (rework):** `tools/reset_home.py`, `tools/watch_home.py`,
  `tools/build_coach_home.sh` — touch parked coach-home/mastery paths.
- **Packaging:** `pyproject.toml` — **fan out** into per-package `engine/` + `backend/` roots.

---

## `docs/` (design + repo docs)

- `design/Lucena App.dc.html`, `design/hero-annotated-board/*` → `docs/design` (watch the ~4 MB
  `seal_sq.png`; the piece SVGs go to mac-client instead).
- `README.md`, `CLAUDE.md` → rewrite for the monorepo; **scrub retired MCP/ADK guidance** from CLAUDE.md.

---

## PARKED (not extracted this cycle; not dropped)

- **Content cluster:** `content/lichess_db_puzzle.csv.zst` (~288 MB, Lichess CC0 — **keep out of git**,
  external/LFS), `content/puzzles/poisoned.jsonl`, `content/special-puzzles/*`. Tests
  `test_puzzle_content`, `test_mastery`.
- **Mastery:** `mastery/core.py`, `mastery/__init__.py`.
- **ADK path:** `agent/runner.py`, `agent/skills.py`.
- **Coach contract:** `agent/coach_instruction.md` (23 KB — only the ADK agent used it).
- **Domain memory:** `memory/domain.json` → parks with the memory/auth cluster.
- **Reference/manual:** `tools/smoke_narration.py` (Claude-era manual smoke test — keep as reference).

---

## DROP — retire (MCP/ADK-era, dead)

- **MCP wrapper:** `mcp/server.py` **FastMCP shell + `@mcp.tool()` registrations** (⚠️ but its
  `serve_http` HTTP *behaviour* — SSE fan-out, drill `/move` adjudication, `/position`/`/view`/
  `/session(s)`/`/analyze`/`/activity`/`/reset` — is backend delivery glue to **re-home**, not drop),
  `mcp/__init__.py`, `cli.py` (`serve`/`serve-http`).
- **Spawners:** `mac-client` `AgentHost.swift`, `MCPServerHost.swift`.
- **Dev shims:** `agent/mock.py` (MCP choreography), `statefile.py` (atomic-JSON persistence → Postgres).
- **MCP/ADK tooling:** `tools/dev_state_driver.py`, `tools/agent_gate_harness.py`,
  `tools/p0_gemini_spike.py`, `tools/p0_pick_model.py`, `tools/relaunch_agent.sh`.
- **Cruft:** all `.DS_Store`, `__pycache__/`, empty `tests/{contract,data,golden}/`, `rust/target/`.

---

## Surgical extractions (intra-file splits — the careful work)

These files are **not** clean moves; they split across destinations:

| File | engine gets | backend gets | drop |
|---|---|---|---|
| `mcp/response.py` | `material`(+helpers), `piece_list`, `eval_block`, `pv_san` | `error`, `fact_wire`, `facts_to_board`, `estimate_tokens`, `enforce_budget`, `MAX_TOKENS` | — |
| `mcp/tools.py` (126 KB) | `_row_squares`, `_captured_piece`, `_norm_fen`, `_num`, `_pgn_line` | `ToolContext`/`_SessCtx`/`_guarded`/gate/`_positional_block`/all tool methods (state glue) | the `@mcp.tool()` registration |
| `mcp/server.py` | — | `serve_http` endpoint behaviour (re-home off MCP) | FastMCP shell + tool registration |
| `mcp/live_analysis.py` | (imports engine, points in) | `LiveAnalyzer` (UI streaming orchestration) | — |
| `engine/gamepass.py` | the pure `run_pass` path | — | the `write_state` progressive write |

---

## Open decisions / flags (resolve during the pass)

1. **Copy vs move** (top of doc) — recommend copy-then-delete-legacy.
2. **Rust license** — AGPL vs MIT header mismatch → settle before public.
3. **Big binaries out of git** — 288 MB puzzle zst, ~4 MB seal PNG → external/LFS, not committed.
4. **`pyproject.toml` fan-out** — two maturin/packaging roots (engine + backend).
5. **Duplicate `_norm_fen`** — collapse to one engine util.
6. **`serve.py` / `build_transcript.py`** — confirm not Claude-era before reusing.
7. **Tests straddling** (`test_classification`, `test_positional`) — light engine/backend decouple.
