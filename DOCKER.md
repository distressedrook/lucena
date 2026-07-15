# Docker

A deployable container stack for Lucena: **Postgres** + a single **app image**
that contains the grounding engine (built from source), the backend, a pinned
**Stockfish 18**, and an isolated **Maia** (torch) environment. The native mac
client is not containerised — it connects to the app's published WebSocket port.

```
compose.yaml            postgres + app
docker/Dockerfile       multi-stage app image (stockfish → engine → maia → runtime)
docker/entrypoint.sh    waits for Postgres, binds the backend to 0.0.0.0
docker/SOURCE_OFFER.txt  AGPL/GPL written source offer (baked into the image)
.env.example            copy to .env, set GEMINI_API_KEY
```

## Quick start

```bash
cp .env.example .env                 # then set GEMINI_API_KEY
ENGINE_GIT_SHA=$(git -C engine rev-parse HEAD) docker compose build
docker compose up
# backend:  ws://127.0.0.1:8766/ws   REST: http://127.0.0.1:8766
```

Point the mac client at `ws://127.0.0.1:8766/ws` (or the host's LAN address).

## Why this topology

The backend is designed to run **in-process** with the engine — `httpserver.py`
builds a `ToolContext` that imports `lucena_engine` directly, and its own header
notes that re-splitting over gRPC is an unfinished follow-up. So there is no
clean seam today to put the engine in one container and the backend in another;
they ship in **one image**. Postgres is the only genuinely separable service.

The engine's gRPC surface still exists for external/networked use, but the live
backend does not go through it. If/when the in-process→gRPC re-split lands, the
engine can move to its own container and this becomes a two-service app.

## Licence posture (AGPL / GPL)

Lucena combines code under three licences, and the image is built to keep them
compliant and cleanly separated:

| Component        | Licence          | How it's used                                   |
|------------------|------------------|-------------------------------------------------|
| lucena-engine    | AGPL-3.0-only    | Imported in-process by the backend              |
| Stockfish 18     | GPL-3.0-only     | Separate process, spoken to over UCI (arm's-length) |
| Maia / maia3     | GPL-3.0-only     | Separate process, spoken to over UCI (arm's-length) |
| lucena-backend   | proprietary      | The app; dual-licensed engine used under owner's grant |

**The engine (AGPL) + backend combination.** The engine is dual-licensed by its
sole copyright holder: AGPL-3.0 to the world, proprietary for use inside the
closed backend. That grant is what lets the backend stay proprietary while
linking the engine in-process — the AGPL's copyleft binds *other* users of the
engine, not the copyright holder.

**AGPL §13 (the network clause).** Anyone operating a network service built on
AGPL code must offer users its Corresponding Source. The image satisfies this
structurally: the build stamps `ENGINE_GIT_SHA` (the exact engine commit) into
`/usr/local/share/lucena-licences/SOURCE_OFFER.txt` and an image label, pointing
at the public engine repo at that revision. **If you modify the engine and
deploy it, publish those modifications at that commit** — that's the one active
obligation. Always pass `ENGINE_GIT_SHA` for images you distribute.

**Stockfish & Maia (GPL, not ours).** Used **unmodified, as separate programs
invoked over the UCI text protocol** — never linked into the engine. That
arm's-length boundary (the same invariant the engine enforces in code, e.g.
`test_gpl_hygiene.py`, and never importing `python-chess`) keeps them mere
aggregation rather than a derivative work. Their licence texts and a written
source offer ship in `/usr/local/share/lucena-licences/`.

**Hygiene gate preserved in the image.** The build installs `backend[gemini]`
only — never `backend[dev]`, which pulls the GPL `python-chess` (a tests-only
dependency). Nothing GPL is linked into the engine or backend process.

## Notable build details

- **Stockfish 18 is a hard pin.** The engine's NNUE eval parser is
  version-specific and refuses any banner that isn't `Stockfish 18`, so the
  image **builds SF18 from source** (`sf_18` tag) rather than using Debian's apt
  Stockfish (15/16). Override the tag with `--build-arg SF_TAG=…`.
- **Engine is an abi3 wheel** built by maturin (Rust board core), forward-compatible
  across CPython ≥3.9.
- **Maia lives in its own venv** (`/opt/maia`) so torch never enters the
  engine/backend process. The model is **`maia3-23m`** by default (build arg
  `MAIA_MODEL` — e.g. `--build-arg MAIA_MODEL=maia3-5m` for the lighter/faster
  CPU variant, or `maia3-79m` for the strongest). Its weights are pre-fetched at
  build time into a cache the runtime reuses (offline-capable after build; falls
  back to a runtime download if the build host had no network). The wrapper
  hard-defaults to 5m but caller args win, so `LUCENA_MAIA` appends
  `--model ${MAIA_MODEL}` to override it.
  - torch defaults to the **CPU-only** index (`download.pytorch.org/whl/cpu`) on
    both arm64 and amd64 — the plain PyPI wheel drags in multi-GB CUDA/nvidia
    packages this container never uses. Override with
    `--build-arg TORCH_PIP_SPEC="torch"` only if you actually want GPU.
  - `maia3` is not on PyPI; it's installed from the CSSLab GitHub repo
    (`git+https://github.com/CSSLab/maia3.git`). Weights (`UofTCSSLab/Maia3-5M`)
    auto-download from HuggingFace into `HF_HOME` on first use.
  - Disable Maia entirely at runtime by setting `LUCENA_MAIA=""` in the app
    service (poisoned-line detection turns off, same as a machine without the
    Maia venv).
- **Non-root** runtime (uid 10001); `tini` as PID 1; `/data` (`LUCENA_HOME`) and
  the durable Postgres data are named volumes.
- **Bind address:** the backend's `__main__` binds `127.0.0.1` (dev default); the
  entrypoint launches `serve(host=0.0.0.0)` so the published port is reachable —
  no backend code change.

## Environment variables

| Var                    | Default                     | Purpose                          |
|------------------------|-----------------------------|----------------------------------|
| `GEMINI_API_KEY`       | —                           | LLM key (coaching turns fail without it) |
| `LUCENA_MODEL`         | `gemini-flash-lite-latest`  | Model the orchestrator drives    |
| `LUCENA_PG_DSN`        | (set by compose)            | Postgres DSN                     |
| `LUCENA_BACKEND_PORT`  | `8766`                      | Published WS/REST port           |
| `LUCENA_STOCKFISH`     | `/usr/local/bin/stockfish`  | Stockfish binary                 |
| `LUCENA_MAIA`          | maia venv + wrapper         | Set `""` to disable Maia         |
| `LUCENA_HOME`          | `/data`                     | Durable app state dir            |
| `ENGINE_GIT_SHA`       | `unknown`                   | AGPL §13 source-offer anchor (build arg) |
