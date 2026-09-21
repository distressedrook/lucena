# Lucena — Architecture

> **Design-first.** This document is the locked high-level design from the 2026-07-14 re-architecture
> session. Per-layer API contracts (below) are locked before their code is written. Supersedes the
> archived designs in `legacy/docs/`.

## One-paragraph system

Lucena is an engine-grounded Socratic chess coach. A native **mac client** talks to a Python
**backend** whose **deterministic ConversationLoop** runs the coaching loop: it classifies each turn, calls
an **open, stateless grounding engine** (Stockfish + Maia3 + validators) for chess *truth*, asks a
commodity **LLM** for exactly one grounded generation, and pushes coaching **beats** to the player.
The LLM is a pure generator — it never tool-calls, never decides chess, and never mutates state. All
application state (sessions, the one board, the gate, beats) lives in a **state machine** inside the
backend, and is mutated only by deterministic code.

## Locked decisions (2026-07-14)

| Decision | Choice |
|---|---|
| **Grounding engine** | OPEN source, **stateless**, **separate repo**, **gRPC** server. Python + Rust (reuse the `lucena-board` Rust core + the Stockfish/Maia/facts Python layer). |
| **Backend** | **Python**, released under AGPL-3.0-or-later. In-process: state machine + ConversationLoop + LLM adapter. **Mastery, memory, and auth are PARKED this cycle** (first-class for v1, not built now). |
| **State machine** | Lifts **intact** from today's MCP server into the backend. Behaves exactly as today; made **more robust**. Mutated ONLY by the deterministic loop — never by the LLM. |
| **LLM** | **Generic, provider-agnostic** in-process adapter — a single interface `generate(messages, {schema?, model?, temperature?, max_tokens?}) -> {text \| json, usage}`, OpenAI-chat-shaped so **OpenRouter is a drop-in**. The loop depends ONLY on this interface; the provider (Gemini now, OpenRouter later) and the model id are **config**. Never tool-calls, never sets state. |
| **Client** | Thin native macOS. **WebSocket** for the interactive coaching loop (input up, beats/board down); **REST** for everything else (auth, library, history, config). |
| **MCP** | **Retired entirely.** Its two jobs split: chess truth → engine gRPC; state/beats/gate → in-process state machine. |
| **This repository** | The open project: `backend/` · `mac-client/` · `infra/` · `docs/` and the research layers. The engine remains separately packaged and is also included as a submodule. |

## Topology (two processes)

```
                      WebSocket (coaching loop) + REST (everything else)
   ┌── mac-client ─────────────────────────────────────────────▶ BACKEND  (open, Python, ONE process)
   │   (renders board + beats,                                     ├─ state machine   (in-process, unchanged, robust)
   │    sends player input)                                        ├─ ConversationLoop (in-process, deterministic)
   └────────────────────────────────────────────────────────────  ├─ (mastery · auth — PARKED)
                                                                   ├─ LLM adapter (in-process) ──HTTP──▶ OpenRouter / Gemini
                                                                   │
                                                                   ├─ SQL ──▶ POSTGRES  (the ONE data store; all durable state)
                                                                   │
                                                                   └────────────────── gRPC ──▶ GROUNDING ENGINE
                                                                                                (open repo, STORELESS:
                                                                                                 validators · Stockfish · Maia3)
```

gRPC is used for **exactly one link**: backend → grounding engine (our own typed, hot service). The
LLM link is HTTP because providers are HTTP. All backend modules are in-process — no network hops
between the loop, the state machine, and the LLM adapter. **Persistence is one Postgres,
owned by the backend; the engine is storeless.**

## Persistence boundary

**All durable, mutable state lives in the backend's one store — Postgres. The engine persists
nothing.** Decided 2026-07-14.

- **Engine = zero persistence.** Stateless by contract; its `(fen, limit, multipv)` cache is
  **in-memory and ephemeral**; its openings DB / tablebases are **read-only bundled assets**, not
  mutable state. No data store in the engine.
- **Backend = one Postgres**, from the start (no SQLite / no now-later split — the schema is the same
  either way). It holds all durable state; the parked cluster (content · mastery · memory · users)
  lands in the *same* store later.
- **No JSON as state.** JSON is allowed only as *configuration*. The session document is **not** a
  jsonb blob — it is **relationalised into columns/tables** (see `state-machine.md`). There is no
  `session.json` pointer file; **at most one session is `is_active`** (a DB flag, flipped when the
  player clicks a session), enforced by a partial unique index.
- **Persist durable facts; re-derive engine artifacts.** `last_analysis` is a cheap engine call
  (sub-second, cached) → **not persisted, re-derived on resume**. The **forcing-line drill tree** is
  expensive (dozens of sequential searches) *and* deterministic given `(fen, nodes-limit, Threads=1)`
  → it is a **precomputed, position-keyed cache**, built offline once and shared across all
  sessions/users — never per-session state, never built on the hot path. (Parks with the content /
  drill cluster; the caching decision is locked.)
- **Single-writer, atomic, version-ordered.** The state machine is the sole writer to session state;
  every mutation is one transaction (document row + its beats together); the monotonic `version` is
  the durability + ordering key (the per-channel `*_seq`s collapse into it).

## Failure & degradation

The governing rule, learned the hard way from the ADK hang: **bound every call and degrade honestly —
never wait unboundedly, never fail silently.** The truth/voice split is also a *resilience* asset —
the engine grounds facts with no LLM, so the LLM failing doesn't kill coaching, it *thins* it.

**Load-bearing now (single process, pre-hosting):**
- **A timeout on every network call**, tuned to **p99 + headroom, not "generous."** This is what
  catches **gray failure** — a dependency that is *slow, not down* (the exact shape of the ADK hang).
  A too-generous timeout doesn't catch it.
- **Bounded retry with backoff + jitter** on transient failures (429/503/blips), **capped attempts
  AND total time — where the total is bounded by the user-facing WS/REST deadline** (attempts×backoff
  must not outlast the request). Jitter matters *even single-process*: concurrent sessions all backing
  off and re-firing together is a retry-storm into a fresh 429.
- **A minimal LLM breaker** (not deferred): after K consecutive 429/timeout, **skip straight to
  truth-without-voice** for a cooldown window instead of retrying. This is the canonical fix for the
  retry-storm above and it is live *today* with concurrent sessions — a full circuit-breaker library
  is hosting-era, this one rule is not.
- **Fail-fast, structured errors** — bounded, actionable, surfaced immediately (never a hang, never a
  stack trace into chat). *(Nygard's "Fail Fast" proper — rejecting known-doomed work before spending
  a timeout, e.g. when the breaker is open — is the hosting-era superset.)*
- **Idempotency keys at the client→backend command boundary.** On a **WebSocket reconnect**, the
  client may resubmit the last move/turn; the key + the monotonic `version` guard against
  double-applying it. (This — not the Postgres write — is where idempotency earns its keep.)
- **WebSocket reconnect / resume** is a first-class failure surface: drop mid-turn → reconnect →
  re-latch to the current version-stamped state (snapshot + deltas) without replaying a beat or
  double-applying a move.

**The degradation ladder** (what a turn does when a dependency is unavailable):

| State | Behavior |
|---|---|
| **Healthy** | engine + LLM → grounded, voiced Socratic coaching |
| **LLM down / rate-limited / slow** | whole-call timeout or breaker → **truth-without-voice** — serve the engine's fact sheet via a small set of **deterministic templated framings** ("Best move: Rd1. +3.2. back-rank."). *Honest and grounded, NOT pedagogically equivalent* — it reads as coaching, not a debug dump, but it's a thinner mode. |
| **Engine down (global)** | state machine still renders board + history + prior beats; *new grounded* coaching pauses with a bounded-retry "one moment." (The truth/voice split does **not** cover this — engine down = no new grounding, full stop.) |
| **Engine error for THIS position (local)** | one bad/illegal FEN ≠ engine down — return a structured "can't ground this one," never retry forever, never take down the call path. |
| **Postgres transient blip** | short bounded retry (a 200ms hiccup ≠ down). |
| **Postgres sustained down** | fail fast on writes — **never lose state silently**; the client holds unsaved intent and re-submits with its idempotency key. Backend is effectively down → supervised restart. (No app-level write-ahead/queue — that reintroduces the silent-divergence risk Postgres already solves.)|

**Retrying the LLM is not free or cleanly idempotent:** a retried generation is a second *paid* call
and (temp > 0) may differ; use the **provider's idempotency key** so a lost-response retry doesn't
double-charge or double-generate.

**Non-streaming today** (per `llm-adapter.md`: hot-path generations return once), so a slow LLM is
covered by the single whole-call timeout — there is no mid-stream stall. *If* beat/token streaming is
added later for UX, it introduces a third "started-then-stalled" state that needs a per-chunk
(inter-token) timeout + graceful-finish (a stalled stream can't be retried from zero).

**Bulkhead by architecture (free):** truth (engine) and voice (LLM) fail independently — we get the
*benefit* of a bulkhead without the thread-pool mechanism.

**Hosting-era, deferred (named, not built):** a full circuit-breaker library, thread-pool bulkheads,
load-shedding / backpressure, and liveness/readiness probes (cheap — add them with process
supervision).

## The coaching turn (end-to-end)

1. **Client → backend (WebSocket):** the player's typed message or a played move.
2. **Resolve mode** — the loop reads the chat's state (deterministic, no LLM): is there an active
   **Lesson** on this chat? If so the turn/move runs in **coach mode**; otherwise it runs in
   **freeform mode**. Mode — not a free-text intent classifier — is what routes the turn.
3. **Route by mode:**
   - **coach mode** — a played move is *adjudicated* against the active Lesson (right/wrong, why); a
     typed turn is answered within the lesson's frame.
   - **freeform mode** — a played move is *explained*; a typed message is classified-and-answered in
     the same single call (question vs. position set-up vs. chat), no separate classify step.
4. **Ground** — the handler reads the current board from the state machine and calls the **grounding
   engine** for the facts (analysis, hints, Maia, validation) it needs.
5. **Generate** — ONE call to the **LLM adapter** (HTTP) with the mode's prompt + the grounded facts +
   the deterministic frame (whose move it is, who the opponent is). The model returns prose or a small
   JSON verdict. It calls no tools.
6. **Act** — the handler writes to the **state machine** deterministically (push beats, set the gate
   on a question; *record a mastery observation — parked this cycle, the seam stays*). The state
   machine streams the new beats + board to the client over the **WebSocket**.

## Invariants (violating any is a bug, not a choice)

1. **The state machine is the single source of truth and is mutated ONLY by the deterministic
   loop.** The LLM never mutates state, never tool-calls, never sets the board. (Its logic is
   lifted intact from today; the migration hardens it, never changes its behavior.)
2. **Determinism first — the LLM interprets, it never calculates or orchestrates.** The backend
   classifies, grounds, and acts; the model only generates over facts it was handed. Perspective,
   evals, and moves are grounded/framed by the backend.
3. **Component firewall.** The backend reaches the grounding engine ONLY over its gRPC contract —
   never by importing engine code. The engine holds no application state.
4. **One bounded LLM call per hot-path turn** — cheap, predictable COGS; the model is swappable.
5. **The engine is pure and stateless** — every request is independent given the position; engine
   processes stay warm, the API carries no session.

## Parked / retired (deliberate)

- **MCP** — retired (see above).
- **Agentic ADK path** — parked in `legacy/agent/`; a future use is content authoring / a pro tier,
  not the hot path (it's too expensive and rate-limits).
- **Content, mastery, memory, and auth — one coupled cluster, parked this cycle** (first-class v1
  candidates; not developed now). They interlock: **content** is the curriculum (a hierarchy of
  *plan → unit → item* — a plan is the organizing spine, the coach's agenda, *and* the coach-authored
  royalty unit); **mastery** drives which content is selected and adapts the plan; **memory** is what
  mastery reads/writes. Building content on a parked mastery system is backwards, so the whole cluster
  waits together. The coaching flows run this cycle without plans/content-selection/mastery — the
  engine grounds whatever position/PGN is in play; curated curriculum lands with mastery. Seams stay
  (content items will carry `concept_id`; the classifier already routes a "give me a puzzle" intent).
- **Cloud hosting details** — later.

## Per-layer API contracts (to lock next, design-first)

- `docs/grounding-engine-api.md` — the engine's **gRPC contract** (`.proto`): validate, analyze,
  hints, maia, … Stateless request/response.
- `docs/backend-api.md` — the **client ↔ backend** contract: the WebSocket coaching-loop messages
  (input up; beat/board/status events down) + the REST surface (auth, library, history).
- `docs/orchestrator.md` — the (now-historical) deterministic coaching pipeline, **flow by flow**
  (classify → ground → generate → act). **Superseded** by the `ConversationLoop` (mode routing); see
  `LLD.md` and `backend/python/lucena_backend/coaching/loop.py`.
- `docs/llm-adapter.md` — the **generic LLM interface** (OpenAI-chat-shaped: messages, JSON/schema
  output, model + params as config), the provider adapters (Gemini now, OpenRouter later), and the
  hard rule that the loop never imports a provider SDK — only the interface. Provider + model
  are configuration, swappable without touching the loop.
- `docs/state-machine.md` — the lifted state machine: its model (session, board, gate, beats,
  activities), its public API to the loop, and the robustness hardening.
