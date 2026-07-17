# syntax=docker/dockerfile:1.7
#
# Lucena — single deployable app image: the grounding engine (built from source)
# + the backend (which imports it in-process) + a pinned Stockfish 18 + an
# isolated Maia (torch) environment. Postgres is a separate service (see
# ../compose.yaml). The native mac client is NOT containerised; it connects to
# this image's published WebSocket port.
#
# Licence posture (see ../DOCKER.md for the full write-up):
#   - lucena-engine is AGPL-3.0. This image records the exact engine source
#     commit (ENGINE_GIT_SHA) so AGPL §13's "offer the Corresponding Source" is
#     always satisfiable against the public repo.
#   - Stockfish 18 (GPL-3.0) and Maia/torch are used ONLY as arm's-length UCI
#     subprocesses — never linked into the engine. Their licence texts + a
#     written source offer ship in /usr/local/share/lucena-licences.
#   - We install backend[gemini] only, NEVER backend[dev] (that would pull the
#     GPL python-chess into the image and break the dual-license hygiene gate).

ARG PYTHON_VERSION=3.12
ARG DEBIAN_REL=bookworm

# =============================================================================
# Stage 1 — Stockfish 18, built from source (the engine hard-pins "Stockfish 18";
# the NNUE eval parser is version-specific, so Debian's apt Stockfish won't do).
# =============================================================================
FROM debian:${DEBIAN_REL}-slim AS stockfish
ARG SF_TAG=sf_18
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch ${SF_TAG} \
        https://github.com/official-stockfish/Stockfish /src
WORKDIR /src/src
# `build` (not profile-build) auto-detects ARCH and avoids PGO's run-the-binary
# step, which is flaky under cross-arch emulation. `make net` fetches the pinned
# NNUE net referenced by this tag.
RUN make -j"$(nproc)" net \
    && make -j"$(nproc)" build \
    && strip stockfish \
    && cp stockfish /stockfish \
    && ./stockfish bench 2>&1 | tail -1

# =============================================================================
# Stage 2 — build the lucena-engine wheel (Rust board core via maturin → abi3).
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_REL} AS engine
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# Rust toolchain (pinned via rustup default stable).
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain stable
RUN pip install --no-cache-dir "maturin>=1.7,<2.0"
COPY engine/ /build/engine/
WORKDIR /build/engine
# abi3 wheel → forward-compatible across CPython ≥3.9.
RUN --mount=type=cache,target=/build/engine/rust/target \
    --mount=type=cache,target=/opt/cargo/registry \
    maturin build --release --out /wheels

# =============================================================================
# Stage 3 — Maia: isolated torch venv at /opt/maia (kept OUT of the app venv so
# torch never enters the engine/backend process; Maia is spawned over UCI).
# Weights for the CPU-friendly maia3-5m model are pre-fetched into a cache the
# runtime stage reuses, so the container is offline-capable after build.
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_REL} AS maia
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
# torch: the plain PyPI wheel drags in multi-GB CUDA/nvidia packages on BOTH
# arm64 and amd64 — useless in a CPU-only container. We install from the CPU
# index (slim CPU-only wheels for linux aarch64 and x86_64). The index URL is
# baked into the RUN below (an ARG default with embedded flags is unreliable);
# TORCH_PIP_SPEC is just the package spec, and TORCH_INDEX_URL the index.
ARG TORCH_PIP_SPEC=torch
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
# maia3 is NOT on PyPI — install from the CSSLab GitHub repo (has a pyproject).
ARG MAIA_PIP_SPEC=git+https://github.com/CSSLab/maia3.git
ENV XDG_CACHE_HOME=/opt/maia-cache HF_HOME=/opt/maia-cache/hf
RUN python -m venv /opt/maia \
    && /opt/maia/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/maia/bin/pip install --no-cache-dir --index-url "${TORCH_INDEX_URL}" ${TORCH_PIP_SPEC} \
    && /opt/maia/bin/pip install --no-cache-dir ${MAIA_PIP_SPEC}
COPY engine/scripts/maia_policy_uci.py /opt/lucena-engine/scripts/maia_policy_uci.py
# Which Maia strength to bundle. The wrapper hard-defaults to maia3-5m but caller
# args win (argparse last-value), so `--model ${MAIA_MODEL}` overrides it.
# maia3-23m is heavier on CPU than 5m but a stronger human-move predictor.
ARG MAIA_MODEL=maia3-23m
# Pre-warm: drive the UCI wrapper once so the model's weights download into the
# cache. REQUIRED, not best-effort — this stage already needs network to pip-install
# torch/maia3 above, so "no network at build time" was never actually a live case; the
# old `|| echo ...skipped` just meant a build could silently ship an image whose
# LUCENA_MAIA env var is set but whose first real call fails at runtime (the weights
# aren't cached and a production container commonly has no outbound network either).
# That is the exact silent-degradation shape `tools.py`'s `human_replies` is built to
# swallow (empty list on any Maia error) — invisible right up until a coach narration
# quietly loses its grounding. Fail the build instead: a bad Maia setup should never
# reach a shipped image.
RUN mkdir -p /opt/maia-cache \
    && printf 'uci\nisready\nposition startpos\ngo depth 1\nquit\n' \
       | /opt/maia/bin/python /opt/lucena-engine/scripts/maia_policy_uci.py --model ${MAIA_MODEL} \
       > /tmp/maia-warm.log 2>&1; \
    cat /tmp/maia-warm.log; \
    grep -q '^bestmove ' /tmp/maia-warm.log

# =============================================================================
# Stage 4 — runtime: slim base + Stockfish binary + engine wheel + backend +
# Maia venv. Non-root. Entrypoint runs the backend bound to 0.0.0.0.
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_REL} AS runtime

# libgomp1 is Stockfish's only shared-lib need; the rest is self-contained.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- Stockfish 18 (arm's-length UCI subprocess) ---
COPY --from=stockfish /stockfish /usr/local/bin/stockfish

# --- lucena-engine (AGPL) + backend (proprietary, gemini provider only) ---
COPY --from=engine /wheels/*.whl /tmp/wheels/
COPY backend/ /opt/lucena/backend/
RUN pip install --no-cache-dir /tmp/wheels/*.whl \
    && pip install --no-cache-dir "/opt/lucena/backend[gemini]" \
    && rm -rf /tmp/wheels

# --- Maia venv + pre-fetched weights ---
COPY --from=maia /opt/maia /opt/maia
COPY --from=maia /opt/maia-cache /opt/maia-cache
COPY --from=maia /opt/lucena-engine/scripts/maia_policy_uci.py /opt/lucena-engine/scripts/maia_policy_uci.py

# --- Licence bundle: AGPL/GPL Corresponding-Source posture (see DOCKER.md) ---
COPY engine/LICENSE engine/NOTICE engine/THIRD-PARTY-NOTICES.md \
     /usr/local/share/lucena-licences/engine/
COPY docker/SOURCE_OFFER.txt /usr/local/share/lucena-licences/SOURCE_OFFER.txt

# ENGINE_GIT_SHA is the exact commit the engine wheel was built from — the
# anchor for AGPL §13's Corresponding-Source offer. Pass it at build time:
#   docker build --build-arg ENGINE_GIT_SHA=$(git -C engine rev-parse HEAD) ...
ARG ENGINE_GIT_SHA=unknown
RUN sed -i "s/@ENGINE_GIT_SHA@/${ENGINE_GIT_SHA}/g" \
        /usr/local/share/lucena-licences/SOURCE_OFFER.txt || true

COPY docker/entrypoint.sh /usr/local/bin/lucena-entrypoint
RUN chmod +x /usr/local/bin/lucena-entrypoint

# --- runtime env ---
# MAIA_MODEL must match the model whose weights were pre-warmed in the maia stage.
ARG MAIA_MODEL=maia3-23m
ENV LUCENA_STOCKFISH=/usr/local/bin/stockfish \
    LUCENA_MAIA="/opt/maia/bin/python /opt/lucena-engine/scripts/maia_policy_uci.py --model ${MAIA_MODEL}" \
    LUCENA_HOME=/data \
    LUCENA_HOST=0.0.0.0 \
    LUCENA_BACKEND_PORT=8766 \
    LUCENA_MODEL=gemini-flash-lite-latest \
    XDG_CACHE_HOME=/opt/maia-cache \
    HF_HOME=/opt/maia-cache/hf \
    PYTHONUNBUFFERED=1

# Non-root. /data (LUCENA_HOME) and the maia cache must be writable.
RUN useradd --create-home --uid 10001 lucena \
    && mkdir -p /data \
    && chown -R lucena:lucena /data /opt/maia-cache
USER lucena

EXPOSE 8766
LABEL org.opencontainers.image.title="lucena" \
      org.opencontainers.image.licenses="AGPL-3.0-only AND GPL-3.0-only AND proprietary" \
      ai.lucena.engine.git-sha="${ENGINE_GIT_SHA}"

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/lucena-entrypoint"]
