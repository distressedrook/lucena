# Lucena

An engine-grounded, Socratic chess coach. A native macOS app talks to a local backend that runs a
**deterministic orchestrator** over an LLM (Gemini) — the LLM *interprets* chess, it never *calculates*
it. A grounding stack (Stockfish + Maia behind the `lucena-engine` wrapper, python-chess board
truth + SEE in `lucena-core`) is the source of truth.

This is the **private superrepo**: one clonable tree that pins each layer as a submodule.

```
engine/       → lucena-engine   PUBLIC  (AGPL-3.0)   — Stockfish/Maia wrapper (uci, maia, pool,
                                 evalmodel, nnue), on PyPI as `lucena-engine`. Slimmed 2026-07-23:
                                 everything else moved private (see below + lucena-tactics/docs/MIGRATION.md)
lucena-core/  → (superrepo dir) PRIVATE — board truth: python-chess board + ported SEE
                                 (differential-gated vs the retired Rust core), positional terms,
                                 detect/pgn/openings/reads/_fen, gRPC client+server. Import name
                                 `lucena_core`; pip install -e lucena-core
lucena-tactics/→ lucena-tactic  PRIVATE — the tactical lifecycle: census detectors + facts/hints,
                                 has_tactics verdict, line_tree/puzzle trees, DrillState walker,
                                 poisoned-line detector, mechanism naming + factsheet + lexicalizer.
                                 Contract: (1) why-wrong fact sheet, (2) has_tactics, (3) forcing tree.
                                 No superrepo remote yet (gitlink only). Its CLAUDE.md is the lab notebook.
backend/      → lucena-backend  PRIVATE (proprietary) — conversation loop, state machine, Postgres
mac-client/   → lucena-mac      PRIVATE (proprietary) — SwiftUI client (thin; streams over WS)
lucena-plans/ → lucena-plan     PRIVATE (proprietary) — position→verified-plans library + research
                                 (src/ library · docs/ · research/ corpora+benchmarks; its CLAUDE.md
                                 is the lab notebook — read it before touching the plan grammar)
```

The filesystem is one tree — edit freely across layers in a single session. Only **git** is split.

## Working across layers (git)

Each layer is its own repo with its own history. After editing:

1. Commit inside the submodule: `git -C engine commit …` (or backend / mac-client).
2. Push the submodule: `git -C engine push`.
3. **Bump the pointer** in the superrepo so it records which layer commits go together:
   `git add engine && git commit -m "bump engine" && git push`.

See `MULTIREPO.md` for the full flow.

**Push identity:** these repos use the `distressedrook` account over SSH (`~/.ssh/id_ed25519`, pinned
via `core.sshCommand`). `gh` may be logged into a **work** account (`avismara-c`) — never run GitHub
actions against these repos with it; for any `gh` need, switch with `gh auth switch --user distressedrook`.
Keep this superrepo **private** (a public superrepo can't recurse a private submodule).

## Run / build / test

- **Run the stack:** `./serve.sh` — Postgres + engine (gRPC) + backend (WS/REST). `GEMINI_API_KEY` is
  read from the environment (it's in `~/.zshrc`). `stop` / `status` / `logs` subcommands too.
- **Engine:** `cd engine && pip install -e . && pytest tests/` (pure python since the 2026-07-23
  slim; needs a `stockfish` binary for the session tests).
- **Core:** `pip install -e lucena-core`; tests run under the tactics venv:
  `cd lucena-tactics && .venv/bin/python -m pytest ../lucena-core/tests/`.
- **Tactics:** `cd lucena-tactics && .venv/bin/python -m pytest tests/` + the rulings suite
  `.venv/bin/python research/experiments/test_rulings.py`.
- **Backend:** `cd backend && PYTHONPATH=python .venv/bin/python -m pytest tests/` (needs Postgres; the
  end-to-end coaching tests need `GEMINI_API_KEY`).
- **Mac app:** `cd mac-client && xcodebuild -project Lucena.xcodeproj -scheme Lucena -destination 'platform=macOS' CODE_SIGNING_ALLOWED=NO build`.

## Code review (Claude implements, Codex reviews)

Every non-trivial change goes through the two-agent loop. **Claude is the implementer; Codex is the
reviewer and never writes code.** The loop ends only when Codex returns `VERDICT: PASS`.
Contract: `AGENTS.md`. Procedure + prompts: `CODE_REVIEW_PROTOCOL.md`.

```bash
./review-loop.sh "task"                              # Claude implements, then Codex reviews
REVIEW_ONLY=1 REVIEW_DIR=backend ./review-loop.sh "describe the change already in the worktree"
```

- `REVIEW_ONLY=1` reviews what is already in the worktree (skips the implement step; the default
  clean-worktree gate otherwise refuses). `ALLOW_DIRTY=1` skips that gate when implementing.
- `REVIEW_DIR=backend` scopes the review to a layer — per the AGENTS.md multi-repo rule, review a
  change in the repo where it actually lives, and call out a stale superrepo pointer separately.
- `CONTEXT_FILE=path` feeds the implementer a plan; without it `claude -p` starts cold, knowing only
  the task string.
- **Dispute findings with evidence, don't silently close them** (test output, the code path, or an
  invariant below). Codex reassesses; that exchange has already caught real bugs on both sides.
- Do NOT use `codex exec review --uncommitted "<prompt>"` — codex-cli rejects a prompt alongside that
  flag, and the loop's exit condition needs our prompt (the `VERDICT:` line). Use plain `codex exec`
  and let the reviewer scope itself to the diff. Always redirect stdin (`</dev/null`) or codex blocks
  waiting for EOF.

## Load-bearing conventions

- **Calculate vs. interpret.** The engine calculates the truth; the LLM only interprets it. Anything the
  model could get wrong is either *grounded* (handed over as facts) or *guarded* (made impossible) —
  never left to the model. The LLM **never tool-calls and never sets the board.**
  - **One deliberate carve-out:** on the freeform *opening-narration* path the model may use its own
    knowledge of a **named** opening (ideas/plans only — never a concrete eval, tactic, or verdict).
    It is the only exception; see `LLD.md` §9 before extending it anywhere.
- **Prompts are first-class citizens.** Every instruction sent to the LLM — system prompt AND user
  message, the fixed wording and the per-turn assembly alike — is built by a typed `Prompt` subclass
  in `backend/python/lucena_backend/coaching/` (`prompts.py`, `mode_prompts.py`), never hand-assembled
  with raw string concatenation in the handlers or anywhere else. Each family's pieces (`_head`/`_tail`/`_body`,
  single-underscore — Python's actual privacy convention) are private; the only public surface is
  `SomePrompt.system(...)` and `SomePrompt.prompt(...)`, taking typed data in and returning text.
  Adding a new prompt or a new fragment of one means adding to that file, not the caller.
- **Loop shape:** `ConversationLoop` resolves the mode (an active Lesson for this chat → coach, else
  freeform), dispatches by input kind, grounds, and makes **one** LLM call. Intent is fused into
  generation (freeform classifies and answers in a single call), not a separate classify step. Handlers
  never call each other — they return a typed `Outcome` the loop re-routes (the loop-mediated seam).
  Unclassifiable action requests (play a bot, etc.) return a polite `unsupported` decline rather than
  coaching the position.
- **In-process, not gRPC-in-dev:** the backend imports `lucena_engine` (wrappers) and `lucena_core`
  (board truth) directly via `ToolContext`, and reaches lucena-tactics through the
  `grounding_tools/_tactics_path.py` bootstrap + thin re-export shims (drill, facts, hints,
  line_tree, brilliant, poisoned_line_detector). A
  separate read-only `ground_ctx` handles coaching grounding so slow analysis never blocks interactive
  moves. (The engine *also* ships a gRPC surface for external/networked use.)
- **The plans layer — (fen, pvs, rolls):** `lucena-plans/src` never rolls an engine or Maia; every
  entry point takes caller-supplied lines and only CHECKS them. The backend produces the lines
  (`lucena_backend.plans.rolls`, in-process pool + Maia) and routes a freeform paste to the plans
  fact sheet when it's out of book, a middlegame, and |eval| ≤ 1.5 (`freeform._plans_read`). Every
  specific the sheet prints (freeing pushes, routes, trade mechanisms) comes from the firing
  eval-equal lines — suggest proposes, verify filters. NOTE: lucena-plans depends on python-chess
  (GPL-3.0) — fine server-side/private, but none of it may ever migrate into the engine (the
  dual-license invariant), and the repo must stay private.
- **SAN on the wire.** UCI is engine-internal only (entry/exit conversion); the backend and app speak SAN.
- **Storeless engine, one Postgres** in the backend. Relational session state (no json-as-state).
  Drill/forcing-line trees are precomputed and position-keyed, never per-session.
- **Backend design detail lives in `LLD.md`** — the three meanings of "session", the ContextVar chat
  cursor, addressed publishes, ownership, the auth middleware. Read it before changing `state.py`,
  `httpserver.py`, `db.py` or `auth.py`.
- **GPL hygiene (the dual-license invariant):** the public engine library **never** imports
  `python-chess`; Stockfish and Maia are used **only as subprocesses over UCI** (arm's-length). A CI
  gate enforces it (`engine/tests/test_gpl_hygiene.py`). Since the 2026-07-23 slim this is easy to
  keep: the engine has no board at all — python-chess lives exclusively in the private layers
  (`lucena-core`, tactics, plans, backend), where GPL is fine.

## Design & brand

- **Identity:** "Annotated Board" — paper (`#F1EDE3`) + ink, no gradients. The mark is a rook that reads
  as the **L** in *Lucena* (rook + "ucena" wordmark).
- **Type:** **Lora** (SIL OFL — free for commercial + web) is the brand serif, bundled in the app and
  driven from `Theme.Typography.serif(_:_:)` — change it there and it changes everywhere. Monospace
  (Menlo) stays for chess notation/eval (it carries the figurine glyphs; Lora doesn't).

## Releasing

- **`RELEASE_CHECKLIST.md` gates the first production deploy** — what's deliberately deferred while
  pre-production. Blocking one: **there is no migration mechanism**, so a schema change reaches fresh
  schemas only and means recreating the dev DB.

- **Engine → PyPI:** bump `engine/pyproject.toml`, tag `vX.Y.Z`, push the tag — CI builds wheels + sdist
  and publishes via Trusted Publishing. Same version can't be re-uploaded; bump on a failed run.
- The engine is AGPL-3.0 public; the backend/mac are closed. As sole copyright holder you dual-license
  the engine (AGPL to the world, proprietary use in the closed backend). New contributors need the CLA
  (`engine/CONTRIBUTING.md`).
