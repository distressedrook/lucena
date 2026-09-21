"""probe_bands — assert the documented semantics of the rollout banks.

`research/gpu_benchmark/plan_frequency_by_strength.py` documents the three
Maia banks as varying the **opponent's** strength while the side to move stays
2400: `maia_shards` = 2400v2400 baseline, `maia_shards_2400v1800` and
`maia_shards_2400v1300` the weaker-opponent conditions. Every position in
`benchmark_v1` is White to move, so the 2400 side is always White and the
named band is always Black.

This probe is the regression that keeps that assumption honest. It measures
White's ply-0 engine agreement — the same direct measurement in every band —
and asserts the rates stay close. If they ever separate materially, either the
banks were regenerated with different semantics or something upstream changed,
and anything built on "White is the strong side" needs re-checking.

Why ply 0 only: rollout ply 0 is the side to move, scored against that
position's own eval-equal engine lines. Deeper plies land in positions the
bank has no lines for, so agreement there is unmeasurable rather than low.

NOT a discovery tool. The earlier version of this file tried to infer the weak
colour by comparing per-colour agreement, which is confounded on this
benchmark: with every position White to move, White is always scored at ply 0
and Black always at ply 1, so a per-colour gap measures the two methods, not
the two colours. See LOG.md P2 for the retracted result.
"""
from __future__ import annotations

import argparse

import bank

# White's ply-0 agreement should be band-independent, since White is 2400
# everywhere. Some drift is expected: the rollout samples at contested nodes,
# and the RNG stream differs once the opponent's policy does.
MAX_EXPECTED_SPREAD = 0.05


def white_ply0_agreement(band: str, limit: int | None,
                         margin_cp: int) -> tuple[float, int, int, int]:
    """(rate, hits, total_rollouts, positions) for the side to move."""
    bench = bank.benchmark()
    eng = bank.engine_lines()
    rolls = bank.rollouts(band)
    ids = sorted(set(bench) & set(eng) & set(rolls))
    if limit:
        ids = ids[:limit]

    hits = total = 0
    for pid in ids:
        fen = bench[pid]["fen"]
        equal = bank.eval_equal_first_moves(eng[pid], fen, margin_cp)
        if not equal:
            continue        # no banked lines to score against
        played = [s for s in rolls[pid] if s]
        hits += sum(1 for s in played if s[0] in equal)
        total += len(played)
    return (hits / total if total else 0.0), hits, total, len(ids)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=800,
                    help="positions per band (default 800; 0 = all 4000)")
    ap.add_argument("--margin-cp", type=int, default=30)
    args = ap.parse_args()

    rates = {}
    for band in sorted(bank.ROLLOUT_BANDS):
        rate, hits, total, n = white_ply0_agreement(
            band, args.limit or None, args.margin_cp)
        rates[band] = rate
        print(f"{band:12s} White ply-0 agreement {rate:.4f} "
              f"({hits}/{total} rollouts over {n} positions)")

    spread = max(rates.values()) - min(rates.values())
    print(f"\nspread {spread:.4f} (expected < {MAX_EXPECTED_SPREAD})")
    if spread >= MAX_EXPECTED_SPREAD:
        raise SystemExit(
            "FAIL — White's strength is not band-independent. The banks may no "
            "longer be opponent-strength studies; re-read the generator before "
            "trusting anything keyed to 'White is the 2400 side'.")
    print("OK — consistent with White = 2400 in every band (opponent varies).")


if __name__ == "__main__":
    main()
