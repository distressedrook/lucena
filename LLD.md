# Low-level design

How the backend actually works, and — more usefully — *why*, where the reason is not visible from the
code. Only the parts where a plausible-looking change silently breaks something.

`CLAUDE.md` is workflows. This is design. Rationale that belongs to one function lives in its
docstring; this file is for the things that span files.

---

## 1. The three "sessions"

The word means three different things. Conflating them is the single easiest way to introduce a
security bug here.

| Term | What it is | Cardinality | Where it lives |
|---|---|---|---|
| **chat session** | one coaching conversation | **many** per user | `session` table; `StateStore._live[sid]` |
| **active chat** | the chat a user currently has open | **one per user** | `session.is_active` |
| **login session** | an authenticated user | one token per login | `auth_token` table |

Traps:

- **`session.status` is not `session.is_active`.** `status` is lifecycle (`active` → `complete`).
  `is_active` is the per-user "which chat is open" pointer. They share a word and nothing else.
- **The `session` table is the CHAT.** The login layer is `auth_token`, deliberately never named
  `session`.
- **`app_user`, not `user`.** `user` is a reserved word in Postgres.

## 2. The bound chat is a ContextVar

`state._current_sid` holds the chat for the current execution context; `_current_user` holds the
login. Bind at entry points (`store.bound(sid)`, `store.as_user(uid)`); `_cur`, `ToolContext._sc` and
`_publish` all resolve from it.

**Why not a plain field.** It was one (`StateStore._current`), and it was the whole bug: *both*
partition dicts (`_live` and `ToolContext._sctx`) keyed off one process-global cursor, so concurrent
chats corrupted each other regardless of locking. This was never a lock problem; it was an ambient
global. A ContextVar is still ambient but **per execution context** — two concurrent turns cannot see
each other's value, and the failure mode inverts from *silently writes the wrong chat* to *resolves
empty*, which `_strict` turns into a loud error.

**Why not a `SessionHandle` façade.** `ToolContext` is a process singleton owning the engine, the
analysis cache and Maia. A handle forces either threading `sid` through 28 `@_guarded` signatures in
a 2250-line file (an attempt that was already abandoned once — `run_turn(session_id)` accepting and
ignoring the param is the fossil), or a `ToolContext` per chat, which duplicates engine/cache/Maia per
chat. The ContextVar left ~40 proxy properties, all 13 `_publish` call sites, and ~30 existing tests
untouched — which is what kept the suite a valid oracle *through* the change.

**Propagation — the part that bites:**

| Boundary | Crosses? |
|---|---|
| `asyncio.create_task` | ✅ context copied at creation |
| `asyncio.to_thread` | ✅ `copy_context().run(...)` |
| **`threading.Thread`** | ❌ **fresh empty context** |
| `loop.run_in_executor` | ❌ (not used; keep it that way) |

Anything on a raw thread takes an explicit `session_id` — see `publish_engine_lines` and
`LiveAnalyzer.set_target`. Grep `threading.Thread(` and `run_in_executor(` to audit.

The pytest suite needs an autouse fixture resetting the var: the server is fine because every
connection/task gets a copied context, but pytest runs every test in **one** context, so a chat bound
by one test would leak into the next.

## 3. Publishes are addressed, not broadcast

`_subscribers: dict[chat_sid, {queue: Subscription}]`. `_publish_to(sid, …)` is the primitive;
`_publish(ch, payload)` resolves the bound chat, which is why all 13 call sites were untouched.

- **The version stamp must come from the publishing chat's bundle** (`_live_for(sid).version`), not
  the caller's cursor. Stamp the wrong chat's number and the app's ordered-delta guard **silently
  drops** the event — a frozen board or a spinner that never clears, with nothing in the logs.
- **Each subscriber stores its OWN loop**, next to its queue. A single store-wide `_loop` is silently
  wrong the moment two loops exist: the last subscriber wins and earlier sockets never wake. (Latent
  in production — uvicorn runs one loop — but it is real, and it is why a beat banked in chat A was
  never delivered to A's own socket under TestClient.)

**A socket switching chats needs three layers**, because each covers what the one before cannot:

1. `_live_lock` — cannot enqueue into a bucket the socket already left.
2. **epoch envelope** — events carry `(sid, epoch)`; `retarget` bumps `epoch`; `Subscription.get`
   drops the stale. Covers what was *already queued*, and `call_soon_threadsafe` callbacks already
   scheduled — neither can be unsent.
3. **`Subscription.gate`** — the reader re-checks the stamp under the gate before sending, and
   `retarget` takes the same gate. Covers an *already-dequeued* event: `send_json` is an await point,
   so a retarget can land between dequeue and send.

The pump must **not** hold the gate across `next_event()` — that awaits the queue and would deadlock
`retarget` against an idle socket. Lock order is `gate → _live_lock`; `_publish_to` takes `_live_lock`
and never `gate`, so there is no cycle.

## 4. attach vs open

- `bind_current(sid)` — pure: set the var, load the bundle.
- `attach_chat(sid)` — bind + mark active. **No publish.** Every REST request, and a socket on
  connect (which sends its own snapshot).
- `open_chat(sid)` — the explicit act of opening: + `reset` and a snapshot replay.

**Never gate the publish on the caller's cursor.** A REST request starts unbound, so
`current_sid != sid` is *always* true and every request would blast a reset + full snapshot at that
chat's sockets. That is a real bug that shipped for an hour; it presented as the app showing a stale
seed board after a `/move`.

**`open_chat` has no `sid == current` early-out**, deliberately. Under a per-context cursor that is a
property of *one* context: a fresh connection whose cursor is unbound must still bind and snapshot
even when another connection already has that chat open. Bailing early leaves it bound to nothing,
reading `_live[""]`, showing an empty board.

## 5. Ownership

Enforced at the **edge** — "can you bind this sid?" — not by putting `user_id` on all 14
session-keyed tables. Same guarantee, far smaller surface. Which means `_authorize_chat` carries the
whole weight:

- It runs **before `bind_current`**, not just before the write. Binding *loads* the chat's document
  into `_live`; checking afterwards still pulls another user's coaching into the process, and "we
  raised after" is not a defence once the data is in memory.
- It distinguishes **missing from unowned** (`db.session_owner -> (exists, user_id)`). Collapsing both
  to `None` lets an authenticated user reach a pre-accounts row — and a *failed* attempt would still
  have committed an `updated_at` bump via `upsert_session`'s `ON CONFLICT DO UPDATE`. An existing
  unowned row is refused for authenticated users; silent adoption would be worse.
- `set_active_session` scopes **both** statements by user. Un-scoped, the first
  (`UPDATE … SET is_active=false WHERE is_active`) clears **every** user's active chat. The second's
  `user_id` predicate *is* the ownership check: 0 rows updated raises rather than leaving the user
  with no active chat.

## 6. Auth is middleware, never per-route

`auth.AuthMiddleware` gates HTTP and WS in one place and binds the user for the whole request; routes
just read `store.current_user`.

Per-route auth is **fail-open** — a new route is unguarded until someone remembers. That is not
theoretical: it produced two real bugs here (`/analyze` and `/config` silently ungated; `/session`,
`/move` and `/drill` validating the body and answering **400** before ever checking the token).
`test_every_non_public_route_is_401_without_a_token` is parametrized over the route table so a new
ungated route fails automatically.

- **Pure ASGI, not `BaseHTTPMiddleware`.** The latter runs the endpoint in a separate task, which
  makes the ContextVar bind fragile. Pure ASGI runs in the same task.
- **WS is rejected before accept** (`{"type": "websocket.close", "code": 1008}`). Accepting first
  leaves an unauthenticated socket alive and makes the token a formality. Browsers cannot set headers
  on a WS handshake, so a socket presents `?token=`.
- Every route that can *name* a chat translates `PermissionError` into **403** — a refusal leaking as
  a 500 is both a worse contract and a wider error-logging surface.
- `LUCENA_REQUIRE_AUTH` defaults **off** so single-user local runs work unchanged. Production must set
  it (`RELEASE_CHECKLIST.md`).

## 7. Auth specifics

- **argon2id**, always off the loop via `asyncio.to_thread` — it is expensive *by design*, and on the
  loop it blocks every coaching turn in the process. Unthrottled it is also a CPU DoS: rate-limiting
  `/auth/login` is a release-checklist item.
- **Opaque DB tokens, not JWT.** One process and a database already in hand, so stateless
  verification buys nothing while revocation (logout, ban) actually works. Only `sha256(token)` is
  stored, so a DB dump is not a credential dump.
- `login()` hashes even when the email is unknown, so a missing account and a wrong password cost the
  same — otherwise response time enumerates registered emails.
- Expiry is enforced in the `user_for_token` query, not by a sweep, so a stale row can never
  authenticate.

## 8. Known shape

- **No migration mechanism.** `_DDL` is `CREATE TABLE IF NOT EXISTS` throughout and
  `meta.schema_version` is never read to branch, so a new column reaches **fresh schemas only**.
  Deliberate while every schema is disposable; **blocking** before the first deploy — see
  `RELEASE_CHECKLIST.md`.
- **One psycopg connection + one RLock.** Correct (serialized), and the real multi-user throughput
  ceiling.
- **`live_analysis.py` is entirely unwired** — nothing constructs `LiveAnalyzer`, `/analyze` is a
  stub. Its `session_id` contract exists so it cannot be rewired wrongly.
- **`ctx` and `ground_ctx` are two ToolContexts sharing the store**, each with its own engine and tool
  lock, so the coach's multi-second analysis never blocks an interactive move. Do not collapse them.
- **`build_app(engine=…)` is close to a decoy**: `test_end_to_end` injects an `EngineClient` that has
  no `.analyse()`/`.new_game()`, and it only works because `ground_ctx` unconditionally builds a real
  local `Engine()`.

## 9. Freeform opening narration (and the one carve-out)

**The voice follows the mode, because the mode is a fact about the board.** In a drill the engine
replies (`drill.py` plays the defence), so the player really is one side and "you" is correct. In
freeform *nothing replies* — `play_move` applies one ply and stops — and the client board has no
side-to-move gate, so either colour is draggable. Freeform is a shared analysis board that the user
drives from both sides. "You played e4" there is not a style choice, it is factually wrong. One
predicate (`ToolContext.freeform`), one prompt block (`_perspective(freeform)`), two bodies.

`result["drill"]` is **tri-state** — `True` / `False` / `"suspended"` — and it answers two different
questions. **Adjudication** (does this move get graded?) is `is True`. **Voice** is `is False`: a
suspended drill is the player stepping back inside their *own* drill line, so they are still one side
and still get "you". One expression answering both is how suspended drills started talking like
freeform.

**Cadence is a pure fold, not a latch.** `openings.book_name(fens)` folds the line; a caller detects a
change with `book_name(hist) != book_name(hist[:-1])`. Nothing is stored, so nothing resyncs after a
restart. It is *not* "the last named position": the table re-attaches **coarser** names deeper in a
line (Najdorf `d6` → "Sicilian Defense: Modern Variations", then `d4` → plain "Sicilian Defense"), so
last-wins walks backwards up the tree and the coach audibly forgets what it just said. A new name
replaces the current one only when it is **not an ancestor** of it.

**End of book:** `plies_since_named(fens) == 4` — exactly at the threshold, so it fires once per exit
with no latch, and re-arms if the line transposes back in. Four, not three: two-unnamed-ply gaps occur
at ~12% of book positions and the probe was capped at 3, so 3 has zero margin. `None` (never named — a
drill, a pasted midgame FEN) must never announce.

**The swing fork is independent of the name cadence.** A move can be pure theory *and* tank the eval;
that is the whole point of a gambit, and "this is the King's Gambit" is a cop-out there. So: quiet +
new name → narrate with `hide_best=True` (there is nothing to judge, and handing over "best: d4" makes
the model report it — which is the "that's fine, though d4 is preferred" this feature exists to kill).
Swing while in book → keep the class/best; *that* is the subject. Both → one beat. In book, neither →
**silent**; do not fill the air. The trigger is the engine's own `classify` boundary (`dubious`+,
measured against the engine's best move), not a threshold of our own. Measured: 2.f4 = `dubious`
(−8.2 win%), so the canonical gambit does fire; `test_the_kings_gambit_actually_triggers_the_swing_fork`
pins it through the real `evaluate`, because a reimplementation of `classify` in a test got the sign
backwards and reported the exact opposite.

**The carve-out.** `CLAUDE.md`'s invariant is that anything the model could get wrong is grounded or
guarded. Narration is the one deliberate exception: on this path the model MAY use its own knowledge
of the **named** opening — ideas, plans, pawn structures, what each side wants. Opening theory is
stable, well-documented knowledge and grounding it would mean shipping a prose database. It may NOT
state any concrete evaluation, tactic, threat, or verdict not in the handed-over facts. Interpret what
you are handed; never calculate. Undocumented, this grows into "the model does chess now" — which is
why it is written in the prompt *and* in both docs.

**Narration is a second prompt body, not a flag.** It inverts the coaching prompt at three points at
once — length (1-2 sentences → a paragraph), register (its ban on "generic strategic advice" is
exactly what narration IS), and verdict. Loosening the shared prompt to fit would make **drills** start
dispensing "control the center".

**Titling on the narrate path is deterministic** (`_title_from_opening`): the opening family, taken
from the table. `_name_hint` asks the *model* for a title because only the model can look at a position
and describe it; here the answer is already known exactly. Move one is also the most likely titling
moment, so a JSON that omitted `name` would silently stop titling forever.

**The wire is an additive field, not a new beat kind.** The neutral `1.e4` lane rides as `notation` on
the existing `kind:"you"` beat. `Beat.kind` decodes as a free String and the view branches only on
`isYou`, so a client predating a `kind:"move"` would render it in the **coach** lane labelled LUCENA —
the coach appearing to utter "1.e4" — and beats are **persisted**, so that corrupts the stored
transcript permanently while the backend deploys independently of the installed app. An unknown *key*
is simply ignored: new client → neutral lane, old client → today's bubble. Degrade, don't regress.

**Known limit (pre-existing):** `play_move` appends to history and never truncates, so a
rewound-and-replayed board leaves the old tail behind and `plies_since_named` counts against a line
that was not played. The fold survives it; end-of-book can fire early. Fixing it is a board-navigation
change, not an opening one.
