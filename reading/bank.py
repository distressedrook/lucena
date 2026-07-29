"""bank — read-only access to the banked benchmark artifacts.

This layer never rolls an engine and never calls Maia. Everything it scores
comes from artifacts already on disk under
`lucena-plans/research/experiments/`, which is what makes every iteration
deterministic and replayable — the same property that lets
`reduce_agreement.py` re-score a new grammar without re-rolling.

Two keying schemes coexist in the bank and are normalized here to `id`:

  * `benchmark_v1.jsonl`, `eng_shards/`, the rating-conditioned rollout dirs
    key on `id` (e.g. `n1883_a30`).
  * `maia_shards/argmax_*.jsonl` and `lift_shards/shard_*.jsonl` key on
    `n` + `anchor`, and hold ALREADY-LABELED plan sets rather than raw moves.

`benchmark_v1.jsonl` is frozen and sha-pinned. Nothing here writes.
"""
from __future__ import annotations

import json
from pathlib import Path

import chess

# reading/ sits beside lucena-plans/ in the superrepo tree.
EXPERIMENTS = (Path(__file__).resolve().parent.parent
               / "lucena-plans" / "research" / "experiments")

BENCHMARK = EXPERIMENTS / "benchmark_v1.jsonl"
ENG_SHARDS = EXPERIMENTS / "eng_shards"

# The rating-conditioned rollout banks. These are ASYMMETRIC strong-vs-weak
# coaching simulations (owner, 2026-07-30): one side plays 2400 policy, the
# other the named weak band. Which COLOUR carries the weak policy is not
# recorded in the row, so it is measured — see `probe_foil_side.py`. Nothing
# in this module assumes it.
ROLLOUT_BANDS = {
    "2400v1300": EXPERIMENTS / "maia_shards_2400v1300",
    "2400v1800": EXPERIMENTS / "maia_shards_2400v1800",
}


def _read_jsonl(path: Path) -> list[dict]:
    with path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _read_shard_dir(path: Path, pattern: str) -> list[dict]:
    """Every row across a shard directory, in sorted shard order so a run is
    reproducible regardless of filesystem enumeration order."""
    rows: list[dict] = []
    for shard in sorted(path.glob(pattern)):
        rows.extend(_read_jsonl(shard))
    return rows


def _id_of(row: dict) -> str:
    """`id` when present, else rebuild it from the `n` + `anchor` keying the
    labeled shards use."""
    if "id" in row:
        return row["id"]
    return f"n{row['n']}_a{row['anchor']}"


def benchmark() -> dict[str, dict]:
    """The frozen 4,000-position eval set, by id.

    Row keys: id, fen, anchor, result, structures, kstudy, plies_total,
    actual_ucis (the game's real continuation), random_ucis (seeded control).
    """
    return {r["id"]: r for r in _read_jsonl(BENCHMARK)}


def engine_lines() -> dict[str, list[dict]]:
    """MultiPV=4 lines by id: [{cp, ucis}, ...], cp normalized to WHITE.

    This is both arm A's raw material and the eval-equal set used for scoring
    — see `eval_equal_first_moves`.
    """
    return {r["id"]: r["pvs"]
            for r in _read_shard_dir(ENG_SHARDS, "engine_*.jsonl")}


def rollouts(band: str) -> dict[str, list[list[str]]]:
    """K rollouts of UCI moves by id, for one rating condition.

    `band` is a key of ROLLOUT_BANDS. Rows are {id, k, samples}; samples is
    K sequences of ~25 plies. Seeds derive from the position id, so these are
    reproducible on any machine.
    """
    if band not in ROLLOUT_BANDS:
        raise KeyError(f"unknown band {band!r}; have {sorted(ROLLOUT_BANDS)}")
    rows = _read_shard_dir(ROLLOUT_BANDS[band], "bench_*.jsonl")
    return {r["id"]: r["samples"] for r in rows}


def labeled_plans(dirname: str = "maia_shards",
                  pattern: str = "argmax_*.jsonl") -> dict[str, dict]:
    """The already-labeled plan sets, by normalized id.

    NOT raw moves — these rows carry plan-name lists under the grammar that
    was current when they were reduced (`actual_slow`, `random_slow`,
    `maia_fast`, `maia_slow` for maia_shards; `af`/`as`/`rf`/`rs` for
    lift_shards). Grammar-versioned: treat as historical unless re-reduced.
    """
    rows = _read_shard_dir(EXPERIMENTS / dirname, pattern)
    return {_id_of(r): r for r in rows}


def white_to_move(fen: str) -> bool:
    return fen.split()[1] == "w"


def eval_equal_first_moves(pvs: list[dict], fen: str,
                           margin_cp: int = 30) -> set[str]:
    """The first moves of the eval-equal engine lines, as UCI.

    `cp` in the bank is normalized to White, so it is flipped to the mover's
    point of view before comparison — otherwise the eval-equal set is
    inverted for every Black-to-move position, which would silently corrupt
    every score this layer produces.

    A student move is credited iff it lands in this set (scoring is
    eval-equality, not argmax match — several moves are often equally good,
    and marking them wrong would punish understanding).
    """
    if not pvs:
        return set()
    sign = 1 if white_to_move(fen) else -1
    scored = [(sign * pv["cp"], pv) for pv in pvs if pv.get("ucis")]
    if not scored:
        return set()
    best = max(cp for cp, _ in scored)
    return {pv["ucis"][0] for cp, pv in scored if best - cp <= margin_cp}


def san(fen: str, uci: str) -> str | None:
    """UCI -> SAN in the position's context. None if illegal there.

    The wire format for anything a reader sees is SAN (root CLAUDE.md: "UCI
    is engine-internal only"), and the leakage stripper needs both spellings
    of a move to redact it.
    """
    board = chess.Board(fen)
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return None
    if move not in board.legal_moves:
        return None
    return board.san(move)


def coverage() -> dict[str, int]:
    """Row counts per artifact — the sanity check before any run.

    Reported into LOG.md alongside a result so a number is always paired with
    the coverage it was computed over ("no silent caps").
    """
    bench = benchmark()
    out = {"benchmark": len(bench), "eng_shards": len(engine_lines())}
    for band in ROLLOUT_BANDS:
        try:
            out[band] = len(rollouts(band))
        except FileNotFoundError:
            out[band] = 0
    out["labeled_maia"] = len(labeled_plans())
    out["labeled_lift"] = len(labeled_plans("lift_shards", "shard_*.jsonl"))
    return out


if __name__ == "__main__":
    for name, n in coverage().items():
        print(f"{name:16s} {n:6d}")
