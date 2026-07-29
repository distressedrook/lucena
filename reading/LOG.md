# reading — run log

Append-only. One entry per experiment or probe: what was asked, what was
measured, over what coverage, and the verdict. Coverage is always stated —
a number without its coverage reads as completeness it doesn't have.

---

## 2026-07-30 · P0 · bank coverage

**Asked:** are the banked artifacts complete enough to run the eval offline?

**Measured** (`bank.py`):

| artifact | rows |
|---|---|
| `benchmark_v1.jsonl` | 4000 |
| `eng_shards` | 4000 |
| `maia_shards_2400v1300` | 4000 |
| `maia_shards_2400v1800` | 4000 |
| `maia_shards` (labeled) | 4000 |
| `lift_shards` (labeled) | 94289 |

**Verdict:** complete. Arms A–D and the lift metric can run with no engine,
no GPU and no gRPC server. `lift_shards` at 94,289 is the older
pre-benchmark corpus scan (finding 12's anchor count), not a benchmark
artifact — don't join it to the 4,000 by id.

---

## 2026-07-30 · P1 · every benchmark position is White to move

**Asked:** incidental check while probing the rollout banks.

**Measured:** side-to-move across all 4,000 rows — `{'w': 4000}`. Anchors are
at even plies (20/30/40/50), so the anchor scheme guarantees it.

**Verdict — two consequences, both real:**

1. **Hypothesis 1 (side order) is NOT testable on `benchmark_v1`.**
   `position_read.render` iterates `("white", "black")`, and the concern was
   that a student playing Black reads the opponent's block first. On this
   benchmark the reader is always White, so the read already leads with the
   reader's side. The hypothesis is still live *for the product* — it just
   needs Black-to-move positions to measure. Mirroring the FENs does not
   work: the banked engine lines and Maia rollouts belong to the original
   positions, and Maia policy is not colour-symmetric in practice. So this
   is a `benchmark_v2` item (odd-ply anchors), not a cheap one.

2. Any per-colour comparison over this benchmark is confounded with
   ply parity. See P2.

---

## 2026-07-30 · P2 · which colour carries the weak policy (RETRACTED, then resolved)

**Asked:** in `maia_shards_2400v1300`, whose moves are the 1300 ones? Getting
this backwards would invert the foil arm without failing any test.

**First attempt — RETRACTED.** `probe_foil_side.py` tallied engine-agreement
by colour, scoring ply 0 directly against the eval-equal set and ply 1 by a
conditional proxy. It reported White 0.680 / Black 0.521, gap 0.159, "strong
side = white". **That result is invalid.** Because every position is White to
move (P1), White was *always* measured at ply 0 and Black *always* at ply 1 —
the gap compares two measurement methods, not two colours. Two tells were
visible in the output and should have been caught before reading the verdict:
`white n = 9600 = 600 × 16` exactly (every rollout scored, i.e. one ply only),
and `black n == white hits` exactly (the ply-1 proxy is conditioned on ply 0
being a hit).

**Second attempt — inconclusive.** Cross-band identity of the ply-0 move
multiset: 605/800 (0.756) identical for White, 508/800 (0.635) for Black.
Not decisive — 0.756 is most plausibly the fraction of positions where
White's choice is uncontested (the 40–60 gating makes obvious moves
deterministic and branches only at real decision points), so the divergence
is RNG, not policy.

**Third attempt — method-consistent.** White ply-0 engine agreement, same
direct measurement, both bands, 800 positions each:

| band | White ply-0 agreement |
|---|---|
| `2400v1300` | 0.6812 (8719/12800) |
| `2400v1800` | 0.6962 (8911/12800) |

1.5pp apart — far too small for a ~500-Elo policy difference, consistent with
RNG divergence at contested nodes. Points to White being the fixed 2400 side.

**Resolved by reading the generator**, which is what should have happened
first: `research/gpu_benchmark/plan_frequency_by_strength.py` documents these
as "compared across **opponent** strength bands (2400v2400 baseline vs
2400v1300 / 2400v1800)". So the 2400 is the side to move (White) and the
named band is the **opponent** (Black). `maia_shards` is the 2400v2400
baseline.

---

## 2026-07-30 · P3 · the foil arm needs new compute after all (CORRECTION)

**Prior claim (mine, stated twice):** the rating-conditioned banks give a
predicted student foil for free, so the foil arm costs zero engine/GPU time.

**Corrected:** wrong. Those banks vary the *opponent's* strength while the
side to move stays 2400. What the foil arm needs is the opposite — weak
policy on the **side to move** — and no bank holds it. Since every benchmark
position is White to move, the reader whose comprehension we measure is the
strong side, and "the move a 1300 would play here" does not exist on disk.

**What is still free** (unchanged, and it is most of the eval):

- Arms A (raw MultiPV from `eng_shards`), B (`position_read.render` over
  `post_verify_json`), C (`lexicalize.py`, verifier-gated), D (`actual_ucis`).
- The baseline-and-lift metric, the `random_ucis` floor, structure
  stratification, the leakage stripper, bits-per-lift.

**What a `1300v2400` roll would buy** (weak policy on the side to move):
a contrastive foil for quiet positions — the thing the tactical layer gets
free from a puzzle and the positional layer has never had (tactics
KNOWN_ISSUES #6 retired *attributed* intent as unverifiable; a *predicted*
foil is falsifiable). `gpu_bench.py` is resume-safe; ~1.6M Maia calls,
1–2h on a GPU. **Not started — needs a ruling on whether it is worth the
GPU time before the eval has shown anything.**

**Recommendation:** build and validate arms A–D first. They answer "does the
shipped read beat a raw PV dump, and by how much, for whom." If the answer is
yes-but-small, the foil roll is the obvious next lever and the eval will say
so with a number. Ordering it the other way spends GPU hours on a hypothesis
the harness can't yet score.

---

## 2026-07-30 · P4 · the baseline raw rollouts were there all along

**Asked:** arm B calls `fact_sheet.post_verify_json(fen, pvs, rolls)`, which
needs *raw* rolls. P0 recorded `maia_shards` as labeled-only, which would have
left the only raw banks as weak-opponent conditions.

**Measured:** `maia_shards/` holds four filename patterns, not one —
`argmax_*.jsonl` (40, labeled), **`bench_*.jsonl` (80, raw rollouts)**,
`ksample_*.jsonl` (12) and `ksample_ext_*.jsonl` (12). The `bench_*` rows have
the same `{id, k:16, samples}` shape as the other bands and cover all 4,000
positions.

So the 2400v2400 **baseline raw rollouts exist**, and they are the correct
rolls leg for arm B: `HUMAN_TAG` means "strong humans play this from here", so
feeding a weak-opponent bank would have biased the human tier in a way no test
would have caught. `bank.ROLLOUT_BANDS` now carries all three, baseline first.

**Verdict:** P0's characterisation of `maia_shards` was wrong (it read only
`argmax_*`). Arm B needs no new compute. `probe_bands.py` now covers three
bands:

| band | White ply-0 engine agreement |
|---|---|
| `2400v1300` | 0.6812 (8719/12800) |
| `2400v2400` | 0.6930 (8870/12800) |
| `2400v1800` | 0.6962 (8911/12800) |

Spread 0.0150 over 800 positions each — White's strength is band-independent,
as it must be if only the opponent varies. Note the baseline sits *between*
the two weak-opponent conditions rather than above both, which is another
reason not to read a strength ordering out of this number: at 1.5pp it is
measuring RNG divergence at contested nodes, not policy.
