# Release checklist

Things that are deliberately deferred while Lucena is pre-production, and **must** be done before
real users' data exists. Each item says what breaks if it is skipped.

## 1. Schema migrations — BLOCKING for the first production deploy

**There is no migration mechanism.** `db.py`'s `_DDL` is entirely `CREATE TABLE IF NOT EXISTS`, and
`SCHEMA_VERSION` is write-only bookkeeping — `_connect` stamps `meta.schema_version` but **nothing
ever reads it to branch**. So:

> A new column added to `_DDL` appears on **fresh** schemas only. On any schema that already exists,
> `CREATE TABLE IF NOT EXISTS` skips the table entirely and the column **silently never appears** —
> dev looks fine, production dies at runtime on the first query that references it.

This is survivable now only because every schema is disposable (tests drop `s_*` schemas around the
session; the dev DB can be recreated). It stops being survivable the moment a real user has a chat.

**Before the first deploy:**
- [ ] Build a versioned stepper: `_MIGRATIONS: list[(version, step)]` from 8 up. In `_connect`:
      baseline `_DDL` for a fresh schema → read `meta.schema_version` → apply every step `>` it in
      order, each in its own transaction, bumping `meta` after each. An existing schema with no meta
      row ⇒ assume 7.
- [ ] **Freeze `_DDL` at its current shape forever.** All future change goes in steps. Enforce with a
      test that hashes `_DDL` and fails with *"add a migration step, don't edit `_DDL`"*.
- [ ] Land the stepper **with a trivial step and a test, before using it for anything real**. A
      stepper you have not proven is the same trap with more code.
- [ ] Test it **starting from a real v7 schema**, not a fresh one — that is the only case that
      actually exercises it. (`_schema_for` hashes the DB path, so you can build one: run the frozen
      v7 DDL, stamp `schema_version=7`, then open `DB(same_path)`.)
- [ ] Retro-fit steps for everything added pre-production while this was deferred (currently: the
      accounts work — `app_user`, `auth_token`, `session.user_id`, and swapping the global
      `one_active_session` index for the per-user one). Order matters: add the column nullable →
      backfill → `SET NOT NULL` → and drop/recreate the unique index **after** that, never before
      (dropping first leaves a window with no uniqueness constraint at all).

**Until then:** a schema change requires recreating the dev database (`dropdb lucena_dev` or
`DROP SCHEMA`), and there is no upgrade path for any deployed instance. Do not deploy a second time
without the stepper.

## 2. Deployment

- [ ] **Build for `linux/amd64`.** The image is currently built arm64 (Apple Silicon); DigitalOcean
      droplets are x86_64 and do not offer ARM. Cross-build with
      `docker buildx build --platform linux/amd64 … --push` and pull on the droplet — do **not** build
      on a small droplet (the Rust + Stockfish compile and torch download will OOM/crawl it).
- [ ] **Pass `ENGINE_GIT_SHA`** (`--build-arg ENGINE_GIT_SHA=$(git -C engine rev-parse HEAD)`). It
      stamps the AGPL §13 source offer and the image label. An image distributed with
      `ENGINE_GIT_SHA=unknown` cannot point users at its Corresponding Source.
- [ ] **Keep the engine commit published.** AGPL §13: if you modify the engine and deploy it, those
      modifications' source must be offered at the deployed revision.
- [ ] Managed Postgres rather than the in-compose one (it deletes a category of 3am problems, and the
      single-operator model has no on-call rotation).
- [ ] Real secrets handling for `GEMINI_API_KEY` — not a `.env` on the box.

## 3. Auth hardening

- [ ] **Rate-limit `/auth/login`.** argon2 is expensive *by design*; unthrottled it is a CPU denial of
      service against the same process serving coaching turns.
- [ ] Confirm password hashing runs off the event loop (`asyncio.to_thread`) — a login on the loop
      blocks every coaching turn in the process.
- [ ] Token expiry + revocation actually exercised (opaque DB tokens were chosen over JWT precisely so
      logout/ban can work).

## 4. Capacity

- [ ] Size the Stockfish pool against real load, not a guess. Each engine is a process with its own
      hash; `_default_threads()` = `max(2, cpu-2)` **per instance**, so a pool that does not pass an
      explicit `threads=` will oversubscribe the box.
- [ ] Decide whether live analysis is ever rewired. It is entirely unwired today (nothing constructs
      `LiveAnalyzer`; `/analyze` is a stub), and it is the only near-continuous CPU cost in the design
      — per-move coaching is bounded and cheap by comparison.
