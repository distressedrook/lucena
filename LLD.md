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
