# common

Small, genuinely-shared packages used by more than one Lucena repo. Lives
directly in the superrepo (not a submodule) — this code isn't independently
versioned or externally consumed, it's internal plumbing shared between
sibling private tools.

**Convention:** a package here is justified only when the SAME logic is
independently duplicated (or hackily cross-imported) across ≥2 repos —
extraction is a response to found duplication, not speculative shared-library
design. Each consumer reaches a package here by computing a relative path up
to the superrepo root (`Path(__file__).resolve().parents[N] / "common"`) and
appending it to `sys.path`, the same convention `backend/plans/service.py`
already uses to reach `lucena-plans/src`.

## Packages

- **`engine_client/`** — the gRPC client wrapper (`Probes`) for lucena-engine's
  Truth service, plus its generated protobuf stubs. Extracted 2026-07-22:
  lucena-tactics (chess-lab) and lucena-plans' research harness each depended
  on the same client, the latter via a sys.path hack reaching directly into
  chess-lab's source tree — which silently broke when chess-lab was renamed/
  moved into the superrepo as `lucena-tactics`. One canonical copy now.
